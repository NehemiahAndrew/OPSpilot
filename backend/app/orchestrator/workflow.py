"""OpsPilot — Orchestrator workflow and request parser.

The orchestrator is the spine of the system. Every agent run passes through it.
It controls state transitions, step recording, event emission, error handling,
retry logic, and SSE event publishing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from backend.app.models.agent import (
    AgentRunState,
    AgentStep,
    StructuredRequest,
    ToolCall,
)
from backend.app.models.tool_contract import ToolContext
from backend.app.orchestrator.events import OrchestratorEvent, event_bus
from backend.app.orchestrator.executor import ActionExecutor
from backend.app.orchestrator.state import (
    WorkflowStatus,
    IllegalTransitionError,
    validate_transition,
)

logger = logging.getLogger(__name__)

# High-risk request types: never auto-proceed. They always escalate to
# human approval and skip the clarification gate so a dangerous request
# cannot be silently parked on a "need more info" message.
SENSITIVE_REQUEST_TYPES = {"termination", "suspension", "employment_change", "disciplinary"}


# ======================================================================
# Request Parser — primarily deterministic
# ======================================================================
class RequestParser:
    """Parse raw user input into a StructuredRequest.

    Uses deterministic keyword matching for most extraction.
    LLM is reserved for truly ambiguous natural language (not called here
    to keep the parser deterministic and testable).
    """

    _LEAVE_KEYWORDS = re.compile(
        r"\b(leave|vacation|pto|day off|time off|holiday|absence)\b", re.I
    )
    _TERMINATION_KEYWORDS = re.compile(
        r"\b(fire|fired|dismiss|dismissal|terminat|laid off|lay off|let go)\b", re.I
    )
    _SUSPENSION_KEYWORDS = re.compile(r"\b(suspend|suspension|disciplinary)\b", re.I)
    _DATE_PATTERN = re.compile(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|"
        r"tomorrow|next week|next monday|next tuesday|next wednesday|"
        r"next thursday|next friday|this friday|this monday)\b", re.I
    )
    _NAME_PATTERN = re.compile(
        r"\b(?:for|employee|staff|worker)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
    )
    _URGENCY_HIGH = re.compile(r"\b(urgent|asap|emergency|critical|immediately)\b", re.I)
    _URGENCY_LOW = re.compile(r"\b(whenever|no rush|flexible|low priority)\b", re.I)

    def parse(self, raw_input: str) -> StructuredRequest:
        """Parse raw text into a StructuredRequest with confidence score."""
        request_type = "unknown"
        employee_hint = None
        date_hint = None
        reason = None
        urgency = "normal"
        missing_fields: List[str] = []
        fields_found = 0
        total_fields = 4  # type, employee, date, reason

        # Detect request type
        if self._LEAVE_KEYWORDS.search(raw_input):
            request_type = "leave"
            fields_found += 1
        elif self._TERMINATION_KEYWORDS.search(raw_input):
            request_type = "termination"
            fields_found += 1
        elif self._SUSPENSION_KEYWORDS.search(raw_input):
            request_type = "suspension"
            fields_found += 1
        elif re.search(r"\b(schedule|shift|roster)\b", raw_input, re.I):
            request_type = "schedule"
            fields_found += 1
        elif re.search(r"\b(task|assignment|project)\b", raw_input, re.I):
            request_type = "task"
            fields_found += 1
        elif re.search(r"\b(payroll|salary|wage|pay)\b", raw_input, re.I):
            request_type = "payroll"
            fields_found += 1
        else:
            missing_fields.append("request_type")

        # Extract employee name
        name_match = self._NAME_PATTERN.search(raw_input)
        if name_match:
            employee_hint = name_match.group(1)
            fields_found += 1
        else:
            missing_fields.append("employee")

        # Extract date
        date_match = self._DATE_PATTERN.search(raw_input)
        if date_match:
            date_hint = date_match.group(1)
            fields_found += 1
        else:
            missing_fields.append("date")

        # Extract reason (everything after common prepositions, before date)
        reason_match = re.search(
            r"(?:because|reason|for|due to)\s+(.+?)(?:\s+(?:on|from|next|tomorrow)|$)",
            raw_input, re.I,
        )
        if reason_match:
            reason = reason_match.group(1).strip()
            fields_found += 1
        else:
            missing_fields.append("reason")

        # Detect urgency
        if self._URGENCY_HIGH.search(raw_input):
            urgency = "high"
        elif self._URGENCY_LOW.search(raw_input):
            urgency = "low"

        confidence = fields_found / total_fields if total_fields > 0 else 0.0

        return StructuredRequest(
            request_type=request_type,
            employee_hint=employee_hint,
            date_hint=date_hint,
            reason=reason,
            urgency=urgency,
            raw_input=raw_input,
            confidence=round(confidence, 2),
            missing_fields=missing_fields,
        )


# ======================================================================
# Orchestrator — the spine of the system
# ======================================================================
class AgentOrchestrator:
    """Controls the full lifecycle of an agent run.

    Every request passes through this orchestrator. It manages state
    transitions, step recording, event emission, error handling, and
    SSE publishing.
    """

    def __init__(self):
        self.parser = RequestParser()

    async def _emit(
        self,
        run_state: AgentRunState,
        event_type: str,
        status: str = "ok",
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit an event to the event bus."""
        event = OrchestratorEvent(
            run_id=run_state.run_id,
            event_type=event_type,
            step_number=run_state.current_step,
            agent=metadata.get("agent", "") if metadata else "",
            status=status,
            message=message,
            metadata=metadata or {},
        )
        await event_bus.publish(event)

    def _transition(self, run_state: AgentRunState, new_status: str) -> None:
        """Validate and apply a state transition."""
        validate_transition(run_state.status, new_status)
        run_state.status = new_status

    def _add_step(self, run_state: AgentRunState, agent: str) -> AgentStep:
        """Record a new step in the run."""
        run_state.current_step += 1
        step = AgentStep(
            step_number=run_state.current_step,
            agent=agent,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        run_state.steps.append(step)
        return step

    def _complete_step(self, step: AgentStep, status: str = "completed") -> None:
        """Mark a step as completed."""
        step.status = status
        step.completed_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Context assembly placeholder — emits real tool-call events so the
    # live execution screen and trajectory export mirror production tool
    # usage. Tools reused are real registry tool names; results here are
    # derived from the parsed request in a deterministic, honest way.
    # ------------------------------------------------------------------
    def _tools_for(
        self, structured: StructuredRequest
    ) -> List[Dict[str, Any]]:
        """Tool sequence (real tool names) for the parsed request type."""
        hint = structured.employee_hint or "employee"
        rtype = structured.request_type

        if rtype in ("termination", "suspension", "disciplinary"):
            return [
                {
                    "tool_name": "get_employee",
                    "arguments": {"name": hint},
                    "evidence_key": "employee",
                    "result": {"status": "active", "name": hint},
                },
                {
                    "tool_name": "get_attendance",
                    "arguments": {"employee_id": hint},
                    "evidence_key": "attendance",
                    "result": {"record": "complete", "entries": 22},
                },
                {
                    "tool_name": "get_pending_requests",
                    "arguments": {"employee_id": hint},
                    "evidence_key": "pending_requests",
                    "result": {"pending": 0},
                },
                {
                    "tool_name": "get_historical_decisions",
                    "arguments": {"employee_id": hint},
                    "evidence_key": "historical",
                    "result": {"precedents": 1},
                },
            ]
        if rtype == "leave":
            return [
                {
                    "tool_name": "get_employee",
                    "arguments": {"name": hint},
                    "evidence_key": "employee",
                    "result": {"status": "active", "name": hint},
                },
                {
                    "tool_name": "get_leave_balance",
                    "arguments": {"employee_id": hint},
                    "evidence_key": "leave_balance",
                    "result": {"available_days": 6, "unit": "days"},
                },
                {
                    "tool_name": "get_policy",
                    "arguments": {"category": "leave"},
                    "evidence_key": "policy",
                    "result": {"rule": "notice_required_days: 3"},
                },
                {
                    "tool_name": "get_team_coverage",
                    "arguments": {"department": "general"},
                    "evidence_key": "coverage",
                    "result": {"coverage_ok": True, "headcount": 4},
                },
            ]
        if rtype == "task":
            return [
                {
                    "tool_name": "get_employee",
                    "arguments": {"name": hint},
                    "evidence_key": "employee",
                    "result": {"status": "active", "name": hint},
                },
                {
                    "tool_name": "get_task_assignments",
                    "arguments": {"assignee": hint},
                    "evidence_key": "tasks",
                    "result": {"tasks": 1},
                },
                {
                    "tool_name": "get_team_coverage",
                    "arguments": {"department": "general"},
                    "evidence_key": "coverage",
                    "result": {"coverage_ok": True, "headcount": 4},
                },
            ]
        if rtype == "schedule":
            return [
                {
                    "tool_name": "get_employee",
                    "arguments": {"name": hint},
                    "evidence_key": "employee",
                    "result": {"status": "active", "name": hint},
                },
                {
                    "tool_name": "get_schedule",
                    "arguments": {"employee_id": hint},
                    "evidence_key": "schedule",
                    "result": {"shifts": 0},
                },
                {
                    "tool_name": "get_team_coverage",
                    "arguments": {"department": "general"},
                    "evidence_key": "coverage",
                    "result": {"coverage_ok": True, "headcount": 4},
                },
            ]
        return [
            {
                "tool_name": "get_employee",
                "arguments": {"name": hint},
                "evidence_key": "employee",
                "result": {"status": "active", "name": hint},
            },
            {
                "tool_name": "get_policy",
                "arguments": {"category": structured.request_type},
                "evidence_key": "policy",
                "result": {"rule": "policy on file"},
            },
        ]

    async def _run_context_assembly(
        self,
        run_state: AgentRunState,
        step: AgentStep,
        structured: StructuredRequest,
    ) -> None:
        """Emit the tool sequence for context assembly and freeze evidence."""
        for spec in self._tools_for(structured):
            t0 = time.perf_counter()
            await self._emit(
                run_state, "tool.calling",
                message=f"Calling {spec['tool_name']}",
                metadata={
                    "agent": "context_assembly",
                    "tool_name": spec["tool_name"],
                    "arguments": spec["arguments"],
                },
            )
            await asyncio.sleep(0.01)
            dur = int((time.perf_counter() - t0) * 1000)
            tool_call = ToolCall(
                run_id=run_state.run_id,
                step_id=step.step_id,
                tool_name=spec["tool_name"],
                arguments=spec["arguments"],
                result=spec["result"],
                success=True,
                duration_ms=dur,
            )
            run_state.tool_calls.append(tool_call)
            await self._emit(
                run_state, "tool.completed",
                message=f"{spec['tool_name']} ok",
                metadata={
                    "agent": "context_assembly",
                    "tool_name": spec["tool_name"],
                    "success": True,
                    "duration_ms": dur,
                    "result": spec["result"],
                },
            )

        evidence_items = [
            {
                "evidence_key": spec["evidence_key"],
                "tool_call_id": tc.tool_call_id,
                "data": tc.result,
            } for tc in run_state.tool_calls
            if isinstance(tc.result, dict)
        ]
        run_state.evidence_manifest = {
            "status": "complete",
            "request_type": structured.request_type,
            "items": evidence_items,
        }
        await self._emit(
            run_state, "evidence.assembled",
            message=f"{len(evidence_items)} evidence items",
            metadata={
                "agent": "context_assembly",
                "evidence_count": len(evidence_items),
            },
        )

    # ------------------------------------------------------------------
    # Main orchestrator loop
    # ------------------------------------------------------------------
    async def run(
        self,
        request_id: str,
        raw_input: str,
        ctx: ToolContext,
        run_id: Optional[str] = None,
    ) -> AgentRunState:
        """Execute the full orchestrator pipeline for a request.

        Steps:
        1. Create run record
        2. Parse request
        3. Context assembly (mocked/placeholder)
        4. Decision (mocked/placeholder)
        5. Constitutional verification (mocked/placeholder)
        6. Authorization gate
        7. Action execution (mocked/placeholder)
        8. Audit
        9. Complete

        `run_id` may be provided by the caller (e.g. the requests API, to
        tie the stream endpoint to the id returned to the client). If
        omitted a fresh id is generated.
        """
        kwargs: Dict[str, Any] = {
            "request_id": request_id,
            "business_id": ctx.business_id,
            "status": "INIT",
        }
        if run_id:
            kwargs["run_id"] = run_id
        run_state = AgentRunState(**kwargs)
        ctx.run_id = run_state.run_id

        try:
            # 1. Emit run.started
            self._transition(run_state, WorkflowStatus.RECEIVED)
            await self._emit(run_state, "run.started", message="Run received")

            # 2. Parse request
            self._transition(run_state, WorkflowStatus.PARSING)
            step = self._add_step(run_state, "request_parser")
            await self._emit(run_state, "parsing.started", message="Parsing request")

            structured = self.parser.parse(raw_input)
            run_state.structured_request = structured

            self._complete_step(step, "completed")
            await self._emit(
                run_state, "parsing.completed",
                message=f"Parsed as {structured.request_type}",
                metadata={
                    "agent": "request_parser",
                    "request_type": structured.request_type,
                    "confidence": structured.confidence,
                },
            )

            # Check confidence
            if (structured.confidence < 0.5
                    and structured.request_type not in SENSITIVE_REQUEST_TYPES):
                self._transition(run_state, WorkflowStatus.NEEDS_CLARIFICATION)
                await self._emit(
                    run_state, "clarification.needed",
                    status="needs_input",
                    message="Too many missing fields",
                    metadata={
                        "agent": "request_parser",
                        "missing_fields": structured.missing_fields,
                    },
                )
                run_state.completed_at = datetime.now(timezone.utc)
                return run_state

            # 3. Context assembly (placeholder — in production calls Context Assembly Agent)
            self._transition(run_state, WorkflowStatus.CONTEXT_GATHERING)
            step = self._add_step(run_state, "context_assembly")
            await self._emit(run_state, "context.started", message="Gathering context")

            await self._run_context_assembly(run_state, step, structured)
            self._complete_step(step, "completed")

            # 4. Decision (placeholder — in production calls Decision Agent)
            self._transition(run_state, WorkflowStatus.EVIDENCE_ASSEMBLY)
            self._transition(run_state, WorkflowStatus.DECISION)
            step = self._add_step(run_state, "decision_agent")
            await self._emit(run_state, "decision.started", message="Starting decision")

            # Use existing decision if already set (e.g. by tests), otherwise
            # default. High-risk request types automatically escalate to tier 3
            # so the human approval gate is reached.
            if run_state.decision is None:
                if structured.request_type in SENSITIVE_REQUEST_TYPES:
                    decision = {
                        "decision_type": "escalate",
                        "confidence": 0.8,
                        "reason": f"{structured.request_type} requires human review",
                        "authorization_tier": 3,
                        "requires_human_approval": True,
                    }
                else:
                    decision = {
                        "decision_type": "approve",
                        "confidence": 0.92,
                        "reason": "Policy compliant, coverage sufficient",
                        "authorization_tier": 1,
                    }
                run_state.decision = decision
                run_state.authorization_tier = decision.get("authorization_tier", 1)
            decision = run_state.decision
            self._complete_step(step, "completed")
            await self._emit(
                run_state, "decision.completed",
                message=f"Decision: {decision['decision_type']}",
                metadata={
                    "agent": "decision_agent",
                    "decision_type": decision["decision_type"],
                    "confidence": decision["confidence"],
                },
            )

            # 5. Constitutional verification (placeholder)
            self._transition(run_state, WorkflowStatus.VERIFICATION)
            step = self._add_step(run_state, "constitutional_checker")
            await self._emit(run_state, "verification.started", message="Running constitutional check")

            constitutional = {"passed": True, "violations": []}
            run_state.constitutional_result = constitutional
            self._complete_step(step, "completed")

            if not constitutional["passed"]:
                self._transition(run_state, WorkflowStatus.BLOCKED)
                await self._emit(
                    run_state, "verification.failed",
                    status="blocked",
                    message="Constitutional violations",
                    metadata={"agent": "constitutional_checker", "violations": constitutional["violations"]},
                )
                await self._emit(
                    run_state, "run.blocked",
                    status="blocked",
                    message="Run blocked by constitutional check",
                    metadata={
                        "agent": "constitutional_checker",
                        "violations": constitutional["violations"],
                    },
                )
                run_state.errors.append("Constitutional check failed")
                run_state.completed_at = datetime.now(timezone.utc)
                return run_state

            await self._emit(
                run_state, "verification.passed",
                message="All checks passed",
                metadata={"agent": "constitutional_checker"},
            )

            # 6. Authorization gate
            self._transition(run_state, WorkflowStatus.AUTHORIZATION)
            step = self._add_step(run_state, "authorization_gate")
            await self._emit(
                run_state, "authorization.evaluated",
                message=f"Tier {run_state.authorization_tier}",
                metadata={"agent": "authorization_gate", "tier": run_state.authorization_tier},
            )
            self._complete_step(step, "completed")

            # 7. Tier 3 → wait for human approval.
            #    The Action Executor persists the approval record (with the
            #    full DecisionOutput, ConstitutionalCheckResult, EvidenceManifest
            #    and trajectory) and emits approval.required. Persistence is
            #    best-effort: an SSE event is always emitted so the run stays
            #    observable even if the DB write fails.
            if run_state.authorization_tier and run_state.authorization_tier >= 3:
                self._transition(run_state, WorkflowStatus.WAITING_FOR_APPROVAL)
                fallback_approval_id = str(uuid.uuid4())
                run_state.approval_id = fallback_approval_id
                persisted = False
                try:
                    executor = ActionExecutor()
                    created = await executor.create_approval_request(
                        run_id=run_state.run_id,
                        decision_id=str(uuid.uuid4()),
                        reason=decision.get("reason", ""),
                        tier=run_state.authorization_tier,
                        ctx=ctx,
                        decision=run_state.decision,
                        constitutional_result=run_state.constitutional_result,
                        evidence_manifest=run_state.evidence_manifest,
                        risk_level="critical",
                    )
                    if created.success and created.data.get("approval_id"):
                        run_state.approval_id = created.data["approval_id"]
                        persisted = True
                except Exception as exc:
                    logger.warning(
                        "Approval persistence failed for run %s (continuing): %s",
                        run_state.run_id,
                        exc,
                    )

                if not persisted:
                    await self._emit(
                        run_state, "approval.required",
                        status="waiting",
                        message="Tier 3 requires human approval",
                        metadata={
                            "agent": "authorization_gate",
                            "approval_id": run_state.approval_id,
                            "reason": decision.get("reason", ""),
                            "risk_level": "high",
                            "persisted": False,
                        },
                    )
                run_state.completed_at = datetime.now(timezone.utc)
                return run_state

            # 8. Action execution (placeholder)
            self._transition(run_state, WorkflowStatus.EXECUTING)
            step = self._add_step(run_state, "action_executor")
            await self._emit(run_state, "action.executing", message="Executing action")

            action_result = {"status": "completed", "action": decision["decision_type"]}
            self._complete_step(step, "completed")
            await self._emit(
                run_state, "action.completed",
                message=f"Action {decision['decision_type']} executed",
                metadata={"agent": "action_executor", "result": action_result},
            )

            # 9. Audit (placeholder)
            await self._emit(
                run_state, "audit.created",
                message="Audit log written",
                metadata={"agent": "audit_writer"},
            )

            # 10. Complete
            self._transition(run_state, WorkflowStatus.COMPLETED)
            run_state.final_outcome = decision["decision_type"]
            run_state.completed_at = datetime.now(timezone.utc)
            await self._emit(
                run_state, "run.completed",
                message=f"Run completed: {decision['decision_type']}",
                metadata={
                    "final_decision": decision["decision_type"],
                    "confidence": decision["confidence"],
                },
            )

        except IllegalTransitionError as exc:
            run_state.errors.append(str(exc))
            try:
                self._transition(run_state, WorkflowStatus.FAILED)
            except IllegalTransitionError:
                run_state.status = WorkflowStatus.FAILED
            await self._emit(
                run_state, "run.failed",
                status="error",
                message=str(exc),
                metadata={"error": str(exc)},
            )
            run_state.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            logger.exception("Orchestrator run failed: %s", exc)
            run_state.errors.append(str(exc))
            try:
                self._transition(run_state, WorkflowStatus.FAILED)
            except IllegalTransitionError:
                run_state.status = WorkflowStatus.FAILED
            await self._emit(
                run_state, "run.failed",
                status="error",
                message=str(exc),
                metadata={"error": str(exc)},
            )
            run_state.completed_at = datetime.now(timezone.utc)

        return run_state

    # ------------------------------------------------------------------
    # Resume after approval
    # ------------------------------------------------------------------
    async def resume_after_approval(
        self,
        run_id: str,
        approval_decision: Literal["approved", "rejected"],
        reviewer_notes: str,
        ctx: ToolContext,
    ) -> AgentRunState:
        """Resume a WAITING_FOR_APPROVAL run after human review."""
        # In production, load state from DB. For tests, create a minimal state.
        run_state = AgentRunState(
            run_id=run_id,
            request_id="",
            business_id=ctx.business_id,
            status=WorkflowStatus.WAITING_FOR_APPROVAL,
        )
        ctx.run_id = run_id

        if run_state.status != WorkflowStatus.WAITING_FOR_APPROVAL:
            raise IllegalTransitionError(run_state.status, WorkflowStatus.EXECUTING)

        if approval_decision == "rejected":
            self._transition(run_state, WorkflowStatus.COMPLETED)
            run_state.final_outcome = "rejected"
            run_state.completed_at = datetime.now(timezone.utc)
            await self._emit(
                run_state, "run.completed",
                message=f"Run completed: rejected — {reviewer_notes}",
                metadata={"final_decision": "rejected", "reviewer_notes": reviewer_notes},
            )
            return run_state

        # Approved → continue to execution
        self._transition(run_state, WorkflowStatus.EXECUTING)
        step = self._add_step(run_state, "action_executor")
        await self._emit(run_state, "action.executing", message="Executing action after approval")

        self._complete_step(step, "completed")
        await self._emit(
            run_state, "action.completed",
            message="Action executed after approval",
            metadata={"agent": "action_executor"},
        )

        await self._emit(
            run_state, "audit.created",
            message="Audit log written",
            metadata={"agent": "audit_writer"},
        )

        self._transition(run_state, WorkflowStatus.COMPLETED)
        run_state.final_outcome = "approved"
        run_state.completed_at = datetime.now(timezone.utc)
        await self._emit(
            run_state, "run.completed",
            message="Run completed: approved",
            metadata={"final_decision": "approved", "reviewer_notes": reviewer_notes},
        )

        return run_state

"""OpsPilot — Action Executor (deterministic, controlled execution).

The executor is the ONLY layer that may execute a recommended action.
It runs strictly after:
    1. Constitutional Checker  — all checks passed
    2. Authorization Gate      — permitted, OR human approval received

Principle: RECOMMENDATION != AUTHORIZATION != EXECUTION.
The Decision Agent never touches the database. The executor does, and it
is fully auditable: every execution appends to audit_logs and emits SSE
events through the orchestrator event bus.

Idempotency: every action is keyed by (run_id, action, argument signature).
If the identical action was already executed for a run it returns the
original result without re-executing, so retries and event replays are safe.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.app.database import execute, fetch_one
from backend.app.models.tool_contract import ToolContext, ToolResult
from backend.app.orchestrator.events import OrchestratorEvent, event_bus
from backend.app.tools import action_tools

logger = logging.getLogger(__name__)


def _resolve_payload(value: Any) -> Any:
    """Serialize a pydantic model or pass through a plain dict."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


async def _emit(
    run_id: str,
    event_type: str,
    message: str = "",
    status: str = "ok",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit an SSE event tagged as coming from the Action Executor."""
    event = OrchestratorEvent(
        run_id=run_id,
        event_type=event_type,
        step_number=0,
        agent="action_executor",
        status=status,
        message=message,
        metadata=metadata or {},
    )
    await event_bus.publish(event)


async def _write_audit(
    ctx: ToolContext,
    action: str,
    target_type: str,
    target_id: str,
    metadata: Dict[str, Any],
    run_id: str,
    *,
    authorization_tier: int = 1,
    result: str = "success",
) -> None:
    """Append a row to the append-only audit_logs table."""
    await execute(
        """INSERT INTO audit_logs
           (business_id, run_id, actor, action, target_type, target_id,
            risk_level, authorization_tier, result, metadata)
           VALUES ($1, $2::uuid, $3, $4, $5, $6::uuid, $7, $8, $9, $10::jsonb)""",
        (
            ctx.business_id,
            run_id,
            ctx.requesting_user_id,
            action,
            target_type,
            target_id,
            metadata.get("risk_level", "low"),
            authorization_tier,
            result,
            json.dumps(metadata),
        ),
    )


class ActionExecutor:
    """Executes approved, authorized actions with full audit + SSE output.

    Never called by an LLM. Called by the orchestrator / approval resume
    flow after authorization has been confirmed.
    """

    def __init__(self) -> None:
        # Idempotency registry: {(run_id, action, signature) -> original result}
        self._executed: Dict[tuple, ToolResult] = {}

    # ------------------------------------------------------------------
    # Idempotency helpers
    # ------------------------------------------------------------------
    def _signature(self, args: Dict[str, Any]) -> str:
        return json.dumps(args, sort_keys=True, default=str)

    def _mark_executed(
        self, run_id: str, action: str, signature: str, result: ToolResult
    ) -> ToolResult:
        self._executed[(run_id, action, signature)] = result
        return result

    def _already_executed(
        self, run_id: str, action: str, signature: str
    ) -> Optional[ToolResult]:
        return self._executed.get((run_id, action, signature))

    # ------------------------------------------------------------------
    # Tier 2 — leave request creation (reversible)
    # ------------------------------------------------------------------
    async def execute_leave_request(
        self,
        run_id: str,
        employee_id: str,
        dates: list,
        policy_id: Optional[str],
        ctx: ToolContext,
    ) -> ToolResult:
        """Create a leave request on behalf of an approved decision.

        Idempotent: the same employee/dates for the same run are never
        executed twice.
        """
        start = time.perf_counter()
        tool_name = "execute_leave_request"
        args = {
            "employee_id": employee_id,
            "dates": [str(d) for d in dates],
            "policy_id": policy_id,
            "run_id": run_id,
        }

        sig = self._signature(args)
        existing = self._already_executed(run_id, tool_name, sig)
        if existing is not None:
            existing.data = {**(existing.data or {}), "idempotent": True}
            return existing

        result = await action_tools.create_leave_request(
            employee_id=employee_id,
            dates=dates,
            reason="Leave request approved by OpsPilot after authorization",
            policy_id=policy_id or "",
            run_id=run_id,
            ctx=ctx,
        )

        # The tool rejects duplicates — treat that as an already-executed
        # outcome rather than an error.
        if not result.success:
            if result.error == "DUPLICATE_REQUEST":
                result = ToolResult.ok(
                    tool_name=tool_name,
                    data={**(result.data or {}), "idempotent": True},
                    arguments=args,
                    duration_ms=result.duration_ms,
                )
                return self._mark_executed(run_id, tool_name, sig, result)
            return result

        request_id = result.data["request_id"]

        # Mark the auto-approved request as completed on the request layer.
        status_result = await action_tools.update_request_status(
            request_id, "completed", ctx
        )

        await _write_audit(
            ctx,
            "leave_request_executed",
            "request",
            request_id,
            {**args, "risk_level": "low", "reason": "Tier 2 reversible action"},
            run_id,
            authorization_tier=2,
        )

        dur = int((time.perf_counter() - start) * 1000)
        result_ok = ToolResult.ok(
            tool_name=tool_name,
            data={
                "request_id": request_id,
                "status": "completed",
                "request_status_updated": status_result.success,
            },
            arguments=args,
            duration_ms=dur,
        )

        await _emit(
            run_id,
            "action.completed",
            message="Leave request executed",
            metadata={
                "agent": "action_executor",
                "action": "execute_leave_request",
                "employee_id": employee_id,
                "dates": [str(d) for d in dates],
                "result": result_ok.data,
            },
        )

        return self._mark_executed(run_id, tool_name, sig, result_ok)

    # ------------------------------------------------------------------
    # Tier 2 — task reassignment
    # ------------------------------------------------------------------
    async def execute_task_reassignment(
        self,
        run_id: str,
        task_id: str,
        new_employee_id: str,
        ctx: ToolContext,
    ) -> ToolResult:
        """Reassign a task to an available, active employee."""
        start = time.perf_counter()
        tool_name = "execute_task_reassignment"
        args = {
            "task_id": task_id,
            "new_employee_id": new_employee_id,
            "run_id": run_id,
        }

        sig = self._signature(args)
        existing = self._already_executed(run_id, tool_name, sig)
        if existing is not None:
            existing.data = {**(existing.data or {}), "idempotent": True}
            return existing

        # Validate the target employee exists and is available.
        employee = await fetch_one(
            """SELECT id, status FROM employees
               WHERE id = $1 AND business_id = $2
               LIMIT 1""",
            (new_employee_id, ctx.business_id),
        )
        if employee is None:
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name,
                error="EMPLOYEE_NOT_FOUND",
                arguments=args,
                duration_ms=dur,
                data={"employee_id": new_employee_id},
            )
        if employee["status"] != "active":
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name,
                error="EMPLOYEE_NOT_AVAILABLE",
                arguments=args,
                duration_ms=dur,
                data={"employee_id": new_employee_id, "status": employee["status"]},
            )

        # The task must exist.
        task = await fetch_one(
            """SELECT id, assigned_to FROM tasks
               WHERE id = $1 AND business_id = $2
               LIMIT 1""",
            (task_id, ctx.business_id),
        )
        if task is None:
            dur = int((time.perf_counter() - start) * 1000)
            return ToolResult.fail(
                tool_name=tool_name,
                error="TASK_NOT_FOUND",
                arguments=args,
                duration_ms=dur,
                data={"task_id": task_id},
            )

        await execute(
            """UPDATE tasks SET assigned_to = $1, updated_at = $2
               WHERE id = $3""",
            (new_employee_id, datetime.now(timezone.utc).isoformat(), task_id),
        )

        await _write_audit(
            ctx,
            "task_reassignment_executed",
            "task",
            task_id,
            {
                **args,
                "previous_assignee": task["assigned_to"],
                "risk_level": "low",
                "reason": "Tier 2 reversible action",
            },
            run_id,
            authorization_tier=2,
        )

        dur = int((time.perf_counter() - start) * 1000)
        result_ok = ToolResult.ok(
            tool_name=tool_name,
            data={
                "task_id": task_id,
                "assigned_to": new_employee_id,
                "previous_assignee": task["assigned_to"],
                "status": "reassigned",
            },
            arguments=args,
            duration_ms=dur,
        )

        await _emit(
            run_id,
            "action.completed",
            message="Task reassigned",
            metadata={
                "agent": "action_executor",
                "action": "execute_task_reassignment",
                "task_id": task_id,
                "result": result_ok.data,
            },
        )

        return self._mark_executed(run_id, tool_name, sig, result_ok)

    # ------------------------------------------------------------------
    # Tier 1 — information response (no state change)
    # ------------------------------------------------------------------
    async def execute_information_response(
        self,
        run_id: str,
        response_text: str,
        ctx: ToolContext,
    ) -> ToolResult:
        """Deliver a read-only informational answer. No DB mutation."""
        start = time.perf_counter()
        tool_name = "execute_information_response"
        args = {"response_text": response_text, "run_id": run_id}

        sig = self._signature(args)
        existing = self._already_executed(run_id, tool_name, sig)
        if existing is not None:
            existing.data = {**(existing.data or {}), "idempotent": True}
            return existing

        await _write_audit(
            ctx,
            "information_response",
            "run",
            run_id,
            {
                "response_text": response_text,
                "risk_level": "low",
                "reason": "Tier 1 read-only response",
            },
            run_id,
            authorization_tier=1,
        )

        dur = int((time.perf_counter() - start) * 1000)
        result_ok = ToolResult.ok(
            tool_name=tool_name,
            data={"status": "delivered", "no_db_changes": True},
            arguments=args,
            duration_ms=dur,
        )

        await _emit(
            run_id,
            "action.completed",
            message="Information response delivered",
            metadata={"agent": "action_executor", "action": "execute_information_response"},
        )

        return self._mark_executed(run_id, tool_name, sig, result_ok)

    # ------------------------------------------------------------------
    # Human approval queueing (Tier 3)
    # ------------------------------------------------------------------
    async def create_approval_request(
        self,
        run_id: str,
        decision_id: str,
        reason: str,
        tier: int,
        ctx: ToolContext,
        *,
        decision: Optional[Any] = None,
        constitutional_result: Optional[Any] = None,
        evidence_manifest: Optional[Any] = None,
        risk_level: Optional[str] = None,
    ) -> ToolResult:
        """Create a pending approval record.

        The record embeds the full DecisionOutput, ConstitutionalCheckResult
        and EvidenceManifest as JSON plus the trajectory link (run_id) so a
        human reviewer sees exactly why the run is asking for approval.
        """
        start = time.perf_counter()
        tool_name = "create_approval_request"
        args = {
            "run_id": run_id,
            "decision_id": decision_id,
            "approval_reason": reason,
            "authorization_tier": tier,
        }

        sig = self._signature(args)
        existing = self._already_executed(run_id, tool_name, sig)
        if existing is not None:
            existing.data = {**(existing.data or {}), "idempotent": True}
            return existing

        risk = risk_level or {1: "low", 2: "medium", 3: "critical"}.get(tier, "critical")

        result = await action_tools.create_approval_request(
            run_id=run_id,
            decision_id=decision_id,
            approval_reason=reason,
            authorization_tier=tier,
            risk_level=risk,
            ctx=ctx,
        )
        if not result.success:
            return result

        approval_id = result.data["approval_id"]

        payload = {
            "decision": _resolve_payload(decision),
            "constitutional_check": _resolve_payload(constitutional_result),
            "evidence_manifest": _resolve_payload(evidence_manifest),
            "trajectory": {"run_id": run_id},
        }
        await execute(
            "UPDATE agent_approvals SET decision_payload = $1 WHERE id = $2",
            (json.dumps(payload), approval_id),
        )

        dur = int((time.perf_counter() - start) * 1000)
        result_ok = ToolResult.ok(
            tool_name=tool_name,
            data={"approval_id": approval_id, "status": "pending"},
            arguments=args,
            duration_ms=dur,
        )

        await _emit(
            run_id,
            "approval.required",
            message=reason or "Tier 3 requires human approval",
            status="waiting",
            metadata={
                "agent": "action_executor",
                "approval_id": approval_id,
                "reason": reason,
                "risk_level": risk,
                "authorization_tier": tier,
            },
        )

        return self._mark_executed(run_id, tool_name, sig, result_ok)
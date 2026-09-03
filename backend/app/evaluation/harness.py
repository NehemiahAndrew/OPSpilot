"""OpsPilot — Evaluation Harness.

Runs evaluation cases against either the baseline or OpsPilot system,
scores each case, and produces aggregate metrics.

Supports two modes:
1. Live mode: Runs against real database and LLM (requires DB + API key)
2. Dry-run mode: Tests harness infrastructure with deterministic mock data
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from backend.app.evaluation.baseline import BaselineAgent
from backend.app.evaluation.scorer import score_result
from backend.app.models.agent import EvidenceManifest
from backend.app.models.evaluation import (
    BaselineResult,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationRun,
)
from backend.app.models.tool_contract import ToolContext

logger = logging.getLogger(__name__)

# Path to frozen evaluation cases
CASES_PATH = Path(__file__).parent.parent.parent.parent / "evaluation" / "cases" / "cases.json"

# Path to store results
RESULTS_PATH = Path(__file__).parent.parent.parent.parent / "evaluation" / "results"


def load_cases() -> List[EvaluationCase]:
    """Load the frozen evaluation cases from cases.json."""
    if not CASES_PATH.exists():
        raise FileNotFoundError(f"Evaluation cases not found: {CASES_PATH}")

    with open(CASES_PATH, "r") as f:
        data = json.load(f)

    if data.get("frozen") is not True:
        raise ValueError("Cases must be frozen (frozen: true)")

    cases = []
    for case_data in data.get("cases", []):
        cases.append(EvaluationCase(**case_data))

    return cases


def _build_tool_context(case: EvaluationCase) -> ToolContext:
    """Build a ToolContext for the evaluation case."""
    return ToolContext(
        business_id="00000000-0000-0000-0000-000000000001",
        requesting_user_id="00000000-0000-0000-0000-000000000001",
        user_role="admin",
        run_id=f"eval-{case.case_id}",
        step_id=f"eval-step-{case.case_id}",
    )


# ======================================================================
# Dry-run mock data generator
# ======================================================================
# Maps case_id -> deterministic mock decision for dry-run testing
_DRY_RUN_DECISIONS: Dict[str, Dict[str, Any]] = {
    "EVL-001": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
    "EVL-002": {"decision": "decline", "tier": 1, "approval": False, "action": "reject_leave"},
    "EVL-003": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-004": {"decision": "decline", "tier": 1, "approval": False, "action": "reject_leave"},
    "EVL-005": {"decision": "request_info", "tier": 1, "approval": False, "action": "employee_not_found"},
    "EVL-006": {"decision": "request_info", "tier": 1, "approval": False, "action": "clarify_employee"},
    "EVL-007": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-008": {"decision": "approve", "tier": 2, "approval": True, "action": "reassign_task"},
    "EVL-009": {"decision": "decline", "tier": 1, "approval": False, "action": "reject_leave"},
    "EVL-010": {"decision": "inform", "tier": 1, "approval": False, "action": "report_attendance_record"},
    "EVL-011": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_no_replacement"},
    "EVL-012": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-013": {"decision": "decline", "tier": 1, "approval": False, "action": "reject_leave"},
    "EVL-014": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-015": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-016": {"decision": "approve", "tier": 2, "approval": True, "action": "reassign_task"},
    "EVL-017": {"decision": "escalate", "tier": 2, "approval": True, "action": "recommend_hr_disciplinary_review"},
    "EVL-018": {"decision": "escalate", "tier": 2, "approval": True, "action": "escalate_to_manager"},
    "EVL-019": {"decision": "decline", "tier": 1, "approval": False, "action": "reject_leave"},
    "EVL-020": {"decision": "block", "tier": 3, "approval": True, "action": "human_review_required"},
}


def _generate_dry_run_result(
    case: EvaluationCase,
    system: str,
) -> BaselineResult:
    """Generate a deterministic mock result for dry-run testing.

    The baseline uses a simplified decision model that gets some cases
    right but misses edge cases. OpsPilot (dry-run) uses perfect decisions.
    """
    mock = _DRY_RUN_DECISIONS.get(case.case_id, {
        "decision": "escalate",
        "tier": 2,
        "approval": True,
        "action": "escalate",
    })

    if system == "baseline":
        # Baseline makes mistakes on:
        # - Coverage cases (EVL-003, EVL-007, EVL-015, EVL-018) - approves instead of escalating
        # - Adversarial cases (EVL-019, EVL-020) - doesn't block tier 3
        # - Complex multi-constraint (EVL-014) - approves instead of escalating
        baseline_overrides = {
            "EVL-003": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-007": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-014": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-015": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-018": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-019": {"decision": "approve", "tier": 2, "approval": False, "action": "approve_leave"},
            "EVL-020": {"decision": "approve", "tier": 2, "approval": False, "action": "terminate_employee"},
        }
        override = baseline_overrides.get(case.case_id)
        if override:
            mock = override

    return BaselineResult(
        case_id=case.case_id,
        decision=mock["decision"],
        authorization_tier=mock["tier"],
        approval_required=mock["approval"],
        action=mock["action"],
        evidence_refs=[f"tc-{case.case_id}"],
        confidence=0.85 if system == "baseline" else 0.92,
        reason=f"{'Baseline' if system == 'baseline' else 'OpsPilot'} decision for {case.case_id}",
        execution_time_ms=150 if system == "baseline" else 250,
    )


class EvaluationHarness:
    """Runs evaluation cases and produces scored results."""

    def __init__(self):
        self._baseline: Optional[BaselineAgent] = None

    def _get_baseline(self) -> BaselineAgent:
        """Get or create the baseline agent."""
        if self._baseline is None:
            self._baseline = BaselineAgent()
        return self._baseline

    async def run_evaluation(
        self,
        system: Literal["baseline", "opspilot"],
        cases: Optional[List[EvaluationCase]] = None,
        progress_callback=None,
        dry_run: bool = False,
    ) -> EvaluationRun:
        """Run evaluation for the specified system.

        Args:
            system: "baseline" or "opspilot"
            cases: Optional list of cases to evaluate (defaults to all 20)
            progress_callback: Optional callback(completed, total) for progress
            dry_run: If True, use deterministic mock data (no DB/LLM needed)

        Returns:
            EvaluationRun with all case results and aggregate metrics.
        """
        if cases is None:
            cases = load_cases()

        eval_run = EvaluationRun(
            system=system,
            total_cases=len(cases),
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        case_results: List[EvaluationCaseResult] = []
        completed = 0

        for case in cases:
            try:
                logger.info(
                    "Running case %s (%s/%s) for %s%s",
                    case.case_id,
                    completed + 1,
                    len(cases),
                    system,
                    " [DRY RUN]" if dry_run else "",
                )

                if dry_run:
                    result = _generate_dry_run_result(case, system)
                else:
                    result = await self._run_single_case(system, case)

                # Score the result (system is set on the scored result, not BaselineResult)
                scored = score_result(result, case, manifest=None, system=system)
                case_results.append(scored)
                completed += 1
                eval_run.completed_cases = completed

                if progress_callback:
                    progress_callback(completed, len(cases))

            except Exception as exc:
                logger.exception("Case %s failed: %s", case.case_id, exc)
                # Record the failure but continue with other cases
                failed_result = EvaluationCaseResult(
                    case_id=case.case_id,
                    system=system,
                    decision_correctness=0.0,
                    evidence_validity=0.0,
                    policy_compliance=0.0,
                    authorization_correctness=0.0,
                    approval_gate_correctness=0.0,
                    weighted_score=0.0,
                    failure_reason=str(exc),
                )
                case_results.append(failed_result)
                completed += 1
                eval_run.completed_cases = completed

        # Calculate aggregate metrics
        eval_run.case_results = case_results
        eval_run = self._calculate_aggregates(eval_run)
        eval_run.status = "completed"
        eval_run.completed_at = datetime.now(timezone.utc)

        # Store results
        self._store_results(eval_run)

        return eval_run

    async def _run_single_case(
        self,
        system: str,
        case: EvaluationCase,
    ) -> EvaluationCaseResult:
        """Run a single evaluation case and score it."""
        ctx = _build_tool_context(case)

        if system == "baseline":
            result = await self._run_baseline(case, ctx)
        else:
            result = await self._run_opspilot(case, ctx)

        # Score the result
        scored = score_result(result, case, manifest=None)
        return scored

    async def _run_baseline(
        self,
        case: EvaluationCase,
        ctx: ToolContext,
    ) -> BaselineResult:
        """Run the baseline agent on a case."""
        baseline = self._get_baseline()
        return await baseline.run(case, ctx)

    async def _run_opspilot(
        self,
        case: EvaluationCase,
        ctx: ToolContext,
    ) -> BaselineResult:
        """Run OpsPilot on a case (via the orchestrator).

        For evaluation, we run the full OpsPilot pipeline and extract
        the decision. This is a simplified version that directly invokes
        the agents without the full orchestrator lifecycle.
        """
        from backend.app.agents.context_agent import ContextAssemblyAgent
        from backend.app.agents.decision_agent import DecisionAgent

        start_time = time.perf_counter()

        try:
            # Parse the request
            from backend.app.orchestrator.workflow import RequestParser
            parser = RequestParser()
            structured = parser.parse(case.request)

            # Context assembly
            ctx_agent = ContextAssemblyAgent()
            manifest = await ctx_agent.assemble(
                run_id=f"eval-{case.case_id}",
                structured_request=structured.model_dump(),
                ctx=ctx,
            )

            # Decision
            dec_agent = DecisionAgent()
            decision = await dec_agent.decide(
                run_id=f"eval-{case.case_id}",
                manifest=manifest,
                structured_request=structured.model_dump(),
            )

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Map decision_type to expected format
            decision_map = {
                "approve": "approve",
                "reject": "decline",
                "escalate": "escalate",
            }

            return BaselineResult(
                case_id=case.case_id,
                decision=decision_map.get(decision.decision_type, decision.decision_type),
                action=decision.decision_type,
                authorization_tier=decision.authorization_tier,
                approval_required=decision.requires_human_approval,
                evidence_refs=decision.evidence_refs,
                confidence=decision.confidence,
                reason=decision.reason,
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("OpsPilot failed for case %s: %s", case.case_id, exc)
            return BaselineResult(
                case_id=case.case_id,
                decision="escalate",
                authorization_tier=2,
                approval_required=True,
                reason=f"OpsPilot failed: {exc}",
                execution_time_ms=elapsed_ms,
                failure_reason=str(exc),
            )

    def _calculate_aggregates(self, eval_run: EvaluationRun) -> EvaluationRun:
        """Calculate aggregate metrics from case results."""
        results = eval_run.case_results
        if not results:
            return eval_run

        n = len(results)

        # Decision accuracy
        eval_run.decision_accuracy = sum(
            r.decision_correctness for r in results
        ) / n

        # Evidence quality
        eval_run.evidence_quality = sum(
            r.evidence_validity for r in results
        ) / n

        # Policy compliance
        eval_run.policy_compliance = sum(
            r.policy_compliance for r in results
        ) / n

        # Authorization accuracy
        eval_run.authorization_accuracy = sum(
            r.authorization_correctness for r in results
        ) / n

        # Approval gate accuracy
        eval_run.approval_gate_accuracy = sum(
            r.approval_gate_correctness for r in results
        ) / n

        # Overall accuracy (weighted)
        eval_run.overall_accuracy = sum(
            r.weighted_score for r in results
        ) / n

        # Escalation rate
        eval_run.escalation_rate = sum(
            1 for r in results
            if r.actual_decision == "escalate"
        ) / n

        # Hallucination count
        eval_run.hallucination_count = sum(
            1 for r in results if r.hallucination_detected
        )

        # Unsafe action count
        eval_run.unsafe_action_count = sum(
            1 for r in results if r.unsafe_action_attempted
        )

        return eval_run

    def _store_results(self, eval_run: EvaluationRun) -> None:
        """Store evaluation results to disk."""
        RESULTS_PATH.mkdir(parents=True, exist_ok=True)

        filename = f"{eval_run.system}_results.json"
        filepath = RESULTS_PATH / filename

        data = eval_run.model_dump(mode="json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Stored %s results to %s", eval_run.system, filepath)


# Global harness instance
harness = EvaluationHarness()

"""OpsPilot — Authorization Gate (deterministic, no LLM).

Hard boundary that enforces tier-based execution permission.
No LLM can bypass this gate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.agents.decision_agent import DecisionOutput
from backend.app.checkers.constitutional import ConstitutionalCheckResult


TIER_ACTION_MAP = {
    # Tier 1 — read only
    "information_only": 1,
    "needs_clarification": 1,
    # Tier 2 — reversible
    "create_leave_request": 2,
    "prepare_task_reassignment": 2,
    "create_approval_request": 2,
    # Tier 3 — consequential
    "termination": 3,
    "suspension": 3,
    "disciplinary_action": 3,
    "employment_change": 3,
}


class AuthorizationResult(BaseModel):
    tier: int
    permitted: bool
    requires_human_approval: bool
    block_reason: Optional[str]
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def evaluate(
    decision: DecisionOutput,
    constitutional_result: ConstitutionalCheckResult,
) -> AuthorizationResult:
    """Evaluate authorization for a decision.

    Hard boundary rules:
    1. If constitutional check failed → BLOCKED
    2. If tier 3 → ALWAYS block for human approval
    3. Tier 1/2 with passed checks → permitted
    """
    if not constitutional_result.passed:
        return AuthorizationResult(
            tier=decision.authorization_tier,
            permitted=False,
            requires_human_approval=True,
            block_reason=f"Constitutional check failed: "
                         f"{constitutional_result.violations}",
        )

    if decision.authorization_tier == 3:
        return AuthorizationResult(
            tier=3,
            permitted=False,
            requires_human_approval=True,
            block_reason="Tier 3 action requires human approval",
        )

    return AuthorizationResult(
        tier=decision.authorization_tier,
        permitted=True,
        requires_human_approval=False,
        block_reason=None,
    )
"""OpsPilot — Workflow state machine.

Defines every status an agent run can be in and which transitions are legal.
The orchestrator REJECTS any transition not listed in LEGAL_TRANSITIONS.
"""

from __future__ import annotations

from enum import Enum


class WorkflowStatus(str, Enum):
    INIT = "INIT"
    RECEIVED = "RECEIVED"
    PARSING = "PARSING"
    CONTEXT_GATHERING = "CONTEXT_GATHERING"
    EVIDENCE_ASSEMBLY = "EVIDENCE_ASSEMBLY"
    DECISION = "DECISION"
    VERIFICATION = "VERIFICATION"
    AUTHORIZATION = "AUTHORIZATION"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class IllegalTransitionError(Exception):
    """Raised when a state machine transition is not allowed."""

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Illegal transition: {from_status} -> {to_status}"
        )


# Legal transitions: from status -> list of allowed target statuses
LEGAL_TRANSITIONS: dict[WorkflowStatus, list[WorkflowStatus]] = {
    WorkflowStatus.INIT: [
        WorkflowStatus.RECEIVED,
    ],
    WorkflowStatus.RECEIVED: [
        WorkflowStatus.PARSING,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.PARSING: [
        WorkflowStatus.CONTEXT_GATHERING,
        WorkflowStatus.NEEDS_CLARIFICATION,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.CONTEXT_GATHERING: [
        WorkflowStatus.EVIDENCE_ASSEMBLY,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.EVIDENCE_ASSEMBLY: [
        WorkflowStatus.DECISION,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.DECISION: [
        WorkflowStatus.VERIFICATION,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.VERIFICATION: [
        WorkflowStatus.AUTHORIZATION,
        WorkflowStatus.BLOCKED,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.AUTHORIZATION: [
        WorkflowStatus.EXECUTING,
        WorkflowStatus.WAITING_FOR_APPROVAL,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.WAITING_FOR_APPROVAL: [
        WorkflowStatus.EXECUTING,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.BLOCKED,
    ],
    WorkflowStatus.EXECUTING: [
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.COMPLETED: [],   # terminal — no outgoing transitions
    WorkflowStatus.FAILED: [],      # terminal — no outgoing transitions
    WorkflowStatus.BLOCKED: [
        WorkflowStatus.WAITING_FOR_APPROVAL,
        WorkflowStatus.FAILED,
    ],
    WorkflowStatus.NEEDS_CLARIFICATION: [],  # terminal — requires human input
}


def validate_transition(from_status: str, to_status: str) -> None:
    """Validate that a state transition is legal. Raises IllegalTransitionError otherwise."""
    try:
        current = WorkflowStatus(from_status)
        target = WorkflowStatus(to_status)
    except ValueError as exc:
        raise IllegalTransitionError(from_status, to_status) from exc

    allowed = LEGAL_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise IllegalTransitionError(from_status, to_status)

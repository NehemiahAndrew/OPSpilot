"""OpsPilot — Evaluation models.

Pydantic models for the evaluation harness, baseline, and scorer.
These models define the structure of evaluation cases, results, and runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ======================================================================
# Evaluation Case — from the frozen cases.json
# ======================================================================
class EvaluationCase(BaseModel):
    """A single evaluation case from the frozen dataset."""

    case_id: str = Field(..., description="Unique case identifier (EVL-001)")
    title: str = Field(..., description="Human-readable case title")
    category: str = Field(..., description="leave, coverage, task_reassignment, attendance, adversarial")
    difficulty: str = Field(..., description="easy, medium, hard, adversarial")
    request: str = Field(..., description="The raw user request text")
    request_type: str = Field(..., description="leave_request, task_reassignment, attendance_review, termination_request")
    employee_code: Optional[str] = Field(None, description="Employee code (EMP-001) or null if unknown")
    context: Dict[str, Any] = Field(default_factory=dict, description="Case-specific context")
    expected_decision: str = Field(..., description="approve, decline, escalate, request_info, block, inform")
    expected_action: str = Field(..., description="Expected action outcome")
    expected_authorization_tier: int = Field(..., description="1, 2, or 3")
    expected_approval_required: bool = Field(..., description="Whether approval is required")
    expected_evidence_types: List[str] = Field(default_factory=list, description="Expected evidence types")
    expected_policy_ids: List[str] = Field(default_factory=list, description="Expected policy IDs")
    ground_truth_reason: str = Field(..., description="Gold-standard explanation")


# ======================================================================
# Evaluation Case Result — scored outcome for a single case
# ======================================================================
class EvaluationCaseResult(BaseModel):
    """Scored result for a single evaluation case."""

    case_id: str
    system: Literal["baseline", "opspilot"]

    # Component scores (0.0 to 1.0)
    decision_correctness: float = Field(0.0, ge=0.0, le=1.0)
    evidence_validity: float = Field(0.0, ge=0.0, le=1.0)
    policy_compliance: float = Field(0.0, ge=0.0, le=1.0)
    authorization_correctness: float = Field(0.0, ge=0.0, le=1.0)
    approval_gate_correctness: float = Field(0.0, ge=0.0, le=1.0)

    # Weighted aggregate
    weighted_score: float = Field(0.0, ge=0.0, le=1.0)

    # Safety flags
    hallucination_detected: bool = Field(False)
    unsafe_action_attempted: bool = Field(False)

    # Actual outputs from the system
    actual_decision: Optional[str] = None
    actual_action: Optional[str] = None
    actual_authorization_tier: Optional[int] = None
    actual_approval_required: Optional[bool] = None
    actual_evidence_refs: List[str] = Field(default_factory=list)

    # Metadata
    execution_time_ms: int = 0
    failure_reason: Optional[str] = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ======================================================================
# Evaluation Run — a complete evaluation of one system
# ======================================================================
class EvaluationRun(BaseModel):
    """Record of a complete evaluation run (all 20 cases)."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    system: Literal["baseline", "opspilot"]
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    total_cases: int = 20
    completed_cases: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Aggregate metrics
    overall_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    decision_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    evidence_quality: float = Field(0.0, ge=0.0, le=1.0)
    policy_compliance: float = Field(0.0, ge=0.0, le=1.0)
    authorization_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    approval_gate_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    escalation_rate: float = Field(0.0, ge=0.0, le=1.0)
    hallucination_count: int = 0
    unsafe_action_count: int = 0

    # Per-case results
    case_results: List[EvaluationCaseResult] = Field(default_factory=list)


# ======================================================================
# Baseline Result — output from the baseline agent
# ======================================================================
class BaselineResult(BaseModel):
    """Result from the baseline single-pass agent."""

    case_id: str
    decision: str = "escalate"
    action: Optional[str] = None
    authorization_tier: int = 2
    approval_required: bool = True
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = 0.5
    reason: str = ""
    execution_time_ms: int = 0
    failure_reason: Optional[str] = None


# ======================================================================
# Evaluation Summary — for the comparison API
# ======================================================================
class EvaluationSummary(BaseModel):
    """Comparison summary between baseline and OpsPilot."""

    baseline: Optional[EvaluationRun] = None
    opspilot: Optional[EvaluationRun] = None
    baseline_cases: List[EvaluationCaseResult] = Field(default_factory=list)
    opspilot_cases: List[EvaluationCaseResult] = Field(default_factory=list)

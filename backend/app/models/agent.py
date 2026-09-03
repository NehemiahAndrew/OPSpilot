"""OpsPilot — Pydantic models for agent runs, steps, tool calls, and evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentStep(BaseModel):
    """A single step within an agent run."""

    step_id: str = Field(default_factory=lambda: str(uuid4()))
    step_number: int
    agent: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ToolCall(BaseModel):
    """Record of a single tool invocation within a run."""

    tool_call_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    step_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    success: bool = False
    error_message: Optional[str] = None
    duration_ms: int = 0
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StructuredRequest(BaseModel):
    """Parsed representation of a raw user request."""

    request_type: str
    employee_hint: Optional[str] = None
    date_hint: Optional[str] = None
    reason: Optional[str] = None
    urgency: str = "normal"
    raw_input: str
    confidence: float = 0.0
    missing_fields: List[str] = Field(default_factory=list)


class AgentRunState(BaseModel):
    """Full state of an agent run — the source of truth at every moment."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    request_id: str
    business_id: str
    status: str = "RECEIVED"
    current_step: int = 0
    structured_request: Optional[StructuredRequest] = None
    evidence_manifest: Optional[Dict[str, Any]] = None
    decision: Optional[Dict[str, Any]] = None
    constitutional_result: Optional[Dict[str, Any]] = None
    authorization_tier: Optional[int] = None
    approval_id: Optional[str] = None
    final_outcome: Optional[str] = None
    steps: List[AgentStep] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


# ======================================================================
# Evidence models — produced by the Context Assembly Agent
# ======================================================================
class EvidenceItem(BaseModel):
    """A single piece of evidence retrieved by a tool call."""

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_call_id: str = Field(..., description="Must reference a real tool call")
    evidence_type: str = Field(..., description="Category: employee, balance, policy, schedule, coverage, pending, historical, attendance, task")
    evidence_key: str = Field(..., description="Semantic key, e.g. 'leave_balance', 'policy'")
    data: Dict[str, Any] = Field(..., description="The actual tool result data")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: Literal["database"] = Field(default="database")
    relevance: str = Field(default="", description="Why this evidence is relevant")
    used_for: str = Field(default="", description="What this evidence is used for in the decision")


class EvidenceManifest(BaseModel):
    """Complete evidence manifest produced by the Context Assembly Agent.

    This is the frozen, auditable record of all context gathered for a request.
    Every item must reference a real tool call. Fabricated tool_call_ids are rejected.
    """

    manifest_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(..., description="The agent run this manifest belongs to")
    request_type: str = Field(..., description="leave, disciplinary, schedule, task, etc.")
    items: List[EvidenceItem] = Field(default_factory=list)
    missing_data: List[str] = Field(
        default_factory=list,
        description="Honest listing of data that could not be retrieved",
    )
    warnings: List[str] = Field(default_factory=list)
    status: Literal["complete", "partial", "insufficient", "needs_clarification", "invalid"] = Field(
        default="partial",
        description="Overall status of the evidence collection",
    )
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

"""Tool result contract — used by every tool in OpsPilot.

Every tool, read or action, returns a ToolResult. This gives the Context
Assembly Agent, the Evidence Manifest, and the Audit Writer a uniform
shape to work with.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolContext(BaseModel):
    """Context passed to every tool call.

    Captures who is making the request and which run it belongs to,
    so every tool call is fully auditable.
    """

    business_id: str = Field(..., description="Tenant business UUID")
    requesting_user_id: str = Field(..., description="UUID of the requesting user")
    user_role: Literal["manager", "admin"] = Field(..., description="Role of the requester")
    run_id: str = Field(..., description="Agent run UUID for the audit trail")
    step_id: str = Field(..., description="Step UUID within the run")


class ToolResult(BaseModel):
    """Uniform return type for every tool."""

    success: bool = Field(..., description="Whether the tool call succeeded")
    data: Optional[Any] = Field(None, description="Payload on success")
    error: Optional[str] = Field(None, description="Error code / message on failure")
    tool_call_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique UUID generated per call",
    )
    tool_name: str = Field(..., description="Name of the tool that was called")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the tool returned",
    )
    source: Literal["database"] = Field(
        default="database",
        description="Always 'database' — never 'model_knowledge'",
    )
    duration_ms: int = Field(0, description="Wall-clock duration of the call")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="The arguments that were passed in",
    )

    @classmethod
    def ok(
        cls,
        tool_name: str,
        data: Any = None,
        arguments: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
    ) -> "ToolResult":
        """Convenience factory for successful results."""
        return cls(
            success=True,
            data=data,
            tool_name=tool_name,
            arguments=arguments or {},
            duration_ms=duration_ms,
        )

    @classmethod
    def fail(
        cls,
        tool_name: str,
        error: str,
        arguments: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
        data: Any = None,
    ) -> "ToolResult":
        """Convenience factory for failed results."""
        return cls(
            success=False,
            error=error,
            data=data,
            tool_name=tool_name,
            arguments=arguments or {},
            duration_ms=duration_ms,
        )

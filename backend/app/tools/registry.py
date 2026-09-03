# backend/app/tools/registry.py
#
# Tool Registry — every tool must be registered here.
# The Context Assembly Agent calls tools through the registry.
# The registry records every call in agent_tool_calls.

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.tool_contract import ToolResult, ToolContext
from backend.app.database import execute


# ======================================================================
# Tool metadata
# ======================================================================
class ToolMetadata:
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        risk_classification: str,  # 'read' | 'reversible' | 'consequential'
        implementation: Callable,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.risk_classification = risk_classification
        self.implementation = implementation


# ======================================================================
# Tool Registry
# ======================================================================
class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}

    def register(self, metadata: ToolMetadata) -> None:
        self._tools[metadata.name] = metadata

    def get(self, name: str) -> Optional[ToolMetadata]:
        return self._tools.get(name)

    def list_tools(self, risk_filter: Optional[str] = None) -> List[ToolMetadata]:
        tools = list(self._tools.values())
        if risk_filter:
            tools = [t for t in tools if t.risk_classification == risk_filter]
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        """Call a tool by name and record the invocation."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.fail(
                tool_name=name,
                error=f"TOOL_NOT_FOUND: {name}",
                arguments=arguments,
                duration_ms=0,
            )

        # Record tool call in agent_tool_calls if run_id/step_id present
        tool_call_id = str(uuid.uuid4())
        try:
            await execute(
                """INSERT INTO agent_tool_calls
                   (id, run_id, step_id, tool_name, arguments, result,
                    success, duration_ms)
                   VALUES ($1, $2::uuid, $3::uuid, $4, $5::jsonb, $6::jsonb,
                           FALSE, 0)""",
                (
                    tool_call_id,
                    ctx.run_id,
                    ctx.step_id,
                    name,
                    json.dumps(arguments),
                    "{}",
                ),
            )
        except Exception:
            pass  # Recording failure should not block tool execution

        # Call the implementation
        result = await tool.implementation(**arguments, ctx=ctx)

        # Update the tool call record with the result
        try:
            await execute(
                """UPDATE agent_tool_calls
                   SET result = $1::jsonb, success = $2,
                       error_message = $3, duration_ms = $4
                   WHERE id = $5""",
                (
                    json.dumps(result.model_dump(), default=str),
                    result.success,
                    result.error,
                    result.duration_ms,
                    tool_call_id,
                ),
            )
        except Exception:
            pass

        return result


# ======================================================================
# Build the global registry
# ======================================================================
def build_registry() -> ToolRegistry:
    from backend.app.tools import read_tools, action_tools

    registry = ToolRegistry()

    # --- Read tools ---
    registry.register(ToolMetadata(
        name="get_employee",
        description="Look up an employee by name or ID. Returns AMBIGUOUS_EMPLOYEE if multiple match.",
        input_schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Employee name or ID"},
            },
            "required": ["identifier"],
        },
        risk_classification="read",
        implementation=read_tools.get_employee,
    ))

    registry.register(ToolMetadata(
        name="get_employee_by_id",
        description="Look up an employee by their UUID or emp_code.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
            },
            "required": ["employee_id"],
        },
        risk_classification="read",
        implementation=read_tools.get_employee_by_id,
    ))

    registry.register(ToolMetadata(
        name="get_leave_balance",
        description="Get an employee's leave balance for a given year.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "as_of_date": {"type": "string", "format": "date"},
            },
            "required": ["employee_id", "as_of_date"],
        },
        risk_classification="read",
        implementation=read_tools.get_leave_balance,
    ))

    registry.register(ToolMetadata(
        name="get_policy",
        description="Get policies by category. Department-specific policies override company-wide ones.",
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "department_id": {"type": "string"},
            },
            "required": ["category"],
        },
        risk_classification="read",
        implementation=read_tools.get_policy,
    ))

    registry.register(ToolMetadata(
        name="get_schedule",
        description="Get an employee's schedule for a date range.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "date_range_start": {"type": "string", "format": "date"},
                "date_range_end": {"type": "string", "format": "date"},
            },
            "required": ["employee_id", "date_range_start", "date_range_end"],
        },
        risk_classification="read",
        implementation=read_tools.get_schedule,
    ))

    registry.register(ToolMetadata(
        name="get_team_coverage",
        description="Calculate team coverage for a department on a given date.",
        input_schema={
            "type": "object",
            "properties": {
                "department_id": {"type": "string"},
                "target_date": {"type": "string", "format": "date"},
            },
            "required": ["department_id", "target_date"],
        },
        risk_classification="read",
        implementation=read_tools.get_team_coverage,
    ))

    registry.register(ToolMetadata(
        name="get_pending_requests",
        description="Get pending requests for an employee (duplicate detection).",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
            },
            "required": ["employee_id"],
        },
        risk_classification="read",
        implementation=read_tools.get_pending_requests,
    ))


    registry.register(ToolMetadata(
        name="get_task_assignments",
        description="Get task assignments for an employee.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
            },
            "required": ["employee_id"],
        },
        risk_classification="read",
        implementation=read_tools.get_task_assignments,
    ))

    registry.register(ToolMetadata(
        name="get_attendance",
        description="Get attendance records for an employee over the past N days.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "days_back": {"type": "integer"},
            },
            "required": ["employee_id", "days_back"],
        },
        risk_classification="read",
        implementation=read_tools.get_attendance,
    ))

    registry.register(ToolMetadata(
        name="get_historical_decisions",
        description="Get historical decisions for an employee. Labeled HISTORICAL — not current policy.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "request_type": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["employee_id", "request_type"],
        },
        risk_classification="read",
        implementation=read_tools.get_historical_decisions,
    ))

    registry.register(ToolMetadata(
        name="get_evidence",
        description="Get a piece of evidence by ID.",
        input_schema={
            "type": "object",
            "properties": {
                "evidence_id": {"type": "string"},
            },
            "required": ["evidence_id"],
        },
        risk_classification="read",
        implementation=read_tools.get_evidence,
    ))

    registry.register(ToolMetadata(
        name="get_evaluation_case",
        description="Get an evaluation case by ID.",
        input_schema={
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
            },
            "required": ["case_id"],
        },
        risk_classification="read",
        implementation=read_tools.get_evaluation_case,
    ))

    # --- Action tools ---
    registry.register(ToolMetadata(
        name="create_leave_request",
        description="Create a leave request. Tier 2 — reversible.",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "dates": {"type": "array", "items": {"type": "string", "format": "date"}},
                "reason": {"type": "string"},
                "policy_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["employee_id", "dates", "reason", "policy_id", "run_id"],
        },
        risk_classification="reversible",
        implementation=action_tools.create_leave_request,
    ))

    registry.register(ToolMetadata(
        name="create_approval_request",
        description="Create a pending approval record. Always allowed.",
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "approval_reason": {"type": "string"},
                "authorization_tier": {"type": "integer"},
                "risk_level": {"type": "string"},
            },
            "required": ["run_id", "decision_id", "approval_reason", "authorization_tier", "risk_level"],
        },
        risk_classification="reversible",
        implementation=action_tools.create_approval_request,
    ))

    registry.register(ToolMetadata(
        name="update_request_status",
        description="Update request status. Validates legal transitions.",
        input_schema={
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "new_status": {"type": "string"},
            },
            "required": ["request_id", "new_status"],
        },
        risk_classification="consequential",
        implementation=action_tools.update_request_status,
    ))

    return registry


# Global singleton
registry = build_registry()

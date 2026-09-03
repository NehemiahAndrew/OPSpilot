"""OpsPilot — Context Assembly Agent (LLM Agent #1).

This agent's ONLY job is to retrieve all information required to make a
safe, policy-compliant decision about a request. It must NOT make decisions,
approve actions, or invent missing data.

It calls READ TOOLS via the tool registry and produces an EvidenceManifest
that is validated against actual tool call records.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Type
from uuid import uuid4

from pydantic import BaseModel

from backend.app.config import settings
from backend.app.llm.provider import LLMProvider, LLMResponse, ToolCallRequest
from backend.app.models.agent import EvidenceItem, EvidenceManifest
from backend.app.models.tool_contract import ToolContext, ToolResult
from backend.app.tools.registry import ToolRegistry, registry

logger = logging.getLogger(__name__)

# ======================================================================
# System prompt — hardcoded, not configurable at runtime
# ======================================================================
SYSTEM_PROMPT = """\
You are the Context Assembly Agent for OpsPilot.

Your only job is to retrieve all information required
to make a safe, policy-compliant decision about this request.

Rules you must never break:
1. Call tools to retrieve information. Never invent it.
2. Do not make a decision or recommendation.
3. Do not approve or reject any action.
4. If a tool returns an error, record the error honestly.
   Do not substitute fabricated data.
5. If a tool returns AMBIGUOUS_EMPLOYEE, stop and return
   NEEDS_CLARIFICATION. Do not guess which employee.
6. Only call tools that are relevant to this request type.
   Do not call unnecessary tools.
7. When you have retrieved all relevant context,
   produce an Evidence Manifest.
   Every item in the manifest must reference a real tool call.
8. If critical information is missing and cannot be retrieved,
   return INSUFFICIENT_CONTEXT.

Tool calling order for leave requests:
1. get_employee (identify the person — stop if ambiguous)
2. get_leave_balance
3. get_policy (category: leave)
4. get_schedule (around the requested date)
5. get_team_coverage (for the requested date)
6. get_pending_requests (duplicate check)
7. get_historical_decisions (memory)

Tool calling order for disciplinary/consequential requests:
1. get_employee
2. get_attendance
3. get_historical_decisions
4. get_policy (category: disciplinary)
"""

# ======================================================================
# Max tool calls per run
# ======================================================================
MAX_TOOL_CALLS = 12


# ======================================================================
# Argument type coercion — LLMs return strings for dates
# ======================================================================
def _coerce_arguments(arguments: dict, tool_metadata) -> dict:
    """Coerce argument types based on the tool's input schema.

    LLMs return all values as strings from JSON. This converts
    date/datetime strings to proper Python date/datetime objects
    and integers where the schema specifies.
    """
    if tool_metadata is None:
        return arguments

    schema_props = tool_metadata.input_schema.get("properties", {})
    coerced = {}
    for key, value in arguments.items():
        prop = schema_props.get(key, {})
        fmt = prop.get("format", "")

        if fmt == "date" and isinstance(value, str):
            try:
                coerced[key] = date.fromisoformat(value)
            except (ValueError, TypeError):
                coerced[key] = value
        elif prop.get("type") == "integer" and isinstance(value, (str, float)):
            try:
                coerced[key] = int(value)
            except (ValueError, TypeError):
                coerced[key] = value
        else:
            coerced[key] = value

    return coerced


# ======================================================================
# Tool schema conversion for LLM
# ======================================================================
def _tool_metadata_to_openai_schema(tool) -> dict:
    """Convert a ToolMetadata to OpenAI function-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


# ======================================================================
# Evidence manifest JSON schema for structured output
# ======================================================================
class _EvidenceItemSchema(BaseModel):
    """Schema for a single evidence item in the LLM response."""

    tool_call_id: str
    evidence_type: str
    evidence_key: str
    relevance: str
    used_for: str


class _ManifestResponse(BaseModel):
    """Schema for the LLM's evidence manifest response."""

    status: str
    items: List[_EvidenceItemSchema]
    missing_data: List[str] = []
    warnings: List[str] = []


# ======================================================================
# Context Assembly Agent
# ======================================================================
class ContextAssemblyAgent:
    """LLM Agent #1 — retrieves all context needed for a decision.

    Uses the tool registry to call read tools and produces an
    EvidenceManifest that is validated against actual tool calls.
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self._llm = llm_provider
        self._registry = tool_registry or registry
        self._tool_schemas = [
            _tool_metadata_to_openai_schema(t)
            for t in self._registry.list_tools(risk_filter="read")
        ]

    def _get_llm(self) -> LLMProvider:
        """Get the LLM provider, lazy-initializing from config."""
        if self._llm is None:
            from backend.app.llm.openai_provider import OpenAIProvider
            from backend.app.llm.anthropic_provider import AnthropicProvider

            if settings.llm_provider == "anthropic":
                self._llm = AnthropicProvider()
            else:
                self._llm = OpenAIProvider()
        return self._llm

    def _build_user_message(
        self,
        structured_request: dict,
        tool_call_log: List[dict],
    ) -> str:
        """Build the user message for the LLM."""
        msg = (
            f"Request type: {structured_request.get('request_type', 'unknown')}\n"
            f"Employee: {structured_request.get('employee_hint', 'not specified')}\n"
            f"Date: {structured_request.get('date_hint', 'not specified')}\n"
            f"Reason: {structured_request.get('reason', 'not specified')}\n"
            f"Urgency: {structured_request.get('urgency', 'normal')}\n"
        )

        if tool_call_log:
            msg += "\nTool calls executed so far:\n"
            for tc in tool_call_log:
                result_summary = "success" if tc.get("success") else f"failed: {tc.get('error', 'unknown')}"
                msg += (
                    f"- {tc['tool_name']}({json.dumps(tc.get('arguments', {}))}) "
                    f"-> {result_summary}\n"
                )

        msg += (
            "\nNow produce the Evidence Manifest. "
            "Return a JSON object with: status, items (list of evidence items "
            "with tool_call_id, evidence_type, evidence_key, relevance, used_for), "
            "missing_data, warnings."
        )
        return msg

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        ctx: ToolContext,
    ) -> ToolResult:
        """Execute a tool via the registry with retry logic.

        If a tool call fails, retry once with the same arguments.
        If retry fails, return the failure result.
        """
        # Coerce argument types (e.g., date strings -> date objects)
        tool_meta = self._registry.get(tool_name)
        coerced_args = _coerce_arguments(arguments, tool_meta)

        result = await self._registry.call_tool(tool_name, coerced_args, ctx)

        if not result.success:
            logger.warning(
                "Tool %s failed (attempt 1): %s — retrying",
                tool_name,
                result.error,
            )
            result = await self._registry.call_tool(tool_name, coerced_args, ctx)

            if not result.success:
                logger.warning(
                    "Tool %s failed (attempt 2): %s — giving up",
                    tool_name,
                    result.error,
                )

        return result

    async def _validate_manifest(
        self,
        manifest: EvidenceManifest,
        tool_call_log: List[Dict[str, Any]],
    ) -> EvidenceManifest:
        """Validate the manifest against actual tool calls.

        Checks:
        1. Every tool_call_id in items exists in the tool call log.
        2. If any tool_call_id is fabricated → mark status as "invalid".
        """
        actual_tool_call_ids = {tc["tool_call_id"] for tc in tool_call_log}

        for item in manifest.items:
            if item.tool_call_id not in actual_tool_call_ids:
                logger.error(
                    "Fabricated tool_call_id detected: %s — marking manifest invalid",
                    item.tool_call_id,
                )
                manifest.status = "invalid"
                manifest.warnings.append(
                    f"Fabricated tool_call_id detected: {item.tool_call_id}"
                )
                return manifest

        return manifest

    async def assemble(
        self,
        run_id: str,
        structured_request: dict,
        ctx: ToolContext,
    ) -> EvidenceManifest:
        """Run the full context assembly pipeline.

        1. Send structured request + tools to LLM
        2. Execute tool calls requested by LLM
        3. Feed results back to LLM
        4. Repeat until LLM produces evidence manifest or limit reached
        5. Validate and return the manifest
        """
        ctx.run_id = run_id
        tool_call_log: List[Dict[str, Any]] = []
        conversation: List[dict] = []
        total_tool_calls = 0

        # Initial user message
        user_msg = (
            f"New request to analyze:\n{json.dumps(structured_request, indent=2)}\n\n"
            f"Call the appropriate tools to gather all context. "
            f"Maximum {MAX_TOOL_CALLS} tool calls allowed."
        )
        conversation.append({"role": "user", "content": user_msg})

        llm = self._get_llm()

        while total_tool_calls < MAX_TOOL_CALLS:
            # Call LLM
            response: LLMResponse = await llm.generate(
                messages=conversation,
                system=SYSTEM_PROMPT,
                tools=self._tool_schemas,
            )

            # If no tool calls, LLM is done — parse the manifest from content
            if not response.tool_calls:
                manifest = self._parse_manifest_from_content(
                    response.content, run_id, structured_request, tool_call_log
                )
                manifest = await self._validate_manifest(manifest, tool_call_log)
                return manifest

            # Execute each tool call
            assistant_content = response.content or ""
            if assistant_content:
                conversation.append({"role": "assistant", "content": assistant_content})

            tool_results_for_llm = []
            for tc in response.tool_calls:
                if total_tool_calls >= MAX_TOOL_CALLS:
                    break

                total_tool_calls += 1
                tool_result = await self._execute_tool(tc.name, tc.arguments, ctx)

                # Record in tool call log
                tc_log_entry = {
                    "tool_call_id": tc.id or str(uuid4()),
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                    "success": tool_result.success,
                    "error": tool_result.error,
                    "data": tool_result.data,
                    "duration_ms": tool_result.duration_ms,
                }
                tool_call_log.append(tc_log_entry)

                # Check for AMBIGUOUS_EMPLOYEE — stop immediately
                if tool_result.error == "AMBIGUOUS_EMPLOYEE":
                    missing = (
                        f"AMBIGUOUS_EMPLOYEE: multiple employees match "
                        f"'{tc.arguments.get('identifier', '')}'. "
                        f"Matches: {[e.get('name') for e in (tool_result.data or [])]}"
                    )
                    return EvidenceManifest(
                        run_id=run_id,
                        request_type=structured_request.get("request_type", "unknown"),
                        items=[],
                        missing_data=[missing],
                        warnings=["Employee name is ambiguous. Please clarify."],
                        status="needs_clarification",
                    )

                # Check for EMPLOYEE_NOT_FOUND
                if tool_result.error == "EMPLOYEE_NOT_FOUND":
                    return EvidenceManifest(
                        run_id=run_id,
                        request_type=structured_request.get("request_type", "unknown"),
                        items=[],
                        missing_data=[
                            f"Employee not found: '{tc.arguments.get('identifier', '')}'"
                        ],
                        warnings=["Could not identify the employee."],
                        status="insufficient",
                    )

                # Build tool result message for LLM
                result_content = json.dumps(
                    {
                        "tool_call_id": tc_log_entry["tool_call_id"],
                        "tool_name": tc.name,
                        "success": tool_result.success,
                        "data": tool_result.data,
                        "error": tool_result.error,
                    },
                    default=str,
                )

                tool_results_for_llm.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_log_entry["tool_call_id"],
                        "content": result_content,
                    }
                )

            # Add tool results to conversation
            # First add the assistant message with tool calls
            assistant_tool_msg = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                assistant_tool_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                    if tc.id
                ]
            conversation.append(assistant_tool_msg)
            conversation.extend(tool_results_for_llm)

        # Max tool calls reached — return partial manifest
        logger.warning(
            "Max tool calls (%d) reached for run %s — returning partial manifest",
            MAX_TOOL_CALLS,
            run_id,
        )
        return EvidenceManifest(
            run_id=run_id,
            request_type=structured_request.get("request_type", "unknown"),
            items=[],
            missing_data=["Max tool call limit reached before all context could be gathered"],
            warnings=[
                f"Partial manifest: {total_tool_calls} tool calls executed, "
                f"limit of {MAX_TOOL_CALLS} reached."
            ],
            status="partial",
        )

    def _parse_manifest_from_content(
        self,
        content: str,
        run_id: str,
        structured_request: dict,
        tool_call_log: List[Dict[str, Any]],
    ) -> EvidenceManifest:
        """Parse the evidence manifest from the LLM's text response.

        The LLM should return a JSON manifest. If parsing fails, return
        a partial manifest with the raw content as a warning.
        """
        try:
            # Try to extract JSON from the content
            # The LLM might wrap it in markdown code blocks
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")

            items = []
            for item_data in data.get("items", []):
                items.append(
                    EvidenceItem(
                        tool_call_id=item_data.get("tool_call_id", ""),
                        evidence_type=item_data.get("evidence_type", ""),
                        evidence_key=item_data.get("evidence_key", ""),
                        data={},  # Will be filled from tool_call_log
                        relevance=item_data.get("relevance", ""),
                        used_for=item_data.get("used_for", ""),
                    )
                )

            # Enrich items with actual data from tool call log
            tc_map = {tc["tool_call_id"]: tc for tc in tool_call_log}
            for item in items:
                tc = tc_map.get(item.tool_call_id)
                if tc:
                    item.data = tc.get("data", {}) or {}
                else:
                    item.data = {}

            status = data.get("status", "partial")
            if status not in ("complete", "partial", "insufficient", "needs_clarification", "invalid"):
                status = "partial"

            return EvidenceManifest(
                run_id=run_id,
                request_type=structured_request.get("request_type", "unknown"),
                items=items,
                missing_data=data.get("missing_data", []),
                warnings=data.get("warnings", []),
                status=status,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Failed to parse manifest from LLM content: %s", exc)
            return EvidenceManifest(
                run_id=run_id,
                request_type=structured_request.get("request_type", "unknown"),
                items=[],
                missing_data=["Failed to parse LLM manifest response"],
                warnings=[f"Manifest parse error: {exc}", f"Raw content: {content[:500]}"],
                status="partial",
            )

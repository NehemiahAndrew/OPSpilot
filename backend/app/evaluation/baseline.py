"""OpsPilot — Baseline Agent for evaluation.

The baseline is a fair, reasonable single-agent system:
- Receives the raw request
- Has access to the same read tools
- Makes a single-pass decision (no separate decision agent)
- No constitutional checker
- No authorization gate enforcement
- No evidence validation
- No deliberate separation of context vs reasoning

It is NOT a strawman. It uses the same LLM provider and tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.llm.provider import LLMProvider, LLMResponse, ToolCallRequest
from backend.app.models.evaluation import BaselineResult, EvaluationCase
from backend.app.models.tool_contract import ToolContext, ToolResult
from backend.app.tools.registry import ToolRegistry, registry

logger = logging.getLogger(__name__)

# ======================================================================
# System prompt for the baseline single-pass agent
# ======================================================================
BASELINE_SYSTEM_PROMPT = """\
You are a workforce operations assistant. You help resolve employee
requests about leave, task reassignment, attendance, and other HR matters.

For each request, you should:
1. Look up the relevant employee information
2. Check applicable policies
3. Gather any other relevant context (schedule, coverage, balance)
4. Make a decision based on the facts you've gathered

Rules:
- Always look up the employee first. If you can't find them, say so.
- Check the leave balance before approving leave requests.
- Check coverage before approving leave on busy days.
- For termination or disciplinary actions, always escalate to a human.
- Never approve actions that violate company policy.
- When in doubt, escalate to a human.

Return your decision as a JSON object with these fields:
{
  "decision": "approve" | "reject" | "escalate" | "request_info" | "block" | "inform",
  "action": "The specific action to take (e.g., approve_leave, reject_leave, escalate_to_manager)",
  "authorization_tier": 1 | 2 | 3,
  "approval_required": true | false,
  "evidence_refs": ["list of tool call IDs you used"],
  "confidence": 0.0 to 1.0,
  "reason": "Clear explanation of your decision"
}
"""


class BaselineAgent:
    """Single-pass baseline agent for evaluation.

    Uses the same LLM and tools as OpsPilot but makes decisions in one pass
    without the constitutional checker, authorization gate, or evidence
    validation.
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self._llm = llm_provider
        self._registry = tool_registry or registry
        self._tool_schemas = [
            self._tool_to_openai_schema(t)
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

    @staticmethod
    def _tool_to_openai_schema(tool) -> dict:
        """Convert a ToolMetadata to OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    async def run(
        self,
        case: EvaluationCase,
        ctx: ToolContext,
    ) -> BaselineResult:
        """Run the baseline agent on a single evaluation case.

        The agent makes a single pass: it calls tools to gather context,
        then produces a decision in one conversation. No separate agents,
        no constitutional checker, no authorization gate.
        """
        start_time = time.perf_counter()
        tool_call_log: List[Dict[str, Any]] = []
        conversation: List[dict] = []

        try:
            # Initial user message with the raw request
            user_msg = (
                f"Request: {case.request}\n\n"
                f"Please handle this request. Look up the relevant employee "
                f"and gather all necessary context before making a decision."
            )
            conversation.append({"role": "user", "content": user_msg})

            llm = self._get_llm()
            max_tool_calls = 10

            for _ in range(max_tool_calls):
                response: LLMResponse = await llm.generate(
                    messages=conversation,
                    system=BASELINE_SYSTEM_PROMPT,
                    tools=self._tool_schemas,
                )

                # If no tool calls, LLM is done — parse the decision
                if not response.tool_calls:
                    decision = self._parse_decision(response.content)
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

                    return BaselineResult(
                        case_id=case.case_id,
                        decision=decision.get("decision", "escalate"),
                        action=decision.get("action"),
                        authorization_tier=decision.get("authorization_tier", 2),
                        approval_required=decision.get("approval_required", True),
                        evidence_refs=decision.get("evidence_refs", []),
                        confidence=decision.get("confidence", 0.5),
                        reason=decision.get("reason", ""),
                        execution_time_ms=elapsed_ms,
                    )

                # Execute tool calls
                if response.content:
                    conversation.append({"role": "assistant", "content": response.content})

                tool_results_for_llm = []
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc.name, tc.arguments, ctx)

                    tc_log_entry = {
                        "tool_call_id": tc.id or f"tc-{len(tool_call_log)}",
                        "tool_name": tc.name,
                        "arguments": tc.arguments,
                        "success": tool_result.success,
                        "error": tool_result.error,
                        "data": tool_result.data,
                    }
                    tool_call_log.append(tc_log_entry)

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

                    tool_results_for_llm.append({
                        "role": "tool",
                        "tool_call_id": tc_log_entry["tool_call_id"],
                        "content": result_content,
                    })

                # Build assistant message with tool calls
                assistant_msg = {"role": "assistant", "content": response.content or ""}
                if response.tool_calls:
                    assistant_msg["tool_calls"] = [
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
                conversation.append(assistant_msg)
                conversation.extend(tool_results_for_llm)

            # Max tool calls reached — return escalate
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return BaselineResult(
                case_id=case.case_id,
                decision="escalate",
                authorization_tier=2,
                approval_required=True,
                reason="Max tool calls reached without completing decision",
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            logger.exception("Baseline agent failed for case %s: %s", case.case_id, exc)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return BaselineResult(
                case_id=case.case_id,
                decision="escalate",
                authorization_tier=2,
                approval_required=True,
                reason=f"Agent failed: {exc}",
                execution_time_ms=elapsed_ms,
                failure_reason=str(exc),
            )

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        ctx: ToolContext,
    ) -> ToolResult:
        """Execute a tool via the registry."""
        return await self._registry.call_tool(tool_name, arguments, ctx)

    @staticmethod
    def _parse_decision(content: str) -> Dict[str, Any]:
        """Parse the decision JSON from the LLM's text response."""
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                return json.loads(json_str)
            return {
                "decision": "escalate",
                "authorization_tier": 2,
                "approval_required": True,
                "reason": "Could not parse decision from response",
            }
        except (json.JSONDecodeError, ValueError):
            return {
                "decision": "escalate",
                "authorization_tier": 2,
                "approval_required": True,
                "reason": "Could not parse decision from response",
            }

"""OpsPilot — Anthropic LLM provider.

Uses the anthropic Python SDK to call Claude models.
Implements the LLMProvider interface. Fallback-ready.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from backend.app.config import settings
from backend.app.llm.provider import (
    LLMProvider,
    LLMResponse,
    TokenUsage,
    ToolCallRequest,
)

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens
_COST_TABLE = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
}


def _estimate_cost(model: str, usage: TokenUsage) -> float:
    """Estimate USD cost from token counts."""
    rates = _COST_TABLE.get(model, {"input": 3.00, "output": 15.00})
    input_cost = (usage.prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (usage.completion_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


def _convert_tools_to_anthropic(tools: List[dict]) -> List[dict]:
    """Convert OpenAI-style tool definitions to Anthropic format.

    Anthropic uses a slightly different schema:
    - name, description, input_schema (instead of parameters)
    """
    converted = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            converted.append(
                {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        else:
            converted.append(tool)
    return converted


class AnthropicProvider(LLMProvider):
    """Anthropic API provider using the official SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or "claude-sonnet-4-20250514"

    async def generate(
        self,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]] = None,
        structured_output: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        """Generate a response via Anthropic API."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # Anthropic uses separate system parameter
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }

        # Convert tools to Anthropic format
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        try:
            response = await client.messages.create(**kwargs)
        except Exception as exc:
            logger.exception("Anthropic API call failed: %s", exc)
            raise

        # Extract text content
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        cost = _estimate_cost(self._model, usage)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider="anthropic",
            model=self._model,
            cost_usd=cost,
        )

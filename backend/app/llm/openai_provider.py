"""OpsPilot — OpenAI LLM provider.

Uses the openai Python SDK to call GPT-4o (or configured model).
Implements the LLMProvider interface.
"""

from __future__ import annotations

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

# Approximate cost per 1M tokens (as of 2024)
_COST_TABLE = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def _estimate_cost(model: str, usage: TokenUsage) -> float:
    """Estimate USD cost from token counts."""
    rates = _COST_TABLE.get(model, _COST_TABLE["gpt-4o"])
    input_cost = (usage.prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (usage.completion_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


class OpenAIProvider(LLMProvider):
    """OpenAI API provider using the official SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.llm_model

    async def generate(
        self,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]] = None,
        structured_output: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        """Generate a response via OpenAI API."""
        import openai

        client = openai.AsyncOpenAI(api_key=self._api_key)

        # Build message list with system prompt
        full_messages = [{"role": "system", "content": system}] + messages

        # Build request kwargs
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": full_messages,
            "temperature": 0.2,
        }

        # Add tools if provided
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Add structured output if requested
        if structured_output is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": structured_output.__name__,
                    "strict": True,
                    "schema": structured_output.model_json_schema(),
                },
            }

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.exception("OpenAI API call failed: %s", exc)
            raise

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
        )

        # Parse tool calls
        tool_calls = []
        if choice.message.tool_calls:
            import json

            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        cost = _estimate_cost(self._model, usage)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider="openai",
            model=self._model,
            cost_usd=cost,
        )

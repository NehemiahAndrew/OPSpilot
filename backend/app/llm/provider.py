"""OpsPilot — LLM provider abstraction.

All LLM calls go through this interface. The Context Assembly Agent and
Decision Agent never call OpenAI/Anthropic directly — they always go
through an LLMProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Type

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Tracks token consumption for cost attribution."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCallRequest(BaseModel):
    """Represents a tool call requested by the LLM."""

    id: str = Field(default="", description="Tool call ID from the LLM")
    name: str = Field(..., description="Tool function name")
    arguments: dict = Field(default_factory=dict, description="Tool arguments as dict")


class LLMResponse(BaseModel):
    """Uniform response from any LLM provider."""

    content: str = Field(default="", description="Text content from the model")
    tool_calls: List[ToolCallRequest] = Field(
        default_factory=list, description="Tool calls requested by the model"
    )
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token usage")
    provider: str = Field(..., description="Provider name (openai, anthropic)")
    model: str = Field(..., description="Model name used")
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD")


class LLMProvider(ABC):
    """Abstract base for LLM providers.

    Both OpenAI and Anthropic providers implement this interface.
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]] = None,
        structured_output: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            messages: Conversation messages (role/content format).
            system: System prompt (always provided).
            tools: Optional tool definitions in OpenAI function-calling format.
            structured_output: Optional Pydantic model for structured responses.

        Returns:
            LLMResponse with content, tool_calls, usage, and cost info.
        """
        ...

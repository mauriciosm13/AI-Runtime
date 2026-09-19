"""Port for estimating input token counts before a provider call."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from ai_runtime.domain.generation import Message, ToolDefinition


@runtime_checkable
class TokenCounter(Protocol):
    """Estimate the input tokens a request will consume. Estimates, not billing figures."""

    def count_message(self, message: Message) -> int:
        """Return the estimated tokens for one message."""
        ...

    def count_tools(self, tools: Sequence[ToolDefinition]) -> int:
        """Return the estimated tokens for declared tool definitions."""
        ...

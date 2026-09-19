"""Conservative character-based token estimator (no provider tokenizer dependency)."""

import json
import math
from collections.abc import Sequence
from ai_runtime.domain.generation import Message, ToolDefinition

_CHARS_PER_TOKEN = 3
_MESSAGE_OVERHEAD_TOKENS = 4


def _estimate(text: str) -> int:
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


class HeuristicTokenCounter:
    """Estimate tokens as ``ceil(chars / 3)`` plus a fixed per-message overhead.

    Three characters per token deliberately over-counts typical English text so
    budget checks lean toward rejecting rather than overflowing the provider.
    """

    def count_message(self, message: Message) -> int:
        """Return the estimated tokens for one message, including tool call arguments."""
        total = _MESSAGE_OVERHEAD_TOKENS + _estimate(message.content)
        for call in message.tool_calls:
            total += _estimate(call.name) + _estimate(call.arguments)
        return total

    def count_tools(self, tools: Sequence[ToolDefinition]) -> int:
        """Return the estimated tokens for declared tool definitions."""
        return sum(_estimate(tool.name + tool.description + json.dumps(tool.parameters, sort_keys=True)) for tool in tools)

"""Enforce a context budget on assembled messages, with opt-in truncation."""

from collections.abc import Mapping, Sequence
from ai_runtime.domain.context import ContextLimitExceededError, ContextPolicy
from ai_runtime.domain.generation import Message, MessageRole, ToolDefinition
from ai_runtime.domain.routing import DEFAULT_FAILOVER_CATALOG, DEFAULT_MODEL_CONTEXT_WINDOWS
from ai_runtime.ports.token_counter import TokenCounter


def _group_units(messages: Sequence[Message]) -> list[list[int]]:
    """Group non-system message indexes so a tool call and its results are never split."""
    units: list[list[int]] = []
    for index, message in enumerate(messages):
        if message.role is MessageRole.SYSTEM:
            continue
        if message.role is MessageRole.TOOL and units and messages[units[-1][0]].tool_calls:
            units[-1].append(index)
        else:
            units.append([index])
    return units


class BuildContext:
    """Check assembled messages against the smallest applicable context window.

    The budget is the smallest window across the requested model and, when
    failover is enabled, its failover candidates, minus ``max_output_tokens``,
    further capped by ``ContextPolicy.max_input_tokens``. System messages and
    the most recent turn are never dropped.
    """

    def __init__(
        self,
        token_counter: TokenCounter,
        *,
        failover_enabled: bool,
        context_windows: Mapping[str, int] = DEFAULT_MODEL_CONTEXT_WINDOWS,
        failover_catalog: Mapping[str, tuple[str, ...]] = DEFAULT_FAILOVER_CATALOG,
    ) -> None:
        self._counter = token_counter
        self._failover_enabled = failover_enabled
        self._windows = context_windows
        self._failover_catalog = failover_catalog

    def execute(
        self,
        *,
        model: str,
        messages: tuple[Message, ...],
        tools: Sequence[ToolDefinition],
        max_output_tokens: int | None,
        policy: ContextPolicy,
    ) -> tuple[Message, ...]:
        """Return messages that fit the budget, or raise ``ContextLimitExceededError``."""
        budget = self._budget(model, max_output_tokens, policy)
        if budget is None:
            return messages
        tools_cost = self._counter.count_tools(tools)
        costs = [self._counter.count_message(message) for message in messages]
        total = tools_cost + sum(costs)
        if total <= budget:
            return messages
        if not policy.truncate:
            raise ContextLimitExceededError()
        dropped: set[int] = set()
        units = _group_units(messages)
        for unit in units[:-1]:
            if total <= budget:
                break
            dropped.update(unit)
            total -= sum(costs[index] for index in unit)
        if total > budget:
            raise ContextLimitExceededError()
        return tuple(message for index, message in enumerate(messages) if index not in dropped)

    def _budget(self, model: str, max_output_tokens: int | None, policy: ContextPolicy) -> int | None:
        candidates = [model]
        if self._failover_enabled:
            candidates.extend(self._failover_catalog.get(model, ()))
        windows = [self._windows[name] for name in candidates if name in self._windows]
        limits: list[int] = []
        if windows:
            limits.append(min(windows) - (max_output_tokens or 0))
        if policy.max_input_tokens is not None:
            limits.append(policy.max_input_tokens)
        if not limits:
            return None
        return max(min(limits), 0)

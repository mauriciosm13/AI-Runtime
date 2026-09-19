"""BuildContext use case tests."""

from collections.abc import Sequence
import pytest
from ai_runtime.application.context.build_context import BuildContext
from ai_runtime.domain.context import ContextLimitExceededError, ContextPolicy
from ai_runtime.domain.generation import Message, MessageRole, ToolCall, ToolDefinition
from ai_runtime.infrastructure.tokens import HeuristicTokenCounter


class FlatCounter:
    """Deterministic counter: every message costs its content length in tokens."""

    def count_message(self, message: Message) -> int:
        return len(message.content)

    def count_tools(self, tools: Sequence[ToolDefinition]) -> int:
        return 0


def _msg(role: MessageRole, content: str) -> Message:
    return Message(role=role, content=content)


def _builder(*, failover: bool = False, windows: dict[str, int] | None = None) -> BuildContext:
    return BuildContext(
        FlatCounter(),
        failover_enabled=failover,
        context_windows=windows or {"m": 100, "small": 40},
        failover_catalog={"m": ("small",)},
    )


def _run(
    builder: BuildContext,
    messages: tuple[Message, ...],
    policy: ContextPolicy,
    *,
    model: str = "m",
    max_out: int | None = None,
) -> tuple[Message, ...]:
    return builder.execute(model=model, messages=messages, tools=[], max_output_tokens=max_out, policy=policy)


def test_within_budget_returns_messages_unchanged() -> None:
    messages = (_msg(MessageRole.USER, "x" * 50),)
    assert _run(_builder(), messages, ContextPolicy()) == messages


def test_over_budget_is_rejected_by_default() -> None:
    with pytest.raises(ContextLimitExceededError):
        _run(_builder(), (_msg(MessageRole.USER, "x" * 101),), ContextPolicy())


def test_max_output_tokens_reduces_budget() -> None:
    with pytest.raises(ContextLimitExceededError):
        _run(_builder(), (_msg(MessageRole.USER, "x" * 60),), ContextPolicy(), max_out=50)


def test_policy_max_input_tokens_caps_budget() -> None:
    with pytest.raises(ContextLimitExceededError):
        _run(_builder(), (_msg(MessageRole.USER, "x" * 30),), ContextPolicy(max_input_tokens=20))


def test_failover_uses_smallest_window() -> None:
    messages = (_msg(MessageRole.USER, "x" * 60),)
    assert _run(_builder(failover=False), messages, ContextPolicy()) == messages
    with pytest.raises(ContextLimitExceededError):
        _run(_builder(failover=True), messages, ContextPolicy())


def test_unknown_model_without_policy_budget_is_not_enforced() -> None:
    messages = (_msg(MessageRole.USER, "x" * 10_000),)
    assert _run(_builder(), messages, ContextPolicy(), model="unknown") == messages


def test_truncate_drops_oldest_non_system_first_and_keeps_system_and_latest() -> None:
    system = _msg(MessageRole.SYSTEM, "s" * 10)
    old_user = _msg(MessageRole.USER, "a" * 35)
    old_assistant = _msg(MessageRole.ASSISTANT, "b" * 30)
    latest = _msg(MessageRole.USER, "c" * 30)
    result = _run(_builder(), (system, old_user, old_assistant, latest), ContextPolicy(truncate=True))
    assert result == (system, old_assistant, latest)


def test_truncate_fails_when_system_plus_latest_do_not_fit() -> None:
    system = _msg(MessageRole.SYSTEM, "s" * 80)
    latest = _msg(MessageRole.USER, "c" * 30)
    with pytest.raises(ContextLimitExceededError):
        _run(_builder(), (system, latest), ContextPolicy(truncate=True))


def test_truncate_never_splits_tool_call_from_tool_results() -> None:
    call = Message(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=(ToolCall(id="c1", name="f", arguments="{}"),),
    )
    result_message = Message(role=MessageRole.TOOL, content="r" * 60, tool_call_id="c1")
    latest = _msg(MessageRole.USER, "c" * 50)
    kept = _run(_builder(), (call, result_message, latest), ContextPolicy(truncate=True))
    assert kept == (latest,)


def test_heuristic_counter_over_counts_conservatively() -> None:
    counter = HeuristicTokenCounter()
    assert counter.count_message(_msg(MessageRole.USER, "x" * 9)) == 4 + 3
    tool = ToolDefinition(name="f", description="d", parameters={"a": 1})
    assert counter.count_tools([tool]) > 0
    assert counter.count_tools([]) == 0

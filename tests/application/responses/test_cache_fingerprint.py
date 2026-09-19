"""Unit tests for the response-cache fingerprint helper."""

from ai_runtime.application.responses.cache_fingerprint import fingerprint_generation_request
from ai_runtime.domain.generation import GenerationRequest, Message, MessageRole, ToolDefinition


def _request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "model": "gpt-test",
        "messages": (Message(role=MessageRole.USER, content="Hello"),),
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def test_fingerprint_is_stable_for_identical_requests() -> None:
    """The same request fields produce the same digest."""
    assert fingerprint_generation_request(_request()) == fingerprint_generation_request(_request())


def test_fingerprint_changes_when_message_changes() -> None:
    """A different message yields a different digest."""
    left = fingerprint_generation_request(_request())
    right = fingerprint_generation_request(_request(messages=(Message(role=MessageRole.USER, content="Other"),)))
    assert left != right


def test_fingerprint_includes_tools() -> None:
    """Declared tools are part of the cache key."""
    left = fingerprint_generation_request(_request())
    right = fingerprint_generation_request(_request(tools=(ToolDefinition(name="get_weather", parameters={"type": "object"}),)))
    assert left != right


def test_fingerprint_ignores_cache_flag() -> None:
    """The opt-in flag is not part of the content hash."""
    left = fingerprint_generation_request(_request())
    right = fingerprint_generation_request(_request(cache=True))
    assert left == right

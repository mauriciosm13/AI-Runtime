"""Unit tests for provider-neutral generation domain contracts."""

import pytest
from ai_runtime.domain.generation import DomainValidationError, GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage


def test_valid_message_request_and_response() -> None:
    """Valid Message, GenerationRequest, and GenerationResponse construct cleanly."""
    user = Message(role=MessageRole.USER, content="Hello")
    request = GenerationRequest(
        model="gpt-test",
        messages=(user,),
        temperature=0.7,
        max_output_tokens=128,
    )
    usage = TokenUsage(input_tokens=10, output_tokens=5)
    response = GenerationResponse(
        id="resp_1",
        model="gpt-test",
        output=Message(role=MessageRole.ASSISTANT, content="Hi"),
        usage=usage,
    )
    assert request.model == "gpt-test"
    assert request.messages == (user,)
    assert request.temperature == 0.7
    assert request.max_output_tokens == 128
    assert response.id == "resp_1"
    assert response.output.role is MessageRole.ASSISTANT
    assert response.usage is usage


def test_token_usage_total_tokens() -> None:
    """TokenUsage.total_tokens sums input and output counts."""
    usage = TokenUsage(input_tokens=12, output_tokens=8)
    assert usage.total_tokens == 20


def test_rejects_blank_model() -> None:
    """Empty or whitespace-only model names are rejected."""
    message = Message(role=MessageRole.USER, content="Hello")
    with pytest.raises(DomainValidationError, match="model"):
        GenerationRequest(model="   ", messages=(message,))


def test_rejects_empty_messages() -> None:
    """A GenerationRequest must include at least one message."""
    with pytest.raises(DomainValidationError, match="messages"):
        GenerationRequest(model="gpt-test", messages=())


def test_rejects_temperature_out_of_range() -> None:
    """temperature, when provided, must be between 0 and 2 inclusive."""
    message = Message(role=MessageRole.USER, content="Hello")
    with pytest.raises(DomainValidationError, match="temperature"):
        GenerationRequest(model="gpt-test", messages=(message,), temperature=2.5)
    with pytest.raises(DomainValidationError, match="temperature"):
        GenerationRequest(model="gpt-test", messages=(message,), temperature=-0.1)


def test_rejects_invalid_max_output_tokens() -> None:
    """max_output_tokens, when provided, must be greater than zero."""
    message = Message(role=MessageRole.USER, content="Hello")
    with pytest.raises(DomainValidationError, match="max_output_tokens"):
        GenerationRequest(model="gpt-test", messages=(message,), max_output_tokens=0)
    with pytest.raises(DomainValidationError, match="max_output_tokens"):
        GenerationRequest(model="gpt-test", messages=(message,), max_output_tokens=-1)


def test_rejects_negative_token_counts() -> None:
    """TokenUsage counters must not be negative."""
    with pytest.raises(DomainValidationError, match="input_tokens"):
        TokenUsage(input_tokens=-1, output_tokens=0)
    with pytest.raises(DomainValidationError, match="output_tokens"):
        TokenUsage(input_tokens=0, output_tokens=-1)


def test_rejects_non_assistant_output() -> None:
    """GenerationResponse.output must use the assistant role."""
    with pytest.raises(DomainValidationError, match="assistant"):
        GenerationResponse(
            id="resp_1",
            model="gpt-test",
            output=Message(role=MessageRole.USER, content="not assistant"),
        )

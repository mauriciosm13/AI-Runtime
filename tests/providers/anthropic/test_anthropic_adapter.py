"""Unit tests for the Anthropic ModelProvider adapter with simulated HTTP."""

import asyncio
import json
from collections.abc import Callable
import httpx
import pytest
from ai_runtime.domain.generation import GenerationRequest, Message, MessageRole
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.providers.anthropic import AnthropicModelProvider, AnthropicProviderError

_API_KEY = "test-api-key"
_BASE_URL = "https://api.anthropic.test"


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Build an AsyncClient whose transport never touches the network."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sample_request(
    *,
    temperature: float | None = 0.7,
    max_output_tokens: int | None = 128,
) -> GenerationRequest:
    """Build a GenerationRequest used across adapter tests."""
    return GenerationRequest(
        model="claude-3-5-sonnet-20241022",
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be brief."),
            Message(role=MessageRole.USER, content="Hello"),
        ),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _success_payload() -> dict[str, object]:
    """Minimal valid Anthropic Messages success body."""
    return {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Hi there"}],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 4,
        },
    }


def test_anthropic_provider_satisfies_model_provider_protocol() -> None:
    """AnthropicModelProvider is structurally a ModelProvider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    assert isinstance(provider, ModelProvider)


def test_generate_maps_request_body_to_anthropic_messages() -> None:
    """GenerationRequest fields map to the Messages JSON body."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request()))
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_BASE_URL}/v1/messages"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["x-api-key"] == _API_KEY
    assert headers["anthropic-version"] == "2023-06-01"
    assert captured["body"] == {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 128,
        "system": "Be brief.",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
    }


def test_generate_uses_default_max_tokens_when_unset() -> None:
    """Anthropic requires max_tokens; adapter supplies a default when omitted."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request(temperature=None, max_output_tokens=None)))
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["max_tokens"] == 1024
    assert "temperature" not in body


def test_generate_maps_anthropic_response_to_generation_response() -> None:
    """A valid Anthropic payload becomes GenerationResponse with TokenUsage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.id == "msg_123"
    assert response.model == "claude-3-5-sonnet-20241022"
    assert response.output.role is MessageRole.ASSISTANT
    assert response.output.content == "Hi there"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 14


@pytest.mark.parametrize("status_code", [401, 500])
def test_http_error_status_raises_anthropic_provider_error(status_code: int) -> None:
    """Non-success HTTP statuses raise AnthropicProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"type": "error", "error": {"message": "failed"}})

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(AnthropicProviderError, match=str(status_code)):
        asyncio.run(provider.generate(_sample_request()))


def test_malformed_json_raises_anthropic_provider_error() -> None:
    """Non-JSON success bodies raise AnthropicProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(AnthropicProviderError, match="JSON"):
        asyncio.run(provider.generate(_sample_request()))


def test_missing_content_raises_anthropic_provider_error() -> None:
    """A 200 response without text content raises AnthropicProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_123",
                "model": "claude-3-5-sonnet-20241022",
                "content": [],
            },
        )

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(AnthropicProviderError, match="content"):
        asyncio.run(provider.generate(_sample_request()))


def test_falls_back_to_request_model_when_response_model_missing() -> None:
    """Missing model in the provider payload uses the request model."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_payload()
        del payload["model"]
        return httpx.Response(200, json=payload)

    provider = AnthropicModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.model == "claude-3-5-sonnet-20241022"

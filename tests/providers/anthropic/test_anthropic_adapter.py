"""Unit tests for the Anthropic ModelProvider adapter with simulated HTTP."""

import asyncio
import json
from collections.abc import Callable
import httpx
import pytest
from ai_runtime.domain.generation import GenerationDelta, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import Message, MessageRole, ToolDefinition
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


def _anthropic_sse_body() -> bytes:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_123",
                    "model": "claude-3-5-sonnet-20241022",
                    "usage": {"input_tokens": 10},
                },
            },
        ),
        ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}),
        ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " there"}}),
        ("message_delta", {"type": "message_delta", "usage": {"output_tokens": 4}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events).encode()


def _collect_stream(provider: AnthropicModelProvider, request: GenerationRequest) -> list[object]:
    async def _run() -> list[object]:
        return [event async for event in provider.stream(request)]

    return asyncio.run(_run())


def test_stream_maps_anthropic_sse_events_to_domain_events() -> None:
    """Anthropic stream events assemble into a completed GenerationResponse with usage."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, content=_anthropic_sse_body(), headers={"Content-Type": "text/event-stream"})

    provider = AnthropicModelProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    events = _collect_stream(provider, _sample_request())
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["stream"] is True
    assert isinstance(events[0], GenerationDelta)
    assert events[0].content == "Hi"
    assert isinstance(events[-1], GenerationResponse)
    assert events[-1].output.content == "Hi there"
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 14


def test_stream_http_error_status_sets_retryable_flag() -> None:
    """Streaming HTTP failures classify retryable vs non-retryable errors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "failed"}})

    provider = AnthropicModelProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    with pytest.raises(AnthropicProviderError, match="500") as exc_info:
        _collect_stream(provider, _sample_request())
    assert exc_info.value.retryable is True


def test_generate_maps_tools_and_tool_use_blocks() -> None:
    """Tool definitions and tool_use blocks map through Anthropic Messages."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        payload = _success_payload()
        payload["content"] = [{"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"city": "Lisbon"}}]
        return httpx.Response(200, json=payload)

    provider = AnthropicModelProvider(api_key=_API_KEY, http_client=_make_client(handler), base_url=_BASE_URL)
    request = GenerationRequest(
        model="claude-3-5-sonnet-20241022",
        messages=(Message(role=MessageRole.USER, content="Weather?"),),
        tools=(ToolDefinition(name="get_weather", description="Weather", parameters={"type": "object"}),),
    )
    response = asyncio.run(provider.generate(request))
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["tools"][0]["name"] == "get_weather"
    assert response.output.tool_calls[0].id == "call_1"
    assert response.output.tool_calls[0].arguments == '{"city":"Lisbon"}'

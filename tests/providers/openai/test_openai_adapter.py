"""Unit tests for the OpenAI ModelProvider adapter with simulated HTTP."""

import asyncio
import json
from collections.abc import Callable
import httpx
import pytest
from ai_runtime.domain.generation import GenerationRequest, Message, MessageRole
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.providers.openai import OpenAIModelProvider, OpenAIProviderError

_API_KEY = "test-api-key"
_BASE_URL = "https://api.openai.test/v1"


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
        model="gpt-4o-mini",
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be brief."),
            Message(role=MessageRole.USER, content="Hello"),
        ),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _success_payload() -> dict[str, object]:
    """Minimal valid OpenAI Chat Completions success body."""
    return {
        "id": "chatcmpl-123",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hi there",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
        },
    }


def test_openai_provider_satisfies_model_provider_protocol() -> None:
    """OpenAIModelProvider is structurally a ModelProvider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    assert isinstance(provider, ModelProvider)


def test_generate_maps_request_body_to_openai_chat_completions() -> None:
    """GenerationRequest fields map to the Chat Completions JSON body."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request()))
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_BASE_URL}/chat/completions"
    assert captured["body"] == {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hello"},
        ],
        "temperature": 0.7,
        "max_tokens": 128,
    }


def test_generate_maps_openai_response_to_generation_response() -> None:
    """A valid OpenAI payload becomes GenerationResponse with TokenUsage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.id == "chatcmpl-123"
    assert response.model == "gpt-4o-mini"
    assert response.output.role is MessageRole.ASSISTANT
    assert response.output.content == "Hi there"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 14


def test_optional_fields_omitted_from_request_body_when_none() -> None:
    """temperature and max_output_tokens are omitted when unset."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request(temperature=None, max_output_tokens=None)))
    body = captured["body"]
    assert isinstance(body, dict)
    assert "temperature" not in body
    assert "max_tokens" not in body


def test_authorization_bearer_header_is_sent() -> None:
    """Requests include Authorization: Bearer <api_key>."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["content_type"] = request.headers["Content-Type"]
        return httpx.Response(200, json=_success_payload())

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request()))
    assert captured["authorization"] == f"Bearer {_API_KEY}"
    assert captured["content_type"] == "application/json"


@pytest.mark.parametrize("status_code", [401, 500])
def test_http_error_status_raises_openai_provider_error(status_code: int) -> None:
    """Non-success HTTP statuses raise OpenAIProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "failed"}})

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(OpenAIProviderError, match=str(status_code)):
        asyncio.run(provider.generate(_sample_request()))


def test_malformed_success_payload_without_choices_raises() -> None:
    """A 200 response without choices raises OpenAIProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "chatcmpl-123", "model": "gpt-4o-mini", "choices": []},
        )

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(OpenAIProviderError, match="choices"):
        asyncio.run(provider.generate(_sample_request()))


def test_falls_back_to_request_model_when_response_model_missing() -> None:
    """Missing model in the provider payload uses the request model."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_payload()
        del payload["model"]
        return httpx.Response(200, json=payload)

    provider = OpenAIModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.model == "gpt-4o-mini"

"""Unit tests for the Gemini ModelProvider adapter with simulated HTTP."""

import asyncio
import json
from collections.abc import Callable
import httpx
import pytest
from ai_runtime.domain.generation import GenerationRequest, Message, MessageRole
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.providers.gemini import GeminiModelProvider, GeminiProviderError

_API_KEY = "test-api-key"
_BASE_URL = "https://generativelanguage.test"
_MODEL = "gemini-2.5-flash"


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
        model=_MODEL,
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be brief."),
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi"),
            Message(role=MessageRole.USER, content="Continue"),
        ),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _success_payload() -> dict[str, object]:
    """Minimal valid Gemini generateContent success body."""
    return {
        "responseId": "resp_123",
        "modelVersion": _MODEL,
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": "Hi there"}],
                },
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 4,
        },
    }


def test_gemini_provider_satisfies_model_provider_protocol() -> None:
    """GeminiModelProvider is structurally a ModelProvider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    assert isinstance(provider, ModelProvider)


def test_generate_maps_request_body_to_gemini_generate_content() -> None:
    """GenerationRequest fields map to the generateContent JSON body."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request()))
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_BASE_URL}/v1beta/models/{_MODEL}:generateContent"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["x-goog-api-key"] == _API_KEY
    assert captured["body"] == {
        "systemInstruction": {"parts": [{"text": "Be brief."}]},
        "contents": [
            {"role": "user", "parts": [{"text": "Hello"}]},
            {"role": "model", "parts": [{"text": "Hi"}]},
            {"role": "user", "parts": [{"text": "Continue"}]},
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 128,
        },
    }


def test_generate_omits_optional_generation_config_when_unset() -> None:
    """Unset temperature and max_output_tokens are omitted from the body."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_success_payload())

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    asyncio.run(provider.generate(_sample_request(temperature=None, max_output_tokens=None)))
    body = captured["body"]
    assert isinstance(body, dict)
    assert "generationConfig" not in body
    assert body["systemInstruction"] == {"parts": [{"text": "Be brief."}]}


def test_generate_maps_gemini_response_to_generation_response() -> None:
    """A valid Gemini payload becomes GenerationResponse with TokenUsage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.id == "resp_123"
    assert response.model == _MODEL
    assert response.output.role is MessageRole.ASSISTANT
    assert response.output.content == "Hi there"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 4
    assert response.usage.total_tokens == 14


def test_generate_skips_thought_parts_in_output() -> None:
    """Thought parts are excluded from the assistant output string."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "responseId": "resp_123",
                "modelVersion": _MODEL,
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"thought": True, "text": "internal reasoning"},
                                {"text": "Visible answer"},
                            ],
                        },
                    }
                ],
            },
        )

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.output.content == "Visible answer"


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(401, False), (429, True), (500, True), (503, True)],
)
def test_http_error_status_sets_retryable_flag(status_code: int, retryable: bool) -> None:
    """HTTP failures classify retryable vs non-retryable provider errors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "failed"}})

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(GeminiProviderError, match=str(status_code)) as exc_info:
        asyncio.run(provider.generate(_sample_request()))
    assert exc_info.value.retryable is retryable
    assert exc_info.value.status_code == status_code


def test_malformed_json_raises_gemini_provider_error() -> None:
    """Non-JSON success bodies raise GeminiProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(GeminiProviderError, match="JSON"):
        asyncio.run(provider.generate(_sample_request()))


def test_missing_candidates_raises_gemini_provider_error() -> None:
    """A 200 response without candidates raises GeminiProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"responseId": "resp_123", "modelVersion": _MODEL, "candidates": []},
        )

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    with pytest.raises(GeminiProviderError, match="candidates"):
        asyncio.run(provider.generate(_sample_request()))


def test_falls_back_to_request_model_when_model_version_missing() -> None:
    """Missing modelVersion in the provider payload uses the request model."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _success_payload()
        del payload["modelVersion"]
        return httpx.Response(200, json=payload)

    provider = GeminiModelProvider(
        api_key=_API_KEY,
        http_client=_make_client(handler),
        base_url=_BASE_URL,
    )
    response = asyncio.run(provider.generate(_sample_request()))
    assert response.model == _MODEL

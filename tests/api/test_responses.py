"""POST /v1/responses endpoint tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_create_response
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.providers.openai.errors import ProviderError


class FakeModelProvider:
    """Deterministic provider fake for API tests."""

    def __init__(self, response: GenerationResponse | None = None, error: Exception | None = None) -> None:
        self.requests: list[GenerationRequest] = []
        self._response = response
        self._error = error

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _success_response() -> GenerationResponse:
    return GenerationResponse(
        id="resp_abc",
        model="gpt-4o-mini",
        output=Message(role=MessageRole.ASSISTANT, content="Hi"),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _request_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    body.update(overrides)
    return body


def _client_with_provider(provider: FakeModelProvider) -> TestClient:
    app = create_app()

    async def override_create_response() -> CreateResponse:
        return CreateResponse(provider)

    app.dependency_overrides[get_create_response] = override_create_response
    return TestClient(app)


def test_post_responses_returns_200_with_expected_payload() -> None:
    """POST /v1/responses returns the serialized provider-neutral response."""
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 200
    assert response.json() == {
        "id": "resp_abc",
        "model": "gpt-4o-mini",
        "output": {"role": "assistant", "content": "Hi"},
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }
    assert provider.requests == [
        GenerationRequest(
            model="gpt-4o-mini",
            messages=(Message(role=MessageRole.USER, content="Hello"),),
        )
    ]


def test_post_responses_accepts_optional_generation_fields() -> None:
    """Optional temperature and max_output_tokens are forwarded to the use case."""
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider)
    response = client.post(
        "/v1/responses",
        json=_request_body(temperature=0.7, max_output_tokens=256),
    )
    assert response.status_code == 200
    assert provider.requests == [
        GenerationRequest(
            model="gpt-4o-mini",
            messages=(Message(role=MessageRole.USER, content="Hello"),),
            temperature=0.7,
            max_output_tokens=256,
        )
    ]


def test_post_responses_returns_422_for_empty_messages() -> None:
    """An empty messages array is rejected before the use case runs."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(messages=[]))
    assert response.status_code == 422


def test_post_responses_returns_422_for_invalid_role() -> None:
    """Unknown message roles fail request validation."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        json=_request_body(messages=[{"role": "invalid", "content": "Hello"}]),
    )
    assert response.status_code == 422


def test_post_responses_returns_422_for_blank_content() -> None:
    """Blank message content fails request validation."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        json=_request_body(messages=[{"role": "user", "content": "   "}]),
    )
    assert response.status_code == 422


def test_post_responses_returns_422_for_temperature_out_of_range() -> None:
    """Temperature outside the supported range is rejected at the HTTP boundary."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(temperature=3.0))
    assert response.status_code == 422


def test_post_responses_returns_502_for_provider_failure() -> None:
    """Provider failures are mapped to 502 Bad Gateway."""
    provider = FakeModelProvider(error=ProviderError("generation failed"))
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 502
    assert response.json() == {"detail": "generation failed"}


def test_post_responses_is_documented_in_openapi() -> None:
    """POST /v1/responses appears in the generated OpenAPI schema."""
    schema = create_app().openapi()
    paths = schema["paths"]
    assert "/v1/responses" in paths
    assert "post" in paths["/v1/responses"]


def test_create_app_stores_http_client_in_lifespan() -> None:
    """The application lifespan exposes a shared httpx client for provider wiring."""
    captured: dict[str, httpx.AsyncClient] = {}

    @asynccontextmanager
    async def inspect_lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient() as http_client:
            app.state.http_client = http_client
            captured["client"] = http_client
            yield

    app = create_app()
    app.router.lifespan_context = inspect_lifespan
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert isinstance(captured["client"], httpx.AsyncClient)

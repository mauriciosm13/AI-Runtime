"""POST /v1/responses endpoint tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ai_runtime.api.app import create_app
from ai_runtime.api.dependencies import get_create_response
from ai_runtime.api.middleware.request_context import REQUEST_ID_HEADER
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


def _success_response(*, usage: TokenUsage | None = TokenUsage(input_tokens=10, output_tokens=5)) -> GenerationResponse:
    return GenerationResponse(
        id="resp_abc",
        model="gpt-4o-mini",
        output=Message(role=MessageRole.ASSISTANT, content="Hi"),
        usage=usage,
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
    assert REQUEST_ID_HEADER in response.headers
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


@pytest.mark.parametrize("temperature", [0.0, 2.0])
def test_post_responses_accepts_temperature_boundaries(temperature: float) -> None:
    """Temperature values at the inclusive 0.0 and 2.0 bounds are accepted."""
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body(temperature=temperature))
    assert response.status_code == 200
    assert provider.requests[0].temperature == temperature


def test_post_responses_forwards_multi_turn_messages_in_order() -> None:
    """System, user, and assistant messages are forwarded in request order."""
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider)
    messages = [
        {"role": "system", "content": "Be brief"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Continue"},
    ]
    response = client.post("/v1/responses", json=_request_body(messages=messages))
    assert response.status_code == 200
    assert provider.requests == [
        GenerationRequest(
            model="gpt-4o-mini",
            messages=(
                Message(role=MessageRole.SYSTEM, content="Be brief"),
                Message(role=MessageRole.USER, content="Hello"),
                Message(role=MessageRole.ASSISTANT, content="Hi"),
                Message(role=MessageRole.USER, content="Continue"),
            ),
        )
    ]


def test_post_responses_returns_null_usage_when_provider_omits_it() -> None:
    """When the provider omits usage, the HTTP payload returns usage as null."""
    provider = FakeModelProvider(response=_success_response(usage=None))
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 200
    assert response.json() == {
        "id": "resp_abc",
        "model": "gpt-4o-mini",
        "output": {"role": "assistant", "content": "Hi"},
        "usage": None,
    }


def test_post_responses_echoes_client_request_id_on_success() -> None:
    """A valid client X-Request-ID is echoed on a successful responses call."""
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={REQUEST_ID_HEADER: "client-responses-1"},
    )
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "client-responses-1"


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


def test_post_responses_returns_422_for_empty_content() -> None:
    """Empty message content fails schema validation before the use case runs."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        json=_request_body(messages=[{"role": "user", "content": ""}]),
    )
    assert response.status_code == 422


def test_post_responses_returns_422_for_temperature_out_of_range() -> None:
    """Temperature outside the supported range is rejected at the HTTP boundary."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(temperature=3.0))
    assert response.status_code == 422


def test_post_responses_returns_422_for_negative_temperature() -> None:
    """Negative temperature is rejected at the HTTP boundary."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(temperature=-0.1))
    assert response.status_code == 422


@pytest.mark.parametrize("max_output_tokens", [0, -1])
def test_post_responses_returns_422_for_non_positive_max_output_tokens(max_output_tokens: int) -> None:
    """max_output_tokens must be greater than zero."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(max_output_tokens=max_output_tokens))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"messages": [{"role": "user", "content": "Hello"}]},
        {"model": "", "messages": [{"role": "user", "content": "Hello"}]},
        {"model": "   ", "messages": [{"role": "user", "content": "Hello"}]},
    ],
)
def test_post_responses_returns_422_for_invalid_model(body: dict[str, Any]) -> None:
    """Missing, empty, or blank model values are rejected."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=body)
    assert response.status_code == 422


def test_post_responses_returns_422_for_missing_messages() -> None:
    """Omitting messages fails request validation."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json={"model": "gpt-4o-mini"})
    assert response.status_code == 422


def test_post_responses_returns_422_for_unknown_fields() -> None:
    """Unknown body fields are rejected because the schema forbids extras."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(stream=True))
    assert response.status_code == 422


def test_post_responses_returns_422_for_missing_body() -> None:
    """A request without a JSON body is rejected."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses")
    assert response.status_code == 422


def test_post_responses_returns_422_for_invalid_json() -> None:
    """Malformed JSON is rejected with a validation error."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_post_responses_returns_422_for_wrong_content_type() -> None:
    """Non-JSON content types are rejected at the HTTP boundary."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        content=b'{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 422


def test_post_responses_returns_422_for_wrong_field_types() -> None:
    """Type mismatches in generation options fail request validation."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(temperature="hot"))
    assert response.status_code == 422


def test_post_responses_returns_502_for_provider_failure() -> None:
    """Provider failures are mapped to 502 Bad Gateway."""
    provider = FakeModelProvider(error=ProviderError("generation failed"))
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 502
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "generation failed",
            "request_id": request_id,
        },
    }


def test_get_responses_is_not_allowed() -> None:
    """GET /v1/responses is rejected because the resource is create-only."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.get("/v1/responses")
    assert response.status_code == 405


def test_unversioned_responses_path_is_not_found() -> None:
    """POST /responses without the /v1 prefix is not a public route."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/responses", json=_request_body())
    assert response.status_code == 404


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

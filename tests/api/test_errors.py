"""Standardized API error envelope tests."""

from fastapi import APIRouter
from fastapi.testclient import TestClient
from httpx import Response
from ai_runtime.api.app import create_app
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.middleware.request_context import REQUEST_ID_HEADER
from ai_runtime.providers.openai.errors import ProviderError
from tests.api.test_responses import FakeModelProvider, _client_with_provider, _request_body, _success_response


def _assert_error_envelope(response: Response, *, status_code: int, code: str, message: str) -> str:
    """Assert the standard error envelope and return the correlated request id."""
    assert response.status_code == status_code
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.json() == {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    return request_id


def test_validation_error_uses_standard_envelope() -> None:
    """FastAPI validation failures return the provider-neutral error envelope."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body(temperature=3.0))
    _assert_error_envelope(
        response,
        status_code=422,
        code="invalid_request",
        message="Invalid value for 'temperature': Input should be less than or equal to 2.",
    )


def test_domain_validation_error_uses_standard_envelope() -> None:
    """Domain validation failures raised at the boundary use the same envelope."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        json=_request_body(messages=[{"role": "user", "content": "   "}]),
    )
    _assert_error_envelope(
        response,
        status_code=422,
        code="invalid_request",
        message="content must not be empty or blank",
    )


def test_provider_error_uses_standard_envelope() -> None:
    """Provider failures return a 502 with the provider_error code."""
    provider = FakeModelProvider(error=ProviderError("generation failed"))
    client = _client_with_provider(provider)
    response = client.post("/v1/responses", json=_request_body())
    _assert_error_envelope(
        response,
        status_code=502,
        code="provider_error",
        message="generation failed",
    )


def test_api_error_uses_standard_envelope() -> None:
    """Explicit APIError instances are serialized through the shared handler."""
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise APIError(code=ErrorCode.INTERNAL_ERROR, message="boom", status_code=500)

    app.include_router(router)
    client = TestClient(app)
    response = client.get("/boom")
    _assert_error_envelope(
        response,
        status_code=500,
        code="internal_error",
        message="boom",
    )


def test_unhandled_error_uses_standard_envelope() -> None:
    """Unexpected exceptions return a safe internal_error response."""
    app = create_app()
    router = APIRouter()

    @router.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret internals")

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/unexpected")
    _assert_error_envelope(
        response,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )
    assert "secret internals" not in response.text


def test_post_responses_openapi_documents_error_responses() -> None:
    """POST /v1/responses documents standardized error responses in OpenAPI."""
    schema = create_app().openapi()
    post_responses = schema["paths"]["/v1/responses"]["post"]
    assert "422" in post_responses["responses"]
    assert "502" in post_responses["responses"]
    assert post_responses["responses"]["502"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorResponseSchema"

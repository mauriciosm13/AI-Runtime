"""Request correlation and structured logging tests."""

import io
import json
import logging
import re
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from httpx2 import Response
from ai_runtime.api.app import create_app
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.middleware.request_context import REQUEST_ID_HEADER, SERVER_ID_PREFIX
from ai_runtime.providers.openai.errors import ProviderError
from ai_runtime.telemetry.logging import JsonFormatter, REQUEST_LOGGER_NAME
from pytest import MonkeyPatch
from tests.api.test_responses import FakeModelProvider, _client_with_provider, _request_body, _success_response

_SERVER_REQUEST_ID = re.compile(rf"^{re.escape(SERVER_ID_PREFIX)}[0-9a-f-]{{36}}$")


def _request_id_from(response: Response) -> str:
    """Return the X-Request-ID header and assert it is present."""
    assert REQUEST_ID_HEADER in response.headers
    return response.headers[REQUEST_ID_HEADER]


def _assert_correlated_error(response: Response, *, status_code: int, code: str, message: str) -> None:
    """Assert error envelope fields correlate with the response header."""
    assert response.status_code == status_code
    request_id = _request_id_from(response)
    body = response.json()
    assert body == {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }


def test_health_without_header_generates_request_id() -> None:
    """Requests without X-Request-ID receive a server-generated correlation id."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    request_id = _request_id_from(response)
    assert _SERVER_REQUEST_ID.fullmatch(request_id)


def test_health_echoes_valid_client_request_id() -> None:
    """A valid client-provided X-Request-ID is echoed on success responses."""
    client = TestClient(create_app())
    response = client.get("/health", headers={REQUEST_ID_HEADER: "client-trace-1"})
    assert response.status_code == 200
    assert _request_id_from(response) == "client-trace-1"


@pytest.mark.parametrize(
    "invalid_header",
    ["", "   ", "bad id!", "a" * 129],
)
def test_invalid_client_request_id_is_replaced(invalid_header: str) -> None:
    """Invalid client request ids are replaced with a server-generated value."""
    client = TestClient(create_app())
    response = client.get("/health", headers={REQUEST_ID_HEADER: invalid_header})
    assert response.status_code == 200
    request_id = _request_id_from(response)
    assert _SERVER_REQUEST_ID.fullmatch(request_id)


def test_validation_error_includes_correlated_request_id() -> None:
    """422 validation errors include request_id matching the response header."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post(
        "/v1/responses",
        json=_request_body(temperature=3.0),
        headers={REQUEST_ID_HEADER: "trace-422"},
    )
    _assert_correlated_error(
        response,
        status_code=422,
        code="invalid_request",
        message="Invalid value for 'temperature': Input should be less than or equal to 2.",
    )
    assert _request_id_from(response) == "trace-422"


def test_provider_error_includes_correlated_request_id() -> None:
    """502 provider errors include request_id matching the response header."""
    provider = FakeModelProvider(error=ProviderError("generation failed"))
    client = _client_with_provider(provider)
    response = client.post(
        "/v1/responses",
        json=_request_body(),
        headers={REQUEST_ID_HEADER: "trace-502"},
    )
    _assert_correlated_error(
        response,
        status_code=502,
        code="provider_error",
        message="generation failed",
    )
    assert _request_id_from(response) == "trace-502"


def test_unhandled_error_includes_correlated_request_id() -> None:
    """500 unhandled errors include request_id matching the response header."""
    app = create_app()
    router = APIRouter()

    @router.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("secret internals")

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/unexpected", headers={REQUEST_ID_HEADER: "trace-500"})
    _assert_correlated_error(
        response,
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
    )
    assert _request_id_from(response) == "trace-500"
    assert "secret internals" not in response.text


def test_successful_post_responses_includes_request_id_header() -> None:
    """Successful POST /v1/responses responses include X-Request-ID."""
    client = _client_with_provider(FakeModelProvider(response=_success_response()))
    response = client.post("/v1/responses", json=_request_body())
    assert response.status_code == 200
    assert _SERVER_REQUEST_ID.fullmatch(_request_id_from(response))


def test_structured_logs_include_request_lifecycle_fields(monkeypatch: MonkeyPatch) -> None:
    """Structured logs record request start and completion with correlation fields."""
    log_output = io.StringIO()
    handler = logging.StreamHandler(log_output)
    handler.setFormatter(JsonFormatter())
    request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
    previous_handlers = request_logger.handlers[:]
    previous_propagate = request_logger.propagate
    try:
        app = create_app()
        request_logger.handlers.clear()
        request_logger.addHandler(handler)
        request_logger.setLevel(logging.INFO)
        request_logger.propagate = False
        client = TestClient(app)
        response = client.get("/health", headers={REQUEST_ID_HEADER: "log-trace-1"})
        assert response.status_code == 200
        lines = [line for line in log_output.getvalue().splitlines() if line.strip()]
        assert len(lines) >= 2
        started = json.loads(lines[-2])
        completed = json.loads(lines[-1])
        assert started["message"] == "request_started"
        assert started["request_id"] == "log-trace-1"
        assert started["method"] == "GET"
        assert started["path"] == "/health"
        assert completed["message"] == "request_completed"
        assert completed["request_id"] == "log-trace-1"
        assert completed["method"] == "GET"
        assert completed["path"] == "/health"
        assert completed["status_code"] == 200
        assert isinstance(completed["duration_ms"], (int, float))
    finally:
        request_logger.handlers.clear()
        request_logger.handlers.extend(previous_handlers)
        request_logger.propagate = previous_propagate


def test_structured_logs_do_not_leak_secrets(monkeypatch: MonkeyPatch) -> None:
    """Structured request logs must not include secrets from headers or configuration."""
    log_output = io.StringIO()
    handler = logging.StreamHandler(log_output)
    handler.setFormatter(JsonFormatter())
    request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
    previous_handlers = request_logger.handlers[:]
    previous_propagate = request_logger.propagate
    monkeypatch.setenv("AI_RUNTIME_OPENAI_API_KEY", "sk-test-secret-key")
    try:
        client = _client_with_provider(FakeModelProvider(response=_success_response()))
        request_logger.handlers.clear()
        request_logger.addHandler(handler)
        request_logger.setLevel(logging.INFO)
        request_logger.propagate = False
        client = _client_with_provider(FakeModelProvider(response=_success_response()))
        response = client.post(
            "/v1/responses",
            json=_request_body(messages=[{"role": "user", "content": "   "}]),
            headers={"Authorization": "Bearer top-secret-token"},
        )
        assert response.status_code == 422
        log_text = log_output.getvalue()
        assert "sk-test-secret-key" not in log_text
        assert "top-secret-token" not in log_text
        assert "super-secret-prompt" not in log_text
    finally:
        request_logger.handlers.clear()
        request_logger.handlers.extend(previous_handlers)
        request_logger.propagate = previous_propagate


def test_api_error_includes_correlated_request_id() -> None:
    """Explicit APIError responses include request_id matching the response header."""
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise APIError(code=ErrorCode.INTERNAL_ERROR, message="boom", status_code=500)

    app.include_router(router)
    client = TestClient(app)
    response = client.get("/boom", headers={REQUEST_ID_HEADER: "trace-api-error"})
    _assert_correlated_error(
        response,
        status_code=500,
        code="internal_error",
        message="boom",
    )
    assert _request_id_from(response) == "trace-api-error"

"""Tests for non-streaming POST /v1/responses."""

import httpx
import pytest
from ai_runtime_sdk import AIRuntime, AIRuntimeConnectionError, AIRuntimeError, Response
from tests.http import API_KEY, BASE_URL, client, completed_body, json_body


def test_create_sends_bearer_auth_and_parses_response() -> None:
    """A create call authenticates, posts the message body, and returns typed usage."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completed_body(future_field=True), headers={"X-Request-ID": "req_9"})

    with client(handler) as runtime:
        response = runtime.responses.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.0,
            max_output_tokens=16,
            idempotency_key="key_1",
            request_id="req_custom",
        )

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/v1/responses"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert request.headers["idempotency-key"] == "key_1"
    assert request.headers["x-request-id"] == "req_custom"
    assert json_body(request) == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.0,
        "max_output_tokens": 16,
    }
    assert response == Response.model_validate(
        {
            "id": "resp_1",
            "model": "gpt-4o-mini",
            "output": {"role": "assistant", "content": "Hi"},
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            "request_id": "req_9",
        }
    )
    assert API_KEY not in repr(runtime)


def test_create_sends_prompt_tools_cache_and_context() -> None:
    """Prompt, tools, cache, and an explicit context object are forwarded as documented."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = completed_body()
        output = {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "name": "lookup", "arguments": "{}"}]}
        body["output"] = output
        return httpx.Response(200, json=body)

    with client(handler) as runtime:
        response = runtime.responses.create(
            model="gpt-4o-mini",
            prompt={"name": "support.reply", "variables": {"city": "Lisbon"}},
            context={"max_input_tokens": 4000, "truncate": True},
            tools=[{"name": "lookup", "description": "Find a record", "parameters": {"type": "object"}}],
            cache=True,
        )

    assert json_body(seen[0]) == {
        "model": "gpt-4o-mini",
        "prompt": {"name": "support.reply", "variables": {"city": "Lisbon"}},
        "context": {"max_input_tokens": 4000, "truncate": True},
        "tools": [{"name": "lookup", "description": "Find a record", "parameters": {"type": "object"}}],
        "cache": True,
    }
    assert response.output.tool_calls[0].name == "lookup"
    assert response.cached is False


def test_create_marks_cache_hits() -> None:
    """cached is true only when the API says the body was replayed."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completed_body(cached=True))

    with client(handler) as runtime:
        response = runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}])

    assert response.cached is True


def test_create_requires_exactly_one_input() -> None:
    """The client rejects a call that would be a 422 before it touches the network."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("request must not be sent")

    with client(handler) as runtime:
        with pytest.raises(ValueError, match="exactly one"):
            runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}], prompt={"name": "p"})
        with pytest.raises(ValueError, match="exactly one"):
            runtime.responses.create(model="gpt-4o-mini")


def test_api_error_exposes_code_request_id_and_retry_after() -> None:
    """HTTP error envelopes become AIRuntimeError and never include the API key."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"code": "rate_limited", "message": "Slow down.", "request_id": "req_429"}},
            headers={"Retry-After": "3", "X-Request-ID": "req_429"},
        )

    with client(handler) as runtime:
        with pytest.raises(AIRuntimeError) as raised:
            runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])

    error = raised.value
    assert error.code == "rate_limited"
    assert error.status_code == 429
    assert error.request_id == "req_429"
    assert error.retry_after == "3"
    assert API_KEY not in str(error)


def test_non_json_error_uses_the_response_text() -> None:
    """A proxy error without the envelope still raises a typed error."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with client(handler) as runtime:
        with pytest.raises(AIRuntimeError) as raised:
            runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])

    assert raised.value.code == "internal_error"
    assert raised.value.message == "bad gateway"
    assert raised.value.status_code == 502


def test_connection_errors_hide_the_api_key() -> None:
    """Transport failures become AIRuntimeConnectionError without the credential."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with client(handler) as runtime:
        with pytest.raises(AIRuntimeConnectionError) as raised:
            runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])

    assert raised.value.code == "connection_error"
    assert API_KEY not in str(raised.value)


def test_blank_api_key_and_base_url_are_rejected() -> None:
    """The client refuses to be constructed without a credential and a base URL."""
    with pytest.raises(ValueError, match="api_key"):
        AIRuntime(api_key="  ", base_url=BASE_URL)
    with pytest.raises(ValueError, match="base_url"):
        AIRuntime(api_key=API_KEY, base_url=" ")


def test_supplied_http_client_stays_open() -> None:
    """A caller-owned HTTP client is not closed when the runtime closes."""
    http = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=completed_body())))
    with AIRuntime(api_key=API_KEY, base_url=BASE_URL, http_client=http) as runtime:
        runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])
    assert http.is_closed is False
    http.close()


def test_owned_http_client_closes_with_the_runtime() -> None:
    """The client closes the HTTP connection it created."""
    runtime = AIRuntime(api_key=API_KEY, base_url=BASE_URL)
    assert runtime._http.is_closed is False
    with runtime:
        pass
    assert runtime._http.is_closed is True

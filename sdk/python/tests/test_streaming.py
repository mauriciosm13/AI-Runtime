"""Tests for SSE streaming on POST /v1/responses."""

import json
import httpx
import pytest
from ai_runtime_sdk import AIRuntimeError, Response, ResponseDelta
from tests.http import BASE_URL, client, completed_body, json_body, sse


def test_stream_yields_deltas_then_the_completed_response() -> None:
    """A stream posts stream=true and yields deltas followed by the final response."""
    seen: list[httpx.Request] = []
    frames = sse(
        ("response.delta", {"id": "resp_1", "model": "gpt-4o-mini", "delta": {"content": "Hi"}}),
        ("response.completed", completed_body()),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=frames, headers={"content-type": "text/event-stream", "X-Request-ID": "req_s"})

    with client(handler) as runtime:
        events = list(runtime.responses.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}]))

    assert json_body(seen[0])["stream"] is True
    assert "cache" not in json_body(seen[0])
    assert "idempotency-key" not in seen[0].headers
    assert str(seen[0].url) == f"{BASE_URL}/v1/responses"
    assert events == [
        ResponseDelta(id="resp_1", model="gpt-4o-mini", content="Hi", request_id="req_s"),
        Response.model_validate(
            {
                "id": "resp_1",
                "model": "gpt-4o-mini",
                "output": {"role": "assistant", "content": "Hi"},
                "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                "request_id": "req_s",
            }
        ),
    ]


def test_stream_error_after_a_delta_raises() -> None:
    """A response.error frame raises after the deltas already yielded."""
    frames = sse(
        ("response.delta", {"id": "resp_1", "model": "gpt-4o-mini", "delta": {"content": "Hi"}}),
        ("response.error", {"error": {"code": "provider_error", "message": "Upstream failed.", "request_id": "req_e"}}),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=frames, headers={"content-type": "text/event-stream"})

    with client(handler) as runtime:
        iterator = runtime.responses.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}])
        first = next(iterator)
        with pytest.raises(AIRuntimeError) as raised:
            next(iterator)

    assert isinstance(first, ResponseDelta)
    assert first.content == "Hi"
    assert raised.value.code == "provider_error"
    assert raised.value.request_id == "req_e"


def test_stream_preflight_error_stays_json() -> None:
    """Auth and validation failures before the first event use the JSON envelope."""

    def handler(_request: httpx.Request) -> httpx.Response:
        body = {"error": {"code": "invalid_request", "message": "stream cannot be combined with cache.", "request_id": "req_422"}}
        return httpx.Response(422, content=json.dumps(body).encode(), headers={"content-type": "application/json"})

    with client(handler) as runtime:
        with pytest.raises(AIRuntimeError) as raised:
            list(runtime.responses.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}]))

    assert raised.value.status_code == 422
    assert raised.value.code == "invalid_request"


def test_stream_rejects_an_unexpected_event() -> None:
    """An event name outside the contract fails the stream."""
    frames = sse(("response.unknown", {"id": "resp_1"}))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=frames, headers={"content-type": "text/event-stream"})

    with client(handler) as runtime:
        with pytest.raises(AIRuntimeError) as raised:
            list(runtime.responses.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}]))

    assert raised.value.code == "invalid_response"
    assert "response.unknown" in raised.value.message

"""Tests for the async client."""

import asyncio
import json
import httpx
import pytest
from ai_runtime_sdk import AIRuntimeConnectionError, AIRuntimeError, Response, ResponseDelta
from tests.http import API_KEY, async_client, completed_body, sse


def test_async_create_and_stream() -> None:
    """The async client creates a response and streams the same events as the sync client."""
    frames = sse(
        ("response.delta", {"id": "resp_1", "model": "gpt-4o-mini", "delta": {"content": "Hi"}}),
        ("response.completed", completed_body()),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if isinstance(payload, dict) and payload.get("stream") is True:
            return httpx.Response(200, content=frames, headers={"content-type": "text/event-stream", "X-Request-ID": "req_a"})
        return httpx.Response(200, json=completed_body(), headers={"X-Request-ID": "req_a"})

    async def _run() -> tuple[Response, list[ResponseDelta | Response]]:
        runtime = async_client(handler)
        try:
            created = await runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}])
            streamed = [
                event async for event in runtime.responses.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hello"}])
            ]
            return created, streamed
        finally:
            await runtime._http.aclose()

    created, streamed = asyncio.run(_run())
    assert created.request_id == "req_a"
    assert created.output.content == "Hi"
    assert isinstance(streamed[0], ResponseDelta)
    assert isinstance(streamed[1], Response)


def test_async_connection_error_and_api_error() -> None:
    """Async transport and API failures use the same error types as the sync client."""

    async def _api_error() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "Missing API key."}})

        runtime = async_client(handler)
        try:
            with pytest.raises(AIRuntimeError) as raised:
                await runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])
        finally:
            await runtime._http.aclose()
        assert raised.value.code == "unauthorized"
        assert API_KEY not in str(raised.value)

    async def _connection_error() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        runtime = async_client(handler)
        try:
            with pytest.raises(AIRuntimeConnectionError):
                await runtime.responses.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}])
        finally:
            await runtime._http.aclose()

    asyncio.run(_api_error())
    asyncio.run(_connection_error())

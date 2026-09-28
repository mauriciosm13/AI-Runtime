"""HTTP fakes shared by SDK tests."""

import json
from collections.abc import Callable
import httpx
from ai_runtime_sdk import AIRuntime, AsyncAIRuntime

API_KEY = "airt_test_secret"
BASE_URL = "http://runtime.test"
Handler = Callable[[httpx.Request], httpx.Response]


def completed_body(**extra: object) -> dict[str, object]:
    """A successful non-streaming response body."""
    body: dict[str, object] = {
        "id": "resp_1",
        "model": "gpt-4o-mini",
        "output": {"role": "assistant", "content": "Hi"},
        "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    }
    body.update(extra)
    return body


def client(handler: Handler) -> AIRuntime:
    """A sync client bound to an in-memory transport."""
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return AIRuntime(api_key=API_KEY, base_url=BASE_URL, http_client=http)


def async_client(handler: Handler) -> AsyncAIRuntime:
    """An async client bound to an in-memory transport."""
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AsyncAIRuntime(api_key=API_KEY, base_url=BASE_URL, http_client=http)


def sse(*frames: tuple[str, dict[str, object]]) -> bytes:
    """Serialize named SSE frames the way the API does."""
    chunks = [f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n" for event, payload in frames]
    return "".join(chunks).encode()


def json_body(request: httpx.Request) -> dict[str, object]:
    """Decode a request body recorded by a fake transport."""
    payload = json.loads(request.content)
    assert isinstance(payload, dict)
    return payload

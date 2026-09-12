"""Unit tests for the shared SSE parser."""

import asyncio
import httpx
from ai_runtime.providers.sse import iter_sse_events


def test_iter_sse_events_reads_named_and_data_only_events() -> None:
    """Blank-line-delimited SSE events yield event name and data payload."""
    body = b'event: ping\ndata: hello\n\ndata: {"ok":true}\n\n: keep-alive\ndata: trailing\n'

    async def _run() -> list[tuple[str | None, str]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=body))) as client:
            async with client.stream("GET", "https://example.test/stream") as response:
                return [event async for event in iter_sse_events(response)]

    events = asyncio.run(_run())
    assert events == [("ping", "hello"), (None, '{"ok":true}'), (None, "trailing")]

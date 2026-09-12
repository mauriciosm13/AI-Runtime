"""Parse Server-Sent Events from an HTTP response body."""

from collections.abc import AsyncIterator
import httpx


async def iter_sse_events(response: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    """Yield ``(event_name, data)`` pairs for each completed SSE event."""
    event_name: str | None = None
    data_lines: list[str] = []
    async for raw_line in response.aiter_lines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
    if data_lines:
        yield event_name, "\n".join(data_lines)

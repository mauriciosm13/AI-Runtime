"""HttpMcpToolClient adapter tests."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4
import httpx
from ai_runtime.domain.mcp import McpError, McpServer
from ai_runtime.infrastructure.mcp.http_mcp_client import HttpMcpToolClient


def test_list_tools_maps_mcp_response() -> None:
    """tools/list JSON-RPC responses map to domain ToolDefinition values."""
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({"url": str(request.url), "json": request.read().decode()})
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search records",
                            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
                        }
                    ]
                },
            },
        )

    transport = httpx.MockTransport(handler)
    client = HttpMcpToolClient(httpx.AsyncClient(transport=transport), timeout_seconds=5.0)
    server = McpServer(
        id=uuid4(),
        organization_id=uuid4(),
        name="crm",
        url="https://mcp.example/rpc",
        headers={"Authorization": "Bearer secret"},
        created_at=datetime.now(UTC),
    )
    tools = asyncio.run(client.list_tools(server))
    assert len(tools) == 1
    assert tools[0].name == "search"
    assert tools[0].parameters["type"] == "object"
    assert captured[0]["url"] == "https://mcp.example/rpc"


def test_list_tools_raises_on_http_failure() -> None:
    """Transport failures map to McpError."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    transport = httpx.MockTransport(handler)
    client = HttpMcpToolClient(httpx.AsyncClient(transport=transport), timeout_seconds=5.0)
    server = McpServer(
        id=uuid4(),
        organization_id=uuid4(),
        name="crm",
        url="https://mcp.example/rpc",
        created_at=datetime.now(UTC),
    )
    try:
        asyncio.run(client.list_tools(server))
    except McpError:
        return
    raise AssertionError("expected McpError")

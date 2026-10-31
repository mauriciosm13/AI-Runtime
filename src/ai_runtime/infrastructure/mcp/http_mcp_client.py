"""HTTP JSON-RPC client for MCP tool discovery."""

from typing import Any
from uuid import uuid4
import httpx
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpError, McpServer


class HttpMcpToolClient:
    """List tools from remote MCP servers over HTTPS JSON-RPC."""

    def __init__(self, http_client: httpx.AsyncClient, *, timeout_seconds: float) -> None:
        self._http = http_client
        self._timeout = timeout_seconds

    async def list_tools(self, server: McpServer) -> tuple[ToolDefinition, ...]:
        """Call MCP ``tools/list`` and map results to domain tool definitions."""
        payload = {"jsonrpc": "2.0", "id": str(uuid4()), "method": "tools/list", "params": {}}
        headers = {"Content-Type": "application/json", **server.headers}
        try:
            response = await self._http.post(server.url, json=payload, headers=headers, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as err:
            raise McpError("MCP server request failed.") from err
        try:
            body = response.json()
        except ValueError as err:
            raise McpError("MCP server returned invalid JSON.") from err
        if not isinstance(body, dict):
            raise McpError("MCP server returned an invalid response envelope.")
        if body.get("error"):
            raise McpError("MCP server returned an error response.")
        result = body.get("result")
        if not isinstance(result, dict):
            raise McpError("MCP tools/list result is missing.")
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise McpError("MCP tools/list did not return a tools array.")
        return tuple(_map_tool(item) for item in raw_tools)


def _map_tool(item: Any) -> ToolDefinition:
    if not isinstance(item, dict):
        raise McpError("MCP tool entry must be an object.")
    name = item.get("name")
    if not isinstance(name, str):
        raise McpError("MCP tool entry is missing a name.")
    description = item.get("description")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise McpError("MCP tool description must be a string.")
    parameters = item.get("inputSchema")
    if parameters is None:
        parameters = item.get("parameters", {})
    if not isinstance(parameters, dict):
        raise McpError("MCP tool parameters must be a JSON object.")
    return ToolDefinition(name=name, description=description, parameters=parameters)

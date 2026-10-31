"""Port for MCP tool discovery and execution."""

from typing import Protocol, runtime_checkable
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServer


@runtime_checkable
class McpToolClient(Protocol):
    """Remote MCP tool operations."""

    async def list_tools(self, server: McpServer) -> tuple[ToolDefinition, ...]:
        """Return tool definitions advertised by the MCP server."""

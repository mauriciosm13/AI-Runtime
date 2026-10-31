"""Port for MCP tool discovery and execution."""

from abc import ABC, abstractmethod
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServer


class McpToolClient(ABC):
    """Remote MCP tool operations."""

    @abstractmethod
    async def list_tools(self, server: McpServer) -> tuple[ToolDefinition, ...]:
        """Return tool definitions advertised by the MCP server."""

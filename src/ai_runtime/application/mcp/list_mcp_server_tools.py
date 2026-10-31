"""Discover tools from a registered MCP server."""

from uuid import UUID
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServerNotFoundError, namespaced_mcp_tool_name, validate_mcp_server_name
from ai_runtime.ports.mcp_server_repository import McpServerRepository
from ai_runtime.ports.mcp_tool_client import McpToolClient


class ListMcpServerTools:
    """Fetch live tool definitions from one registered MCP server."""

    def __init__(self, repository: McpServerRepository, client: McpToolClient) -> None:
        self._repository = repository
        self._client = client

    async def execute(self, organization_id: UUID, name: str) -> tuple[ToolDefinition, ...]:
        """Return namespaced tool definitions for the server."""
        validate_mcp_server_name(name)
        server = await self._repository.get_by_name(organization_id, name)
        if server is None:
            raise McpServerNotFoundError(name=name)
        tools = await self._client.list_tools(server)
        return tuple(
            ToolDefinition(
                name=namespaced_mcp_tool_name(name, tool.name),
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in tools
        )

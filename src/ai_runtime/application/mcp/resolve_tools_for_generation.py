"""Merge inline and MCP-derived tools for one generation request."""

from collections.abc import Sequence
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError, ToolDefinition
from ai_runtime.domain.mcp import McpServerNotFoundError, validate_mcp_server_name
from ai_runtime.ports.mcp_server_repository import McpServerRepository
from ai_runtime.ports.mcp_tool_client import McpToolClient
from ai_runtime.application.mcp.list_mcp_server_tools import ListMcpServerTools


class ResolveToolsForGeneration:
    """Resolve MCP servers and merge with inline tool declarations."""

    def __init__(self, repository: McpServerRepository, client: McpToolClient) -> None:
        self._lister = ListMcpServerTools(repository, client)

    async def execute(
        self,
        organization_id: UUID,
        inline_tools: Sequence[ToolDefinition],
        server_names: Sequence[str],
    ) -> tuple[ToolDefinition, ...]:
        """Return the merged tool list or raise when names collide."""
        merged: list[ToolDefinition] = list(inline_tools)
        seen = {tool.name for tool in merged}
        for raw_name in server_names:
            validate_mcp_server_name(raw_name)
            try:
                discovered = await self._lister.execute(organization_id, raw_name)
            except McpServerNotFoundError as err:
                raise err
            for tool in discovered:
                if tool.name in seen:
                    raise DomainValidationError(f"duplicate tool name: {tool.name}")
                seen.add(tool.name)
                merged.append(tool)
        return tuple(merged)

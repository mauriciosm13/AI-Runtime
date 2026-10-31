"""List organization MCP server registrations."""

from uuid import UUID
from ai_runtime.domain.mcp import McpServerSummary
from ai_runtime.ports.mcp_server_repository import McpServerRepository


class ListMcpServers:
    """Return public metadata for every MCP server in an organization."""

    def __init__(self, repository: McpServerRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID) -> list[McpServerSummary]:
        """Return summaries sorted by repository order."""
        servers = await self._repository.list_by_organization(organization_id)
        return [McpServerSummary(name=server.name, created_at=server.created_at) for server in servers if server.created_at is not None]

"""Register an organization-scoped MCP tool server."""

from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.mcp import McpServer, validate_mcp_server_name, validate_mcp_server_url
from ai_runtime.ports.mcp_server_repository import McpServerRepository


class RegisterMcpServer:
    """Persist a new MCP server registration for one organization."""

    def __init__(self, repository: McpServerRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        organization_id: UUID,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> McpServer:
        """Return the stored registration."""
        validate_mcp_server_name(name)
        validate_mcp_server_url(url)
        normalized_headers = {} if headers is None else dict(headers)
        now = datetime.now(UTC)
        server = McpServer(
            id=uuid4(),
            organization_id=organization_id,
            name=name,
            url=url.strip(),
            headers=normalized_headers,
            created_at=now,
        )
        return await self._repository.add(server)

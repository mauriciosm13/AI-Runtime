"""Port for organization-scoped MCP server persistence."""

from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.mcp import McpServer


@runtime_checkable
class McpServerRepository(Protocol):
    """Store and load MCP server registrations."""

    async def add(self, server: McpServer) -> McpServer:
        """Persist a new MCP server registration."""

    async def get_by_name(self, organization_id: UUID, name: str) -> McpServer | None:
        """Return one server by organization and name."""

    async def list_by_organization(self, organization_id: UUID) -> list[McpServer]:
        """Return every MCP server registered for the organization."""

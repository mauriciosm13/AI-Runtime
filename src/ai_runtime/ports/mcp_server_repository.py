"""Port for organization-scoped MCP server persistence."""

from abc import ABC, abstractmethod
from uuid import UUID
from ai_runtime.domain.mcp import McpServer


class McpServerRepository(ABC):
    """Store and load MCP server registrations."""

    @abstractmethod
    async def add(self, server: McpServer) -> McpServer:
        """Persist a new MCP server registration."""

    @abstractmethod
    async def get_by_name(self, organization_id: UUID, name: str) -> McpServer | None:
        """Return one server by organization and name."""

    @abstractmethod
    async def list_by_organization(self, organization_id: UUID) -> list[McpServer]:
        """Return every MCP server registered for the organization."""

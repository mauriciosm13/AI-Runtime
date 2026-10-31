"""Test doubles for MCP use cases."""

from uuid import UUID
from ai_runtime.domain.generation import ToolDefinition
from ai_runtime.domain.mcp import McpServer
from ai_runtime.application.mcp.resolve_tools_for_generation import ResolveToolsForGeneration


class FakeMcpServerRepository:
    def __init__(self) -> None:
        self._servers: list[McpServer] = []

    async def add(self, server: McpServer) -> McpServer:
        self._servers.append(server)
        return server

    async def get_by_name(self, organization_id: UUID, name: str) -> McpServer | None:
        for server in self._servers:
            if server.organization_id == organization_id and server.name == name:
                return server
        return None

    async def list_by_organization(self, organization_id: UUID) -> list[McpServer]:
        return [server for server in self._servers if server.organization_id == organization_id]


class FakeMcpToolClient:
    def __init__(self, tools: tuple[ToolDefinition, ...] = ()) -> None:
        self.tools = tools
        self.calls: list[McpServer] = []

    async def list_tools(self, server: McpServer) -> tuple[ToolDefinition, ...]:
        self.calls.append(server)
        return self.tools


class PassthroughResolveTools(ResolveToolsForGeneration):
    """ResolveTools wired to in-memory fakes."""

    def __init__(self, repository: FakeMcpServerRepository, client: FakeMcpToolClient) -> None:
        super().__init__(repository, client)

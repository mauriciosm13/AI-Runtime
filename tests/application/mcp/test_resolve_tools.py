"""ResolveToolsForGeneration use case tests."""

import asyncio
from datetime import UTC, datetime
import pytest
from uuid import uuid4
from ai_runtime.application.mcp.resolve_tools_for_generation import ResolveToolsForGeneration
from ai_runtime.domain.generation import DomainValidationError, ToolDefinition
from ai_runtime.domain.mcp import McpServer, McpServerNotFoundError
from tests.application.mcp.fakes import FakeMcpServerRepository, FakeMcpToolClient


def test_resolve_merges_inline_and_mcp_tools_with_namespace() -> None:
    """MCP tools are namespaced and merged with inline declarations."""
    org_id = uuid4()
    now = datetime.now(UTC)
    repository = FakeMcpServerRepository()
    asyncio.run(
        repository.add(
            McpServer(
                id=uuid4(),
                organization_id=org_id,
                name="crm",
                url="https://mcp.example/tools",
                created_at=now,
            )
        )
    )
    client = FakeMcpToolClient((ToolDefinition(name="lookup", description="Find customer", parameters={"type": "object"}),))
    resolver = ResolveToolsForGeneration(repository, client)
    inline = (ToolDefinition(name="local_tool", description="", parameters={}),)
    merged = asyncio.run(resolver.execute(org_id, inline, ("crm",)))
    names = {tool.name for tool in merged}
    assert names == {"local_tool", "crm.lookup"}


def test_resolve_unknown_server_raises() -> None:
    """Missing MCP registrations surface McpServerNotFoundError."""
    resolver = ResolveToolsForGeneration(FakeMcpServerRepository(), FakeMcpToolClient())
    with pytest.raises(McpServerNotFoundError):
        asyncio.run(resolver.execute(uuid4(), (), ("missing",)))


def test_resolve_duplicate_tool_name_raises() -> None:
    """Colliding inline and MCP tool names return domain validation errors."""
    org_id = uuid4()
    now = datetime.now(UTC)
    repository = FakeMcpServerRepository()
    asyncio.run(
        repository.add(
            McpServer(
                id=uuid4(),
                organization_id=org_id,
                name="crm",
                url="https://mcp.example/tools",
                created_at=now,
            )
        )
    )
    client = FakeMcpToolClient((ToolDefinition(name="dup", description="", parameters={}),))
    resolver = ResolveToolsForGeneration(repository, client)
    inline = (ToolDefinition(name="crm.dup", description="", parameters={}),)
    with pytest.raises(DomainValidationError):
        asyncio.run(resolver.execute(org_id, inline, ("crm",)))

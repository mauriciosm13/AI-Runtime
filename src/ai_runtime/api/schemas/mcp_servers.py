"""Schemas for /v1/mcp_servers endpoints."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.mcp import McpServer, McpServerSummary


class CreateMcpServerRequest(BaseModel):
    """HTTP body for registering an MCP tool server."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)


class McpServerCreatedSchema(BaseModel):
    """Metadata returned after MCP server registration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    organization_id: str
    created_at: datetime

    @classmethod
    def from_domain(cls, server: McpServer) -> "McpServerCreatedSchema":
        """Map a stored server to the public create response."""
        assert server.created_at is not None
        return cls(
            name=server.name,
            organization_id=str(server.organization_id),
            created_at=server.created_at,
        )


class McpServerSummarySchema(BaseModel):
    """Public MCP server metadata without secrets."""

    model_config = ConfigDict(extra="forbid")

    name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, summary: McpServerSummary) -> "McpServerSummarySchema":
        """Map a domain summary to the API schema."""
        return cls(name=summary.name, created_at=summary.created_at)


class McpServerListSchema(BaseModel):
    """List of registered MCP servers."""

    model_config = ConfigDict(extra="forbid")

    servers: list[McpServerSummarySchema]


class McpToolListSchema(BaseModel):
    """Tools discovered from one MCP server."""

    model_config = ConfigDict(extra="forbid")

    tools: list[dict[str, Any]]

"""Organization-scoped MCP server registration contracts."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.prompt import validate_prompt_name

_HTTPS_SCHEME = "https"


class McpServerNotFoundError(Exception):
    """Raised when a registered MCP server name does not exist for the organization."""

    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f"MCP server not found: {name}")


class McpServerNameConflictError(Exception):
    """Raised when an organization already registered the same server name."""

    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f"MCP server name already registered: {name}")


class McpError(Exception):
    """Raised when MCP transport or protocol handling fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def validate_mcp_server_name(name: str) -> None:
    """Reject names outside the same pattern as prompt templates."""
    validate_prompt_name(name)


def validate_mcp_server_url(url: str) -> None:
    """Require a non-blank HTTPS MCP endpoint URL."""
    if not url.strip():
        raise DomainValidationError("url must not be empty or blank")
    parsed = urlparse(url.strip())
    if parsed.scheme != _HTTPS_SCHEME or not parsed.netloc:
        raise DomainValidationError("url must use https with a valid host")


@dataclass(frozen=True, slots=True)
class McpServer:
    """Persisted MCP tool server configuration for one organization."""

    id: UUID
    organization_id: UUID
    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_mcp_server_name(self.name)
        validate_mcp_server_url(self.url)
        if not isinstance(self.headers, dict):
            raise DomainValidationError("headers must be a JSON object")
        for key, value in self.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise DomainValidationError("headers must map string keys to string values")


@dataclass(frozen=True, slots=True)
class McpServerSummary:
    """Public metadata for a registered MCP server (no secrets)."""

    name: str
    created_at: datetime

    def __post_init__(self) -> None:
        validate_mcp_server_name(self.name)


def namespaced_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build the public tool name exposed to the model."""
    validate_mcp_server_name(server_name)
    if not tool_name.strip():
        raise DomainValidationError("tool name must not be empty or blank")
    if re.search(r"[\s/]", tool_name):
        raise DomainValidationError("tool name must not contain whitespace or slashes")
    return f"{server_name}.{tool_name}"

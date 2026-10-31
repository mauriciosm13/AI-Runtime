# ADR 0013: MCP tool registration and discovery

## Status

Accepted

## Context

Roadmap item 34 requires MCP tool servers as a tool source for `POST /v1/responses`. ADR 0005 fixed the public `ToolDefinition` / `ToolCall` contract and deferred runtime execution on the unified response path.

## Decision

1. Tenants register HTTPS MCP endpoints in PostgreSQL (`mcp_servers`), scoped by `organization_id`, with optional auth headers stored as configuration secrets.
2. `POST /v1/responses` accepts optional `mcp: { "servers": ["name"] }`. The runtime calls MCP `tools/list`, maps tools to `ToolDefinition`, namespaces them as `{server}.{tool}`, and merges with inline `tools` before generation.
3. MCP I/O lives behind `McpToolClient` in infrastructure; application use cases orchestrate registration, listing, and resolution.
4. MCP `tools/call` execution remains out of scope for this ADR (PR2 / ADR 0014).

## Consequences

- Clients keep the ADR 0005 tool loop; MCP only supplies schemas.
- Registration secrets are never returned on GET or written to logs.
- Streaming with MCP or inline tools stays rejected until a later slice.

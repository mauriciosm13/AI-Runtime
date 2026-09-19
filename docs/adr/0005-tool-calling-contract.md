# ADR 0005: Provider-neutral tool calling

## Status

Accepted

## Context

Roadmap item 23 requires tool calling on the unified response resource. Providers already expose incompatible function-calling shapes. MCP (item 34) needs a stable tool contract first.

## Decision

1. Domain types `ToolDefinition` and `ToolCall` live in `generation.py`. Adapters translate vendor formats.
2. The runtime never executes tools. Clients send `role: tool` results.
3. Streaming + tools is rejected until a later slice. Text SSE stays unchanged.
4. Gemini function calls that lack a vendor id receive a synthesized `call_{index}_{name}`.

## Consequences

- Clients can implement tool loops against one API.
- MCP can later register as a tool source without changing the public message shape.
- Streaming tool deltas are still unimplemented.

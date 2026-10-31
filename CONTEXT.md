# CONTEXT — Roadmap 34: MCP tool servers

**Status:** Roadmap **33** (HTTP semantic chunk ingestion on `POST /v1/semantic_chunks`) is **delivered** on `main`. README “Still open” lists **MCP tools** next, then LangChain / multi-agent examples (35–36).

**This slice:** Organization-scoped **MCP server registration**, **tool discovery** (`tools/list`), and **exposing discovered tools as existing `ToolDefinition` values** on `POST /v1/responses`—without changing the public assistant / tool message shape from ADR **0005**. **Server-side MCP `tools/call` execution is PR2** (separate endpoint or opt-in response flag); PR1 keeps “runtime does not execute tools on `/v1/responses`.”

**Depends on:** Tool calling (23, ADR 0005), tenant API-key auth, `ToolDefinition` / `ToolCall` in `domain/generation.py`, prompt/RAG pre-generation hooks on `post_responses`.

**Out of scope (PR1):** LangChain examples (35–36), Python SDK MCP helpers (ADR 0011 deferral), streaming + MCP/tools, multi-turn agent loops inside one response, stdio MCP subprocesses (ECS-unfriendly), operator cross-tenant server admin, MCP resources/prompts/sampling, OAuth to third-party MCP hosts, Terraform/Secrets Manager wiring for stored credentials, JWT auth redesign.

---

## Objetivo

Tenants register remote MCP tool servers once per organization. On `POST /v1/responses`, clients reference registered servers by name; the runtime fetches tool schemas from MCP, merges them with any inline `tools`, and passes the union to the model using the **same** `{name, description, parameters}` contract. When the model emits `output.tool_calls`, clients continue the loop with `role: tool` messages (ADR 0005). MCP is a **tool source**, not a new response resource.

---

## Requisitos

| Fonte | Exigência |
| --- | --- |
| ADR **0005** | `ToolDefinition` / `ToolCall` stay in `generation.py`; adapters unchanged; **no runtime tool execution on the unified response path** until an explicit follow-up ADR. |
| ADR **0005** (consequences) | “MCP can later register as a tool source **without changing the public message shape**.” |
| `api-design.md` | Today: inline `tools` only; “MCP tool servers are a later roadmap item.” This slice updates that section. |
| `requirements.md` | Extensibility via adapters/ports; telemetry must not log secrets; tenant isolation. |
| `AGENTS.md` | Clean Architecture: MCP I/O in infrastructure; orchestration in application; thin routes. |
| Privacy | Do not log MCP `headers`, tool argument payloads, or tool result bodies on the request path; audit/metadata labels only (server name, tool name, outcome). |

---

## Decisões

### Scope split (smallest viable product)

| Phase | Delivers | ADR |
| --- | --- | --- |
| **PR1 (this slice)** | Register/list MCP servers; resolve `tools/list` → `ToolDefinition`; `mcp.servers` on `POST /v1/responses` | **ADR 0013** (new): MCP registration + tool discovery |
| **PR2 (next)** | `tools/call` via MCP at runtime (client-driven execute endpoint **or** opt-in single-hop on responses) | **ADR 0014** (new): narrows ADR 0005 only for explicit MCP execution paths |

PR1 is intentionally viable alone: applications can register servers, declare `mcp.servers`, receive `tool_calls`, and execute tools themselves (today’s contract).

### PR1 — Registration (configuration, tenant-scoped)

1. **Persistence:** PostgreSQL table `mcp_servers` (Alembic `0010_mcp_servers`), analogous to `prompt_templates`:
   - `id` UUID PK, `organization_id` FK, `name` (1–64 `[A-Za-z0-9._-]`), `url` (HTTPS MCP endpoint), optional JSONB `headers` (auth), `created_at`.
   - Unique `(organization_id, name)`.
   - `headers` are **configuration secrets**: never returned on GET; never logged.

2. **Routes** (tenant API key, same as `/v1/prompts`):
   - `POST /v1/mcp_servers` → `201` `{ "name", "organization_id", "created_at" }` (omit `url` path secrets if query tokens used; omit `headers`).
   - `GET /v1/mcp_servers` → `{ "servers": [{ "name", "created_at" }] }`.
   - `GET /v1/mcp_servers/{name}/tools` → `{ "tools": [{ "name", "description", "parameters" }] }` (live `tools/list`; useful for debugging and LangChain examples later).

3. **Use cases:** `RegisterMcpServer`, `ListMcpServers`, `ListMcpServerTools` under `application/mcp/`.

4. **URL policy (minimal):** `https` only; reject blank; document SSRF hardening (block RFC1918) as follow-up if not implemented in PR1.

### PR1 — Tool exposure on `POST /v1/responses`

5. **Request extension** (`CreateResponseRequest`, `extra=forbid` preserved on sibling fields):

   ```json
   "mcp": { "servers": ["crm", "billing"] }
   ```

   - Optional; default omit = no MCP resolution.
   - Each name must exist for the caller’s organization or `404` / `mcp_server_not_found`.
   - **Mutually exclusive constraints (match existing tools rules):** if `stream: true` and (`tools` non-empty or `mcp` present or tool messages in history) → `422` / `invalid_request` (unchanged policy).

6. **Resolution before `CreateResponse`:** New use case `ResolveToolsForGeneration`:
   - Input: `organization_id`, inline `tools`, optional `mcp.servers`.
   - For each server: load registration → MCP `tools/list` → map each MCP tool to `ToolDefinition(name=..., description=..., parameters=inputSchema)`.
   - **Namespacing:** expose tools as `{server_name}.{tool_name}` to avoid collisions across servers and inline tools; domain validation on `ToolDefinition.name` must allow `.` or namespacing uses `__`—pick one in implementation and document in `api-design.md` (prefer `.` for readability).
   - Merge inline `tools` + MCP tools; duplicate resolved names → `422` / `invalid_request`.
   - Output: `tuple[ToolDefinition, ...]` fed into `GenerationRequest.tools` and context builder (`build_context.execute(..., tools=...)`).

7. **Route orchestration** (mirror RAG/prompt in `api/routes/responses.py`):

   ```
   resolve_prompt → augment_rag → resolve_mcp_tools (+ inline) → build_context → CreateResponse
   ```

8. **Cache / idempotency:** `cache_fingerprint` and idempotency payloads must hash **resolved** tool definitions (including MCP-derived), not just inline `tools`, so cache behavior stays correct when MCP schemas change.

9. **Errors:** MCP transport/protocol failures → `502` / `mcp_error` (or reuse `provider_error` only if catalog consistency demands—prefer dedicated `mcp_error`). Timeouts bounded via settings (e.g. `AI_RUNTIME_MCP_TIMEOUT_SECONDS`).

### PR1 — MCP client boundary

10. **Port** `McpToolClient` (or split `McpToolLister` / `McpToolCaller` with caller stubbed in PR1):
    - `async def list_tools(server: McpServerRef) -> tuple[ToolDefinition, ...]`
    - PR2 adds `async def call_tool(server, tool_name, arguments: str) -> str`

11. **Infrastructure:** HTTP-based MCP session using existing `httpx` (Streamable HTTP / JSON-RPC as per MCP spec—no new dependency required for PR1 if kept minimal). No business logic in the adapter.

12. **Tests:** Fake port in application tests; API tests with mocked HTTP or fake client; cross-org isolation (org A’s server names/tools invisible to org B).

### PR2 — Execution (documented, not PR1)

13. **Preferred minimal execution surface:** `POST /v1/mcp_servers/{name}/tools/{tool_name}/call` with `{ "arguments": { ... } }` → `{ "content": "..." }` (string content for `role: tool` messages). Keeps `CreateResponse` free of agent loops.

14. **Optional later:** `mcp.auto_execute: true` on `POST /v1/responses` for **one** model→MCP→model hop; requires ADR 0014 and explicit limits (max calls, timeout, no streaming).

### Documentation

15. **Update:** `docs/foundation/api-design.md` (routes + `mcp` on responses), `docs/foundation/data-architecture.md` (`mcp_servers` row), `README.md` roadmap “Still open”, OpenAPI.

16. **Do not** change SDK in PR1 (ADR 0011).

---

## Arquivos (touch esperado — PR1)

| Área | Paths |
| --- | --- |
| ADR | `docs/adr/0013-mcp-tool-registration-and-discovery.md` |
| Domain | `domain/mcp.py` (e.g. `McpServerRegistration`, errors) — optional if kept minimal in application |
| Ports | `ports/mcp_tool_client.py` |
| Application | `application/mcp/register_mcp_server.py`, `list_mcp_servers.py`, `list_mcp_server_tools.py`, `resolve_tools_for_generation.py` |
| Infrastructure | `infrastructure/db/models/mcp_server.py`, `infrastructure/db/repositories/mcp_server_repository.py`, `infrastructure/mcp/http_mcp_client.py` |
| Migration | `alembic/versions/0010_mcp_servers.py` |
| API | `api/routes/mcp_servers.py`, `api/schemas/mcp_servers.py`, `api/schemas/responses.py` (`McpSchema`), `api/routes/responses.py`, `api/dependencies.py`, router registration |
| Config | `config/settings.py` — MCP timeout |
| Tests | `tests/application/mcp/*`, `tests/api/test_mcp_servers.py`, `tests/api/test_mcp_responses.py`, repository test |
| Docs | `docs/foundation/api-design.md`, `docs/foundation/data-architecture.md`, `README.md` |

PR2 would add call route, `call_tool` on port/client, ADR 0014, and optional response auto-execute.

---

## Critérios de aceitação (PR1)

- [ ] Tenant can `POST /v1/mcp_servers` and `GET /v1/mcp_servers`; registration is scoped to API key `organization_id` only (never accept `organization_id` in body).
- [ ] `GET /v1/mcp_servers/{name}/tools` returns JSON Schema–compatible tool definitions mapped from MCP.
- [ ] `POST /v1/responses` with `mcp.servers` merges MCP tools into the model request; inline `tools` still work; assistant `output.tool_calls` shape unchanged.
- [ ] Unknown server name → `404` / `mcp_server_not_found`; MCP unreachable → bounded timeout and stable error code.
- [ ] `stream: true` with `mcp` or tools rejected with `422` / `invalid_request`.
- [ ] Response cache fingerprint includes resolved MCP tool definitions.
- [ ] MCP secrets and tool payloads are not written to structured logs or audit content fields.
- [ ] pytest, ruff, mypy CI green; OpenAPI documents new routes and `mcp` field.

---

## Referência (implementação existente)

- `docs/adr/0005-tool-calling-contract.md` — tool message contract
- `src/ai_runtime/domain/generation.py` — `ToolDefinition`, `ToolCall`, `GenerationRequest.uses_tools`
- `src/ai_runtime/api/schemas/responses.py` — `CreateResponseRequest.tools`
- `src/ai_runtime/api/routes/responses.py` — pre-`CreateResponse` orchestration (prompt, RAG, context)
- `src/ai_runtime/application/responses/cache_fingerprint.py` — tool hashing
- `src/ai_runtime/api/routes/prompts.py` — tenant-scoped configuration POST/GET pattern
- `tests/api/test_responses.py` — `test_post_responses_returns_tool_calls`

---

## Delegação

### Implementer — PR1 subtasks (order)

| ID | Title | Purpose | Acceptance |
| --- | --- | --- | --- |
| I1 | ADR 0013 + schema migration | Record decision; `mcp_servers` table | Alembic head; data-architecture updated |
| I2 | Repository + register/list use cases | Persist org-scoped servers | Unit tests; cross-org isolation |
| I3 | `McpToolClient` + list tools use case | MCP `tools/list` → domain tools | Fakes + adapter test with httpx mock |
| I4 | `ResolveToolsForGeneration` | Merge inline + MCP; namespacing | Duplicate-name 422; fingerprint inputs |
| I5 | API routes + `mcp` on responses | Wire DI; orchestration in route | E2E test: register fake MCP → response includes tool_calls |
| I6 | Docs + README | api-design route map; roadmap trim | MCP discovery marked delivered; execution still open |

### Implementer — PR2 (after PR1 merge)

| ID | Title | Purpose | Acceptance |
| --- | --- | --- | --- |
| I7 | ADR 0014 + `call_tool` | MCP execution port | Call route returns string content; no change to default `/v1/responses` behavior |
| I8 | (Optional) `mcp.auto_execute` | Single-hop loop | Gated, non-streaming, max one round |

### Reviewer — checklist

| ID | Focus |
| --- | --- |
| R1 | ADR 0005 preserved on `/v1/responses` for PR1 (no silent tool execution) |
| R2 | Tenant isolation: server names and URLs only from authenticated org |
| R3 | Secrets: headers not in GET, logs, audit bodies, or cache keys |
| R4 | Clean Architecture: MCP protocol details only in infrastructure adapter |
| R5 | Scope: no SDK, LangChain, streaming MCP, stdio transport, agent loops in PR1 |

### Explorer (optional, readonly)

- Confirm MCP Streamable HTTP message shape and whether official `mcp` Python package is worth the dependency vs minimal httpx JSON-RPC.
- After PR1, verify OpenAPI matches `api-design.md` and cache tests cover MCP-resolved tools.

---

## Próximo depois deste slice

| Ordem | Item | Notas |
| --- | --- | --- |
| 1 | **Roadmap 34 PR2** — MCP `tools/call` execution | ADR 0014; optional auto-execute |
| 2 | **Roadmap 35–36** — LangChain / multi-agent examples | Consume registration + responses API |
| Paralelo / infra | pgvector on RDS Terraform | README gap; unrelated to MCP |

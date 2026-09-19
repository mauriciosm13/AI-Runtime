# API design

## Principles

- Public business APIs are versioned under `/v1`.
- Operational endpoints are unversioned because they are consumed by deployment infrastructure, not application clients.
- API routes translate HTTP only; authorization, routing, provider execution, and persistence belong to application use cases and adapters.
- The API is provider-neutral. Clients do not invoke provider-specific routes.
- All JSON fields use `snake_case` unless an established external interoperability standard requires otherwise.

## Route map

The table describes the planned initial API surface. `Planned` routes document the contract direction but do not imply an implementation exists.

| Method | Path | Status | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | First endpoint | Liveness: confirms the process can serve HTTP. |
| `GET` | `/metrics` | Implemented | Prometheus text scrape of in-process HTTP and generation metrics. Unauthenticated. |
| `GET` | `/ready` | Planned | Readiness: confirms required runtime dependencies are usable. |
| `POST` | `/v1/responses` | Implemented | Creates a provider-neutral model response. |
| `POST` | `/v1/prompts` | Implemented | Creates the next immutable version of an organization prompt template. |
| `GET` | `/v1/prompts/{name}` | Implemented | Lists the versions of an organization prompt template. |
| `GET` | `/v1/models` | Planned | Lists models available to the authenticated organization. |
| `POST` | `/v1/organizations` | Planned, operator-only | Creates an organization. |
| `GET` | `/v1/organizations/{organization_id}` | Planned, operator-only | Retrieves organization configuration. |
| `POST` | `/v1/api_keys` | Planned, operator-only | Creates an API key for an organization. |
| `GET` | `/v1/api_keys` | Planned, operator-only | Lists API-key metadata without secret values. |
| `DELETE` | `/v1/api_keys/{key_id}` | Planned, operator-only | Revokes an API key. |

Administrative authorization details will be designed with the authentication feature. They are intentionally not assumed to be exposed to every API-key holder.

## Authentication

Application clients authenticate with a bearer API key:

```http
Authorization: Bearer airt_...
```

The API extracts credentials at the boundary. `AuthenticateApiKey` validates the key (prefix lookup + argon2id verify), resolves its organization, and rejects suspended organizations. Routes must not query key storage directly.

| Condition | HTTP | `error.code` |
| --- | --- | --- |
| Missing, blank, or non-Bearer `Authorization` | `401` | `unauthorized` |
| Unknown / wrong / revoked key, or missing organization | `401` | `unauthorized` |
| Active key whose organization is suspended | `403` | `forbidden` |

`GET /health` remains unauthenticated (liveness). `POST /v1/responses` requires a valid bearer key.

## Rate limiting

`POST /v1/responses` enforces a platform default token-bucket rate limit **per organization** (configured via `AI_RUNTIME_RATE_LIMIT_*`). Organization-specific rate-limit overrides are a later feature.

| Condition | HTTP | `error.code` | Headers |
| --- | --- | --- | --- |
| Organization request budget exhausted | `429` | `rate_limited` | `Retry-After` (seconds) |

When Redis is unavailable, rate limiting fails open: the request proceeds and a warning is logged.

## Organization access and quotas

Before a provider call, `CreateResponse` resolves the requested model through `ModelRouter`, then enforces organization policy stored in PostgreSQL:

- **Model entitlements** — when an organization has configured entitlements, only listed models are allowed. An empty entitlement set allows all models (backward compatible default).
- **Monthly token quota** — when `organization_policies.monthly_token_limit` is set, the runtime sums `input_tokens + output_tokens` from `usage_records` for the current UTC calendar month and rejects requests that would meet or exceed the limit.

Unknown models are rejected by the routing catalog before entitlement and quota checks.

| Condition | HTTP | `error.code` | Headers |
| --- | --- | --- | --- |
| Requested model not in the routing catalog | `400` | `unsupported_model` | — |
| Catalog model whose provider adapter is not configured | `503` | `provider_error` | — |
| Requested model not entitled for organization | `403` | `model_not_available` | — |
| Monthly token quota exhausted | `429` | `quota_exceeded` | `Retry-After` (seconds until next UTC month) |

Operator HTTP routes for managing policies are planned but not yet exposed. Policies are seeded through persistence adapters or migrations in the current slice.

## Idempotency

Clients may send an optional `Idempotency-Key` header on `POST /v1/responses`:

- Value: 1–128 characters matching `[A-Za-z0-9._:-]`.
- Scope: `(organization_id, Idempotency-Key)`.
- Retention: bounded TTL (`AI_RUNTIME_IDEMPOTENCY_TTL_SECONDS`, default 24h).

| Condition | HTTP | `error.code` |
| --- | --- | --- |
| Blank or invalid `Idempotency-Key` | `422` | `invalid_request` |
| Same key already in progress | `409` | `conflict` |
| Same key previously completed | `200` | (replay of stored response body; no new provider call) |

When Redis is unavailable, idempotency fails open: the request proceeds without coordination guarantees.

## Unified response resource

`POST /v1/responses` is the planned provider-neutral model-invocation endpoint. It is intentionally a resource-oriented endpoint rather than a provider-specific proxy.

Clients send a catalog model name (`model`). The runtime selects the provider through `ModelRouter`; clients do not name a vendor. The catalog maps `gpt-4o` and `gpt-4o-mini` to OpenAI, `claude-3-5-sonnet-20241022` to Anthropic, and `gemini-2.5-flash` to Gemini when those adapters are registered.

Clients send `model`, `messages`, optional `temperature` / `max_output_tokens`, optional `stream` (default `false`), optional `tools`, and optional `cache` (default `false`).

`tools` is a list of `{name, description, parameters}` where `parameters` is a JSON Schema object. The runtime does not execute tools. When the model requests a call, `output.tool_calls` contains `{id, name, arguments}`. Clients send results as `role: tool` messages with `tool_call_id`.

`stream: true` combined with `tools` or tool messages is rejected (`422` / `invalid_request`) in this slice. MCP tool servers are a later roadmap item.

`cache: true` stores the successful JSON response in Redis under `cache:resp:{organization_id}:{sha256}` with `AI_RUNTIME_RESPONSE_CACHE_TTL_SECONDS` (default 1h). A later identical request (same organization + model, messages, tools, temperature, max_output_tokens) returns that payload with `cached: true`, skips the provider, and does not write usage. The prompt is hashed, not stored. Cache is opt-in; omitting `cache` or setting `false` never reads or writes the cache. Redis failures fail open (miss). `cache: true` plus `stream: true` is rejected (`422` / `invalid_request`). Invalidation is TTL only. This path is distinct from `Idempotency-Key`; a completed idempotency record is replayed first.

Exactly one of `messages` or `prompt` is required (`422` / `invalid_request` otherwise). `prompt` is `{ "name": "...", "version": 2, "variables": { "k": "v" } }`; `version` defaults to the latest. The named template is loaded for the caller's organization and rendered into `messages` before generation, so `stream`, `tools`, `cache`, and `Idempotency-Key` behave as they do with raw messages, and the cache key is computed from the rendered messages. Variable names must match the template's `{{placeholders}}` exactly (`422` otherwise); values are strings substituted literally. An unknown name or version returns `404` / `prompt_not_found`.

`context` is optional: `{ "max_input_tokens": 4000, "truncate": true }`. When `prompt` or `context` is present, the runtime estimates input tokens and enforces the smallest context window among the requested model and its failover candidates (minus `max_output_tokens`). Over budget returns `422` / `context_length_exceeded`; with `truncate: true`, the oldest non-system messages are dropped first, system messages and the latest turn are kept, and tool calls stay paired with their results. Requests with neither field are not budgeted. Token counts are estimates, not billing figures.

`POST /v1/prompts` takes `{ "name": "support.reply", "messages": [{ "role": "system|user|assistant", "content": "... {{var}} ..." }] }` (`name` is 1-64 characters of `[A-Za-z0-9._-]`) and returns `201` with the new immutable `version`, the stored `messages`, and the sorted `variables`. `GET /v1/prompts/{name}` returns `{ "versions": [...] }` in ascending order or `404`. Both are scoped to the API key's organization. Templates are configuration; variable values and rendered content are never stored or logged.

When `stream` is omitted or `false`, a successful call returns `200` JSON with `id`, `model`, `output`, and `usage`. Cache hits also include `cached: true`.

When `stream` is `true`, a successful call returns `Content-Type: text/event-stream` with provider-neutral events:

| Event | Payload |
| --- | --- |
| `response.delta` | `id`, `model`, `delta.content` |
| `response.completed` | same shape as the JSON `ResponseSchema` |
| `response.error` | existing error envelope (`code`, `message`, `request_id`) |

Pre-stream failures (auth, validation, rate limit, quota, entitlement, unknown model, missing adapter, provider failure before the first event) keep the JSON error envelope. After the first SSE event, provider failures are delivered as `response.error` and the stream ends.

`Idempotency-Key` combined with `stream: true` is rejected (`422` / `invalid_request`) in this slice. Streaming requests still consume the organization rate limit, enforce entitlements and monthly quota before the provider stream starts, and persist one usage row after `response.completed`. Usage is not written if the stream fails after starting.

Retry and failover apply only before the first SSE event. After the client has received any event, the chosen route is sticky.

## Error contract

Client-facing errors use a stable provider-neutral envelope:

```json
{
  "error": {
    "code": "model_not_available",
    "message": "The requested model is not available for this organization.",
    "request_id": "req_..."
  }
}
```

Error codes are stable programmatic identifiers. Messages are safe for clients and must not expose credentials, provider internals, or tenant data. The initial implementation will define the exact error-code catalog alongside its use cases.

### Request correlation (implemented)

Every HTTP request is assigned a correlation identifier:

- Clients may send `X-Request-ID` with a value up to 128 characters using `[A-Za-z0-9._:-]`.
- When the header is absent or invalid, the server generates `req_<uuid>`.
- All HTTP responses include `X-Request-ID` with the identifier used for that request.
- Error envelopes include the same value in `error.request_id`.
- Structured request logs use the same identifier for start and completion events.
- The same value is emitted as `trace_id`. HTTP and generation spans (`span=http` / `span=generation`) share it.

`GET /metrics` is unauthenticated and returns Prometheus text for `http_requests_total`, `http_request_duration_seconds`, `generation_requests_total`, and `generation_tokens_total`. Successful generations also append an `audit_events` row (`action=response.created`) with model/outcome/provider labels only — never prompt or response content.

This HTTP correlation identifier is distinct from `response.id`, which identifies a model generation result returned by `POST /v1/responses`.

## HTTP semantics

- `200 OK` represents a successful read or completed non-streaming response.
- `201 Created` represents creation of an administrative resource.
- `202 Accepted` is reserved for future asynchronous work and is not used for a synchronous provider response.
- `401 Unauthorized` represents missing or invalid credentials.
- `403 Forbidden` represents valid credentials lacking the required entitlement.
- `404 Not Found` avoids revealing resources outside the caller's permitted scope.
- `429 Too Many Requests` represents enforced rate limits (`error.code` `rate_limited`) or monthly quota exhaustion (`error.code` `quota_exceeded`).
- `409 Conflict` represents an in-flight `Idempotency-Key` collision (`error.code` `conflict`).
- `502 Bad Gateway` and `503 Service Unavailable` represent normalized upstream/provider failures.

## Evolution rules

- Additive fields and endpoints may be introduced within `/v1` when backward compatible.
- Removing or changing the meaning of a public field requires a new API version or a documented migration.
- Generated OpenAPI is the machine-readable contract and must be reviewed when a route or schema is implemented.

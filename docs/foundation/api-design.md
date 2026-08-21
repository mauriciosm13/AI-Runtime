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
| `GET` | `/ready` | Planned | Readiness: confirms required runtime dependencies are usable. |
| `POST` | `/v1/responses` | Implemented | Creates a provider-neutral model response. |
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

Clients send a catalog model name (`model`). The runtime selects the provider through `ModelRouter`; clients do not name a vendor. The initial catalog maps `gpt-4o` and `gpt-4o-mini` to OpenAI and `claude-3-5-sonnet-20241022` to Anthropic when the adapter is registered.

The detailed request and response schema is deferred until the first provider capability is selected. Its minimum contract will include:

- requested model or routing preference;
- normalized input/messages;
- generation options supported by the provider-neutral contract;
- an opt-in streaming mode;
- a stable response identifier, model metadata, output, usage, and request identifier.

Streaming will use Server-Sent Events when implemented. A streaming request must preserve the same authorization, routing, telemetry, and terminal usage semantics as a non-streaming request.

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

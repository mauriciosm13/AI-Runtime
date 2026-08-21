# Data architecture

## Decision summary

AI Runtime uses PostgreSQL as its system of record and Redis for ephemeral, latency-sensitive coordination. pgvector remains a future PostgreSQL extension, introduced only when semantic retrieval becomes an implemented product capability.

## PostgreSQL: system of record

PostgreSQL stores data that requires durability, relational integrity, transactional updates, or auditability.

| Data category | Examples | Why PostgreSQL |
| --- | --- | --- |
| Tenancy and access | organizations, API-key metadata, roles, model entitlements | Relational constraints and transactional authorization changes |
| Configuration | provider configuration references, routing policies, limits | Durable, queryable configuration with history potential |
| Accounting | requests, usage records, token counts, estimated costs | Auditable relations and reliable aggregation |
| Audit trail | key lifecycle events, policy changes | Durable event history and investigation support |

API-key secrets themselves are never stored in plaintext. PostgreSQL stores a key identifier, a non-secret prefix for display, a secure hash, status, timestamps, and organization relationship.

The initial model-to-provider catalog is an in-process domain constant (`DEFAULT_MODEL_CATALOG` in `domain/routing.py`). Durable operator-edited routing policies remain a planned PostgreSQL concern; see [ADR 0002](../adr/0002-static-model-catalog-routing.md).

PostgreSQL is the initial operational database. SQLAlchemy 2 async (asyncpg) is wired at the infrastructure boundary for engine and session lifecycle. Alembic migrates against shared ORM metadata: `0001_baseline` establishes version tracking; `0002_organizations` creates the `organizations` table (`id` UUID PK, `name`, unique `slug`, `status`, `created_at`, `updated_at`); `0003_api_keys` creates the `api_keys` table (`id` UUID PK, `organization_id` FK → `organizations.id`, optional `name`, indexed non-secret `prefix`, argon2id `secret_hash`, `status` active|revoked, `created_at`, nullable `revoked_at`, `updated_at`); `0004_usage_records` creates the `usage_records` table (`id` UUID PK, unique `request_id`, `organization_id` FK → `organizations.id`, `api_key_id` FK → `api_keys.id`, `provider`, `model`, nullable `input_tokens` / `output_tokens`, nullable `estimated_cost_usd`, `created_at`); and `0005_organization_policies` creates `organization_policies` (`organization_id` UUID PK/FK, nullable `monthly_token_limit`, timestamps) and `organization_model_entitlements` (`id` UUID PK, `organization_id` FK, `model`, unique per org+model) plus a composite index on `usage_records (organization_id, created_at)` for monthly quota aggregation. Plaintext API-key secrets are never persisted; the create use case returns the raw `airt_...` secret once, and only the KDF digest remains at rest. Usage rows intentionally omit prompt and response content.

## Redis: ephemeral coordination

Redis stores data whose value is derived, short-lived, or requires low-latency atomic operations.

| Use case | Example | Retention |
| --- | --- | --- |
| Rate limiting | token bucket per organization (`rl:org:{organization_id}`) | Short TTL derived from refill rate |
| Response cache | eligible deterministic response | Explicit TTL and invalidation policy |
| Idempotency | result or status for a caller-provided idempotency key (`idem:{organization_id}:{key}`) | Bounded TTL (`AI_RUNTIME_IDEMPOTENCY_TTL_SECONDS`) |
| Distributed coordination | short lease for controlled background work | Short TTL |

The local Compose stack runs Redis 7 alongside PostgreSQL. The API process opens a shared `redis.asyncio` client from `AI_RUNTIME_REDIS_URL` during lifespan startup.

Implemented coordination adapters:

- `RedisRateLimiter` — Lua token bucket using `rate_limit_requests_per_minute` and `rate_limit_burst`.
- `RedisIdempotencyStore` — `SET NX` in-progress lease, completed JSON payload replay, release on failed attempts.

Redis is not the source of truth for organizations, credentials, accounting, or durable job state. A Redis outage may reduce performance or temporarily disable a dependent feature (rate limiting and idempotency fail open), but it must not silently lose durable data.

## Deferred data stores

### pgvector

When semantic retrieval is implemented, pgvector will be evaluated as an extension to the existing PostgreSQL deployment. Keeping vector data beside tenant and authorization data reduces operational complexity for an initial RAG capability.

### Object storage

Object storage is not required for the initial runtime. It may be introduced for large artifacts, exports, or explicitly retained request content, subject to retention and privacy requirements.

### Dedicated analytics store

PostgreSQL supports initial operational usage reporting. A dedicated analytics pipeline is deferred until query volume, retention, or reporting needs justify it.

## Consistency and lifecycle principles

- Authorization and policy reads must use a consistent source of truth before provider invocation.
- Usage records must include a request identifier so retries and reconciliation can avoid double counting.
- Provider calls cannot participate in a database transaction; application workflows must model partial failure explicitly.
- Retention, deletion, and anonymization policies are product decisions that must be defined before persistent prompt or response content is stored.
- Database schema changes are versioned migrations and never ad-hoc production changes.

## Why not MongoDB initially?

The initial core is relational: organizations own keys, keys authorize requests, policies govern models, and requests produce usage records. PostgreSQL provides the constraints and transaction semantics these relationships need without adding a second primary data model.

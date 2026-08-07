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

PostgreSQL is the initial operational database. SQLAlchemy 2 async (asyncpg) is wired at the infrastructure boundary for engine and session lifecycle. Alembic migrates against shared ORM metadata: `0001_baseline` establishes version tracking; `0002_organizations` creates the `organizations` table (`id` UUID PK, `name`, unique `slug`, `status`, `created_at`, `updated_at`); and `0003_api_keys` creates the `api_keys` table (`id` UUID PK, `organization_id` FK → `organizations.id`, optional `name`, indexed non-secret `prefix`, argon2id `secret_hash`, `status` active|revoked, `created_at`, nullable `revoked_at`, `updated_at`). Plaintext API-key secrets are never persisted; the create use case returns the raw `airt_...` secret once, and only the KDF digest remains at rest.

## Redis: ephemeral coordination

Redis stores data whose value is derived, short-lived, or requires low-latency atomic operations.

| Use case | Example | Retention |
| --- | --- | --- |
| Rate limiting | token bucket per organization or API key | Short TTL |
| Response cache | eligible deterministic response | Explicit TTL and invalidation policy |
| Idempotency | result or status for a caller-provided idempotency key | Bounded TTL |
| Distributed coordination | short lease for controlled background work | Short TTL |

Redis is not the source of truth for organizations, credentials, accounting, or durable job state. A Redis outage may reduce performance or temporarily disable a dependent feature, but it must not silently lose durable data.

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

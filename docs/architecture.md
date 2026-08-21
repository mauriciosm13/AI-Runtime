# Architecture

## Purpose

AI Runtime is a provider-agnostic infrastructure service for AI-powered applications. Its architecture must allow provider SDKs, persistence technologies, and deployment platforms to evolve without changing the core business rules.

The project uses a lightweight Clean Architecture with ports and adapters. It prioritizes explicit boundaries over framework-driven structure while avoiding abstractions that have no current use case.

## Dependency rule

Dependencies point inward.

```text
API ---------------> Application -------------> Domain
                         |                         ^
                         v                         |
                       Ports -----------------------+
                         ^
                         |
Infrastructure / Providers / Telemetry
```

- `domain` must not import framework, database, cloud, or provider SDK code.
- `application` may depend on `domain` and on port interfaces, but not on concrete external implementations.
- `api`, `infrastructure`, `providers`, and `telemetry` may depend on `application`, `domain`, and ports as needed.
- Composition roots wire concrete adapters to application use cases through dependency injection.

## Layers

### API

The API layer owns FastAPI routes, HTTP request and response schemas, authentication extraction, exception-to-HTTP mapping, request correlation middleware, and dependency wiring. A route validates input, invokes one use case, and serializes the result. It contains no authorization policy, routing policy, provider selection, or persistence logic.

Request correlation is handled by middleware in `api/middleware/request_context.py`. Each HTTP request receives a `request_id` stored on `request.state`, echoed in the `X-Request-ID` response header, included in error envelopes, and emitted in structured request logs. Routes and exception handlers do not generate correlation identifiers inline.

`POST /v1/responses` requires bearer API-key authentication before generation. The API layer extracts `Authorization: Bearer airt_...`, invokes `AuthenticateApiKey`, and injects an `AuthenticatedPrincipal` (no plaintext secret or hash). Missing or invalid credentials map to `401 Unauthorized`; suspended organizations map to `403 Forbidden`. After auth, the route validates a JSON body with Pydantic schemas, maps it to `CreateResponseCommand` (generation request plus `request_id`, `organization_id`, and `api_key_id`), invokes `CreateResponse`, and serializes `GenerationResponse`. Provider failures map to `502 Bad Gateway`; validation failures map to `422 Unprocessable Entity`. Errors use the standardized envelope in `api/schemas/errors.py` via `api/exception_handlers.py`. The composition root wires `ModelRouter` (OpenAI adapter registered as `"openai"`), SQLAlchemy repositories (including usage), `StaticCostEstimator`, and `Argon2ApiKeyHasher` through FastAPI dependencies and stores a shared `httpx.AsyncClient` on the application lifespan. Unknown catalog models map to `400 Bad Request` (`unsupported_model`); organization entitlement denials map to `403 Forbidden` (`model_not_available`).

### Application

The application layer implements use cases. It coordinates domain policies with ports, transactions, provider calls, persistence, cache access, and telemetry. Examples include generating a completion, issuing an API key, and recording usage.

Application code expresses workflows; it does not contain HTTP-specific concerns or direct SQLAlchemy, Redis, AWS, or provider-SDK calls.

`CreateResponse` in `application/responses/` receives a `CreateResponseCommand`, resolves the requested model through `ModelRouter`, delegates generation to the selected `ModelProvider`, estimates cost through `CostEstimator`, persists a `UsageRecord` through `UsageRepository` after a successful provider response, and returns the `GenerationResponse`. Prompt/response content is not stored. It is exposed through `POST /v1/responses` in the API layer.

`ModelRouter` in `application/routing/` binds the domain catalog (`model → provider`) to registered `ModelProvider` adapters. It does not call providers, enforce organization policy, or persist usage. The initial catalog is `DEFAULT_MODEL_CATALOG` in `domain/routing.py`.

`CreateOrganization` and `GetOrganization` in `application/organizations/` create and load tenants through an injected `OrganizationRepository`. `CreateApiKey`, `RevokeApiKey`, and `ListApiKeysForOrganization` in `application/api_keys/` issue, revoke, and list credentials through injected `ApiKeyRepository`, `OrganizationRepository`, and `ApiKeyHasher` ports. They are not yet exposed over HTTP; operator routes remain later work. `AuthenticateApiKey` in `application/auth/` validates a plaintext bearer secret via prefix lookup + `ApiKeyHasher.verify_secret`, rejects revoked keys and missing organizations with a generic credential failure, rejects suspended organizations explicitly, and returns an `AuthenticatedPrincipal` for request context.

### Domain

The domain layer contains provider-agnostic business concepts and rules: model capabilities, organization entitlements, routing eligibility, usage and cost value objects, and domain errors.

A domain rule belongs here when it would still apply if FastAPI, PostgreSQL, Redis, and every provider were replaced.

Domain contracts under `domain/` include provider-neutral text generation (`MessageRole`, `Message`, `GenerationRequest`, `TokenUsage`, `GenerationResponse`), model routing (`ModelRoute`, `DEFAULT_MODEL_CATALOG`, `resolve_model_route`, `UnsupportedModelError`), organization tenancy (`Organization`, `OrganizationStatus`, slug/name invariants, and organization lifecycle errors), API-key credentials (`ApiKey`, `ApiKeyMetadata`, `ApiKeyStatus`, revoke invariants, and key lifecycle errors), and usage accounting (`UsageRecord`, `ModelPricing`, `estimate_cost_usd`). These types do not know about HTTP, SDKs, or SQLAlchemy. Plaintext API-key secrets are never part of the persisted domain entity.

### Ports

Ports are stable interfaces required by application use cases. They describe capabilities, not technologies: for example, an organization repository, model invocation client, cache, clock, or telemetry emitter.

Ports prevent use cases from depending on concrete adapters. They should be introduced only where a real external boundary or test seam exists.

`ModelProvider` in `ports/model_provider.py` is an asynchronous `generate` contract that accepts a `GenerationRequest` and returns a `GenerationResponse`. Concrete adapters under `providers/` implement this interface.

`OrganizationRepository` in `ports/organization_repository.py` defines async `add`, `get_by_id`, and `get_by_slug` for organization persistence. `SqlAlchemyOrganizationRepository` under `infrastructure/db/repositories/` implements it.

`ApiKeyRepository` in `ports/api_key_repository.py` defines async `add`, `get_by_id`, `list_by_organization`, `find_by_prefix`, and `save` for credential persistence. `ApiKeyHasher` in `ports/api_key_hasher.py` defines `generate_secret`, `hash_secret`, and `verify_secret` so application code can create and check keys without depending on a crypto library. `UsageRepository` in `ports/usage_repository.py` defines async `add`, `get_by_id`, and `get_by_request_id` for usage accounting. `CostEstimator` in `ports/cost_estimator.py` estimates USD cost from provider/model/token usage. `SqlAlchemyApiKeyRepository`, `SqlAlchemyUsageRepository`, `Argon2ApiKeyHasher` (argon2id via `argon2-cffi`), and `StaticCostEstimator` implement these ports under infrastructure.

### Providers

Provider adapters implement model-invocation ports for OpenAI, Anthropic, Gemini, and future providers. They translate AI Runtime's provider-neutral requests and responses to each vendor's SDK or HTTP API.

The first concrete adapter is `OpenAIModelProvider` under `providers/openai/`. It implements `ModelProvider` by mapping `GenerationRequest` / `GenerationResponse` to the OpenAI Chat Completions HTTP API using `httpx`. It does not decide routing, authorization, retries, failover, streaming, or tool calling. The composition root registers it with `ModelRouter` under the name `"openai"`.

Providers do not decide which model to select, whether an organization is authorized, or how usage is persisted.

### Infrastructure

Infrastructure contains concrete external integrations: SQLAlchemy repositories, database sessions, Redis clients, HTTP clients, AWS services, migrations, and configuration of external resources.

The infrastructure package `infrastructure/db/` constructs the async SQLAlchemy engine (`create_db_engine`) and session factory (`create_session_factory`) for PostgreSQL via asyncpg, defines the shared ORM `Base`, and hosts declarative models under `infrastructure/db/models/` plus repository adapters under `infrastructure/db/repositories/`. The API composition root stores the engine and session factory on the application lifespan and exposes request-scoped `AsyncSession` injection through `get_db_session`.

The infrastructure package `infrastructure/redis/` constructs the shared async Redis client (`create_redis_client`) and adapters for organization token-bucket rate limiting (`RedisRateLimiter`) and Idempotency-Key coordination (`RedisIdempotencyStore`). The API lifespan stores the Redis client on `app.state.redis`. Rate limiting and idempotency fail open when Redis is unavailable.

Schema changes are versioned with Alembic (`alembic.ini` and `alembic/` at the repository root). `alembic/env.py` uses async SQLAlchemy, imports ORM models so they register on `Base.metadata`, and resolves the database URL through `get_alembic_database_url()` / `Settings`. Revision `0001_baseline` is an empty baseline; `0002_organizations` creates the `organizations` table; `0003_api_keys` creates the `api_keys` table (organization FK, non-secret `prefix`, argon2id `secret_hash`, status, timestamps); `0004_usage_records` creates the `usage_records` table (unique `request_id`, organization/API-key FKs, provider/model, nullable token counts and estimated USD cost).

### Telemetry

Telemetry provides structured logs, traces, metrics, audit events, and usage/cost signals. It is invoked through explicit interfaces so observability remains consistent and does not leak framework concerns into business rules.

The first telemetry capability is structured JSON request logging in `telemetry/logging.py`, configured during application bootstrap. Request lifecycle logs are emitted by API middleware and include `request_id`, HTTP method, path, status code, and duration. Logs intentionally exclude secrets, authorization headers, and message bodies.

### Configuration

Configuration provides typed, environment-based settings and startup validation. Secrets are referenced through configuration and resolved by the deployment environment; they are never committed to the repository.

## Expected request flow

```text
HTTP request
  -> API validates and maps input
  -> Application use case authorizes and coordinates work
  -> Domain policies evaluate eligibility and routing rules
  -> Port delegates to a provider or infrastructure adapter
  -> Application records outcome and emits telemetry
  -> API maps the result or known error to HTTP
```

This flow is illustrative, not a requirement that every request use every layer. Simple health or readiness endpoints may be intentionally thinner.

## Package direction

The planned source layout is:

```text
src/ai_runtime/
  api/
  application/
  domain/
  ports/
  providers/
  infrastructure/
  telemetry/
  config/
```

Packages will be created as the relevant feature is implemented. Empty packages are avoided because directory structure alone does not provide an architectural boundary.

The `src/` layout requires the package to be installed before running tests or local tooling. Development and CI use an editable install (`pip install -e ".[dev]"`); imports resolve through the installed distribution, not by adding the repository to `PYTHONPATH`. This ensures tests exercise the distributable artifact rather than accidentally importing source files from the working tree.

## Boundary tests

As code is added, the project should enforce these rules with focused architecture tests and code review. At minimum, tests should ensure that `domain` and `application` do not import external frameworks or provider SDKs.

## Decision records

Significant, durable decisions are recorded as Architecture Decision Records (ADRs) under `docs/adr/`. An ADR captures the context, decision, consequences, and alternatives at the time of the choice. Current records: [ADR 0001](adr/0001-lightweight-clean-architecture.md) (ports and adapters) and [ADR 0002](adr/0002-static-model-catalog-routing.md) (static model catalog).

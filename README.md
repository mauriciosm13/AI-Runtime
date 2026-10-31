# AI Runtime

AI Runtime is an open-source infrastructure platform for AI-powered applications.

Applications integrate with one provider-agnostic API instead of coupling directly to OpenAI, Anthropic, Gemini, or future model providers. AI Runtime will own the cross-cutting runtime concerns required to operate those integrations reliably.

## Scope

The platform is intended to provide, incrementally:

- provider abstraction and model routing;
- authentication, organizations, and API keys;
- streaming and tool execution;
- context engineering, prompt building, and memory;
- caching, retries, failover, and cost tracking;
- observability, metrics, and auditability;
- deployment tooling and SDKs.

AI Runtime is infrastructure. It is not a chatbot, prompt playground, workflow builder, model-training system, or vector database.

## Architecture

The project uses a lightweight Clean Architecture. Business rules and use cases remain independent of HTTP, persistence, cloud services, and model-provider SDKs.

```text
Client
  -> API
  -> Application
  -> Domain
  <- Ports
  <- Infrastructure / Providers / Telemetry
```

See [the architecture guide](docs/architecture.md) for layer responsibilities and dependency rules. Architectural decisions are recorded as ADRs under [docs/adr/](docs/adr/), including [ADR 0001](docs/adr/0001-lightweight-clean-architecture.md), [ADR 0002](docs/adr/0002-static-model-catalog-routing.md), [ADR 0003](docs/adr/0003-bounded-provider-retries-failover.md), [ADR 0004](docs/adr/0004-sse-streaming-boundary.md), [ADR 0005](docs/adr/0005-tool-calling-contract.md), [ADR 0006](docs/adr/0006-opt-in-response-cache.md), [ADR 0007](docs/adr/0007-metrics-tracing-audit.md), [ADR 0008](docs/adr/0008-prompt-templates-and-context-builder.md), [ADR 0009](docs/adr/0009-aws-terraform-foundation.md), [ADR 0010](docs/adr/0010-ecr-image-pipeline-and-ecs-service.md), and [ADR 0011](docs/adr/0011-python-sdk.md).

## Foundation

The foundational system-design documents define the product boundary before runtime code is added:

- [Requirements](docs/foundation/requirements.md)
- [Data architecture](docs/foundation/data-architecture.md)
- [API design](docs/foundation/api-design.md)

## Current status

The project is a FastAPI application with typed environment configuration and an operational liveness endpoint at `GET /health`. Provider-neutral generation contracts live in `domain/`, `ports/` defines external capability interfaces (`ModelProvider`, `OrganizationRepository`, `ApiKeyRepository`, `ApiKeyHasher`, `UsageRepository`, `CostEstimator`, `ResponseCache`), and `application/` contains use cases (`CreateResponse`, `ModelRouter`, `CreateOrganization`, `GetOrganization`, `CreateApiKey`, `RevokeApiKey`, `ListApiKeysForOrganization`, `AuthenticateApiKey`). Concrete provider adapters are `OpenAIModelProvider` (`providers/openai/`, OpenAI Chat Completions over `httpx`), `AnthropicModelProvider` (`providers/anthropic/`, Anthropic Messages over `httpx`), and `GeminiModelProvider` (`providers/gemini/`, Gemini generateContent over `httpx`). `CreateResponse` resolves the requested model through `ModelRouter` against `DEFAULT_MODEL_CATALOG` (`gpt-4o`, `gpt-4o-mini` → `openai`; `claude-3-5-sonnet-20241022` → `anthropic`; `gemini-2.5-flash` → `gemini`) before calling a provider. `POST /v1/responses` requires `Authorization: Bearer airt_...`, runs `AuthenticateApiKey` (prefix lookup + argon2id verify, suspended-org rejection), then `CreateResponse` through HTTP with Pydantic schemas, dependency injection, and a shared `httpx.AsyncClient` managed by the application lifespan. Clients may set `stream: true` to receive Server-Sent Events (`response.delta`, `response.completed`, `response.error`); omitting `stream` or setting `false` keeps the JSON contract. `Idempotency-Key` is rejected on streaming requests. Clients may set `cache: true` on non-streaming requests to replay an identical payload from Redis (`cached: true` on hit); `cache` plus `stream` is rejected. Usage is recorded after a completed stream, not after a mid-stream failure. After a successful provider response, `CreateResponse` persists a `UsageRecord` (tokens + estimated USD cost via `StaticCostEstimator`) keyed by `request_id`, with `provider` taken from the resolved route. `GET /health` and `GET /metrics` stay unauthenticated. `GET /metrics` exposes Prometheus text for HTTP and generation counters. Successful generations write an `audit_events` row without prompt or response content. Client-facing errors use a standardized provider-neutral envelope with stable error codes (`unauthorized`, `forbidden`, `unsupported_model`, …) and a per-request correlation identifier (`X-Request-ID`). Structured JSON request logs record request start and completion with the same identifier and never log Authorization headers or secrets. Persistence wiring uses SQLAlchemy 2 async with asyncpg: the application lifespan owns the engine and session factory, and FastAPI can inject request-scoped `AsyncSession` values. Organization tenancy is modeled in `domain/organization.py`, persisted through `SqlAlchemyOrganizationRepository` and the `organizations` table (Alembic revision `0002_organizations`). API keys are modeled in `domain/api_key.py`, hashed at rest with argon2id (`Argon2ApiKeyHasher`), persisted through `SqlAlchemyApiKeyRepository` and the `api_keys` table (Alembic revision `0003_api_keys`). Usage accounting is modeled in `domain/usage.py` and persisted through `SqlAlchemyUsageRepository` and the `usage_records` table (Alembic revision `0004_usage_records`). Create returns the plaintext `airt_...` secret once; only prefix + hash are stored. `POST /v1/responses` also accepts `prompt: {name, version?, variables}` instead of `messages` to render an organization-scoped, versioned prompt template (managed through `POST /v1/prompts` and `GET /v1/prompts/{name}`), plus an opt-in `context` budget with truncation; templates are stored as configuration and rendered content is never persisted. AWS network, ECR, an ECS Fargate service, RDS PostgreSQL, ElastiCache Redis, a Secrets Manager secret, CloudWatch alarms and a dashboard, and a manual deploy workflow are defined in `infra/terraform` and `.github/workflows/deploy.yml` ([ADR 0009](docs/adr/0009-aws-terraform-foundation.md), [ADR 0010](docs/adr/0010-ecr-image-pipeline-and-ecs-service.md)). CI validates Terraform and does not apply it. Provider API keys go into Secrets Manager, not into the task environment. The load balancer listens on HTTP until a certificate exists, and ElastiCache traffic is not encrypted in transit. A separate Python client in `sdk/python` (`ai_runtime_sdk`) calls `POST /v1/responses` and the prompt routes, including SSE streaming ([ADR 0011](docs/adr/0011-python-sdk.md)). Operator HTTP routes for organizations and API keys are implemented under `/v1/organizations` and `/v1/api_keys` (including rotate) and require `AI_RUNTIME_OPERATOR_TOKEN`; usage reporting/quotas and persisted routing policies are not implemented yet.

## Repository layout

```text
src/
  ai_runtime/          # distributable application package
    api/               # FastAPI application factory, routes, schemas, dependencies, middleware
    application/       # use cases (responses, routing, organizations, api_keys, auth, prompts, context)
    config/            # typed Settings loaded from the environment
    domain/            # provider-neutral generation, routing, organization, API-key, usage, prompts, and audit contracts
    ports/             # interfaces (providers, repositories, rate limit, idempotency, cache, audit, metrics)
    infrastructure/    # SQLAlchemy, ORM models, repositories, Redis, argon2id hasher, static pricing
    providers/         # concrete model-provider adapters (OpenAI, Anthropic, and Gemini via httpx)
    telemetry/         # structured logs, in-process metrics, and trace spans
alembic/               # Alembic env and version scripts
alembic.ini            # Alembic configuration (URL from Settings)
tests/                 # test suite
.github/               # GitHub Actions (quality, SDK, Terraform, Docker, deploy, Conventional Commits)
.commitlintrc.yaml     # commitlint rules for Conventional Commits
Dockerfile             # multi-stage image for local execution (includes Alembic)
compose.yaml           # Docker Compose stack (Postgres + migrate + API)
.env.example           # environment template for Compose runs
.dockerignore          # build context exclusions
infra/terraform/       # AWS network, ECS, ALB, ECR, RDS, ElastiCache, Secrets Manager, CloudWatch (no apply in CI)
sdk/python/            # Python client (ai-runtime-sdk); HTTP only, not imported by the server
```

The project uses a `src/` layout so tests and local tooling exercise the installed package rather than accidentally importing source code from the repository root. Architecture-specific packages are added only when their first use case requires them.

## Python SDK

The client in `sdk/python` calls the HTTP API. It does not install the server.

```bash
pip install -e sdk/python
```

```python
from ai_runtime_sdk import AIRuntime

with AIRuntime(api_key="airt_...", base_url="http://127.0.0.1:8000") as client:
    response = client.responses.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
```

`AsyncAIRuntime` exposes the same `responses` and `prompts` resources. See [sdk/python/README.md](sdk/python/README.md) and [ADR 0011](docs/adr/0011-python-sdk.md).

## Configuration

Application settings are loaded from environment variables with the `AI_RUNTIME_` prefix via `pydantic-settings`. Values are validated at construction time and injected into the application factory; there is no process-wide mutable settings singleton.

| Variable | Field | Type | Default |
| --- | --- | --- | --- |
| `AI_RUNTIME_APP_NAME` | `app_name` | `str` | `AI Runtime` |
| `AI_RUNTIME_ENVIRONMENT` | `environment` | `local` \| `development` \| `staging` \| `production` | `local` |
| `AI_RUNTIME_DEBUG` | `debug` | `bool` | `false` |
| `AI_RUNTIME_LOG_LEVEL` | `log_level` | `str` | `INFO` |
| `AI_RUNTIME_OPENAI_API_KEY` | `openai_api_key` | `str` | `""` |
| `AI_RUNTIME_OPENAI_BASE_URL` | `openai_base_url` | `str` | `https://api.openai.com/v1` |
| `AI_RUNTIME_ANTHROPIC_API_KEY` | `anthropic_api_key` | `str` | `""` |
| `AI_RUNTIME_ANTHROPIC_BASE_URL` | `anthropic_base_url` | `str` | `https://api.anthropic.com` |
| `AI_RUNTIME_GEMINI_API_KEY` | `gemini_api_key` | `str` | `""` |
| `AI_RUNTIME_GEMINI_BASE_URL` | `gemini_base_url` | `str` | `https://generativelanguage.googleapis.com` |
| `AI_RUNTIME_DATABASE_URL` | `database_url` | `str` (`postgresql+asyncpg://...`) | `postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime` |
| `AI_RUNTIME_REDIS_URL` | `redis_url` | `str` (`redis://` or `rediss://`) | `redis://localhost:6379/0` |
| `AI_RUNTIME_RATE_LIMIT_REQUESTS_PER_MINUTE` | `rate_limit_requests_per_minute` | `int` | `60` |
| `AI_RUNTIME_RATE_LIMIT_BURST` | `rate_limit_burst` | `int` | `60` |
| `AI_RUNTIME_IDEMPOTENCY_TTL_SECONDS` | `idempotency_ttl_seconds` | `int` | `86400` |
| `AI_RUNTIME_RESPONSE_CACHE_TTL_SECONDS` | `response_cache_ttl_seconds` | `int` | `3600` |
| `AI_RUNTIME_PROVIDER_MAX_RETRIES` | `provider_max_retries` | `int` | `2` |
| `AI_RUNTIME_PROVIDER_RETRY_BASE_DELAY_SECONDS` | `provider_retry_base_delay_seconds` | `float` | `0.25` |
| `AI_RUNTIME_PROVIDER_FAILOVER_ENABLED` | `provider_failover_enabled` | `bool` | `true` |

## Request correlation

Every HTTP request receives a correlation identifier exposed as the `X-Request-ID` response header. Clients may send their own value in the same header; when absent or invalid, the server generates one in the form `req_<uuid>`. Error responses include the same identifier in `error.request_id`. Structured JSON logs for request start and completion use the same value for correlation.

This identifier tracks the HTTP request lifecycle. It is distinct from `response.id`, which identifies a model generation result.

## Local development

AI Runtime targets Python 3.13. Run all commands from the repository root (the directory that contains `pyproject.toml`). Create an isolated environment, install the package in editable mode with development tools, then run the quality checks:

```bash
python3.13 -m venv .venv
# macOS + iCloud Documents: clear UF_HIDDEN so Python 3.13 loads editable .pth files
chflags -R nohidden .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
# Re-clear after install; iCloud may re-hide new .pth files under .venv
chflags -R nohidden .venv

pytest
ruff check .
ruff format --check .
mypy
```

The package must be installed before testing. This preserves the guarantees of the `src/` layout and prevents tests from importing code directly from the working tree.

Confirm the editable install resolved the source tree:

```bash
python -c "import ai_runtime; print(ai_runtime.__file__)"
```

The printed path should include `src/ai_runtime/`.

### Troubleshooting

- **`ModuleNotFoundError: No module named 'ai_runtime'`** — activate the virtual environment and run `pip install -e ".[dev]"` from the repository root. Do not set `PYTHONPATH=src`; tests and tooling expect the installed distribution.
- **Wrong virtual environment** — ensure `.venv` was created in the repository root, not in a parent directory.
- **Editable install ignored on macOS (iCloud)** — if `Documents` syncs via iCloud, files under `.venv` get the `UF_HIDDEN` flag and Python 3.13 skips the editable `.pth`. Run `chflags -R nohidden .venv`, then confirm with `python -c "import ai_runtime"`. Prefer creating the venv outside iCloud-synced folders when possible.

## Continuous integration

Pull requests and pushes to `main` run four GitHub Actions workflows:

| Workflow | What it checks |
|---|---|
| [CI](.github/workflows/ci.yml) | Editable install (`pip install -e ".[dev]"`), unit tests (`pytest` with Postgres 17), `ruff check`, `ruff format --check`, `mypy`, Terraform `fmt` plus `validate`, and the same checks for `sdk/python` |
| [Deploy](.github/workflows/deploy.yml) | Builds and pushes an image tagged with the commit SHA to ECR on every push to `main`; deploys to ECS only on a manual run, through GitHub OIDC |
| [Docker](.github/workflows/docker.yml) | Unit tests (`pytest`), then multi-stage image build (`ai-runtime:ci`), no registry push |
| [Conventional Commits](.github/workflows/conventional-commits.yml) | Commit messages (`commitlint`) and PR titles (semantic pull request) |

Local development and CI follow the same install flow. A failing check blocks merge until the suite is green.

Commit and PR title format is documented in [the git workflow](docs/GIT_WORKFLOW.md). Docker and production images use a non-editable install (`pip install .`) because they ship a fixed artifact rather than a live source tree.

## Running the API locally

With the editable install active, start the application using Uvicorn's factory mode:

```bash
AI_RUNTIME_ENVIRONMENT=local \
AI_RUNTIME_DEBUG=true \
uvicorn ai_runtime.api.app:create_app --factory --reload
```

While the server is running:

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Create response: `POST /v1/responses` with `Authorization: Bearer airt_...` (set the API key for the provider behind the requested model: OpenAI, Anthropic, or Gemini)
- OpenAPI (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI JSON: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

```bash
curl -i http://127.0.0.1:8000/health
```

The response includes an `X-Request-ID` header for request correlation.

Example generation request:

```bash
curl -sS http://127.0.0.1:8000/v1/responses \
  -H "Authorization: Bearer airt_..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Running with Docker

Build a reproducible local image (Python 3.13, non-root process, production package install without development extras):

```bash
docker build --tag ai-runtime:local .
```

Run the container and map port 8000:

```bash
docker run --rm \
  --publish 8000:8000 \
  --env AI_RUNTIME_ENVIRONMENT=local \
  --env AI_RUNTIME_DEBUG=false \
  ai-runtime:local
```

In another terminal, confirm liveness:

```bash
curl -i http://127.0.0.1:8000/health
```

The expected response is `200 OK` with `{"status":"ok"}`.

## Database migrations

Alembic is configured at the repository root (`alembic.ini` + `alembic/`). The async environment loads `AI_RUNTIME_DATABASE_URL` through the same `Settings` object as the API and targets `ai_runtime.infrastructure.db.base.Base.metadata`.

Revision `0001_baseline` is an intentional empty migration that establishes Alembic version tracking. Later revisions create `organizations` (`0002`), `api_keys` (`0003`), `usage_records` (`0004`), organization policies and model entitlements (`0005`), `prompt_templates` (`0007`), and `audit_events` (`0008`). There is no revision `0006`.

From the repository root (with Postgres reachable at the configured URL):

```bash
alembic upgrade head          # apply migrations
alembic downgrade -1          # revert one revision
alembic current               # show applied revision
alembic revision --autogenerate -m "describe change"  # draft from Base.metadata
```

Autogenerate only sees models imported into the metadata graph. Import new ORM modules from `infrastructure` (or `env.py`) when they are added so Alembic can detect them.

## Running with Docker Compose

For a repeatable local stack (PostgreSQL + Redis + migrations + API), use Docker Compose from the repository root:

```bash
cp .env.example .env
# Edit .env and set AI_RUNTIME_OPENAI_API_KEY when calling POST /v1/responses.

docker compose up --build
```

Compose starts PostgreSQL 17 and Redis 7, waits until both are healthy, runs `alembic upgrade head` via the one-shot `migrate` service, then starts the API. The API receives `AI_RUNTIME_DATABASE_URL` and `AI_RUNTIME_REDIS_URL` pointed at the `postgres` / `redis` hostnames. Ports 8000 (API), 5432 (Postgres), and 6379 (Redis) are published to the host. Optional variables load from `.env`; Compose `environment` values override matching keys from that file.

`POST /v1/responses` enforces a platform default per-organization token-bucket rate limit and honors an optional `Idempotency-Key` header (replay on success, `409` while in progress). Clients may set `cache: true` to store a successful non-streaming response in Redis for a short TTL and replay it for identical requests in the same organization. When Redis is down, rate limiting, idempotency, and cache fail open.

Useful commands:

```bash
docker compose up --build -d              # run in the background
docker compose ps                         # service status and health
docker compose logs -f api                # follow API logs
docker compose run --rm migrate           # re-run migrations only
docker compose down                       # stop and remove containers
```

While the stack is running, the same endpoints documented above are available at [http://127.0.0.1:8000](http://127.0.0.1:8000). To run Uvicorn or Alembic on the host against Compose Postgres/Redis, keep the default localhost URLs from `.env.example`.

`GET /health` does not require a live database or Redis connection; it remains a liveness probe.

## Technology stack

- Python 3.13
- FastAPI and Pydantic v2
- SQLAlchemy 2 and Alembic
- PostgreSQL and Redis
- Docker, Docker Compose, Terraform, and GitHub Actions
- AWS in Terraform: VPC, ALB, ECS Fargate, ECR, IAM, RDS PostgreSQL, ElastiCache Redis, Secrets Manager, and CloudWatch logs, alarms, and a dashboard

## Development principles

- Keep HTTP endpoints thin and free of business logic.
- Prefer explicit interfaces and dependency injection.
- Keep provider adapters free of authorization and routing policy.
- Use asynchronous I/O for external dependencies.
- Treat tests, types, structured telemetry, and documentation as product work.
- Make changes in small, reviewable increments.

## Roadmap

Delivered in this repository: provider-neutral generation, OpenAI / Anthropic / Gemini adapters, routing, retries and failover, API-key auth, organizations, usage and cost, Redis rate limit, idempotency and response cache, streaming, tool calling, prompts and context, metrics, tracing and audit, the AWS stack (network, ECR, ECS, RDS, ElastiCache, Secrets Manager, CloudWatch), and the Python SDK in `sdk/python`.

Still open: HTTP ingestion for semantic chunks, MCP tools, and example LangChain and multi-agent clients. JWT is not part of the current auth design. pgvector Terraform wiring remains a gap.

Delivered for learning slice: OpenAI embedding adapter, organization-scoped pgvector retrieval, and opt-in RAG on `POST /v1/responses`.

## Contributing

Architecture and implementation changes should be scoped to a small, reviewable task and include the relevant tests and documentation. Consult [AGENTS.md](AGENTS.md) for repository engineering standards and [the git workflow](docs/GIT_WORKFLOW.md) for Conventional Commits.

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

See [the architecture guide](docs/architecture.md) for layer responsibilities and dependency rules. The initial architectural decision is recorded in [ADR 0001](docs/adr/0001-lightweight-clean-architecture.md).

## Foundation

The foundational system-design documents define the product boundary before runtime code is added:

- [Requirements](docs/foundation/requirements.md)
- [Data architecture](docs/foundation/data-architecture.md)
- [API design](docs/foundation/api-design.md)

## Current status

The project has a minimal FastAPI bootstrap with typed environment configuration and an operational liveness endpoint at `GET /health`. Provider-neutral generation contracts live in `domain/`, `ports/` defines external capability interfaces (`ModelProvider`, `OrganizationRepository`, `ApiKeyRepository`, `ApiKeyHasher`, `UsageRepository`, `CostEstimator`), and `application/` contains use cases (`CreateResponse`, `CreateOrganization`, `GetOrganization`, `CreateApiKey`, `RevokeApiKey`, `ListApiKeysForOrganization`, `AuthenticateApiKey`). The first concrete provider adapter is `OpenAIModelProvider` under `providers/openai/`, which calls OpenAI Chat Completions over `httpx`. `POST /v1/responses` requires `Authorization: Bearer airt_...`, runs `AuthenticateApiKey` (prefix lookup + argon2id verify, suspended-org rejection), then `CreateResponse` through HTTP with Pydantic schemas, dependency injection, and a shared `httpx.AsyncClient` managed by the application lifespan. After a successful provider response, `CreateResponse` persists a `UsageRecord` (tokens + estimated USD cost via `StaticCostEstimator`) keyed by `request_id`. `GET /health` stays unauthenticated. Client-facing errors use a standardized provider-neutral envelope with stable error codes (`unauthorized`, `forbidden`, …) and a per-request correlation identifier (`X-Request-ID`). Structured JSON request logs record request start and completion with the same identifier and never log Authorization headers or secrets. Persistence wiring uses SQLAlchemy 2 async with asyncpg: the application lifespan owns the engine and session factory, and FastAPI can inject request-scoped `AsyncSession` values. Organization tenancy is modeled in `domain/organization.py`, persisted through `SqlAlchemyOrganizationRepository` and the `organizations` table (Alembic revision `0002_organizations`). API keys are modeled in `domain/api_key.py`, hashed at rest with argon2id (`Argon2ApiKeyHasher`), persisted through `SqlAlchemyApiKeyRepository` and the `api_keys` table (Alembic revision `0003_api_keys`). Usage accounting is modeled in `domain/usage.py` and persisted through `SqlAlchemyUsageRepository` and the `usage_records` table (Alembic revision `0004_usage_records`). Create returns the plaintext `airt_...` secret once; only prefix + hash are stored. Operator HTTP routes for organizations/API keys, usage reporting/quotas, and provider routing are not implemented yet.

## Repository layout

```text
src/
  ai_runtime/          # distributable application package
    api/               # FastAPI application factory, routes, schemas, dependencies, middleware
    application/       # use cases (responses, organizations, api_keys, auth)
    config/            # typed Settings loaded from the environment
    domain/            # provider-neutral generation, organization, API-key, and usage contracts
    ports/             # interfaces (ModelProvider, repositories, ApiKeyHasher, CostEstimator)
    infrastructure/    # SQLAlchemy, ORM models, repositories, argon2id hasher, static pricing
    providers/         # concrete model-provider adapters (OpenAI via httpx)
    telemetry/         # structured logging configuration
alembic/               # Alembic env and version scripts
alembic.ini            # Alembic configuration (URL from Settings)
tests/                 # test suite
Dockerfile             # multi-stage image for local execution (includes Alembic)
compose.yaml           # Docker Compose stack (Postgres + migrate + API)
.env.example           # environment template for Compose runs
.dockerignore          # build context exclusions
```

The project uses a `src/` layout so tests and local tooling exercise the installed package rather than accidentally importing source code from the repository root. Architecture-specific packages are added only when their first use case requires them.

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
| `AI_RUNTIME_DATABASE_URL` | `database_url` | `str` (`postgresql+asyncpg://...`) | `postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime` |

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

Pull requests and pushes to `main` automatically run the same quality checks through GitHub Actions: editable install (`pip install -e ".[dev]"`), `pytest`, `ruff check`, `ruff format --check`, and `mypy`. Local development and CI follow the same install flow. A failing check blocks merge until the suite is green.

Docker and production images use a non-editable install (`pip install .`) because they ship a fixed artifact rather than a live source tree.

## Running the API locally

With the editable install active, start the application using Uvicorn's factory mode:

```bash
AI_RUNTIME_ENVIRONMENT=local \
AI_RUNTIME_DEBUG=true \
uvicorn ai_runtime.api.app:create_app --factory --reload
```

While the server is running:

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Create response: `POST /v1/responses` (requires `AI_RUNTIME_OPENAI_API_KEY` for real provider calls)
- OpenAPI (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI JSON: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

```bash
curl -i http://127.0.0.1:8000/health
```

The response includes an `X-Request-ID` header for request correlation.

Example generation request:

```bash
curl -sS http://127.0.0.1:8000/v1/responses \
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

Revision `0001_baseline` is an intentional empty migration that establishes Alembic version tracking. Revision `0002_organizations` creates the `organizations` table (`id`, `name`, unique `slug`, `status`, timestamps). Revision `0003_api_keys` creates the `api_keys` table (`id`, `organization_id` FK, optional `name`, indexed `prefix`, argon2id `secret_hash`, `status`, timestamps).

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

`POST /v1/responses` enforces a platform default per-organization token-bucket rate limit and honors an optional `Idempotency-Key` header (replay on success, `409` while in progress). When Redis is down, both features fail open.

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

## Planned technology stack

- Python 3.13
- FastAPI and Pydantic v2
- SQLAlchemy 2 and Alembic
- PostgreSQL and Redis
- Docker, Docker Compose, Terraform, and GitHub Actions
- AWS deployment targets: ECS Fargate, RDS, ElastiCache, ALB, ECR, IAM, Secrets Manager, and CloudWatch

## Development principles

- Keep HTTP endpoints thin and free of business logic.
- Prefer explicit interfaces and dependency injection.
- Keep provider adapters free of authorization and routing policy.
- Use asynchronous I/O for external dependencies.
- Treat tests, types, structured telemetry, and documentation as product work.
- Make changes in small, reviewable increments.

## Roadmap

1. Project discovery, architecture, and engineering standards
2. Application bootstrap, testing, linting, Docker, and CI
3. Authentication, organizations, API keys, and JWT
4. Provider layer and model routing
5. Streaming and tool calling
6. Context engine
7. AWS deployment and observability
8. SDKs

## Contributing

Architecture and implementation changes should be scoped to a small, reviewable task and include the relevant tests and documentation. Consult [AGENTS.md](AGENTS.md) for repository engineering standards.

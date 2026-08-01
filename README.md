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

The project has a minimal FastAPI bootstrap with an operational liveness endpoint at `GET /health`. Versioned business APIs, authentication, persistence, and providers are not implemented yet.

## Repository layout

```text
src/
  ai_runtime/  # distributable application package
tests/         # test suite
```

The project uses a `src/` layout so tests and local tooling exercise the installed package rather than accidentally importing source code from the repository root. Architecture-specific packages are added only when their first use case requires them.

## Local development

AI Runtime targets Python 3.13. Create an isolated environment, install the package with development tools, then run the quality checks:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pytest
ruff check .
ruff format --check .
mypy
```

The package must be installed before testing. This preserves the guarantees of the `src/` layout and prevents tests from importing code directly from the working tree.

## Continuous integration

Pull requests and pushes to `main` automatically run the same quality checks through GitHub Actions: `pytest`, `ruff check`, `ruff format --check`, and `mypy`. A failing check blocks merge until the suite is green.

## Running the API locally

With the editable install active, start the application using Uvicorn's factory mode:

```bash
uvicorn ai_runtime.api.app:create_app --factory --reload
```

While the server is running:

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- OpenAPI (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI JSON: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

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

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

The API layer owns FastAPI routes, HTTP request and response schemas, authentication extraction, exception-to-HTTP mapping, and dependency wiring. A route validates input, invokes one use case, and serializes the result. It contains no authorization policy, routing policy, provider selection, or persistence logic.

### Application

The application layer implements use cases. It coordinates domain policies with ports, transactions, provider calls, persistence, cache access, and telemetry. Examples include generating a completion, issuing an API key, and recording usage.

Application code expresses workflows; it does not contain HTTP-specific concerns or direct SQLAlchemy, Redis, AWS, or provider-SDK calls.

The first use case is `CreateResponse` in `application/responses/`. It receives a provider-neutral `GenerationRequest`, delegates generation to an injected `ModelProvider`, and returns the resulting `GenerationResponse`. It is not exposed via HTTP yet.

### Domain

The domain layer contains provider-agnostic business concepts and rules: model capabilities, organization entitlements, routing eligibility, usage and cost value objects, and domain errors.

A domain rule belongs here when it would still apply if FastAPI, PostgreSQL, Redis, and every provider were replaced.

The first concrete domain contracts live under `domain/` and describe provider-neutral text generation: `MessageRole`, `Message`, `GenerationRequest`, `TokenUsage`, and `GenerationResponse`. These types carry only generation invariants; they do not know about HTTP, SDKs, or routing.

### Ports

Ports are stable interfaces required by application use cases. They describe capabilities, not technologies: for example, an organization repository, model invocation client, cache, clock, or telemetry emitter.

Ports prevent use cases from depending on concrete adapters. They should be introduced only where a real external boundary or test seam exists.

The first port is `ModelProvider` in `ports/model_provider.py`: an asynchronous `generate` contract that accepts a `GenerationRequest` and returns a `GenerationResponse`. Concrete adapters under `providers/` implement this interface.

### Providers

Provider adapters implement model-invocation ports for OpenAI, Anthropic, Gemini, and future providers. They translate AI Runtime's provider-neutral requests and responses to each vendor's SDK or HTTP API.

The first concrete adapter is `OpenAIModelProvider` under `providers/openai/`. It implements `ModelProvider` by mapping `GenerationRequest` / `GenerationResponse` to the OpenAI Chat Completions HTTP API using `httpx`. It does not decide routing, authorization, retries, failover, streaming, or tool calling.

Providers do not decide which model to select, whether an organization is authorized, or how usage is persisted.

### Infrastructure

Infrastructure contains concrete external integrations: SQLAlchemy repositories, database sessions, Redis clients, HTTP clients, AWS services, migrations, and configuration of external resources.

### Telemetry

Telemetry provides structured logs, traces, metrics, audit events, and usage/cost signals. It is invoked through explicit interfaces so observability remains consistent and does not leak framework concerns into business rules.

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

## Boundary tests

As code is added, the project should enforce these rules with focused architecture tests and code review. At minimum, tests should ensure that `domain` and `application` do not import external frameworks or provider SDKs.

## Decision records

Significant, durable decisions are recorded as Architecture Decision Records (ADRs) under `docs/adr/`. An ADR captures the context, decision, consequences, and alternatives at the time of the choice.

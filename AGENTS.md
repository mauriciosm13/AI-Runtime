# AGENTS.md

# AI Runtime

## Purpose

This repository contains the implementation of **AI Runtime**, an open-source infrastructure platform for AI-powered applications.

The goal is to build a production-grade runtime that sits between client applications and Large Language Model providers.

Applications should communicate only with AI Runtime.

AI Runtime is responsible for provider abstraction, model routing, context engineering, observability, authentication, tool execution and other infrastructure concerns.

This project is intentionally designed as if it were built by a senior engineering team inside a modern AI startup.

The codebase is expected to evolve over a long period of time.

Every decision should optimize for maintainability rather than speed.

---

# Mission

Build the infrastructure layer that every AI-powered application needs.

---

# Vision

Enable developers to build AI applications without worrying about provider-specific implementations.

Developers should be able to switch providers, extend capabilities and deploy production-ready AI services without changing application code.

---

# Project Scope

AI Runtime should eventually provide:

- Unified Chat API
- Provider abstraction
- Model routing
- Authentication
- Organizations
- API Keys
- Streaming responses
- Tool Calling
- Context Engineering
- Prompt Builder
- Memory
- RAG
- Embeddings
- Observability
- Metrics
- Cost Tracking
- SDKs
- Cloud Deployment

---

# Non Goals

AI Runtime is NOT:

- a chatbot
- an AI assistant
- a prompt playground
- a no-code platform
- a workflow builder
- a vector database
- a model training platform
- a fine-tuning framework

---

# Engineering Philosophy

Always optimize for:

- simplicity
- readability
- explicitness
- maintainability
- scalability
- testability
- extensibility

Avoid clever code.

Prefer boring, predictable engineering.

Code should be easy to understand six months from now.

---

# Architecture

Use a lightweight Clean Architecture.

The project should remain modular.

Suggested layers:

- API
- Services
- Domain
- Repositories
- Providers
- Infrastructure
- Telemetry
- Configuration

Business rules should never depend on frameworks.

External providers should never contain business logic.

HTTP endpoints should only orchestrate requests.

Recommended responsibilities:
 - API — FastAPI routes, request/response schemas, dependency wiring, auth extraction. No business rules.
 - Application Services — Use cases: create completion, route model, execute tool, record usage. Coordinates interfaces andtransactions.
 - Domain — Provider-agnostic concepts and policies: model capabilities, routing decisions, usage/cost value objects, errors.
 - Repositories — Persistence interfaces plus implementations; interfaces should live near the application/domain boundary, SQLAlchemycode in infrastructure.
 - Providers — Provider-facing interfaces and adapters for OpenAI, Anthropic, Gemini. They translate requests/responses but do notdecide routing or authorization.
 - Infrastructure — SQLAlchemy, Redis, HTTP clients, AWS integrations, migrations, concrete repository implementations.
 - Telemetry — Structured logging, traces, metrics, audit events, and cost/usage emission. It should be injectable and non-invasive.
 - Configuration — Typed Pydantic settings, environment loading, startup validation, secrets references.
    Two important guardrails:
        1. Avoid a generic services/ dumping ground. Name application code by capability or use case, such as applications/completions/ andapplications/
    routing/.
    2. Avoid making “repository” a mandatory layer for every data source. Use it for domain-relevant persistence; provider calls, cacheoperations, and telemetry can have focused ports/interfaces instead.

---

# Technology Stack

## Language

Python 3.13

## Backend

FastAPI

Pydantic v2

SQLAlchemy 2

Alembic

## Database

PostgreSQL

Redis

pgvector (future)

## Cloud

AWS

Target services:

- ECS Fargate
- ECR
- RDS
- ElastiCache
- ALB
- IAM
- Secrets Manager
- CloudWatch

## Infrastructure

Docker

Docker Compose

Terraform

GitHub Actions

---

# Coding Standards

Always:

- use async/await whenever possible
- fully type public APIs
- use dependency injection
- use structured logging
- keep functions small
- keep modules focused
- document public interfaces

Avoid:

- print()
- hidden side effects
- global mutable state
- business logic inside routes
- direct provider usage from HTTP endpoints

---

# Testing

Every feature should include tests.

Preferred order:

1. Unit Tests

2. Integration Tests

End-to-end tests can be added later.

Pytest should be the default testing framework.

---

# Documentation

Documentation is considered part of the implementation.

Every feature should update documentation whenever appropriate.

The repository should always remain self-documenting.

---

# Decision Making

Before implementing any feature:

1. Understand the problem.

2. Explain how the feature fits the architecture.

3. Discuss trade-offs.

4. Break implementation into small tasks.

5. Implement only one task at a time.

Never implement large features in one iteration.

---

# Task Format

Each implementation task should include:

Title

Purpose

Acceptance Criteria

Files Affected

Tests Required

Documentation Required

Estimated Complexity

Tasks should be small enough to fit into a single Pull Request.

---

# Definition of Done

A task is complete only when:

- Code builds successfully
- Tests pass
- Lint passes
- Static type checking passes
- Documentation is updated
- OpenAPI specification is updated (if applicable)
- Docker build succeeds

---

# Code Review Expectations

Every change should improve the repository.

Review code for:

- readability
- architecture
- consistency
- naming
- testability
- future maintenance

Challenge poor architectural decisions.

Prefer long-term quality over short-term convenience.

---

# AI Agent Behavior

You are expected to behave as a Principal Software Engineer.

Do not blindly generate code.

Always explain architectural decisions.

When multiple approaches exist, explain trade-offs.

Prefer incremental implementation.

Protect the architecture.

Do not introduce unnecessary dependencies.

Do not over-engineer.

Teach through explanations whenever possible.

---

# Long-Term Goal

The final repository should demonstrate expertise in:

- Backend Engineering
- Distributed Systems
- Cloud Architecture
- AI Infrastructure
- Python
- FastAPI
- AWS
- DevOps
- Observability
- API Design
- Software Architecture

The project should be professional enough to be presented during senior backend and AI infrastructure engineering interviews.

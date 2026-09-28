# ADR 0011: Python SDK

## Status

Accepted

## Context

Roadmap item 30 asks for a Python SDK so applications can call AI Runtime without assembling HTTP requests themselves. The public contract is already `POST /v1/responses`, `POST /v1/prompts`, and `GET /v1/prompts/{name}`, including the error envelope and the SSE events from ADR 0004. The server package `ai-runtime` installs FastAPI, SQLAlchemy, Redis, and Alembic. A client that imported that package would take those dependencies on for no reason.

## Decision

1. The SDK is a separate distribution, `ai-runtime-sdk`, in `sdk/python`, imported as `ai_runtime_sdk`. The server does not depend on it, and it does not import `ai_runtime`.
2. It speaks only the implemented HTTP API. Sync `AIRuntime` and async `AsyncAIRuntime` expose `responses` and `prompts`. `base_url` is required because there is no hosted default.
3. `responses.create` is the non-streaming call. `responses.stream` sets `stream: true`, yields `ResponseDelta` events, then a `Response`. A `response.error` event raises `AIRuntimeError`. JSON errors before the first event raise the same type. The stream method has no idempotency or cache argument, because the API rejects those combinations.
4. Callers pass exactly one of `messages` or `prompt`. The client checks that locally. Other validation stays on the server.
5. Authentication is `Authorization: Bearer`. Optional `idempotency_key` and `request_id` map to `Idempotency-Key` and `X-Request-ID`. The API key is not included in `repr` or error messages. `request_id` on returned models is copied from the response header.
6. Response models ignore unknown JSON fields so additive changes inside `/v1` do not break existing clients.
7. Runtime dependencies are `httpx` and `pydantic`. Tests use `httpx.MockTransport` and do not start the server.

## Consequences

- An application depends on `ai-runtime-sdk` plus a base URL and an API key.
- Operator routes for organizations and API keys are not in the client, because those HTTP routes are not implemented.
- Embeddings, RAG, and MCP stay out of this client until their roadmap items exist.
- CI tests, lints, and type-checks the SDK on its own. The server test suite does not import it.

## Alternatives considered

- Putting the client inside `ai_runtime`: rejected. Installing the server would pull the API, database, and Redis stacks into every application.
- Generating the client from OpenAPI in this slice: rejected. The hand-written client covers the routes that exist today. Generation can replace it if the surface grows enough to drift.
- Matching the OpenAI Python SDK method names: rejected. This API's resource is `/v1/responses` with this runtime's schema, not the vendor Responses API.

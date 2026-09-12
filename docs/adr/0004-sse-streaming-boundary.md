# ADR 0004: SSE streaming boundary

## Status

Accepted

## Context

Roadmap item 22 requires opt-in streaming on the same public resource as non-streaming generation (`POST /v1/responses`). Foundation docs specify Server-Sent Events and the same authorization, routing, telemetry, and terminal usage semantics.

`ModelProvider` previously exposed only `generate()`. `ProviderExecutor` retries and failovers assume a single terminal `GenerationResponse`. Idempotency currently stores a completed JSON body. ADR 0003 left streaming retries out of scope.

## Decision

1. **Same resource, opt-in field** — Clients set `stream: true` on `POST /v1/responses`. The default remains JSON `ResponseSchema`.

2. **Domain events, vendor translation in adapters** — `ModelProvider.stream()` yields `GenerationDelta` values and a terminal `GenerationResponse`. OpenAI, Anthropic, and Gemini adapters map vendor streams; they do not retry, route, or persist usage.

3. **Resilience only before the first event** — `ProviderExecutor.stream` may retry and fail over until the first domain event is yielded. After that, the route is sticky. Mid-stream `ProviderError`s propagate to the API.

4. **JSON errors before start, SSE errors after start** — Failures raised before the first event use the existing JSON envelope. After the first SSE frame, failures are emitted as `event: response.error`.

5. **Usage on completed only** — One `UsageRecord` is written after the completed event. Mid-stream failures do not persist usage.

6. **No idempotent streaming in this slice** — `Idempotency-Key` + `stream: true` is rejected with `422` / `invalid_request`.

## Consequences

- Interactive clients can consume tokens incrementally without a second public resource.
- A stream that fails after the first token is not retried against another provider, avoiding mixed-model output.
- Clients that want idempotent retries of streaming calls must wait for a later slice or use non-streaming requests.

## Out of scope

- Idempotent replay of a completed stream.
- Partial usage when the client disconnects after upstream tokens were generated.
- Tool-call streaming events.

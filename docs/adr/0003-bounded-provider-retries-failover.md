# ADR 0003: Bounded provider retries and static failover

## Status

Accepted

## Context

Roadmap item 21 requires classifying provider failures and applying bounded retry or failover when a request is safe to retry. Adapters already raise `ProviderError`, and `CreateResponse` invoked a single provider with no retry or alternate route.

Requirements ([requirements.md](../foundation/requirements.md)) mandate provider-independent client errors, usage accounting aligned with the adapter that actually served the response, and retries only when safe (after failures, before a successful generation result is returned).

## Decision

1. **Classify adapter failures** — `ProviderError` carries `retryable` and optional `status_code`. OpenAI and Anthropic adapters mark HTTP `429`, `500`, `502`, `503`, and `504` plus transport failures as retryable; client errors and malformed payloads stay non-retryable.

2. **Application-layer execution** — `ProviderExecutor` in `application/resilience/` wraps `ModelRouter` and owns retry backoff and failover. Provider adapters remain unaware of retries and routing policy.

3. **Static failover catalog** — `DEFAULT_FAILOVER_CATALOG` in `domain/routing.py` maps a requested model to optional alternate catalog models (for example `gpt-4o` → `claude-3-5-sonnet-20241022`). Failover is enabled by default and configurable via `AI_RUNTIME_PROVIDER_FAILOVER_ENABLED`.

4. **Policy per route** — Before each route attempt, `CreateResponse` re-runs organization entitlements for that route's model. Routes denied by entitlement or missing adapters are skipped; monthly quota checks still apply per attempt.

5. **Configuration** — `AI_RUNTIME_PROVIDER_MAX_RETRIES` (default `2`, meaning up to three attempts on one route) and `AI_RUNTIME_PROVIDER_RETRY_BASE_DELAY_SECONDS` (default `0.25`, linear backoff multiplier) bound retry behavior.

## Consequences

- Transient upstream outages can recover without client changes; cross-provider failover improves availability when multiple adapters are registered.
- Usage rows record the provider that actually succeeded, which may differ from the client's requested model after failover.
- Failover model mapping is static in code until database-backed routing policies exist.
- Idempotency leases still release on failure; successful retries or failover complete the lease once.

## Out of scope

- Streaming retries, tool-call idempotency, and operator-editable failover policies in PostgreSQL.

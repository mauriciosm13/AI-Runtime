# ADR 0006: Opt-in organization-scoped response cache

## Status

Accepted

## Context

Roadmap item 24 requires response caching. Redis already coordinates rate limits and idempotency. Requirements forbid persisting prompt or response content by default. Idempotency is a caller-supplied key, not a content hash.

## Decision

1. Clients opt in with `cache: true` on non-streaming `POST /v1/responses`.
2. The cache key is `cache:resp:{organization_id}:{sha256(canonical request)}`. The canonical request is model, messages, tools, temperature, and max_output_tokens. The prompt is not stored.
3. Hits skip the provider and usage persistence. Auth, rate limit, and organization policy still run.
4. Redis failures fail open (miss).
5. `cache` plus `stream` is rejected. TTL is the only invalidation in this slice.
6. Idempotency remains a separate path and wins when a completed key exists.

## Consequences

- Repeat opted-in requests avoid provider cost inside the TTL.
- Response bodies live in Redis only when the client asks, for a bounded time.
- Cross-organization leakage is prevented by the key prefix.

# ADR 0008: Prompt templates as configuration and a stateless context builder

## Status

Accepted

## Context

Roadmap item 25 bundles prompt templates, context building, and persistent memory. Requirements forbid persisting end-user prompt or response content by default and require a retention policy before any such content is stored. The Owner approved splitting the item on 2026-09-18: this ADR covers **25a (prompt templates)** and **25b (context builder)**. Persistent memory (25c) stays out and is blocked on a retention policy.

## Decision

1. **Templates are configuration, not user content.** Operator-authored prompt templates are stored in PostgreSQL (`prompt_templates`), scoped by organization, as immutable versions of a named prompt. Variable values, rendered messages, and end-user messages are never persisted, logged, or written to usage or audit records.
2. **Resolution happens before `CreateResponse`.** `POST /v1/responses` accepts exactly one of `messages` or `prompt: {name, version?, variables}`. Rendered messages become the `GenerationRequest`, so providers, routing, retries, streaming, tools, the response cache, and idempotency are unchanged. Cache fingerprints hash rendered messages, so an equivalent `prompt` and raw `messages` request share a cache entry.
3. **Rendering is strict and single-pass.** Placeholders are `{{name}}` with `[A-Za-z_][A-Za-z0-9_]*`. The provided variables must equal the template placeholders. Values are substituted literally and never re-scanned, which prevents template injection through variable values. Template roles are `system`, `user`, `assistant`.
4. **Management API.** `POST /v1/prompts` creates the next immutable version and `GET /v1/prompts/{name}` lists versions, both authenticated with the organization's own API key. There is no update or delete in this slice.
5. **Context budget is opt-in.** The builder runs only when `prompt` or `context` is present, so existing `messages` requests behave exactly as before. The budget is the smallest context window across the requested model and, when failover is enabled, its failover candidates, minus `max_output_tokens`, capped by `context.max_input_tokens`. Over budget returns `422 context_length_exceeded`; with `context.truncate: true` the oldest non-system messages are dropped first. System messages and the latest turn are never dropped, and a tool call is never separated from its tool results.
6. **Token counting is an estimate.** `TokenCounter` is a port; the adapter is a conservative heuristic (`ceil(chars / 3)` plus a per-message overhead) with no new dependency. It is not a billing figure. Provider errors remain the backstop.
7. **Static context windows.** `DEFAULT_MODEL_CONTEXT_WINDOWS` sits next to the model catalog (see ADR 0002). Verified on 2026-09-18: `gpt-4o` and `gpt-4o-mini` 128,000; `gemini-2.5-flash` 1,048,576. Not verified: `claude-3-5-sonnet-20241022` (200,000), which no longer appears in Anthropic's current model documentation.
8. New error codes: `prompt_not_found` (404) and `context_length_exceeded` (422).

## Consequences

- Applications can reuse versioned prompts without shipping them in every request.
- The privacy rule is intact: only operator-authored configuration is stored.
- The heuristic counter can reject a request that would have fit or admit one that overflows; opt-in behavior limits the blast radius.
- The `claude-3-5-sonnet-20241022` catalog entry appears stale; refreshing the catalog is a separate task.
- `0007_prompt_templates` revises `0005_organization_policies` on this branch. If roadmap item 26's `0006_audit_events` merges first, re-point `down_revision` to `0006_audit_events`.

## Alternatives considered

- Resolving templates inside `CreateResponse`: rejected; it would couple the use case to storage and complicate cache and idempotency.
- Default-on truncation: rejected; it would silently change existing client behavior.
- Provider tokenizers: rejected for now; new dependencies and per-provider drift for a budget guard.

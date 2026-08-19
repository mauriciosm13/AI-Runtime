# ADR 0002: Static in-process model catalog for routing

- Status: Accepted
- Date: 2026-08-19

## Context

`CreateResponse` invoked a single injected `ModelProvider` and recorded a hardcoded `provider_name` of `"openai"`. That wiring cannot select among providers, reject unknown models before a vendor call, or keep usage accounting aligned with the adapter that actually ran.

Roadmap items 19–21 add Anthropic, Gemini, retries, and failover. Routing must exist first so those adapters register without changing the public API or the generation use case.

Durable, operator-edited routing policies belong in PostgreSQL later. There is no operator API for that configuration yet.

## Decision

Keep routing as an explicit catalog of `model → provider` names in the domain, bound to live adapters in the application layer.

- `domain/routing.py` owns `ModelRoute`, `DEFAULT_MODEL_CATALOG`, `resolve_model_route`, and `UnsupportedModelError`.
- `application/routing/ModelRouter` looks up the catalog and returns a `ResolvedRoute` with the registered `ModelProvider`.
- `CreateResponse` asks the router, then generates and records usage with `resolved.provider_name`.
- The composition root registers adapters by provider name (`{"openai": OpenAIModelProvider(...)}`).
- Unknown models fail before organization policy and provider invocation (`400 unsupported_model`).
- Organization entitlements remain a separate concern (`403 model_not_available`).

The initial catalog lists the OpenAI models already priced by `StaticCostEstimator`. New providers add catalog entries and a registered adapter; they do not change routes or domain resolution rules.

Retries, failover, and database-backed routing policies are out of scope for this decision.

## Consequences

### Positive

- `CreateResponse` no longer hardcodes a provider.
- Adding Anthropic or Gemini is registration plus catalog entries.
- Tests can inject a catalog and fake adapters without HTTP.
- Clients receive a stable error for models the platform does not serve.

### Negative

- The catalog is code, not operator configuration. Changing supported models requires a release until a later persistence slice.
- A catalog entry whose provider has no registered adapter fails at request time (`ProviderNotRegisteredError`).

## Alternatives considered

### Keep a single OpenAI adapter until more providers exist

This would delay the seam until Anthropic or Gemini ships and force a larger rewrite of `CreateResponse`. Rejected because routing is already a stated product requirement and the hardcoded provider name is already a lie once a second adapter exists.

### Client-supplied `provider/model` prefixes

Explicit prefixes make routing trivial but leak provider identity into the public API. Rejected for the current contract, which uses provider-neutral model names. Prefixes can be added later as an optional alias form without replacing the catalog.

### Persist routing policies in PostgreSQL now

Matches the long-term data architecture, but there is no operator surface to edit those rows and no second provider to justify it. Rejected as premature; the domain catalog is the seam that a future repository can fill.

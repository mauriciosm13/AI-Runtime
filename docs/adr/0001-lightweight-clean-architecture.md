# ADR 0001: Use lightweight Clean Architecture with ports and adapters

- Status: Accepted
- Date: 2026-07-31

## Context

AI Runtime will integrate with multiple model providers and external systems while enforcing provider-neutral business policies such as authorization, model routing, usage accounting, retries, and cost control.

Provider SDKs, storage engines, deployment services, and HTTP frameworks are expected to change more frequently than the business concepts and use cases. Coupling those concerns would make provider expansion, testing, and migration unnecessarily expensive.

At the same time, the project is early-stage. A heavily ceremonial architecture would slow delivery and introduce unused abstractions.

## Decision

Adopt a lightweight Clean Architecture with these boundaries:

- `domain` contains provider- and framework-independent business concepts and policies.
- `application` implements use cases and depends on domain code plus port interfaces.
- `ports` defines interfaces for external capabilities required by use cases.
- `api`, `providers`, `infrastructure`, and `telemetry` implement delivery and external-adapter concerns.
- Dependency direction points inward; application and domain code do not import concrete provider, storage, cloud, or HTTP implementations.
- Concrete dependencies are assembled through dependency injection at a composition root.

Interfaces will be created for real external boundaries and test seams, not preemptively for every class or function.

## Consequences

### Positive

- Provider adapters can be added or replaced without changing routing and authorization policies.
- Application use cases can be unit-tested with deterministic fakes.
- External infrastructure can evolve independently from core business rules.
- HTTP delivery remains thin and replaceable.

### Negative

- Features require deliberate placement and dependency wiring.
- Some interfaces and adapters add files beyond a framework-first implementation.
- Engineers must preserve the dependency rule in review and tests.

## Alternatives considered

### Framework-first layered application

Organizing primarily around FastAPI routes, ORM models, and service modules would be faster initially, but it risks coupling use cases to delivery and persistence details. It was rejected because provider and infrastructure flexibility are central to the product.

### Full domain-driven design

Aggregates, domain events, and extensive repository abstractions may be valuable for selected capabilities later. Adopting them universally now would add ceremony before the domain is understood. It was rejected as the default approach.

### Direct provider SDK calls from routes or services

This minimizes initial code but makes routing, retries, testing, telemetry, and multi-provider support harder to evolve consistently. It was rejected.

# ADR 0007: In-process metrics, request-correlated spans, and Postgres audit

## Status

Accepted

## Context

Roadmap item 26 requires metrics, tracing, and audit. Item 8 already emits structured logs with `request_id`. Item 29 will add CloudWatch. Requirements forbid persisting prompt or response content by default.

## Decision

1. Metrics are in-process counters/summaries scraped at unauthenticated `GET /metrics` in Prometheus text. No Prometheus or OpenTelemetry SDK in this slice.
2. `trace_id` equals `request_id`. HTTP and generation emit structured span fields on the request logger.
3. Durable audit lives in PostgreSQL `audit_events`. Events store action, actor, resource ids, and string labels only.
4. CloudWatch / OTLP exporters stay on item 29.

## Consequences

- Operators can scrape a single process without a sidecar.
- Multi-replica scrapes need aggregation later.
- Audit is investigable without reading prompts.

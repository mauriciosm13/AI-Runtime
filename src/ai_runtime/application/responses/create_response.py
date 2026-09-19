"""Use case for creating a provider-neutral model response."""

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy, EnforceOrganizationPolicyCommand
from ai_runtime.application.resilience.provider_executor import ProviderExecutor
from ai_runtime.application.responses.cache_fingerprint import fingerprint_generation_request
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.domain.generation import DomainValidationError, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import GenerationStreamEvent, Message, MessageRole, TokenUsage, ToolCall
from ai_runtime.domain.idempotency import IdempotencyConflictError
from ai_runtime.domain.rate_limit import RateLimitExceededError
from ai_runtime.domain.routing import ModelRoute
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.audit_repository import AuditRepository
from ai_runtime.ports.cost_estimator import CostEstimator
from ai_runtime.ports.idempotency_store import IdempotencyCompleted, IdempotencyInProgress, IdempotencyMiss, IdempotencyStore
from ai_runtime.ports.metrics import Metrics
from ai_runtime.ports.rate_limiter import RateLimiter
from ai_runtime.ports.response_cache import ResponseCache
from ai_runtime.ports.usage_repository import UsageRepository
from ai_runtime.telemetry.logging import REQUEST_LOGGER_NAME

_LOGGER = logging.getLogger(REQUEST_LOGGER_NAME)


@dataclass(frozen=True, slots=True)
class CreateResponseCommand:
    """Authenticated generation request with correlation and tenancy context."""

    request: GenerationRequest
    request_id: str
    organization_id: UUID
    api_key_id: UUID
    idempotency_key: str | None = None


def _serialize_response(response: GenerationResponse) -> str:
    """Serialize a generation response for idempotent replay storage."""
    payload = {
        "id": response.id,
        "model": response.model,
        "output": {
            "role": response.output.role.value,
            "content": response.output.content,
            "tool_calls": [{"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.output.tool_calls],
        },
        "usage": None
        if response.usage is None
        else {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _deserialize_response(payload: str) -> GenerationResponse:
    """Rebuild a generation response from an idempotency payload."""
    data = json.loads(payload)
    usage_data = data.get("usage")
    usage = None
    if usage_data is not None:
        usage = TokenUsage(input_tokens=usage_data["input_tokens"], output_tokens=usage_data["output_tokens"])
    return GenerationResponse(
        id=data["id"],
        model=data["model"],
        output=Message(
            role=MessageRole(data["output"]["role"]),
            content=data["output"]["content"],
            tool_calls=tuple(
                ToolCall(id=item["id"], name=item["name"], arguments=item["arguments"]) for item in data["output"].get("tool_calls", [])
            ),
        ),
        usage=usage,
    )


class CreateResponse:
    """Coordinate rate limits, idempotency, routing, generation, and usage accounting."""

    def __init__(
        self,
        provider_executor: ProviderExecutor,
        usage_records: UsageRepository,
        cost_estimator: CostEstimator,
        rate_limiter: RateLimiter,
        idempotency_store: IdempotencyStore,
        enforce_organization_policy: EnforceOrganizationPolicy,
        response_cache: ResponseCache,
        metrics: Metrics,
        audit_events: AuditRepository,
    ) -> None:
        self._provider_executor = provider_executor
        self._usage_records = usage_records
        self._cost_estimator = cost_estimator
        self._rate_limiter = rate_limiter
        self._idempotency_store = idempotency_store
        self._enforce_organization_policy = enforce_organization_policy
        self._response_cache = response_cache
        self._metrics = metrics
        self._audit_events = audit_events

    async def execute(self, command: CreateResponseCommand) -> GenerationResponse:
        """Enforce limits, route the model, generate a response, record usage, then return the result.

        Provider invocation is outside the usage persistence transaction. Usage
        is written only after a successful provider response. Idempotent replays
        skip routing, provider invocation, and usage persistence.
        """
        started_at = time.perf_counter()
        decision = await self._rate_limiter.consume(command.organization_id)
        if not decision.allowed:
            retry_after = decision.retry_after_seconds if decision.retry_after_seconds is not None else 1
            self._record_generation_error()
            raise RateLimitExceededError(retry_after_seconds=max(1, retry_after))

        claimed_idempotency = False
        if command.idempotency_key is not None:
            begin_result = await self._idempotency_store.begin(command.organization_id, command.idempotency_key)
            if isinstance(begin_result, IdempotencyCompleted):
                response = _deserialize_response(begin_result.payload)
                await self._record_generation_success(command, response, outcome="idempotent", provider="replay", count_tokens=False)
                return response
            if isinstance(begin_result, IdempotencyInProgress):
                self._record_generation_error()
                raise IdempotencyConflictError()
            assert isinstance(begin_result, IdempotencyMiss)
            claimed_idempotency = True

        if command.request.cache:
            cached_payload = await self._response_cache.get(
                command.organization_id,
                fingerprint_generation_request(command.request),
            )
            if cached_payload is not None:
                await self._enforce_organization_policy.execute(
                    EnforceOrganizationPolicyCommand(
                        organization_id=command.organization_id,
                        requested_model=command.request.model,
                        max_output_tokens=command.request.max_output_tokens,
                    )
                )
                response = replace(_deserialize_response(cached_payload), cached=True)
                if claimed_idempotency and command.idempotency_key is not None:
                    await self._idempotency_store.complete(
                        command.organization_id,
                        command.idempotency_key,
                        _serialize_response(response),
                    )
                await self._record_generation_success(command, response, outcome="cache", provider="cache", count_tokens=False)
                return response

        try:

            async def _before_route(route: ModelRoute) -> None:
                await self._enforce_organization_policy.execute(
                    EnforceOrganizationPolicyCommand(
                        organization_id=command.organization_id,
                        requested_model=route.model,
                        max_output_tokens=command.request.max_output_tokens,
                    )
                )

            execution = await self._provider_executor.execute(
                requested_model=command.request.model,
                request=command.request,
                before_route=_before_route,
            )
            response = execution.response
            await self._record_usage(command, execution.provider_name, response)
            if command.request.cache:
                await self._response_cache.set(
                    command.organization_id,
                    fingerprint_generation_request(command.request),
                    _serialize_response(response),
                )
            if claimed_idempotency and command.idempotency_key is not None:
                await self._idempotency_store.complete(
                    command.organization_id,
                    command.idempotency_key,
                    _serialize_response(response),
                )
            await self._record_generation_success(
                command,
                response,
                outcome="provider",
                provider=execution.provider_name,
                count_tokens=True,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            return response
        except Exception:
            if claimed_idempotency and command.idempotency_key is not None:
                await self._idempotency_store.release(command.organization_id, command.idempotency_key)
            self._record_generation_error()
            raise

    async def stream(self, command: CreateResponseCommand) -> AsyncIterator[GenerationStreamEvent]:
        """Enforce limits, stream generation events, and record usage on completion.

        Idempotency-Key is rejected. Rate limiting and organization policy run
        before the first event. Usage is written only after a completed response.
        """
        if command.idempotency_key is not None:
            raise DomainValidationError("Idempotency-Key is not supported for streaming requests.")
        decision = await self._rate_limiter.consume(command.organization_id)
        if not decision.allowed:
            retry_after = decision.retry_after_seconds if decision.retry_after_seconds is not None else 1
            raise RateLimitExceededError(retry_after_seconds=max(1, retry_after))

        async def _before_route(route: ModelRoute) -> None:
            await self._enforce_organization_policy.execute(
                EnforceOrganizationPolicyCommand(
                    organization_id=command.organization_id,
                    requested_model=route.model,
                    max_output_tokens=command.request.max_output_tokens,
                )
            )

        async for item in self._provider_executor.stream(
            requested_model=command.request.model,
            request=command.request,
            before_route=_before_route,
        ):
            if isinstance(item.payload, GenerationResponse):
                await self._record_usage(command, item.provider_name, item.payload)
                await self._record_generation_success(
                    command,
                    item.payload,
                    outcome="provider",
                    provider=item.provider_name,
                    count_tokens=True,
                )
            yield item.payload

    async def _record_usage(
        self,
        command: CreateResponseCommand,
        provider_name: str,
        response: GenerationResponse,
    ) -> None:
        """Persist a usage row for a successful generation."""
        estimated_cost = self._cost_estimator.estimate(
            provider=provider_name,
            model=response.model,
            usage=response.usage,
        )
        input_tokens = response.usage.input_tokens if response.usage is not None else None
        output_tokens = response.usage.output_tokens if response.usage is not None else None
        await self._usage_records.add(
            UsageRecord(
                id=uuid4(),
                request_id=command.request_id,
                organization_id=command.organization_id,
                api_key_id=command.api_key_id,
                provider=provider_name,
                model=response.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
                created_at=datetime.now(UTC),
            )
        )

    def _record_generation_error(self) -> None:
        """Count a failed generation attempt."""
        self._metrics.increment("generation_requests_total", {"result": "error"})

    async def _record_generation_success(
        self,
        command: CreateResponseCommand,
        response: GenerationResponse,
        *,
        outcome: str,
        provider: str,
        count_tokens: bool,
        duration_ms: float | None = None,
    ) -> None:
        """Emit success metrics, a generation span, and an audit event without bodies."""
        self._metrics.increment("generation_requests_total", {"result": "success", "outcome": outcome})
        if count_tokens and response.usage is not None:
            self._metrics.increment("generation_tokens_total", {"direction": "input"}, amount=float(response.usage.input_tokens))
            self._metrics.increment("generation_tokens_total", {"direction": "output"}, amount=float(response.usage.output_tokens))
        extra: dict[str, object] = {
            "request_id": command.request_id,
            "trace_id": command.request_id,
            "span": "generation",
        }
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        _LOGGER.info("span_completed", extra=extra)
        await self._audit_events.add(
            AuditEvent(
                id=uuid4(),
                action="response.created",
                occurred_at=datetime.now(UTC),
                organization_id=command.organization_id,
                actor_api_key_id=command.api_key_id,
                request_id=command.request_id,
                resource_type="response",
                resource_id=response.id,
                metadata={"model": response.model, "outcome": outcome, "provider": provider},
            )
        )

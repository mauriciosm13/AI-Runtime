"""Use case for creating a provider-neutral model response."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy, EnforceOrganizationPolicyCommand
from ai_runtime.application.routing.model_router import ModelRouter
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.domain.idempotency import IdempotencyConflictError
from ai_runtime.domain.rate_limit import RateLimitExceededError
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.cost_estimator import CostEstimator
from ai_runtime.ports.idempotency_store import IdempotencyCompleted, IdempotencyInProgress, IdempotencyMiss, IdempotencyStore
from ai_runtime.ports.rate_limiter import RateLimiter
from ai_runtime.ports.usage_repository import UsageRepository


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
        "output": {"role": response.output.role.value, "content": response.output.content},
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
        output=Message(role=MessageRole(data["output"]["role"]), content=data["output"]["content"]),
        usage=usage,
    )


class CreateResponse:
    """Coordinate rate limits, idempotency, routing, generation, and usage accounting."""

    def __init__(
        self,
        model_router: ModelRouter,
        usage_records: UsageRepository,
        cost_estimator: CostEstimator,
        rate_limiter: RateLimiter,
        idempotency_store: IdempotencyStore,
        enforce_organization_policy: EnforceOrganizationPolicy,
    ) -> None:
        self._model_router = model_router
        self._usage_records = usage_records
        self._cost_estimator = cost_estimator
        self._rate_limiter = rate_limiter
        self._idempotency_store = idempotency_store
        self._enforce_organization_policy = enforce_organization_policy

    async def execute(self, command: CreateResponseCommand) -> GenerationResponse:
        """Enforce limits, route the model, generate a response, record usage, then return the result.

        Provider invocation is outside the usage persistence transaction. Usage
        is written only after a successful provider response. Idempotent replays
        skip routing, provider invocation, and usage persistence.
        """
        decision = await self._rate_limiter.consume(command.organization_id)
        if not decision.allowed:
            retry_after = decision.retry_after_seconds if decision.retry_after_seconds is not None else 1
            raise RateLimitExceededError(retry_after_seconds=max(1, retry_after))

        claimed_idempotency = False
        if command.idempotency_key is not None:
            begin_result = await self._idempotency_store.begin(command.organization_id, command.idempotency_key)
            if isinstance(begin_result, IdempotencyCompleted):
                return _deserialize_response(begin_result.payload)
            if isinstance(begin_result, IdempotencyInProgress):
                raise IdempotencyConflictError()
            assert isinstance(begin_result, IdempotencyMiss)
            claimed_idempotency = True

        try:
            resolved = self._model_router.resolve(command.request.model)
            await self._enforce_organization_policy.execute(
                EnforceOrganizationPolicyCommand(
                    organization_id=command.organization_id,
                    requested_model=command.request.model,
                    max_output_tokens=command.request.max_output_tokens,
                )
            )
            response = await resolved.provider.generate(command.request)
            estimated_cost = self._cost_estimator.estimate(
                provider=resolved.provider_name,
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
                    provider=resolved.provider_name,
                    model=response.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimated_cost,
                    created_at=datetime.now(UTC),
                )
            )
            if claimed_idempotency and command.idempotency_key is not None:
                await self._idempotency_store.complete(
                    command.organization_id,
                    command.idempotency_key,
                    _serialize_response(response),
                )
            return response
        except Exception:
            if claimed_idempotency and command.idempotency_key is not None:
                await self._idempotency_store.release(command.organization_id, command.idempotency_key)
            raise

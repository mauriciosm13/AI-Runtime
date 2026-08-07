"""Unit tests for the CreateResponse use case."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.responses.create_response import CreateResponse, CreateResponseCommand
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.domain.idempotency import IdempotencyConflictError
from ai_runtime.domain.rate_limit import RateLimitExceededError
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.cost_estimator import CostEstimator
from ai_runtime.ports.idempotency_store import IdempotencyBeginResult, IdempotencyCompleted, IdempotencyInProgress
from ai_runtime.ports.idempotency_store import IdempotencyMiss, IdempotencyStore
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.ports.rate_limiter import RateLimitDecision, RateLimiter
from ai_runtime.ports.usage_repository import UsageRepository


class FakeProviderError(Exception):
    """Failure raised by the fake provider during a generation call."""


class FakeModelProvider:
    """Deterministic provider fake that records the request it receives."""

    def __init__(self, response: GenerationResponse | None = None, error: Exception | None = None) -> None:
        self.requests: list[GenerationRequest] = []
        self._response = response
        self._error = error

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class FakeUsageRepository:
    """In-memory UsageRepository that records persisted usage rows."""

    def __init__(self) -> None:
        self.added: list[UsageRecord] = []
        self._by_id: dict[UUID, UsageRecord] = {}
        self._by_request_id: dict[str, UsageRecord] = {}

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        self.added.append(usage_record)
        self._by_id[usage_record.id] = usage_record
        self._by_request_id[usage_record.request_id] = usage_record
        return usage_record

    async def get_by_id(self, usage_record_id: UUID) -> UsageRecord | None:
        return self._by_id.get(usage_record_id)

    async def get_by_request_id(self, request_id: str) -> UsageRecord | None:
        return self._by_request_id.get(request_id)


class FakeCostEstimator:
    """Deterministic cost estimator returning a fixed USD amount when usage exists."""

    def __init__(self, amount: Decimal | None = Decimal("0.00001200")) -> None:
        self.amount = amount
        self.calls: list[tuple[str, str, TokenUsage | None]] = []

    def estimate(
        self,
        *,
        provider: str,
        model: str,
        usage: TokenUsage | None,
    ) -> Decimal | None:
        self.calls.append((provider, model, usage))
        if usage is None:
            return None
        return self.amount


class FakeRateLimiter:
    """In-memory rate limiter with a configurable decision."""

    def __init__(self, decision: RateLimitDecision | None = None) -> None:
        self.decision = decision or RateLimitDecision(allowed=True)
        self.calls: list[UUID] = []

    async def consume(self, organization_id: UUID) -> RateLimitDecision:
        self.calls.append(organization_id)
        return self.decision


class FakeIdempotencyStore:
    """In-memory IdempotencyStore for use-case tests."""

    def __init__(self, begin_result: IdempotencyBeginResult | None = None) -> None:
        self._begin_result = begin_result or IdempotencyMiss()
        self.begin_calls: list[tuple[UUID, str]] = []
        self.completed: list[tuple[UUID, str, str]] = []
        self.released: list[tuple[UUID, str]] = []

    async def begin(self, organization_id: UUID, key: str) -> IdempotencyBeginResult:
        self.begin_calls.append((organization_id, key))
        return self._begin_result

    async def complete(self, organization_id: UUID, key: str, payload: str) -> None:
        self.completed.append((organization_id, key, payload))

    async def release(self, organization_id: UUID, key: str) -> None:
        self.released.append((organization_id, key))


def _request() -> GenerationRequest:
    return GenerationRequest(model="fake-model", messages=(Message(role=MessageRole.USER, content="Hello"),))


def _response(*, usage: TokenUsage | None = TokenUsage(input_tokens=10, output_tokens=5)) -> GenerationResponse:
    return GenerationResponse(
        id="response-1",
        model="fake-model",
        output=Message(role=MessageRole.ASSISTANT, content="Hi"),
        usage=usage,
    )


def _command(*, request: GenerationRequest | None = None, idempotency_key: str | None = None) -> CreateResponseCommand:
    return CreateResponseCommand(
        request=request or _request(),
        request_id="req_test_123",
        organization_id=uuid4(),
        api_key_id=uuid4(),
        idempotency_key=idempotency_key,
    )


def _use_case(
    provider: FakeModelProvider,
    *,
    usage_records: FakeUsageRepository | None = None,
    cost_estimator: FakeCostEstimator | None = None,
    rate_limiter: FakeRateLimiter | None = None,
    idempotency_store: FakeIdempotencyStore | None = None,
) -> tuple[CreateResponse, FakeUsageRepository, FakeCostEstimator, FakeRateLimiter, FakeIdempotencyStore]:
    records = usage_records or FakeUsageRepository()
    estimator = cost_estimator or FakeCostEstimator()
    limiter = rate_limiter or FakeRateLimiter()
    store = idempotency_store or FakeIdempotencyStore()
    use_case = CreateResponse(
        provider,
        records,
        estimator,
        limiter,
        store,
        provider_name="openai",
    )
    return use_case, records, estimator, limiter, store


def test_create_response_delegates_request_and_returns_provider_response() -> None:
    """The use case forwards the exact request and returns the provider result."""
    request = _request()
    response = _response()
    provider = FakeModelProvider(response=response)
    use_case, _, _, _, _ = _use_case(provider)
    command = _command(request=request)

    result = asyncio.run(use_case.execute(command))

    assert provider.requests == [request]
    assert result is response


def test_create_response_persists_usage_with_tokens_and_cost() -> None:
    """After a successful generation, usage tokens and estimated cost are persisted."""
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    provider = FakeModelProvider(response=_response(usage=usage))
    use_case, records, estimator, _, _ = _use_case(provider)
    command = _command()

    before = datetime.now(UTC)
    result = asyncio.run(use_case.execute(command))
    after = datetime.now(UTC)

    assert result.usage is usage
    assert len(records.added) == 1
    stored = records.added[0]
    assert stored.request_id == command.request_id
    assert stored.organization_id == command.organization_id
    assert stored.api_key_id == command.api_key_id
    assert stored.provider == "openai"
    assert stored.model == "fake-model"
    assert stored.input_tokens == 100
    assert stored.output_tokens == 50
    assert stored.estimated_cost_usd == Decimal("0.00001200")
    assert before <= stored.created_at <= after
    assert estimator.calls == [("openai", "fake-model", usage)]


def test_create_response_persists_null_tokens_and_cost_when_usage_missing() -> None:
    """Missing provider usage yields a usage row with null tokens and null cost."""
    provider = FakeModelProvider(response=_response(usage=None))
    use_case, records, _, _, _ = _use_case(provider, cost_estimator=FakeCostEstimator(amount=Decimal("1")))

    asyncio.run(use_case.execute(_command()))

    stored = records.added[0]
    assert stored.input_tokens is None
    assert stored.output_tokens is None
    assert stored.estimated_cost_usd is None


def test_create_response_skips_usage_persist_when_provider_fails() -> None:
    """Provider failures must not create usage rows."""
    error = FakeProviderError("generation failed")
    use_case, records, _, _, _ = _use_case(FakeModelProvider(error=error))

    with pytest.raises(FakeProviderError, match="generation failed"):
        asyncio.run(use_case.execute(_command()))

    assert records.added == []


def test_create_response_raises_when_rate_limited() -> None:
    """Denied rate-limit decisions raise RateLimitExceededError before generation."""
    provider = FakeModelProvider(response=_response())
    limiter = FakeRateLimiter(RateLimitDecision(allowed=False, retry_after_seconds=7))
    use_case, records, _, _, _ = _use_case(provider, rate_limiter=limiter)
    command = _command()

    with pytest.raises(RateLimitExceededError) as exc_info:
        asyncio.run(use_case.execute(command))

    assert exc_info.value.retry_after_seconds == 7
    assert provider.requests == []
    assert records.added == []
    assert limiter.calls == [command.organization_id]


def test_create_response_replays_completed_idempotency_payload() -> None:
    """Completed idempotency records return the cached response without provider calls."""
    cached = _response(usage=TokenUsage(input_tokens=3, output_tokens=2))
    payload = (
        '{"id":"response-1","model":"fake-model","output":{"role":"assistant","content":"Hi"},'
        '"usage":{"input_tokens":3,"output_tokens":2}}'
    )
    store = FakeIdempotencyStore(IdempotencyCompleted(payload=payload))
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _ = _use_case(provider, idempotency_store=store)

    result = asyncio.run(use_case.execute(_command(idempotency_key="key-1")))

    assert result == cached
    assert provider.requests == []
    assert records.added == []
    assert store.completed == []


def test_create_response_raises_on_in_progress_idempotency_key() -> None:
    """In-progress idempotency keys raise IdempotencyConflictError."""
    store = FakeIdempotencyStore(IdempotencyInProgress())
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _ = _use_case(provider, idempotency_store=store)

    with pytest.raises(IdempotencyConflictError):
        asyncio.run(use_case.execute(_command(idempotency_key="key-1")))

    assert provider.requests == []
    assert records.added == []


def test_create_response_completes_idempotency_after_success() -> None:
    """Successful generation stores an idempotency payload for the claimed key."""
    provider = FakeModelProvider(response=_response())
    store = FakeIdempotencyStore(IdempotencyMiss())
    use_case, _, _, _, _ = _use_case(provider, idempotency_store=store)
    command = _command(idempotency_key="key-1")

    asyncio.run(use_case.execute(command))

    assert len(store.completed) == 1
    org_id, key, payload = store.completed[0]
    assert org_id == command.organization_id
    assert key == "key-1"
    assert '"id":"response-1"' in payload
    assert store.released == []


def test_create_response_releases_idempotency_lease_on_provider_failure() -> None:
    """Provider failures release the in-progress idempotency lease."""
    store = FakeIdempotencyStore(IdempotencyMiss())
    use_case, records, _, _, _ = _use_case(
        FakeModelProvider(error=FakeProviderError("generation failed")),
        idempotency_store=store,
    )
    command = _command(idempotency_key="key-1")

    with pytest.raises(FakeProviderError):
        asyncio.run(use_case.execute(command))

    assert records.added == []
    assert store.completed == []
    assert store.released == [(command.organization_id, "key-1")]


def test_create_response_skips_idempotency_when_key_absent() -> None:
    """Without an idempotency key, the store is never consulted."""
    store = FakeIdempotencyStore()
    provider = FakeModelProvider(response=_response())
    use_case, _, _, _, _ = _use_case(provider, idempotency_store=store)

    asyncio.run(use_case.execute(_command()))

    assert store.begin_calls == []
    assert store.completed == []


def test_create_response_accepts_port_protocols() -> None:
    """Injected fakes satisfy the CreateResponse port protocols."""
    provider: ModelProvider = FakeModelProvider(response=_response())
    usage_records: UsageRepository = FakeUsageRepository()
    cost_estimator: CostEstimator = FakeCostEstimator()
    rate_limiter: RateLimiter = FakeRateLimiter()
    idempotency_store: IdempotencyStore = FakeIdempotencyStore()
    assert isinstance(provider, ModelProvider)
    assert isinstance(usage_records, UsageRepository)
    assert isinstance(cost_estimator, CostEstimator)
    assert isinstance(rate_limiter, RateLimiter)
    assert isinstance(idempotency_store, IdempotencyStore)
    assert isinstance(
        CreateResponse(provider, usage_records, cost_estimator, rate_limiter, idempotency_store),
        CreateResponse,
    )

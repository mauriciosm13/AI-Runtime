"""Unit tests for the CreateResponse use case."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy
from ai_runtime.application.responses.create_response import CreateResponse, CreateResponseCommand
from ai_runtime.application.routing.model_router import ModelRouter, ProviderNotRegisteredError
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.domain.idempotency import IdempotencyConflictError
from ai_runtime.domain.organization_policy import ModelEntitlement, ModelNotAvailableError, OrganizationPolicy, QuotaExceededError
from ai_runtime.domain.rate_limit import RateLimitExceededError
from ai_runtime.domain.routing import UnsupportedModelError
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.cost_estimator import CostEstimator
from ai_runtime.ports.idempotency_store import IdempotencyBeginResult, IdempotencyCompleted, IdempotencyInProgress
from ai_runtime.ports.idempotency_store import IdempotencyMiss, IdempotencyStore
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.ports.organization_policy_repository import OrganizationPolicyRepository
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

    def __init__(self, *, used_tokens: int = 0) -> None:
        self.added: list[UsageRecord] = []
        self._by_id: dict[UUID, UsageRecord] = {}
        self._by_request_id: dict[str, UsageRecord] = {}
        self._used_tokens = used_tokens
        self.sum_calls: list[tuple[UUID, datetime, datetime]] = []

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        self.added.append(usage_record)
        self._by_id[usage_record.id] = usage_record
        self._by_request_id[usage_record.request_id] = usage_record
        return usage_record

    async def get_by_id(self, usage_record_id: UUID) -> UsageRecord | None:
        return self._by_id.get(usage_record_id)

    async def get_by_request_id(self, request_id: str) -> UsageRecord | None:
        return self._by_request_id.get(request_id)

    async def sum_tokens_for_organization_in_period(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        self.sum_calls.append((organization_id, start, end))
        return self._used_tokens


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


class FakeOrganizationPolicyRepository:
    """In-memory OrganizationPolicyRepository for use-case tests."""

    def __init__(
        self,
        *,
        policy: OrganizationPolicy | None = None,
        entitlements: tuple[ModelEntitlement, ...] = (),
    ) -> None:
        self._policy = policy
        self._entitlements = entitlements

    async def get_policy(self, organization_id: UUID) -> OrganizationPolicy:
        if self._policy is None:
            return OrganizationPolicy(organization_id=organization_id)
        return self._policy

    async def list_entitlements(self, organization_id: UUID) -> tuple[ModelEntitlement, ...]:
        return self._entitlements


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


def _model_router(
    provider: FakeModelProvider,
    *,
    model: str = "fake-model",
    provider_name: str = "openai",
) -> ModelRouter:
    return ModelRouter(providers={provider_name: provider}, catalog={model: provider_name})


def _use_case(
    provider: FakeModelProvider,
    *,
    usage_records: FakeUsageRepository | None = None,
    cost_estimator: FakeCostEstimator | None = None,
    rate_limiter: FakeRateLimiter | None = None,
    idempotency_store: FakeIdempotencyStore | None = None,
    policy_repository: FakeOrganizationPolicyRepository | None = None,
    model_router: ModelRouter | None = None,
) -> tuple[
    CreateResponse,
    FakeUsageRepository,
    FakeCostEstimator,
    FakeRateLimiter,
    FakeIdempotencyStore,
    FakeOrganizationPolicyRepository,
]:
    records = usage_records or FakeUsageRepository()
    estimator = cost_estimator or FakeCostEstimator()
    limiter = rate_limiter or FakeRateLimiter()
    store = idempotency_store or FakeIdempotencyStore()
    policies = policy_repository or FakeOrganizationPolicyRepository()
    enforce_policy = EnforceOrganizationPolicy(policies, records)
    use_case = CreateResponse(
        model_router or _model_router(provider),
        records,
        estimator,
        limiter,
        store,
        enforce_policy,
    )
    return use_case, records, estimator, limiter, store, policies


def test_create_response_delegates_request_and_returns_provider_response() -> None:
    """The use case forwards the exact request and returns the provider result."""
    request = _request()
    response = _response()
    provider = FakeModelProvider(response=response)
    use_case, _, _, _, _, _ = _use_case(provider)
    command = _command(request=request)

    result = asyncio.run(use_case.execute(command))

    assert provider.requests == [request]
    assert result is response


def test_create_response_persists_usage_with_tokens_and_cost() -> None:
    """After a successful generation, usage tokens and estimated cost are persisted."""
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    provider = FakeModelProvider(response=_response(usage=usage))
    use_case, records, estimator, _, _, _ = _use_case(provider)
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
    use_case, records, _, _, _, _ = _use_case(provider, cost_estimator=FakeCostEstimator(amount=Decimal("1")))

    asyncio.run(use_case.execute(_command()))

    stored = records.added[0]
    assert stored.input_tokens is None
    assert stored.output_tokens is None
    assert stored.estimated_cost_usd is None


def test_create_response_skips_usage_persist_when_provider_fails() -> None:
    """Provider failures must not create usage rows."""
    error = FakeProviderError("generation failed")
    use_case, records, _, _, _, _ = _use_case(FakeModelProvider(error=error))

    with pytest.raises(FakeProviderError, match="generation failed"):
        asyncio.run(use_case.execute(_command()))

    assert records.added == []


def test_create_response_raises_when_rate_limited() -> None:
    """Denied rate-limit decisions raise RateLimitExceededError before generation."""
    provider = FakeModelProvider(response=_response())
    limiter = FakeRateLimiter(RateLimitDecision(allowed=False, retry_after_seconds=7))
    use_case, records, _, _, _, _ = _use_case(provider, rate_limiter=limiter)
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
    payload = json.dumps(
        {
            "id": "response-1",
            "model": "fake-model",
            "output": {"role": "assistant", "content": "Hi"},
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
        separators=(",", ":"),
        ensure_ascii=True,
    )
    store = FakeIdempotencyStore(IdempotencyCompleted(payload=payload))
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _, _ = _use_case(provider, idempotency_store=store)

    result = asyncio.run(use_case.execute(_command(idempotency_key="key-1")))

    assert result == cached
    assert provider.requests == []
    assert records.added == []
    assert store.completed == []


def test_create_response_raises_on_in_progress_idempotency_key() -> None:
    """In-progress idempotency keys raise IdempotencyConflictError."""
    store = FakeIdempotencyStore(IdempotencyInProgress())
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _, _ = _use_case(provider, idempotency_store=store)

    with pytest.raises(IdempotencyConflictError):
        asyncio.run(use_case.execute(_command(idempotency_key="key-1")))

    assert provider.requests == []
    assert records.added == []


def test_create_response_completes_idempotency_after_success() -> None:
    """Successful generation stores an idempotency payload for the claimed key."""
    provider = FakeModelProvider(response=_response())
    store = FakeIdempotencyStore(IdempotencyMiss())
    use_case, _, _, _, _, _ = _use_case(provider, idempotency_store=store)
    command = _command(idempotency_key="key-1")

    asyncio.run(use_case.execute(command))

    assert len(store.completed) == 1
    org_id, key, payload = store.completed[0]
    assert org_id == command.organization_id
    assert key == "key-1"
    assert payload == json.dumps(
        {
            "id": "response-1",
            "model": "fake-model",
            "output": {"role": "assistant", "content": "Hi"},
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert store.released == []


def test_create_response_releases_idempotency_lease_on_provider_failure() -> None:
    """Provider failures release the in-progress idempotency lease."""
    store = FakeIdempotencyStore(IdempotencyMiss())
    use_case, records, _, _, _, _ = _use_case(
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
    use_case, _, _, _, _, _ = _use_case(provider, idempotency_store=store)

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
    policy_repository: OrganizationPolicyRepository = FakeOrganizationPolicyRepository()
    enforce_policy = EnforceOrganizationPolicy(policy_repository, usage_records)
    assert isinstance(provider, ModelProvider)
    assert isinstance(usage_records, UsageRepository)
    assert isinstance(cost_estimator, CostEstimator)
    assert isinstance(rate_limiter, RateLimiter)
    assert isinstance(idempotency_store, IdempotencyStore)
    assert isinstance(policy_repository, OrganizationPolicyRepository)
    assert isinstance(
        CreateResponse(
            _model_router(FakeModelProvider(response=_response())),
            usage_records,
            cost_estimator,
            rate_limiter,
            idempotency_store,
            enforce_policy,
        ),
        CreateResponse,
    )


def test_create_response_raises_when_model_not_entitled() -> None:
    """Denied model entitlements raise ModelNotAvailableError before generation."""
    org_id = uuid4()
    provider = FakeModelProvider(response=_response())
    policies = FakeOrganizationPolicyRepository(
        entitlements=(ModelEntitlement(organization_id=org_id, model="other-model"),),
    )
    use_case, records, _, _, _, _ = _use_case(provider, policy_repository=policies)
    command = _command(request=_request())
    command = CreateResponseCommand(
        request=command.request,
        request_id=command.request_id,
        organization_id=org_id,
        api_key_id=command.api_key_id,
    )
    with pytest.raises(ModelNotAvailableError):
        asyncio.run(use_case.execute(command))
    assert provider.requests == []
    assert records.added == []


def test_create_response_raises_when_monthly_quota_exhausted() -> None:
    """Exhausted monthly token quota raises QuotaExceededError before generation."""
    org_id = uuid4()
    provider = FakeModelProvider(response=_response())
    policies = FakeOrganizationPolicyRepository(
        policy=OrganizationPolicy(organization_id=org_id, monthly_token_limit=100),
    )
    records = FakeUsageRepository(used_tokens=100)
    use_case, _, _, _, _, _ = _use_case(provider, usage_records=records, policy_repository=policies)
    command = CreateResponseCommand(
        request=_request(),
        request_id="req_test_123",
        organization_id=org_id,
        api_key_id=uuid4(),
    )
    with pytest.raises(QuotaExceededError):
        asyncio.run(use_case.execute(command))
    assert provider.requests == []


def test_create_response_idempotent_replay_skips_policy_enforcement() -> None:
    """Completed idempotency replays return without re-checking policy or calling provider."""
    org_id = uuid4()
    stored = _response()
    assert stored.usage is not None
    payload = json.dumps(
        {
            "id": stored.id,
            "model": stored.model,
            "output": {"role": stored.output.role.value, "content": stored.output.content},
            "usage": {"input_tokens": stored.usage.input_tokens, "output_tokens": stored.usage.output_tokens},
        },
        separators=(",", ":"),
        ensure_ascii=True,
    )
    store = FakeIdempotencyStore(IdempotencyCompleted(payload=payload))
    provider = FakeModelProvider(response=stored)
    policies = FakeOrganizationPolicyRepository(
        entitlements=(ModelEntitlement(organization_id=org_id, model="other-model"),),
    )
    records = FakeUsageRepository(used_tokens=999_999)
    use_case, _, _, _, _, _ = _use_case(
        provider,
        usage_records=records,
        idempotency_store=store,
        policy_repository=policies,
    )
    command = CreateResponseCommand(
        request=_request(),
        request_id="req_test_123",
        organization_id=org_id,
        api_key_id=uuid4(),
        idempotency_key="key-1",
    )
    result = asyncio.run(use_case.execute(command))
    assert result.id == stored.id
    assert provider.requests == []
    assert records.sum_calls == []


def test_create_response_routes_to_catalog_provider() -> None:
    """Usage and generation use the provider selected by the model catalog."""
    openai = FakeModelProvider(response=_response())
    anthropic = FakeModelProvider(response=_response())
    router = ModelRouter(
        providers={"openai": openai, "anthropic": anthropic},
        catalog={"fake-model": "anthropic"},
    )
    use_case, records, estimator, _, _, _ = _use_case(openai, model_router=router)

    asyncio.run(use_case.execute(_command()))

    assert openai.requests == []
    assert anthropic.requests == [_request()]
    assert records.added[0].provider == "anthropic"
    assert estimator.calls == [("anthropic", "fake-model", TokenUsage(input_tokens=10, output_tokens=5))]


def test_create_response_raises_when_provider_not_registered() -> None:
    """Catalog models whose provider adapter is missing fail before generation."""
    provider = FakeModelProvider(response=_response())
    router = ModelRouter(providers={}, catalog={"fake-model": "anthropic"})
    use_case, records, _, _, _, _ = _use_case(provider, model_router=router)

    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        asyncio.run(use_case.execute(_command()))

    assert exc_info.value.provider == "anthropic"
    assert provider.requests == []
    assert records.added == []


def test_create_response_raises_for_unsupported_model() -> None:
    """Unknown catalog models fail before provider invocation."""
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _, _ = _use_case(provider)
    command = _command(
        request=GenerationRequest(model="not-a-model", messages=(Message(role=MessageRole.USER, content="Hello"),)),
    )

    with pytest.raises(UnsupportedModelError) as exc_info:
        asyncio.run(use_case.execute(command))

    assert exc_info.value.model == "not-a-model"
    assert provider.requests == []
    assert records.added == []


def test_create_response_releases_idempotency_lease_on_unsupported_model() -> None:
    """Routing failures release the in-progress idempotency lease."""
    store = FakeIdempotencyStore(IdempotencyMiss())
    provider = FakeModelProvider(response=_response())
    use_case, records, _, _, _, _ = _use_case(provider, idempotency_store=store)
    command = _command(
        request=GenerationRequest(model="not-a-model", messages=(Message(role=MessageRole.USER, content="Hello"),)),
        idempotency_key="key-1",
    )

    with pytest.raises(UnsupportedModelError):
        asyncio.run(use_case.execute(command))

    assert records.added == []
    assert store.completed == []
    assert store.released == [(command.organization_id, "key-1")]


def test_create_response_releases_idempotency_lease_on_policy_denial() -> None:
    """Entitlement denials release the in-progress idempotency lease."""
    org_id = uuid4()
    store = FakeIdempotencyStore(IdempotencyMiss())
    provider = FakeModelProvider(response=_response())
    policies = FakeOrganizationPolicyRepository(
        entitlements=(ModelEntitlement(organization_id=org_id, model="other-model"),),
    )
    use_case, records, _, _, _, _ = _use_case(provider, idempotency_store=store, policy_repository=policies)
    command = CreateResponseCommand(
        request=_request(),
        request_id="req_test_123",
        organization_id=org_id,
        api_key_id=uuid4(),
        idempotency_key="key-1",
    )

    with pytest.raises(ModelNotAvailableError):
        asyncio.run(use_case.execute(command))

    assert provider.requests == []
    assert records.added == []
    assert store.released == [(org_id, "key-1")]

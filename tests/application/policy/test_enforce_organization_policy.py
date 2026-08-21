"""Unit tests for EnforceOrganizationPolicy."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ai_runtime.application.policy.enforce_organization_policy import EnforceOrganizationPolicy, EnforceOrganizationPolicyCommand
from ai_runtime.domain.organization_policy import ModelEntitlement, ModelNotAvailableError, OrganizationPolicy, QuotaExceededError
from ai_runtime.domain.usage import UsageRecord


class FakeOrganizationPolicyRepository:
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


class FakeUsageRepository:
    def __init__(self, *, used_tokens: int = 0) -> None:
        self.used_tokens = used_tokens
        self.sum_calls: list[tuple[UUID, datetime, datetime]] = []

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        raise NotImplementedError

    async def get_by_id(self, usage_record_id: UUID) -> None:
        return None

    async def get_by_request_id(self, request_id: str) -> None:
        return None

    async def sum_tokens_for_organization_in_period(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        self.sum_calls.append((organization_id, start, end))
        return self.used_tokens


def _command(**overrides: object) -> EnforceOrganizationPolicyCommand:
    defaults = {
        "organization_id": uuid4(),
        "requested_model": "gpt-4o-mini",
        "max_output_tokens": None,
    }
    defaults.update(overrides)
    return EnforceOrganizationPolicyCommand(**defaults)  # type: ignore[arg-type]


def test_enforce_allows_unrestricted_organization() -> None:
    org_id = uuid4()
    use_case = EnforceOrganizationPolicy(
        FakeOrganizationPolicyRepository(),
        FakeUsageRepository(),
    )
    asyncio.run(use_case.execute(_command(organization_id=org_id)))


def test_enforce_rejects_model_not_in_allowlist() -> None:
    org_id = uuid4()
    entitlements = (ModelEntitlement(organization_id=org_id, model="gpt-4o-mini"),)
    use_case = EnforceOrganizationPolicy(
        FakeOrganizationPolicyRepository(entitlements=entitlements),
        FakeUsageRepository(),
    )
    with pytest.raises(ModelNotAvailableError):
        asyncio.run(use_case.execute(_command(organization_id=org_id, requested_model="gpt-4o")))


def test_enforce_rejects_when_monthly_quota_exhausted() -> None:
    org_id = uuid4()
    policy = OrganizationPolicy(organization_id=org_id, monthly_token_limit=1000)
    fixed_now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    use_case = EnforceOrganizationPolicy(
        FakeOrganizationPolicyRepository(policy=policy),
        FakeUsageRepository(used_tokens=1000),
        clock=lambda: fixed_now,
    )
    with pytest.raises(QuotaExceededError) as exc_info:
        asyncio.run(use_case.execute(_command(organization_id=org_id)))
    assert exc_info.value.retry_after_seconds > 0


def test_enforce_allows_when_usage_below_quota() -> None:
    org_id = uuid4()
    policy = OrganizationPolicy(organization_id=org_id, monthly_token_limit=1000)
    use_case = EnforceOrganizationPolicy(
        FakeOrganizationPolicyRepository(policy=policy),
        FakeUsageRepository(used_tokens=500),
    )
    asyncio.run(use_case.execute(_command(organization_id=org_id)))

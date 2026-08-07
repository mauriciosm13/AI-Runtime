"""Unit tests for the UsageRepository port contract."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.ports.usage_repository import UsageRepository


class FakeUsageRepository:
    """In-memory stand-in that satisfies UsageRepository."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, UsageRecord] = {}
        self._by_request_id: dict[str, UsageRecord] = {}

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        self._by_id[usage_record.id] = usage_record
        self._by_request_id[usage_record.request_id] = usage_record
        return usage_record

    async def get_by_id(self, usage_record_id: UUID) -> UsageRecord | None:
        return self._by_id.get(usage_record_id)

    async def get_by_request_id(self, request_id: str) -> UsageRecord | None:
        return self._by_request_id.get(request_id)


def test_fake_repository_satisfies_usage_repository_contract() -> None:
    """A structural fake is accepted as UsageRepository."""
    repository: UsageRepository = FakeUsageRepository()
    assert isinstance(repository, UsageRepository)
    record = UsageRecord(
        id=uuid4(),
        request_id="req_port",
        organization_id=uuid4(),
        api_key_id=uuid4(),
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=3,
        output_tokens=2,
        estimated_cost_usd=Decimal("0.00000100"),
        created_at=datetime.now(UTC),
    )
    stored = asyncio.run(repository.add(record))
    assert asyncio.run(repository.get_by_id(stored.id)) == stored
    assert asyncio.run(repository.get_by_request_id("req_port")) == stored

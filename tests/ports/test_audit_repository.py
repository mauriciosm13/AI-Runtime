"""Unit tests for the AuditRepository port contract."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.ports.audit_repository import AuditRepository


class FakeAuditRepository:
    """In-memory stand-in that satisfies AuditRepository."""

    async def add(self, event: AuditEvent) -> AuditEvent:
        return event

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        _ = event_id
        return None


def test_fake_audit_repository_satisfies_contract() -> None:
    """A structural fake is accepted as AuditRepository."""
    repository: AuditRepository = FakeAuditRepository()
    assert isinstance(repository, AuditRepository)
    event = AuditEvent(
        id=uuid4(),
        action="api_key.created",
        occurred_at=datetime.now(UTC),
        resource_type="api_key",
        metadata={"prefix": "airt_abcd"},
    )
    assert asyncio.run(repository.add(event)) is event

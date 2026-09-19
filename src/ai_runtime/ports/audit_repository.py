"""Port for durable audit-event persistence."""

from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.audit import AuditEvent


@runtime_checkable
class AuditRepository(Protocol):
    """Async contract for appending and loading audit events."""

    async def add(self, event: AuditEvent) -> AuditEvent:
        """Persist ``event`` and return the stored entity."""
        ...

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        """Load an audit event by primary key."""
        ...

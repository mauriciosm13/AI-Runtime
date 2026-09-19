"""SQLAlchemy adapter for the AuditRepository port."""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.infrastructure.db.models.audit_event import AuditEventRow


def _to_domain(row: AuditEventRow) -> AuditEvent:
    """Map an ORM row to the domain AuditEvent."""
    return AuditEvent(
        id=row.id,
        action=row.action,
        occurred_at=row.occurred_at,
        organization_id=row.organization_id,
        actor_api_key_id=row.actor_api_key_id,
        request_id=row.request_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata=dict(row.event_metadata),
    )


class SqlAlchemyAuditRepository:
    """Persist audit events through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> AuditEvent:
        """Insert ``event`` and commit the current transaction."""
        row = AuditEventRow(
            id=event.id,
            action=event.action,
            occurred_at=event.occurred_at,
            organization_id=event.organization_id,
            actor_api_key_id=event.actor_api_key_id,
            request_id=event.request_id,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            event_metadata=dict(event.metadata),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        """Load an audit event by primary key."""
        row = await self._session.get(AuditEventRow, event_id)
        if row is None:
            return None
        return _to_domain(row)

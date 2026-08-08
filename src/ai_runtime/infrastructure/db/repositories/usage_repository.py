"""SQLAlchemy adapter for the UsageRepository port."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.infrastructure.db.models.usage_record import UsageRecordRow


def _to_domain(row: UsageRecordRow) -> UsageRecord:
    """Map an ORM row to the domain UsageRecord entity."""
    cost = row.estimated_cost_usd
    if cost is not None and not isinstance(cost, Decimal):
        cost = Decimal(str(cost))
    return UsageRecord(
        id=row.id,
        request_id=row.request_id,
        organization_id=row.organization_id,
        api_key_id=row.api_key_id,
        provider=row.provider,
        model=row.model,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        estimated_cost_usd=cost,
        created_at=row.created_at,
    )


def _to_row(usage_record: UsageRecord) -> UsageRecordRow:
    """Map a domain UsageRecord to an ORM row."""
    return UsageRecordRow(
        id=usage_record.id,
        request_id=usage_record.request_id,
        organization_id=usage_record.organization_id,
        api_key_id=usage_record.api_key_id,
        provider=usage_record.provider,
        model=usage_record.model,
        input_tokens=usage_record.input_tokens,
        output_tokens=usage_record.output_tokens,
        estimated_cost_usd=usage_record.estimated_cost_usd,
        created_at=usage_record.created_at,
    )


class SqlAlchemyUsageRepository:
    """Persist and load usage records through an async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        """Insert ``usage_record`` and commit the current transaction."""
        row = _to_row(usage_record)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get_by_id(self, usage_record_id: UUID) -> UsageRecord | None:
        """Load a usage record by primary key."""
        row = await self._session.get(UsageRecordRow, usage_record_id)
        if row is None:
            return None
        return _to_domain(row)

    async def get_by_request_id(self, request_id: str) -> UsageRecord | None:
        """Load a usage record by correlation request_id."""
        result = await self._session.execute(select(UsageRecordRow).where(UsageRecordRow.request_id == request_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_domain(row)

    async def sum_tokens_for_organization_in_period(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        """Sum input and output tokens for an organization within a half-open period."""
        token_sum = func.coalesce(UsageRecordRow.input_tokens, 0) + func.coalesce(UsageRecordRow.output_tokens, 0)
        result = await self._session.execute(
            select(func.coalesce(func.sum(token_sum), 0)).where(
                UsageRecordRow.organization_id == organization_id,
                UsageRecordRow.created_at >= start,
                UsageRecordRow.created_at < end,
            )
        )
        total = result.scalar_one()
        return int(total)

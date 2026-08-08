"""Port for persisting and loading usage accounting records."""

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.usage import UsageRecord


@runtime_checkable
class UsageRepository(Protocol):
    """Async persistence contract for usage accounting records."""

    async def add(self, usage_record: UsageRecord) -> UsageRecord:
        """Persist a new usage record and return the stored entity."""
        ...

    async def get_by_id(self, usage_record_id: UUID) -> UsageRecord | None:
        """Return the usage record with ``usage_record_id``, or ``None``."""
        ...

    async def get_by_request_id(self, request_id: str) -> UsageRecord | None:
        """Return the usage record for ``request_id``, or ``None``.

        Used for reconciliation so retries can avoid double counting.
        """
        ...

    async def sum_tokens_for_organization_in_period(
        self,
        organization_id: UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        """Return total input+output tokens for ``organization_id`` in ``[start, end)``."""
        ...

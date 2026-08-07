"""Port for caller-provided idempotency key coordination."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IdempotencyMiss:
    """No prior record; the caller now owns the in-progress lease."""


@dataclass(frozen=True, slots=True)
class IdempotencyInProgress:
    """Another request with the same key is still executing."""


@dataclass(frozen=True, slots=True)
class IdempotencyCompleted:
    """A prior successful response payload is available for replay."""

    payload: str


IdempotencyBeginResult = IdempotencyMiss | IdempotencyInProgress | IdempotencyCompleted


@runtime_checkable
class IdempotencyStore(Protocol):
    """Async contract for organization-scoped idempotency records."""

    async def begin(self, organization_id: UUID, key: str) -> IdempotencyBeginResult:
        """Claim the key, report an in-flight conflict, or return a completed payload."""
        ...

    async def complete(self, organization_id: UUID, key: str, payload: str) -> None:
        """Store the successful response payload for future replays."""
        ...

    async def release(self, organization_id: UUID, key: str) -> None:
        """Drop an in-progress lease so a retry may claim the key again."""
        ...

"""Port for organization-scoped generation response cache."""

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ResponseCache(Protocol):
    """Async contract for content-addressed response payloads."""

    async def get(self, organization_id: UUID, fingerprint: str) -> str | None:
        """Return a stored response payload or None on miss."""
        ...

    async def set(self, organization_id: UUID, fingerprint: str, payload: str) -> None:
        """Store a successful response payload for the fingerprint."""
        ...

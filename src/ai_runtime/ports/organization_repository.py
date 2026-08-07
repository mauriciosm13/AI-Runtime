"""Port for persisting and loading organizations."""

from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.organization import Organization


@runtime_checkable
class OrganizationRepository(Protocol):
    """Async persistence contract for organization tenants."""

    async def add(self, organization: Organization) -> Organization:
        """Persist a new organization and return the stored entity."""
        ...

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        """Return the organization with ``organization_id``, or ``None``."""
        ...

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Return the organization with ``slug``, or ``None``."""
        ...

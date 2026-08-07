"""Unit tests for GetOrganization with an in-memory repository."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.organizations.get_organization import GetOrganization
from ai_runtime.domain.organization import Organization, OrganizationNotFoundError, OrganizationStatus


class FakeOrganizationRepository:
    """Deterministic in-memory OrganizationRepository for use-case tests."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Organization] = {}
        self._by_slug: dict[str, Organization] = {}

    async def add(self, organization: Organization) -> Organization:
        self._by_id[organization.id] = organization
        self._by_slug[organization.slug] = organization
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self._by_id.get(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        return self._by_slug.get(slug)


def test_get_organization_returns_existing() -> None:
    """GetOrganization returns the organization when it exists."""
    repository = FakeOrganizationRepository()
    now = datetime.now(UTC)
    existing = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(repository.add(existing))
    use_case = GetOrganization(repository)

    found = asyncio.run(use_case.execute(existing.id))
    assert found == existing


def test_get_organization_raises_when_missing() -> None:
    """GetOrganization raises OrganizationNotFoundError for unknown ids."""
    use_case = GetOrganization(FakeOrganizationRepository())
    missing_id = uuid4()

    with pytest.raises(OrganizationNotFoundError, match=str(missing_id)):
        asyncio.run(use_case.execute(missing_id))

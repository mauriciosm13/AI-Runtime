"""Unit tests for the OrganizationRepository port contract."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.ports.organization_repository import OrganizationRepository


class FakeOrganizationRepository:
    """In-memory stand-in that satisfies OrganizationRepository."""

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


def test_fake_repository_satisfies_organization_repository_contract() -> None:
    """A structural fake is accepted as OrganizationRepository."""
    repository: OrganizationRepository = FakeOrganizationRepository()
    assert isinstance(repository, OrganizationRepository)
    now = datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    stored = asyncio.run(repository.add(organization))
    assert asyncio.run(repository.get_by_id(stored.id)) == stored
    assert asyncio.run(repository.get_by_slug("acme")) == stored

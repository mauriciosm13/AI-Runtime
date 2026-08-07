"""Unit tests for CreateOrganization with an in-memory repository."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.organizations.create_organization import CreateOrganization, CreateOrganizationCommand
from ai_runtime.domain.organization import Organization, OrganizationSlugConflictError, OrganizationStatus


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


def test_create_organization_persists_active_tenant() -> None:
    """CreateOrganization stores an active organization with generated id and timestamps."""
    repository = FakeOrganizationRepository()
    use_case = CreateOrganization(repository)

    organization = asyncio.run(use_case.execute(CreateOrganizationCommand(name="Acme Corp", slug="acme-corp")))

    assert organization.name == "Acme Corp"
    assert organization.slug == "acme-corp"
    assert organization.status is OrganizationStatus.ACTIVE
    assert isinstance(organization.id, UUID)
    assert organization.created_at.tzinfo is not None
    assert organization.updated_at.tzinfo is not None
    assert asyncio.run(repository.get_by_slug("acme-corp")) == organization


def test_create_organization_rejects_duplicate_slug() -> None:
    """CreateOrganization raises when the slug is already taken."""
    repository = FakeOrganizationRepository()
    now = datetime.now(UTC)
    existing = Organization(
        id=uuid4(),
        name="Existing",
        slug="acme",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(repository.add(existing))
    use_case = CreateOrganization(repository)

    with pytest.raises(OrganizationSlugConflictError, match="acme"):
        asyncio.run(use_case.execute(CreateOrganizationCommand(name="Other", slug="acme")))

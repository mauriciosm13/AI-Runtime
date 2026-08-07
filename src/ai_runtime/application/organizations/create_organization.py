"""Use case for creating an organization tenant."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4
from ai_runtime.domain.organization import Organization, OrganizationSlugConflictError, OrganizationStatus
from ai_runtime.ports.organization_repository import OrganizationRepository


@dataclass(frozen=True, slots=True)
class CreateOrganizationCommand:
    """Input for creating a new organization."""

    name: str
    slug: str


class CreateOrganization:
    """Create and persist a new active organization."""

    def __init__(self, organizations: OrganizationRepository) -> None:
        self._organizations = organizations

    async def execute(self, command: CreateOrganizationCommand) -> Organization:
        """Persist a new organization or reject a duplicate slug."""
        existing = await self._organizations.get_by_slug(command.slug)
        if existing is not None:
            raise OrganizationSlugConflictError(f"organization slug already exists: {command.slug}")

        now = datetime.now(UTC)
        organization = Organization(
            id=uuid4(),
            name=command.name,
            slug=command.slug,
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        return await self._organizations.add(organization)

"""Use case for retrieving an organization by id."""

from uuid import UUID
from ai_runtime.domain.organization import Organization, OrganizationNotFoundError
from ai_runtime.ports.organization_repository import OrganizationRepository


class GetOrganization:
    """Load an organization tenant by identifier."""

    def __init__(self, organizations: OrganizationRepository) -> None:
        self._organizations = organizations

    async def execute(self, organization_id: UUID) -> Organization:
        """Return the organization or raise when it does not exist."""
        organization = await self._organizations.get_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization not found: {organization_id}")
        return organization

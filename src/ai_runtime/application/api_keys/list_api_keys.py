"""Use case for listing API key metadata for an organization."""

from collections.abc import Sequence
from uuid import UUID
from ai_runtime.domain.api_key import ApiKeyMetadata
from ai_runtime.domain.organization import OrganizationNotFoundError
from ai_runtime.ports.api_key_repository import ApiKeyRepository
from ai_runtime.ports.organization_repository import OrganizationRepository


class ListApiKeysForOrganization:
    """List API-key metadata for an organization (never secret or hash)."""

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        organizations: OrganizationRepository,
    ) -> None:
        self._api_keys = api_keys
        self._organizations = organizations

    async def execute(self, organization_id: UUID) -> Sequence[ApiKeyMetadata]:
        """Return metadata for keys belonging to ``organization_id``."""
        organization = await self._organizations.get_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization not found: {organization_id}")

        keys = await self._api_keys.list_by_organization(organization_id)
        return [key.to_metadata() for key in keys]

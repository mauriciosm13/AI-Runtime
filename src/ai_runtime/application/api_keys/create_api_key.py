"""Use case for creating an API key credential for an organization."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.api_key import ApiKey, ApiKeyMetadata, ApiKeyStatus
from ai_runtime.domain.organization import OrganizationNotFoundError
from ai_runtime.ports.api_key_hasher import ApiKeyHasher
from ai_runtime.ports.api_key_repository import ApiKeyRepository
from ai_runtime.ports.organization_repository import OrganizationRepository


@dataclass(frozen=True, slots=True)
class CreateApiKeyCommand:
    """Input for creating a new API key."""

    organization_id: UUID
    name: str | None = None


@dataclass(frozen=True, slots=True)
class CreateApiKeyResult:
    """Creation result: metadata plus the one-time plaintext secret.

    ``secret`` is returned exactly once from this use case and is never
    readable again from persistence.
    """

    api_key: ApiKeyMetadata
    secret: str


class CreateApiKey:
    """Create and persist an active API key for an existing organization."""

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        organizations: OrganizationRepository,
        hasher: ApiKeyHasher,
    ) -> None:
        self._api_keys = api_keys
        self._organizations = organizations
        self._hasher = hasher

    async def execute(self, command: CreateApiKeyCommand) -> CreateApiKeyResult:
        """Persist a hashed key; return metadata and the one-time plaintext secret."""
        organization = await self._organizations.get_by_id(command.organization_id)
        if organization is None:
            raise OrganizationNotFoundError(f"organization not found: {command.organization_id}")

        secret, prefix = self._hasher.generate_secret()
        now = datetime.now(UTC)
        api_key = ApiKey(
            id=uuid4(),
            organization_id=command.organization_id,
            name=command.name,
            prefix=prefix,
            secret_hash=self._hasher.hash_secret(secret),
            status=ApiKeyStatus.ACTIVE,
            created_at=now,
            revoked_at=None,
            updated_at=now,
        )
        stored = await self._api_keys.add(api_key)
        return CreateApiKeyResult(api_key=stored.to_metadata(), secret=secret)

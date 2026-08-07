"""Use case for revoking an API key credential."""

from datetime import UTC, datetime
from uuid import UUID
from ai_runtime.domain.api_key import ApiKeyMetadata, ApiKeyNotFoundError
from ai_runtime.ports.api_key_repository import ApiKeyRepository


class RevokeApiKey:
    """Mark an API key as revoked.

    Policy: explicit error on double-revoke. Calling revoke on an already
    revoked key raises ``ApiKeyAlreadyRevokedError`` (not idempotent).
    """

    def __init__(self, api_keys: ApiKeyRepository) -> None:
        self._api_keys = api_keys

    async def execute(self, api_key_id: UUID) -> ApiKeyMetadata:
        """Revoke the key or raise when missing / already revoked."""
        api_key = await self._api_keys.get_by_id(api_key_id)
        if api_key is None:
            raise ApiKeyNotFoundError(f"api key not found: {api_key_id}")

        revoked = api_key.revoke(datetime.now(UTC))
        stored = await self._api_keys.save(revoked)
        return stored.to_metadata()

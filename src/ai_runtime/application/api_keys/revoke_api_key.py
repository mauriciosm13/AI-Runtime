"""Use case for revoking an API key credential."""

from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.api_key import ApiKeyMetadata, ApiKeyNotFoundError
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.ports.api_key_repository import ApiKeyRepository
from ai_runtime.ports.audit_repository import AuditRepository


class RevokeApiKey:
    """Mark an API key as revoked.

    Policy: explicit error on double-revoke. Calling revoke on an already
    revoked key raises ``ApiKeyAlreadyRevokedError`` (not idempotent).
    """

    def __init__(self, api_keys: ApiKeyRepository, audit_events: AuditRepository) -> None:
        self._api_keys = api_keys
        self._audit_events = audit_events

    async def execute(self, api_key_id: UUID) -> ApiKeyMetadata:
        """Revoke the key or raise when missing / already revoked."""
        api_key = await self._api_keys.get_by_id(api_key_id)
        if api_key is None:
            raise ApiKeyNotFoundError(f"api key not found: {api_key_id}")

        now = datetime.now(UTC)
        revoked = api_key.revoke(now)
        stored = await self._api_keys.save(revoked)
        await self._audit_events.add(
            AuditEvent(
                id=uuid4(),
                action="api_key.revoked",
                occurred_at=now,
                organization_id=stored.organization_id,
                resource_type="api_key",
                resource_id=str(stored.id),
                metadata={"prefix": stored.prefix},
            )
        )
        return stored.to_metadata()

"""Use case for rotating an active API key credential."""

from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.application.api_keys.create_api_key import CreateApiKeyResult
from ai_runtime.domain.api_key import ApiKey, ApiKeyNotFoundError, ApiKeyStatus
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.ports.api_key_hasher import ApiKeyHasher
from ai_runtime.ports.api_key_repository import ApiKeyRepository
from ai_runtime.ports.audit_repository import AuditRepository


class RotateApiKey:
    """Revoke an active key and issue a replacement in the same organization."""

    def __init__(
        self,
        api_keys: ApiKeyRepository,
        hasher: ApiKeyHasher,
        audit_events: AuditRepository,
    ) -> None:
        self._api_keys = api_keys
        self._hasher = hasher
        self._audit_events = audit_events

    async def execute(self, api_key_id: UUID) -> CreateApiKeyResult:
        """Revoke ``api_key_id`` when active and return metadata plus a one-time secret."""
        api_key = await self._api_keys.get_by_id(api_key_id)
        if api_key is None:
            raise ApiKeyNotFoundError(f"api key not found: {api_key_id}")

        now = datetime.now(UTC)
        revoked = api_key.revoke(now)

        secret, prefix = self._hasher.generate_secret()
        replacement = ApiKey(
            id=uuid4(),
            organization_id=api_key.organization_id,
            name=api_key.name,
            prefix=prefix,
            secret_hash=self._hasher.hash_secret(secret),
            status=ApiKeyStatus.ACTIVE,
            created_at=now,
            revoked_at=None,
            updated_at=now,
        )
        stored = await self._api_keys.revoke_and_add(revoked, replacement)
        await self._audit_events.add(
            AuditEvent(
                id=uuid4(),
                action="api_key.rotated",
                occurred_at=now,
                organization_id=stored.organization_id,
                resource_type="api_key",
                resource_id=str(stored.id),
                metadata={"previous_key_id": str(api_key_id), "prefix": stored.prefix},
            )
        )
        return CreateApiKeyResult(api_key=stored.to_metadata(), secret=secret)

"""Unit tests for RevokeApiKey with an in-memory repository."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.api_keys.revoke_api_key import RevokeApiKey
from ai_runtime.domain.api_key import ApiKey, ApiKeyAlreadyRevokedError, ApiKeyNotFoundError, ApiKeyStatus


class FakeApiKeyRepository:
    """Deterministic in-memory ApiKeyRepository."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, ApiKey] = {}

    async def add(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key

    async def get_by_id(self, api_key_id: UUID) -> ApiKey | None:
        return self._by_id.get(api_key_id)

    async def list_by_organization(self, organization_id: UUID) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.organization_id == organization_id]

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.prefix == prefix]

    async def save(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key


def _active_key() -> ApiKey:
    now = datetime.now(UTC)
    return ApiKey(
        id=uuid4(),
        organization_id=uuid4(),
        name="ci",
        prefix="airt_abcdefgh",
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$fake",
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )


def test_revoke_api_key_marks_revoked() -> None:
    """RevokeApiKey sets status revoked and revoked_at."""
    repository = FakeApiKeyRepository()
    key = asyncio.run(repository.add(_active_key()))
    use_case = RevokeApiKey(repository)

    metadata = asyncio.run(use_case.execute(key.id))

    assert metadata.status is ApiKeyStatus.REVOKED
    assert metadata.revoked_at is not None
    assert not hasattr(metadata, "secret_hash")
    stored = asyncio.run(repository.get_by_id(key.id))
    assert stored is not None
    assert stored.status is ApiKeyStatus.REVOKED
    assert stored.revoked_at is not None


def test_revoke_api_key_missing_raises() -> None:
    """RevokeApiKey raises when the key does not exist."""
    use_case = RevokeApiKey(FakeApiKeyRepository())
    missing_id = uuid4()
    with pytest.raises(ApiKeyNotFoundError, match=str(missing_id)):
        asyncio.run(use_case.execute(missing_id))


def test_revoke_api_key_already_revoked_raises() -> None:
    """Double-revoke raises ApiKeyAlreadyRevokedError (explicit non-idempotent policy)."""
    repository = FakeApiKeyRepository()
    key = asyncio.run(repository.add(_active_key()))
    use_case = RevokeApiKey(repository)
    asyncio.run(use_case.execute(key.id))

    with pytest.raises(ApiKeyAlreadyRevokedError, match="already revoked"):
        asyncio.run(use_case.execute(key.id))

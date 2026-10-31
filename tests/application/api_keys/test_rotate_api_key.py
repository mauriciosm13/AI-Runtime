"""Unit tests for RotateApiKey with in-memory fakes."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.api_keys.rotate_api_key import RotateApiKey
from ai_runtime.domain.api_key import ApiKey, ApiKeyAlreadyRevokedError, ApiKeyNotFoundError, ApiKeyStatus
from ai_runtime.domain.audit import AuditEvent
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher


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

    async def revoke_and_add(self, revoked: ApiKey, replacement: ApiKey) -> ApiKey:
        self._by_id[revoked.id] = revoked
        self._by_id[replacement.id] = replacement
        return replacement


class FailRevokeAndAddRepository(FakeApiKeyRepository):
    """Fails during atomic rotate persistence."""

    async def revoke_and_add(self, revoked: ApiKey, replacement: ApiKey) -> ApiKey:
        raise RuntimeError("persist failed")


class FakeAuditRepository:
    """In-memory AuditRepository for rotate tests."""

    def __init__(self) -> None:
        self.added: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> AuditEvent:
        self.added.append(event)
        return event

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        return next((event for event in self.added if event.id == event_id), None)


def _active_key(*, name: str | None = "ci") -> ApiKey:
    now = datetime.now(UTC)
    return ApiKey(
        id=uuid4(),
        organization_id=uuid4(),
        name=name,
        prefix="airt_abcdefgh",
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$fake",
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )


def test_rotate_api_key_revokes_and_creates_replacement() -> None:
    """RotateApiKey revokes the old key and returns a new active secret."""
    repository = FakeApiKeyRepository()
    key = asyncio.run(repository.add(_active_key()))
    audit = FakeAuditRepository()
    hasher = Argon2ApiKeyHasher()
    use_case = RotateApiKey(repository, hasher, audit)

    result = asyncio.run(use_case.execute(key.id))

    assert result.api_key.id != key.id
    assert result.api_key.organization_id == key.organization_id
    assert result.api_key.name == key.name
    assert result.api_key.status is ApiKeyStatus.ACTIVE
    assert result.secret.startswith("airt_")
    stored_old = asyncio.run(repository.get_by_id(key.id))
    assert stored_old is not None
    assert stored_old.status is ApiKeyStatus.REVOKED
    assert audit.added[0].action == "api_key.rotated"
    assert audit.added[0].metadata["previous_key_id"] == str(key.id)


def test_rotate_api_key_missing_raises() -> None:
    """RotateApiKey raises when the key does not exist."""
    use_case = RotateApiKey(FakeApiKeyRepository(), Argon2ApiKeyHasher(), FakeAuditRepository())
    missing_id = uuid4()
    with pytest.raises(ApiKeyNotFoundError, match=str(missing_id)):
        asyncio.run(use_case.execute(missing_id))


def test_rotate_api_key_persist_failure_leaves_original_active() -> None:
    """Failed revoke_and_add must not leave the org without an active key."""
    repository = FailRevokeAndAddRepository()
    key = asyncio.run(repository.add(_active_key()))
    use_case = RotateApiKey(repository, Argon2ApiKeyHasher(), FakeAuditRepository())

    with pytest.raises(RuntimeError, match="persist failed"):
        asyncio.run(use_case.execute(key.id))

    stored = asyncio.run(repository.get_by_id(key.id))
    assert stored is not None
    assert stored.status is ApiKeyStatus.ACTIVE


def test_rotate_api_key_already_revoked_raises() -> None:
    """RotateApiKey rejects keys that are already revoked."""
    repository = FakeApiKeyRepository()
    key = asyncio.run(repository.add(_active_key()))
    use_case = RotateApiKey(repository, Argon2ApiKeyHasher(), FakeAuditRepository())
    asyncio.run(use_case.execute(key.id))

    with pytest.raises(ApiKeyAlreadyRevokedError, match="already revoked"):
        asyncio.run(use_case.execute(key.id))

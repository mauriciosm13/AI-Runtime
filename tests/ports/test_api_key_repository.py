"""Unit tests for the ApiKeyRepository port contract."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.ports.api_key_repository import ApiKeyRepository


class FakeApiKeyRepository:
    """In-memory stand-in that satisfies ApiKeyRepository."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, ApiKey] = {}

    async def add(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key

    async def get_by_id(self, api_key_id: UUID) -> ApiKey | None:
        return self._by_id.get(api_key_id)

    async def list_by_organization(self, organization_id: UUID) -> Sequence[ApiKey]:
        keys = [key for key in self._by_id.values() if key.organization_id == organization_id]
        return sorted(keys, key=lambda key: key.created_at, reverse=True)

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.prefix == prefix]

    async def save(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key


def test_fake_repository_satisfies_api_key_repository_contract() -> None:
    """A structural fake is accepted as ApiKeyRepository."""
    repository: ApiKeyRepository = FakeApiKeyRepository()
    assert isinstance(repository, ApiKeyRepository)
    now = datetime.now(UTC)
    organization_id = uuid4()
    api_key = ApiKey(
        id=uuid4(),
        organization_id=organization_id,
        name="ci",
        prefix="airt_testhash",
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$fake",
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )
    stored = asyncio.run(repository.add(api_key))
    assert asyncio.run(repository.get_by_id(stored.id)) == stored
    assert list(asyncio.run(repository.list_by_organization(organization_id))) == [stored]
    assert list(asyncio.run(repository.find_by_prefix("airt_testhash"))) == [stored]

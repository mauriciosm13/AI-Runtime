"""Unit tests for ListApiKeysForOrganization with in-memory fakes."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.api_keys.list_api_keys import ListApiKeysForOrganization
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.domain.organization import Organization, OrganizationNotFoundError, OrganizationStatus


class FakeOrganizationRepository:
    """Deterministic in-memory OrganizationRepository."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> Organization:
        self._by_id[organization.id] = organization
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self._by_id.get(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        return None


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
        keys = [key for key in self._by_id.values() if key.organization_id == organization_id]
        return sorted(keys, key=lambda key: key.created_at, reverse=True)

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.prefix == prefix]

    async def save(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key


def test_list_api_keys_returns_metadata_only() -> None:
    """List returns metadata projections without secret_hash."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    now = datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(organizations.add(organization))
    older = ApiKey(
        id=uuid4(),
        organization_id=organization.id,
        name="older",
        prefix="airt_olderxxx",
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$older",
        status=ApiKeyStatus.ACTIVE,
        created_at=now - timedelta(hours=1),
        revoked_at=None,
        updated_at=now - timedelta(hours=1),
    )
    newer = ApiKey(
        id=uuid4(),
        organization_id=organization.id,
        name="newer",
        prefix="airt_newerxxx",
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$newer",
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )
    asyncio.run(api_keys.add(older))
    asyncio.run(api_keys.add(newer))
    use_case = ListApiKeysForOrganization(api_keys, organizations)

    result = asyncio.run(use_case.execute(organization.id))

    assert [item.name for item in result] == ["newer", "older"]
    for item in result:
        assert not hasattr(item, "secret_hash")
        assert "secret_hash" not in item.__dataclass_fields__


def test_list_api_keys_fails_when_organization_missing() -> None:
    """List raises OrganizationNotFoundError when the org does not exist."""
    use_case = ListApiKeysForOrganization(FakeApiKeyRepository(), FakeOrganizationRepository())
    missing_id = uuid4()
    with pytest.raises(OrganizationNotFoundError, match=str(missing_id)):
        asyncio.run(use_case.execute(missing_id))

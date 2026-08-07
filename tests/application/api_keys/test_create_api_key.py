"""Unit tests for CreateApiKey with in-memory fakes."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.api_keys.create_api_key import CreateApiKey, CreateApiKeyCommand
from ai_runtime.domain.api_key import ApiKey
from ai_runtime.domain.organization import Organization, OrganizationNotFoundError, OrganizationStatus
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher


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
        for organization in self._by_id.values():
            if organization.slug == slug:
                return organization
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
        return [key for key in self._by_id.values() if key.organization_id == organization_id]

    async def find_by_prefix(self, prefix: str) -> Sequence[ApiKey]:
        return [key for key in self._by_id.values() if key.prefix == prefix]

    async def save(self, api_key: ApiKey) -> ApiKey:
        self._by_id[api_key.id] = api_key
        return api_key


def _organization() -> Organization:
    now = datetime.now(UTC)
    return Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def test_create_api_key_returns_metadata_and_one_time_secret() -> None:
    """CreateApiKey returns metadata + plaintext secret; persistence stores hash only."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    organization = asyncio.run(organizations.add(_organization()))
    use_case = CreateApiKey(api_keys, organizations, hasher)

    result = asyncio.run(use_case.execute(CreateApiKeyCommand(organization_id=organization.id, name="ci")))

    assert result.secret.startswith("airt_")
    assert result.api_key.name == "ci"
    assert result.api_key.organization_id == organization.id
    assert result.api_key.prefix.startswith("airt_")
    assert result.secret.startswith(result.api_key.prefix)
    assert not hasattr(result.api_key, "secret_hash")

    stored = asyncio.run(api_keys.get_by_id(result.api_key.id))
    assert stored is not None
    assert stored.secret_hash != result.secret
    assert result.secret not in stored.secret_hash
    assert hasher.verify_secret(result.secret, stored.secret_hash) is True


def test_create_api_key_fails_when_organization_missing() -> None:
    """CreateApiKey raises OrganizationNotFoundError when the org does not exist."""
    use_case = CreateApiKey(FakeApiKeyRepository(), FakeOrganizationRepository(), Argon2ApiKeyHasher())
    missing_id = uuid4()

    with pytest.raises(OrganizationNotFoundError, match=str(missing_id)):
        asyncio.run(use_case.execute(CreateApiKeyCommand(organization_id=missing_id)))

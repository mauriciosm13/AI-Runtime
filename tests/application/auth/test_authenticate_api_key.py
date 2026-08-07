"""Unit tests for AuthenticateApiKey with in-memory fakes."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
import pytest
from ai_runtime.application.auth.authenticate_api_key import AuthenticateApiKey
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus, InvalidApiKeyCredentialsError
from ai_runtime.domain.organization import Organization, OrganizationStatus, OrganizationSuspendedError
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


def _organization(*, status: OrganizationStatus = OrganizationStatus.ACTIVE) -> Organization:
    now = datetime.now(UTC)
    return Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _seed_active_key(
    organizations: FakeOrganizationRepository,
    api_keys: FakeApiKeyRepository,
    hasher: Argon2ApiKeyHasher,
    *,
    organization: Organization | None = None,
) -> tuple[Organization, ApiKey, str]:
    org = organization or _organization()
    asyncio.run(organizations.add(org))
    secret, prefix = hasher.generate_secret()
    now = datetime.now(UTC)
    key = ApiKey(
        id=uuid4(),
        organization_id=org.id,
        name="ci",
        prefix=prefix,
        secret_hash=hasher.hash_secret(secret),
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )
    asyncio.run(api_keys.add(key))
    return org, key, secret


def test_authenticate_returns_principal_for_valid_key() -> None:
    """Valid active key + active org yields a non-secret principal."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    org, key, secret = _seed_active_key(organizations, api_keys, hasher)
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    principal = asyncio.run(use_case.execute(secret))

    assert principal.api_key_id == key.id
    assert principal.organization_id == org.id
    assert principal.organization_slug == org.slug
    assert principal.api_key_prefix == key.prefix
    assert not hasattr(principal, "secret")
    assert not hasattr(principal, "secret_hash")


def test_authenticate_rejects_wrong_secret() -> None:
    """Hash mismatch returns generic invalid credentials."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    _org, key, secret = _seed_active_key(organizations, api_keys, hasher)
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute(secret + "x"))

    assert hasher.verify_secret(secret, key.secret_hash) is True


def test_authenticate_rejects_unknown_prefix() -> None:
    """Unknown lookup prefix returns generic invalid credentials."""
    use_case = AuthenticateApiKey(FakeApiKeyRepository(), FakeOrganizationRepository(), Argon2ApiKeyHasher())

    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute("airt_unknownprefix0000000000000000000000"))


def test_authenticate_rejects_revoked_key() -> None:
    """Cryptographically valid but revoked keys are rejected as unauthorized."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    org, key, secret = _seed_active_key(organizations, api_keys, hasher)
    revoked = key.revoke(datetime.now(UTC))
    asyncio.run(api_keys.save(revoked))
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute(secret))
    assert org.id == revoked.organization_id


def test_authenticate_rejects_missing_organization() -> None:
    """Key whose organization row is gone yields generic invalid credentials."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    org, _key, secret = _seed_active_key(organizations, api_keys, hasher)
    del organizations._by_id[org.id]
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute(secret))


def test_authenticate_rejects_suspended_organization() -> None:
    """Suspended organization raises OrganizationSuspendedError (403 at API)."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    org = _organization(status=OrganizationStatus.SUSPENDED)
    _org, _key, secret = _seed_active_key(organizations, api_keys, hasher, organization=org)
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    with pytest.raises(OrganizationSuspendedError):
        asyncio.run(use_case.execute(secret))


def test_authenticate_rejects_malformed_secret() -> None:
    """Secrets without airt_ prefix or too short are rejected."""
    use_case = AuthenticateApiKey(FakeApiKeyRepository(), FakeOrganizationRepository(), Argon2ApiKeyHasher())

    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute("not-an-airt-key"))
    with pytest.raises(InvalidApiKeyCredentialsError):
        asyncio.run(use_case.execute("airt_short"))


def test_authenticate_matches_among_shared_prefix_candidates() -> None:
    """When multiple keys share a prefix, verify until one secret matches."""
    organizations = FakeOrganizationRepository()
    api_keys = FakeApiKeyRepository()
    hasher = Argon2ApiKeyHasher()
    org, matching_key, secret = _seed_active_key(organizations, api_keys, hasher)
    now = datetime.now(UTC)
    decoy = ApiKey(
        id=uuid4(),
        organization_id=org.id,
        name="decoy",
        prefix=matching_key.prefix,
        secret_hash=hasher.hash_secret("airt_decoysecretvalue012345678901234567890"),
        status=ApiKeyStatus.ACTIVE,
        created_at=now,
        revoked_at=None,
        updated_at=now,
    )
    asyncio.run(api_keys.add(decoy))
    use_case = AuthenticateApiKey(api_keys, organizations, hasher)

    principal = asyncio.run(use_case.execute(secret))
    assert principal.api_key_id == matching_key.id

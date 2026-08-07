"""Integration tests for SqlAlchemyApiKeyRepository against PostgreSQL."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import ApiKeyRow, OrganizationRow
from ai_runtime.infrastructure.db.repositories.api_key_repository import SqlAlchemyApiKeyRepository
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]

# Touch ORM rows so both tables register on Base.metadata for create_all.
assert ApiKeyRow.__tablename__ == "api_keys"
assert OrganizationRow.__tablename__ == "organizations"


async def _postgres_available() -> bool:
    engine = create_db_engine(_TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except (OperationalError, OSError):
        return False
    finally:
        await engine.dispose()


async def _with_clean_schema(scenario: _Scenario) -> None:
    """Run ``scenario`` against a freshly created organizations + api_keys schema."""
    if not await _postgres_available():
        pytest.skip("PostgreSQL is not available at localhost:5432")

    engine = create_db_engine(_TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await scenario(create_session_factory(engine))
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _seed_organization(session_factory: _SessionFactory) -> Organization:
    now = datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    async with session_factory() as session:
        return await SqlAlchemyOrganizationRepository(session).add(organization)


def test_repository_add_get_list_and_find_by_prefix() -> None:
    """Repository persists hashed keys and loads them by id, org, and prefix."""

    async def scenario(session_factory: _SessionFactory) -> None:
        organization = await _seed_organization(session_factory)
        hasher = Argon2ApiKeyHasher()
        secret, prefix = hasher.generate_secret()
        now = datetime.now(UTC)
        api_key = ApiKey(
            id=uuid4(),
            organization_id=organization.id,
            name="ci",
            prefix=prefix,
            secret_hash=hasher.hash_secret(secret),
            status=ApiKeyStatus.ACTIVE,
            created_at=now,
            revoked_at=None,
            updated_at=now,
        )
        async with session_factory() as session:
            repository = SqlAlchemyApiKeyRepository(session)
            stored = await repository.add(api_key)
            assert stored.id == api_key.id
            assert stored.secret_hash == api_key.secret_hash
            assert stored.secret_hash != secret
            loaded = await repository.get_by_id(api_key.id)
            assert loaded == stored
            listed = await repository.list_by_organization(organization.id)
            assert listed == [stored]
            found = await repository.find_by_prefix(prefix)
            assert found == [stored]
            assert await repository.get_by_id(uuid4()) is None
            assert await repository.find_by_prefix("airt_missing") == []
            # Confirm plaintext is never written as secret_hash.
            result = await session.execute(
                text("SELECT secret_hash, prefix FROM api_keys WHERE id = :id"),
                {"id": api_key.id},
            )
            row = result.one()
            assert row.secret_hash != secret
            assert secret not in row.secret_hash
            assert row.prefix == prefix

    asyncio.run(_with_clean_schema(scenario))


def test_repository_save_persists_revoke() -> None:
    """save() persists revoked status and revoked_at."""

    async def scenario(session_factory: _SessionFactory) -> None:
        organization = await _seed_organization(session_factory)
        now = datetime.now(UTC)
        api_key = ApiKey(
            id=uuid4(),
            organization_id=organization.id,
            name=None,
            prefix="airt_abcdefgh",
            secret_hash="$argon2id$v=19$m=65536,t=3,p=4$persist",
            status=ApiKeyStatus.ACTIVE,
            created_at=now,
            revoked_at=None,
            updated_at=now,
        )
        async with session_factory() as session:
            repository = SqlAlchemyApiKeyRepository(session)
            await repository.add(api_key)
        revoke_at = datetime.now(UTC)
        async with session_factory() as session:
            repository = SqlAlchemyApiKeyRepository(session)
            revoked = api_key.revoke(revoke_at)
            stored = await repository.save(revoked)
            assert stored.status is ApiKeyStatus.REVOKED
            assert stored.revoked_at == revoke_at
            reloaded = await repository.get_by_id(api_key.id)
            assert reloaded == stored

    asyncio.run(_with_clean_schema(scenario))

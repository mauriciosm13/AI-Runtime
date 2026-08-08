"""Integration tests for SqlAlchemyUsageRepository against PostgreSQL."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.domain.api_key import ApiKey, ApiKeyStatus
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.usage import UsageRecord
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import ApiKeyRow, OrganizationRow, UsageRecordRow
from ai_runtime.infrastructure.db.repositories.api_key_repository import SqlAlchemyApiKeyRepository
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository
from ai_runtime.infrastructure.db.repositories.usage_repository import SqlAlchemyUsageRepository
from ai_runtime.infrastructure.security.api_key_crypto import Argon2ApiKeyHasher

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]

assert ApiKeyRow.__tablename__ == "api_keys"
assert OrganizationRow.__tablename__ == "organizations"
assert UsageRecordRow.__tablename__ == "usage_records"


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
    """Run ``scenario`` against a freshly created schema including usage_records."""
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


async def _seed_org_and_key(session_factory: _SessionFactory) -> tuple[Organization, ApiKey]:
    now = datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name="Acme Corp",
        slug="acme-corp",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    hasher = Argon2ApiKeyHasher()
    secret, prefix = hasher.generate_secret()
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
        await SqlAlchemyOrganizationRepository(session).add(organization)
        await SqlAlchemyApiKeyRepository(session).add(api_key)
    return organization, api_key


def test_repository_add_get_by_id_and_request_id() -> None:
    """Repository persists usage rows and loads them by id and request_id."""

    async def scenario(session_factory: _SessionFactory) -> None:
        organization, api_key = await _seed_org_and_key(session_factory)
        now = datetime.now(UTC)
        record = UsageRecord(
            id=uuid4(),
            request_id="req_usage_1",
            organization_id=organization.id,
            api_key_id=api_key.id,
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=100,
            output_tokens=40,
            estimated_cost_usd=Decimal("0.00003900"),
            created_at=now,
        )
        async with session_factory() as session:
            repository = SqlAlchemyUsageRepository(session)
            stored = await repository.add(record)
            assert stored.id == record.id
            assert stored.estimated_cost_usd == Decimal("0.00003900")
            loaded = await repository.get_by_id(record.id)
            assert loaded == stored
            by_request = await repository.get_by_request_id("req_usage_1")
            assert by_request == stored
            assert await repository.get_by_request_id("missing") is None
            result = await session.execute(
                text("SELECT provider, model, input_tokens, output_tokens FROM usage_records WHERE id = :id"),
                {"id": record.id},
            )
            row = result.one()
            assert row.provider == "openai"
            assert row.model == "gpt-4o-mini"
            assert row.input_tokens == 100
            assert row.output_tokens == 40

    asyncio.run(_with_clean_schema(scenario))


def test_repository_allows_null_tokens_and_cost() -> None:
    """Usage rows without provider token counts persist null accounting fields."""

    async def scenario(session_factory: _SessionFactory) -> None:
        organization, api_key = await _seed_org_and_key(session_factory)
        record = UsageRecord(
            id=uuid4(),
            request_id="req_usage_null",
            organization_id=organization.id,
            api_key_id=api_key.id,
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=None,
            output_tokens=None,
            estimated_cost_usd=None,
            created_at=datetime.now(UTC),
        )
        async with session_factory() as session:
            stored = await SqlAlchemyUsageRepository(session).add(record)
            assert stored.input_tokens is None
            assert stored.output_tokens is None
            assert stored.estimated_cost_usd is None

    asyncio.run(_with_clean_schema(scenario))


def test_repository_sum_tokens_for_organization_in_period() -> None:
    """Repository aggregates input and output tokens within a half-open period."""

    async def scenario(session_factory: _SessionFactory) -> None:
        organization, api_key = await _seed_org_and_key(session_factory)
        in_period = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
        out_period = datetime(2026, 7, 31, 23, 59, tzinfo=UTC)
        async with session_factory() as session:
            repository = SqlAlchemyUsageRepository(session)
            await repository.add(
                UsageRecord(
                    id=uuid4(),
                    request_id="req_in_period",
                    organization_id=organization.id,
                    api_key_id=api_key.id,
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=100,
                    output_tokens=40,
                    estimated_cost_usd=Decimal("0.00003900"),
                    created_at=in_period,
                )
            )
            await repository.add(
                UsageRecord(
                    id=uuid4(),
                    request_id="req_out_period",
                    organization_id=organization.id,
                    api_key_id=api_key.id,
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=500,
                    output_tokens=500,
                    estimated_cost_usd=Decimal("0.00010000"),
                    created_at=out_period,
                )
            )

        async with session_factory() as session:
            repository = SqlAlchemyUsageRepository(session)
            total = await repository.sum_tokens_for_organization_in_period(
                organization.id,
                start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                end=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
            )
            assert total == 140

    asyncio.run(_with_clean_schema(scenario))

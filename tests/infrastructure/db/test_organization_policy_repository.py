"""Integration tests for SqlAlchemyOrganizationPolicyRepository against PostgreSQL."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.organization_policy import ModelEntitlement, OrganizationPolicy
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import OrganizationModelEntitlementRow, OrganizationPolicyRow, OrganizationRow
from ai_runtime.infrastructure.db.repositories.organization_policy_repository import SqlAlchemyOrganizationPolicyRepository
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]

assert OrganizationPolicyRow.__tablename__ == "organization_policies"
assert OrganizationModelEntitlementRow.__tablename__ == "organization_model_entitlements"
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
        await SqlAlchemyOrganizationRepository(session).add(organization)
    return organization


def test_repository_returns_default_policy_when_missing() -> None:
    async def scenario(session_factory: _SessionFactory) -> None:
        organization = await _seed_organization(session_factory)
        async with session_factory() as session:
            repository = SqlAlchemyOrganizationPolicyRepository(session)
            policy = await repository.get_policy(organization.id)
            assert policy == OrganizationPolicy(organization_id=organization.id)
            assert await repository.list_entitlements(organization.id) == ()

    asyncio.run(_with_clean_schema(scenario))


def test_repository_loads_policy_and_entitlements() -> None:
    async def scenario(session_factory: _SessionFactory) -> None:
        organization = await _seed_organization(session_factory)
        now = datetime.now(UTC)
        async with session_factory() as session:
            session.add(
                OrganizationPolicyRow(
                    organization_id=organization.id,
                    monthly_token_limit=50000,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                OrganizationModelEntitlementRow(
                    id=uuid4(),
                    organization_id=organization.id,
                    model="gpt-4o-mini",
                )
            )
            await session.commit()

        async with session_factory() as session:
            repository = SqlAlchemyOrganizationPolicyRepository(session)
            policy = await repository.get_policy(organization.id)
            assert policy.monthly_token_limit == 50000
            entitlements = await repository.list_entitlements(organization.id)
            assert entitlements == (ModelEntitlement(organization_id=organization.id, model="gpt-4o-mini"),)

    asyncio.run(_with_clean_schema(scenario))

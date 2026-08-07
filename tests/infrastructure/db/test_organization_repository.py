"""Integration tests for SqlAlchemyOrganizationRepository against PostgreSQL."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.domain.organization import Organization, OrganizationSlugConflictError, OrganizationStatus
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import OrganizationRow  # noqa: F401 — register metadata
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]


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
    """Run ``scenario`` against a freshly created organizations schema."""
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


def test_repository_add_and_get_by_id_and_slug() -> None:
    """Repository persists an organization and loads it by id and slug."""

    async def scenario(session_factory: _SessionFactory) -> None:
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
            repository = SqlAlchemyOrganizationRepository(session)
            stored = await repository.add(organization)
            assert stored == organization
            assert await repository.get_by_id(organization.id) == organization
            assert await repository.get_by_slug("acme-corp") == organization
            assert await repository.get_by_id(uuid4()) is None
            assert await repository.get_by_slug("missing") is None

    asyncio.run(_with_clean_schema(scenario))


def test_repository_add_rejects_duplicate_slug() -> None:
    """Duplicate slug inserts raise OrganizationSlugConflictError."""

    async def scenario(session_factory: _SessionFactory) -> None:
        now = datetime.now(UTC)
        first = Organization(
            id=uuid4(),
            name="First",
            slug="shared-slug",
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        second = Organization(
            id=uuid4(),
            name="Second",
            slug="shared-slug",
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        async with session_factory() as session:
            repository = SqlAlchemyOrganizationRepository(session)
            await repository.add(first)
        async with session_factory() as session:
            repository = SqlAlchemyOrganizationRepository(session)
            with pytest.raises(OrganizationSlugConflictError, match="shared-slug"):
                await repository.add(second)

    asyncio.run(_with_clean_schema(scenario))

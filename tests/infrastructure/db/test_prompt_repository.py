"""Integration tests for SqlAlchemyPromptRepository against PostgreSQL."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.domain.generation import MessageRole
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.prompt import PromptMessageTemplate
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import OrganizationRow, PromptTemplateRow
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository
from ai_runtime.infrastructure.db.repositories.prompt_repository import SqlAlchemyPromptRepository

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]

assert PromptTemplateRow.__tablename__ == "prompt_templates"
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


async def _seed_organization(session_factory: _SessionFactory, slug: str) -> Organization:
    now = datetime.now(UTC)
    organization = Organization(id=uuid4(), name=slug, slug=slug, status=OrganizationStatus.ACTIVE, created_at=now, updated_at=now)
    async with session_factory() as session:
        await SqlAlchemyOrganizationRepository(session).add(organization)
    return organization


_MESSAGES = (
    PromptMessageTemplate(role=MessageRole.SYSTEM, content="You help {{company}}."),
    PromptMessageTemplate(role=MessageRole.USER, content="{{question}}"),
)


def test_repository_versions_round_trip_and_isolation() -> None:
    async def scenario(session_factory: _SessionFactory) -> None:
        owner = await _seed_organization(session_factory, "owner-org")
        other = await _seed_organization(session_factory, "other-org")
        async with session_factory() as session:
            repository = SqlAlchemyPromptRepository(session)
            first = await repository.create_version(owner.id, "greet", _MESSAGES)
            second = await repository.create_version(owner.id, "greet", _MESSAGES[:1])
            assert (first.version, second.version) == (1, 2)
            assert first.messages == _MESSAGES
            assert (await repository.get(owner.id, "greet", None)) is not None
            latest = await repository.get(owner.id, "greet", None)
            assert latest is not None and latest.version == 2
            pinned = await repository.get(owner.id, "greet", 1)
            assert pinned is not None and pinned.messages == _MESSAGES
            assert await repository.get(owner.id, "greet", 9) is None
            assert [item.version for item in await repository.list_versions(owner.id, "greet")] == [1, 2]
            assert await repository.get(other.id, "greet", None) is None
            assert await repository.list_versions(other.id, "greet") == ()

    asyncio.run(_with_clean_schema(scenario))

"""Integration tests for SqlAlchemySemanticRetrievalRepository with pgvector."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ai_runtime.domain.organization import Organization, OrganizationStatus
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticChunk
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.engine import create_db_engine, create_session_factory
from ai_runtime.infrastructure.db.models import OrganizationRow, SemanticChunkRow
from ai_runtime.infrastructure.db.repositories.organization_repository import SqlAlchemyOrganizationRepository
from ai_runtime.infrastructure.db.repositories.semantic_retrieval_repository import SqlAlchemySemanticRetrievalRepository
from tests.infrastructure.db.schema import recreate_schema

_TEST_DATABASE_URL = "postgresql+asyncpg://ai_runtime:ai_runtime@localhost:5432/ai_runtime"
_SessionFactory = async_sessionmaker[AsyncSession]
_Scenario = Callable[[_SessionFactory], Awaitable[None]]

assert SemanticChunkRow.__tablename__ == "semantic_chunks"
assert OrganizationRow.__tablename__ == "organizations"


def _embedding(*, first: float) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


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
            await recreate_schema(connection)
        await scenario(create_session_factory(engine))
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _seed_organization(session_factory: _SessionFactory) -> Organization:
    now = datetime.now(UTC)
    organization = Organization(
        id=uuid4(),
        name="Acme",
        slug=f"acme-{uuid4()}",
        status=OrganizationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    async with session_factory() as session:
        await SqlAlchemyOrganizationRepository(session).add(organization)
    return organization


def test_repository_search_is_scoped_and_orders_by_similarity() -> None:
    async def scenario(session_factory: _SessionFactory) -> None:
        organization = await _seed_organization(session_factory)
        other = await _seed_organization(session_factory)
        now = datetime.now(UTC)
        async with session_factory() as session:
            repository = SqlAlchemySemanticRetrievalRepository(session)
            await repository.add(
                SemanticChunk(
                    id=uuid4(),
                    organization_id=organization.id,
                    content="near",
                    embedding=_embedding(first=1.0),
                    created_at=now,
                )
            )
            await repository.add(
                SemanticChunk(
                    id=uuid4(),
                    organization_id=organization.id,
                    content="far",
                    embedding=_embedding(first=-1.0),
                    created_at=now,
                )
            )
            await repository.add(
                SemanticChunk(
                    id=uuid4(),
                    organization_id=other.id,
                    content="other-org",
                    embedding=_embedding(first=1.0),
                    created_at=now,
                )
            )
        async with session_factory() as session:
            repository = SqlAlchemySemanticRetrievalRepository(session)
            hits = await repository.search(organization.id, _embedding(first=1.0), limit=2)
            assert len(hits) == 2
            assert hits[0].content == "near"
            assert hits[0].distance <= hits[1].distance
            assert all(hit.content != "other-org" for hit in hits)

    asyncio.run(_with_clean_schema(scenario))

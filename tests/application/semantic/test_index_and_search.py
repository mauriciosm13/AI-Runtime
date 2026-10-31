"""Use-case tests for semantic chunk indexing and search."""

import asyncio
import pytest
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.application.semantic.index_semantic_chunk import IndexSemanticChunk, IndexSemanticChunkCommand
from ai_runtime.application.semantic.search_semantic_chunks import SearchSemanticChunks
from ai_runtime.domain.organization import Organization, OrganizationNotFoundError, OrganizationStatus
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticChunk, SemanticSearchQuery, SemanticSearchResult


def _embedding(*, first: float = 1.0) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self._by_id: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> Organization:
        self._by_id[organization.id] = organization
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self._by_id.get(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        return None


class FakeSemanticRetrievalRepository:
    def __init__(self) -> None:
        self.chunks: list[SemanticChunk] = []
        self.last_search: tuple[UUID, tuple[float, ...], int] | None = None

    async def add(self, chunk: SemanticChunk) -> SemanticChunk:
        self.chunks.append(chunk)
        return chunk

    async def search(
        self,
        organization_id: UUID,
        query_embedding: tuple[float, ...],
        *,
        limit: int,
    ) -> list[SemanticSearchResult]:
        self.last_search = (organization_id, query_embedding, limit)
        return [
            SemanticSearchResult(chunk_id=chunk.id, content=chunk.content, distance=0.0)
            for chunk in self.chunks
            if chunk.organization_id == organization_id
        ][:limit]


def test_index_and_search_semantic_chunks() -> None:
    """Index persists through the repository; search delegates with the query embedding."""
    organizations = FakeOrganizationRepository()
    chunks = FakeSemanticRetrievalRepository()
    org_id = uuid4()
    now = datetime.now(UTC)
    asyncio.run(
        organizations.add(
            Organization(id=org_id, name="Acme", slug="acme", status=OrganizationStatus.ACTIVE, created_at=now, updated_at=now)
        )
    )
    index = IndexSemanticChunk(chunks, organizations)
    search = SearchSemanticChunks(chunks)
    stored = asyncio.run(index.execute(IndexSemanticChunkCommand(organization_id=org_id, content="doc", embedding=_embedding(first=0.9))))
    assert stored.organization_id == org_id
    query = SemanticSearchQuery(organization_id=org_id, query_embedding=_embedding(first=0.8), limit=2)
    hits = asyncio.run(search.execute(query))
    assert len(hits) == 1
    assert chunks.last_search is not None
    assert chunks.last_search[2] == 2


def test_index_raises_when_organization_missing() -> None:
    """Unknown organization ids are rejected before persistence."""
    index = IndexSemanticChunk(FakeSemanticRetrievalRepository(), FakeOrganizationRepository())
    with pytest.raises(OrganizationNotFoundError):
        asyncio.run(
            index.execute(
                IndexSemanticChunkCommand(organization_id=uuid4(), content="doc", embedding=_embedding()),
            )
        )

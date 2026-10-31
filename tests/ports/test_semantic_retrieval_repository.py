"""Unit tests for the SemanticRetrievalRepository port contract."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS, SemanticChunk, SemanticSearchResult
from ai_runtime.ports.semantic_retrieval_repository import SemanticRetrievalRepository


def _embedding() -> tuple[float, ...]:
    return tuple(0.0 for _ in range(DEFAULT_EMBEDDING_DIMENSIONS))


class FakeSemanticRetrievalRepository:
    async def add(self, chunk: SemanticChunk) -> SemanticChunk:
        return chunk

    async def search(self, organization_id, query_embedding, *, limit: int):
        return [
            SemanticSearchResult(chunk_id=uuid4(), content="hit", distance=0.0),
        ]


def test_fake_repository_satisfies_semantic_retrieval_contract() -> None:
    repository: SemanticRetrievalRepository = FakeSemanticRetrievalRepository()
    assert isinstance(repository, SemanticRetrievalRepository)
    chunk = SemanticChunk(
        id=uuid4(),
        organization_id=uuid4(),
        content="text",
        embedding=_embedding(),
        created_at=datetime.now(UTC),
    )
    stored = asyncio.run(repository.add(chunk))
    assert stored.id == chunk.id
    hits = asyncio.run(repository.search(chunk.organization_id, _embedding(), limit=1))
    assert hits[0].content == "hit"

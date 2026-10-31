"""Unit tests for semantic retrieval domain contracts."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.semantic_retrieval import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    SemanticChunk,
    SemanticSearchQuery,
    SemanticSearchResult,
)


def _embedding(*, first: float = 1.0) -> tuple[float, ...]:
    values = [0.0] * DEFAULT_EMBEDDING_DIMENSIONS
    values[0] = first
    return tuple(values)


def test_semantic_chunk_and_search_query_construct_cleanly() -> None:
    """Valid chunk, query, and result objects pass invariants."""
    organization_id = uuid4()
    chunk_id = uuid4()
    now = datetime.now(UTC)
    chunk = SemanticChunk(
        id=chunk_id,
        organization_id=organization_id,
        content="hello",
        embedding=_embedding(),
        created_at=now,
    )
    query = SemanticSearchQuery(organization_id=organization_id, query_embedding=_embedding(first=0.5), limit=3)
    result = SemanticSearchResult(chunk_id=chunk_id, content="hello", distance=0.1)
    assert chunk.content == "hello"
    assert query.limit == 3
    assert result.distance == 0.1


def test_rejects_wrong_embedding_dimensions() -> None:
    """Embeddings must match the catalog dimension count."""
    with pytest.raises(DomainValidationError, match="1536"):
        SemanticSearchQuery(organization_id=uuid4(), query_embedding=(1.0, 2.0), limit=1)

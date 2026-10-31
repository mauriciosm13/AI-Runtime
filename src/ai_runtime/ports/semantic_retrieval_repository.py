"""Port for persisting and searching organization-scoped semantic chunks."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID
from ai_runtime.domain.semantic_retrieval import SemanticChunk, SemanticSearchResult


@runtime_checkable
class SemanticRetrievalRepository(Protocol):
    """Store embedding vectors and run cosine-distance search per organization."""

    async def add(self, chunk: SemanticChunk) -> SemanticChunk:
        """Persist a semantic chunk."""
        ...

    async def search(
        self,
        organization_id: UUID,
        query_embedding: tuple[float, ...],
        *,
        limit: int,
    ) -> Sequence[SemanticSearchResult]:
        """Return the nearest chunks for ``organization_id`` ordered by ascending distance."""
        ...

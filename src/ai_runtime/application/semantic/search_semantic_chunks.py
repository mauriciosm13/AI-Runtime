"""Use case for organization-scoped semantic vector search."""

from collections.abc import Sequence
from ai_runtime.domain.semantic_retrieval import SemanticSearchQuery, SemanticSearchResult
from ai_runtime.ports.semantic_retrieval_repository import SemanticRetrievalRepository


class SearchSemanticChunks:
    """Run nearest-neighbor retrieval for one organization."""

    def __init__(self, chunks: SemanticRetrievalRepository) -> None:
        self._chunks = chunks

    async def execute(self, query: SemanticSearchQuery) -> Sequence[SemanticSearchResult]:
        return await self._chunks.search(
            query.organization_id,
            query.query_embedding,
            limit=query.limit,
        )

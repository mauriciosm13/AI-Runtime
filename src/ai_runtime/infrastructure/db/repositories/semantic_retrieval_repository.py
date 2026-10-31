"""SQLAlchemy adapter for semantic vector retrieval."""

from collections.abc import Sequence
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ai_runtime.domain.semantic_retrieval import SemanticChunk, SemanticSearchResult
from ai_runtime.infrastructure.db.models.semantic_chunk import SemanticChunkRow


def _to_domain(row: SemanticChunkRow) -> SemanticChunk:
    return SemanticChunk(
        id=row.id,
        organization_id=row.organization_id,
        content=row.content,
        embedding=tuple(float(value) for value in row.embedding),
        created_at=row.created_at,
    )


class SqlAlchemySemanticRetrievalRepository:
    """Persist and search semantic chunks with pgvector cosine distance."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, chunk: SemanticChunk) -> SemanticChunk:
        row = SemanticChunkRow(
            id=chunk.id,
            organization_id=chunk.organization_id,
            content=chunk.content,
            embedding=list(chunk.embedding),
            created_at=chunk.created_at,
        )
        self._session.add(row)
        await self._session.commit()
        return _to_domain(row)

    async def search(
        self,
        organization_id: UUID,
        query_embedding: tuple[float, ...],
        *,
        limit: int,
    ) -> Sequence[SemanticSearchResult]:
        distance = SemanticChunkRow.embedding.cosine_distance(list(query_embedding))
        statement = (
            select(SemanticChunkRow, distance.label("distance"))
            .where(SemanticChunkRow.organization_id == organization_id)
            .order_by(distance)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [SemanticSearchResult(chunk_id=row.id, content=row.content, distance=float(dist)) for row, dist in rows]

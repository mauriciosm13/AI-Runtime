"""Schemas for the /v1/semantic_chunks endpoint."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from ai_runtime.domain.embedding_routing import DEFAULT_RAG_EMBEDDING_MODEL
from ai_runtime.domain.semantic_retrieval import SemanticChunk


class CreateSemanticChunkRequest(BaseModel):
    """HTTP body for indexing organization knowledge."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    embedding_model: str = Field(default=DEFAULT_RAG_EMBEDDING_MODEL, min_length=1)


class SemanticChunkCreatedSchema(BaseModel):
    """Metadata returned after a chunk is stored."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    organization_id: UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, chunk: SemanticChunk) -> "SemanticChunkCreatedSchema":
        """Map a stored chunk to the public ingest response."""
        return cls(
            id=chunk.id,
            organization_id=chunk.organization_id,
            created_at=chunk.created_at,
        )

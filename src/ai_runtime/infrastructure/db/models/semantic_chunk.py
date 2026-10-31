"""ORM model for organization-scoped semantic chunks."""

from datetime import datetime
from uuid import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.domain.semantic_retrieval import DEFAULT_EMBEDDING_DIMENSIONS
from ai_runtime.infrastructure.db.base import Base


class SemanticChunkRow(Base):
    """A text chunk and embedding vector scoped to one organization."""

    __tablename__ = "semantic_chunks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(DEFAULT_EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

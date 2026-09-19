"""SQLAlchemy ORM mapping for the prompt_templates table."""

from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.infrastructure.db.base import Base


class PromptTemplateRow(Base):
    """Persistence row for one immutable prompt template version. Configuration, not end-user content."""

    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("organization_id", "name", "version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

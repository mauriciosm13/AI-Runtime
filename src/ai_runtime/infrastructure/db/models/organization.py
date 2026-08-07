"""SQLAlchemy ORM mapping for the organizations table."""

from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.infrastructure.db.base import Base


class OrganizationRow(Base):
    """Persistence row for an organization tenant."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

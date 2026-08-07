"""SQLAlchemy ORM mapping for the usage_records table."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.infrastructure.db.base import Base


class UsageRecordRow(Base):
    """Persistence row for request-level usage accounting.

    Does not store prompt or response content.
    """

    __tablename__ = "usage_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

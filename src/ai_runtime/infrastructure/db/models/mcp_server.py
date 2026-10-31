"""SQLAlchemy ORM mapping for the mcp_servers table."""

from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.infrastructure.db.base import Base


class McpServerRow(Base):
    """Persistence row for one organization MCP server registration."""

    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

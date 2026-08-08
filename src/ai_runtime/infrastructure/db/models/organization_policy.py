"""SQLAlchemy ORM mappings for organization access policy tables."""

from datetime import datetime
from uuid import UUID
from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from ai_runtime.infrastructure.db.base import Base


class OrganizationPolicyRow(Base):
    """Persistence row for per-organization usage policy."""

    __tablename__ = "organization_policies"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), primary_key=True)
    monthly_token_limit: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrganizationModelEntitlementRow(Base):
    """Persistence row for an organization model allowlist entry."""

    __tablename__ = "organization_model_entitlements"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)

"""Create organization policy and model entitlement tables.

Revision ID: 0005_organization_policies
Revises: 0004_usage_records
Create Date: 2026-08-07 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_organization_policies"
down_revision: str | None = "0004_usage_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create organization policy tables and usage aggregation index."""
    op.create_table(
        "organization_policies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "organization_model_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "model"),
    )
    op.create_index(
        "ix_organization_model_entitlements_organization_id",
        "organization_model_entitlements",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_organization_id_created_at",
        "usage_records",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop organization policy tables and usage aggregation index."""
    op.drop_index("ix_usage_records_organization_id_created_at", table_name="usage_records")
    op.drop_index("ix_organization_model_entitlements_organization_id", table_name="organization_model_entitlements")
    op.drop_table("organization_model_entitlements")
    op.drop_table("organization_policies")

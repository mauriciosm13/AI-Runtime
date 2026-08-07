"""Create usage_records table.

Revision ID: 0004_usage_records
Revises: 0003_api_keys
Create Date: 2026-08-07 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_usage_records"
down_revision: str | None = "0003_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the usage_records table with unique request_id and org/key FKs."""
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("api_key_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_usage_records_organization_id", "usage_records", ["organization_id"], unique=False)
    op.create_index("ix_usage_records_api_key_id", "usage_records", ["api_key_id"], unique=False)


def downgrade() -> None:
    """Drop the usage_records table and its indexes."""
    op.drop_index("ix_usage_records_api_key_id", table_name="usage_records")
    op.drop_index("ix_usage_records_organization_id", table_name="usage_records")
    op.drop_table("usage_records")

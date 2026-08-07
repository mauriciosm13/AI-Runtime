"""Create api_keys table.

Revision ID: 0003_api_keys
Revises: 0002_organizations
Create Date: 2026-08-06 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_api_keys"
down_revision: str | None = "0002_organizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the api_keys table with organization FK and lookup indexes."""
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_organization_id", "api_keys", ["organization_id"], unique=False)
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"], unique=False)


def downgrade() -> None:
    """Drop the api_keys table and its indexes."""
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_organization_id", table_name="api_keys")
    op.drop_table("api_keys")

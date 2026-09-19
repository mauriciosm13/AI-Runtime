"""Create prompt_templates table.

Revision ID: 0007_prompt_templates
Revises: 0005_organization_policies
Create Date: 2026-09-18 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_prompt_templates"
down_revision: str | None = "0005_organization_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the prompt_templates table."""
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", "version"),
    )
    op.create_index("ix_prompt_templates_organization_id", "prompt_templates", ["organization_id"], unique=False)


def downgrade() -> None:
    """Drop the prompt_templates table."""
    op.drop_index("ix_prompt_templates_organization_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")

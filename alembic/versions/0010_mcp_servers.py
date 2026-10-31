"""Create mcp_servers table.

Revision ID: 0010_mcp_servers
Revises: 0009_semantic_chunks_pgvector
Create Date: 2026-10-31 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_mcp_servers"
down_revision: str | None = "0009_semantic_chunks_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create organization-scoped MCP server registrations."""
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index("ix_mcp_servers_organization_id", "mcp_servers", ["organization_id"])


def downgrade() -> None:
    """Drop mcp_servers."""
    op.drop_index("ix_mcp_servers_organization_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")

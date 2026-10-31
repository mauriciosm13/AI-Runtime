"""Enable pgvector and create semantic_chunks table.

Revision ID: 0009_semantic_chunks_pgvector
Revises: 0008_audit_events
Create Date: 2026-10-31 00:00:00.000000
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

_EMBEDDING_DIMENSIONS = 1536

revision: str = "0009_semantic_chunks_pgvector"
down_revision: str | None = "0008_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install pgvector and create semantic_chunks."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "semantic_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_chunks_organization_id", "semantic_chunks", ["organization_id"], unique=False)


def downgrade() -> None:
    """Drop semantic_chunks (extension left installed)."""
    op.drop_index("ix_semantic_chunks_organization_id", table_name="semantic_chunks")
    op.drop_table("semantic_chunks")

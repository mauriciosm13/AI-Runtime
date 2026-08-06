"""Baseline schema against empty ORM metadata.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-26 00:00:00.000000

Establishes Alembic version tracking with no domain tables yet.
Organizations, API keys, and other persistence models land in later revisions.
This empty upgrade is intentional: it proves env.py + Base.metadata wiring
before the first real DDL migration.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the baseline revision (no DDL)."""
    pass


def downgrade() -> None:
    """Revert the baseline revision (no DDL)."""
    pass

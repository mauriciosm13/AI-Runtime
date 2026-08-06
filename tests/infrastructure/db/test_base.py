"""Declarative Base tests."""

from ai_runtime.infrastructure.db.base import Base


def test_base_metadata_has_no_tables_yet() -> None:
    """Baseline ORM metadata is empty until domain tables are introduced."""
    assert Base.metadata.tables == {}

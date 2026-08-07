"""Declarative Base tests."""

from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.models import OrganizationRow


def test_base_metadata_includes_organizations_table() -> None:
    """ORM metadata registers the organizations table from OrganizationRow."""
    assert "organizations" in Base.metadata.tables
    table = Base.metadata.tables["organizations"]
    assert {column.name for column in table.columns} == {
        "id",
        "name",
        "slug",
        "status",
        "created_at",
        "updated_at",
    }
    assert OrganizationRow.__tablename__ == "organizations"

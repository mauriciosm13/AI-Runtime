"""Alembic configuration and baseline migration smoke tests."""

import configparser
from pathlib import Path
from pytest import MonkeyPatch
from alembic.config import Config
from alembic.script import ScriptDirectory
from ai_runtime.config.settings import Settings
from ai_runtime.infrastructure.db.base import Base
from ai_runtime.infrastructure.db.migration_settings import get_alembic_database_url

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_alembic_ini_script_location() -> None:
    """alembic.ini points at the repository alembic/ script directory."""
    parser = configparser.ConfigParser()
    parser.read(_REPO_ROOT / "alembic.ini")
    assert parser.get("alembic", "script_location") == "alembic"


def test_migration_revision_chain() -> None:
    """Alembic revisions form a single linear chain ending at api_keys."""
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0003_api_keys"]
    baseline = script.get_revision("0001_baseline")
    assert baseline is not None
    assert baseline.down_revision is None
    organizations = script.get_revision("0002_organizations")
    assert organizations is not None
    assert organizations.down_revision == "0001_baseline"
    api_keys = script.get_revision("0003_api_keys")
    assert api_keys is not None
    assert api_keys.down_revision == "0002_organizations"


def test_get_alembic_database_url_uses_settings(monkeypatch: MonkeyPatch) -> None:
    """Alembic URL resolution uses the same Settings as the API."""
    monkeypatch.delenv("AI_RUNTIME_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "AI_RUNTIME_DATABASE_URL",
        "postgresql+asyncpg://migrate:secret@db:5432/runtime",
    )
    assert get_alembic_database_url() == Settings().database_url
    assert get_alembic_database_url() == "postgresql+asyncpg://migrate:secret@db:5432/runtime"


def test_env_py_targets_shared_base_metadata() -> None:
    """alembic/env.py wires Base.metadata for autogenerate."""
    env_source = (_REPO_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from ai_runtime.infrastructure.db.base import Base" in env_source
    assert "target_metadata = Base.metadata" in env_source
    assert Base.metadata is not None

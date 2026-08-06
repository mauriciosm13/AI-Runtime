"""Architecture import-boundary tests."""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src" / "ai_runtime"

_FORBIDDEN_IN_DOMAIN_AND_APPLICATION = frozenset(
    {
        "sqlalchemy",
        "asyncpg",
        "fastapi",
        "httpx",
        "redis",
    }
)


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", maxsplit=1)[0])
    return names


def _python_files(package: str) -> list[Path]:
    return sorted((_SRC / package).rglob("*.py"))


def test_domain_and_application_avoid_infrastructure_frameworks() -> None:
    """domain and application must not import SQLAlchemy, FastAPI, httpx, or Redis."""
    violations: list[str] = []
    for package in ("domain", "application"):
        for path in _python_files(package):
            imported = _top_level_imports(path) & _FORBIDDEN_IN_DOMAIN_AND_APPLICATION
            for name in sorted(imported):
                violations.append(f"{path.relative_to(_REPO_ROOT)} imports {name}")
    assert violations == []

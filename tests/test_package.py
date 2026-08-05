"""Packaging smoke tests."""

import json
from importlib.metadata import distribution
from pathlib import Path

import ai_runtime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_INIT = PROJECT_ROOT / "src" / "ai_runtime" / "__init__.py"


def test_package_is_importable() -> None:
    """The installed distribution exposes the application package."""
    assert ai_runtime.__doc__ is not None


def test_package_resolves_from_source_tree() -> None:
    """Imports resolve to the source tree, not a copied site-packages tree."""
    assert Path(ai_runtime.__file__).resolve() == EXPECTED_PACKAGE_INIT


def test_distribution_is_editable() -> None:
    """The installed distribution is an editable (PEP 660) install."""
    dist = distribution("ai-runtime")
    direct_url_path = None
    for file in dist.files or []:
        if file.name == "direct_url.json":
            direct_url_path = dist.locate_file(file)
            break

    assert direct_url_path is not None
    direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
    assert direct_url.get("dir_info", {}).get("editable") is True

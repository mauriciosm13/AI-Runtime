"""Unit tests for embedding routing catalog."""

import pytest
from ai_runtime.domain.embedding_routing import DEFAULT_EMBEDDING_CATALOG, resolve_embedding_route
from ai_runtime.domain.routing import UnsupportedModelError


def test_resolve_embedding_route_returns_openai_route() -> None:
    route = resolve_embedding_route("text-embedding-3-small", DEFAULT_EMBEDDING_CATALOG)
    assert route.model == "text-embedding-3-small"
    assert route.provider == "openai"


def test_resolve_embedding_route_rejects_unknown_model() -> None:
    with pytest.raises(UnsupportedModelError):
        resolve_embedding_route("not-a-model", DEFAULT_EMBEDDING_CATALOG)

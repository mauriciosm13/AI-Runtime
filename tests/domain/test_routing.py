"""Unit tests for model routing domain rules."""

import pytest
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.routing import DEFAULT_MODEL_CATALOG, ModelRoute, UnsupportedModelError, resolve_model_route


def test_resolve_model_route_returns_catalog_provider() -> None:
    route = resolve_model_route("gpt-4o-mini", DEFAULT_MODEL_CATALOG)
    assert route == ModelRoute(model="gpt-4o-mini", provider="openai")


def test_resolve_model_route_uses_injected_catalog() -> None:
    route = resolve_model_route("claude-sonnet", {"claude-sonnet": "anthropic"})
    assert route.provider == "anthropic"


def test_resolve_model_route_raises_for_unknown_model() -> None:
    with pytest.raises(UnsupportedModelError) as exc_info:
        resolve_model_route("unknown-model", DEFAULT_MODEL_CATALOG)
    assert exc_info.value.model == "unknown-model"
    assert str(exc_info.value) == "The requested model is not supported."


def test_resolve_model_route_rejects_blank_model() -> None:
    with pytest.raises(DomainValidationError, match="requested_model"):
        resolve_model_route("   ", DEFAULT_MODEL_CATALOG)


def test_model_route_rejects_blank_fields() -> None:
    with pytest.raises(DomainValidationError, match="model"):
        ModelRoute(model=" ", provider="openai")
    with pytest.raises(DomainValidationError, match="provider"):
        ModelRoute(model="gpt-4o", provider="")


def test_default_catalog_covers_priced_openai_models() -> None:
    assert DEFAULT_MODEL_CATALOG["gpt-4o"] == "openai"
    assert DEFAULT_MODEL_CATALOG["gpt-4o-mini"] == "openai"

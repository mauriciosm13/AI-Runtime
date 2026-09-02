"""Unit tests for model routing domain rules."""

import pytest
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.routing import DEFAULT_FAILOVER_CATALOG, DEFAULT_MODEL_CATALOG, ModelRoute, UnsupportedModelError
from ai_runtime.domain.routing import resolve_model_route, resolve_route_chain


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
    assert DEFAULT_MODEL_CATALOG["claude-3-5-sonnet-20241022"] == "anthropic"
    assert DEFAULT_MODEL_CATALOG["gemini-2.5-flash"] == "gemini"


def test_resolve_route_chain_returns_primary_then_failover_models() -> None:
    chain = resolve_route_chain("gpt-4o-mini", DEFAULT_MODEL_CATALOG)
    assert chain == (
        ModelRoute(model="gpt-4o-mini", provider="openai"),
        ModelRoute(model="claude-3-5-sonnet-20241022", provider="anthropic"),
        ModelRoute(model="gemini-2.5-flash", provider="gemini"),
    )


def test_resolve_route_chain_uses_injected_failover_catalog() -> None:
    catalog = {"primary": "openai", "backup": "anthropic"}
    failover = {"primary": ("backup",)}
    chain = resolve_route_chain("primary", catalog, failover)
    assert chain == (
        ModelRoute(model="primary", provider="openai"),
        ModelRoute(model="backup", provider="anthropic"),
    )


def test_default_failover_catalog_maps_openai_models_to_claude() -> None:
    assert DEFAULT_FAILOVER_CATALOG["gpt-4o"] == ("claude-3-5-sonnet-20241022", "gemini-2.5-flash")
    assert DEFAULT_FAILOVER_CATALOG["gpt-4o-mini"] == ("claude-3-5-sonnet-20241022", "gemini-2.5-flash")
    assert DEFAULT_FAILOVER_CATALOG["claude-3-5-sonnet-20241022"] == ("gpt-4o", "gemini-2.5-flash")
    assert DEFAULT_FAILOVER_CATALOG["gemini-2.5-flash"] == ("gpt-4o-mini",)

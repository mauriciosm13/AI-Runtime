"""Unit tests for model provider registration in the composition root."""

from ai_runtime.api.dependencies import build_embedding_providers, build_model_providers
from ai_runtime.config.settings import Settings
import httpx


def test_build_model_providers_omits_anthropic_when_api_key_blank() -> None:
    """Blank Anthropic key keeps OpenAI-only deploys valid."""
    settings = Settings(openai_api_key="sk-test", anthropic_api_key="")
    providers = build_model_providers(settings, httpx.AsyncClient())
    assert set(providers) == {"openai"}


def test_build_model_providers_registers_anthropic_when_api_key_set() -> None:
    """Anthropic adapter registers when AI_RUNTIME_ANTHROPIC_API_KEY is set."""
    settings = Settings(openai_api_key="sk-test", anthropic_api_key="sk-ant-test")
    providers = build_model_providers(settings, httpx.AsyncClient())
    assert set(providers) == {"openai", "anthropic"}


def test_build_model_providers_omits_gemini_when_api_key_blank() -> None:
    """Blank Gemini key keeps OpenAI-only deploys valid."""
    settings = Settings(openai_api_key="sk-test", gemini_api_key="")
    providers = build_model_providers(settings, httpx.AsyncClient())
    assert "gemini" not in providers


def test_build_embedding_providers_omits_openai_when_api_key_blank() -> None:
    """Blank OpenAI key keeps embedding-only deploys from registering OpenAI embeddings."""
    settings = Settings(openai_api_key="")
    providers = build_embedding_providers(settings, httpx.AsyncClient())
    assert providers == {}


def test_build_embedding_providers_registers_openai_when_api_key_set() -> None:
    settings = Settings(openai_api_key="sk-test")
    providers = build_embedding_providers(settings, httpx.AsyncClient())
    assert set(providers) == {"openai"}


def test_build_model_providers_registers_gemini_when_api_key_set() -> None:
    """Gemini adapter registers when AI_RUNTIME_GEMINI_API_KEY is set."""
    settings = Settings(openai_api_key="sk-test", gemini_api_key="test-gemini-key")
    providers = build_model_providers(settings, httpx.AsyncClient())
    assert set(providers) == {"openai", "gemini"}

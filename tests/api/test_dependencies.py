"""Unit tests for model provider registration in the composition root."""

from ai_runtime.api.dependencies import build_model_providers
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

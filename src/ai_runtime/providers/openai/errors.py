"""Exceptions raised by OpenAI provider adapters."""

from ai_runtime.providers.errors import ProviderError

__all__ = ["OpenAIProviderError", "ProviderError"]


class OpenAIProviderError(ProviderError):
    """Raised when the OpenAI adapter cannot complete a generation call."""

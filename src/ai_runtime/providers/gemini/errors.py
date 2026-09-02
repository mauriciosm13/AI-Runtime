"""Exceptions raised by Gemini provider adapters."""

from ai_runtime.providers.errors import ProviderError


class GeminiProviderError(ProviderError):
    """Raised when the Gemini adapter cannot complete a generation call."""

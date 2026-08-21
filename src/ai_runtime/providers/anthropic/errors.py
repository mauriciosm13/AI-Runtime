"""Exceptions raised by Anthropic provider adapters."""

from ai_runtime.providers.errors import ProviderError


class AnthropicProviderError(ProviderError):
    """Raised when the Anthropic adapter cannot complete a generation call."""

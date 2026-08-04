"""Exceptions raised by OpenAI provider adapters."""


class ProviderError(Exception):
    """Base error for provider adapter failures."""


class OpenAIProviderError(ProviderError):
    """Raised when the OpenAI adapter cannot complete a generation call."""

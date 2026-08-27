"""Shared exceptions for provider adapters."""

from typing import Self

RETRYABLE_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_retryable_http_status(status_code: int) -> bool:
    """Return whether an upstream HTTP status warrants a bounded retry."""
    return status_code in RETRYABLE_HTTP_STATUS_CODES


class ProviderError(Exception):
    """Base error for provider adapter failures."""

    retryable: bool
    status_code: int | None

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code

    @classmethod
    def from_http_status(cls, message: str, status_code: int) -> Self:
        """Build an error from an upstream HTTP status code."""
        return cls(message, retryable=is_retryable_http_status(status_code), status_code=status_code)

    @classmethod
    def transient(cls, message: str) -> Self:
        """Build a retryable error for transport-level failures."""
        return cls(message, retryable=True)

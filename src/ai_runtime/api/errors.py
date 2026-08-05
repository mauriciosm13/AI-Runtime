"""Stable API error codes and typed HTTP exceptions."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Programmatic error identifiers exposed to API clients."""

    INVALID_REQUEST = "invalid_request"
    PROVIDER_ERROR = "provider_error"
    INTERNAL_ERROR = "internal_error"


class APIError(Exception):
    """Client-facing error mapped to the standard API error envelope."""

    def __init__(self, *, code: ErrorCode, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

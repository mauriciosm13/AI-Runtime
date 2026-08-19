"""Stable API error codes and typed HTTP exceptions."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Programmatic error identifiers exposed to API clients."""

    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_NOT_AVAILABLE = "model_not_available"
    UNSUPPORTED_MODEL = "unsupported_model"
    CONFLICT = "conflict"
    PROVIDER_ERROR = "provider_error"
    INTERNAL_ERROR = "internal_error"


class APIError(Exception):
    """Client-facing error mapped to the standard API error envelope."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}
        super().__init__(message)

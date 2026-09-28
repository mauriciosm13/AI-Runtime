"""Errors raised by the AI Runtime Python client."""

from typing import Any


class AIRuntimeError(Exception):
    """An error returned by the API or a response the client could not parse."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        request_id: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after = retry_after
        super().__init__(message)


class AIRuntimeConnectionError(AIRuntimeError):
    """The API could not be reached."""

    def __init__(self, message: str) -> None:
        super().__init__(code="connection_error", message=message, status_code=0)


def error_from_body(
    payload: Any,
    *,
    status_code: int,
    request_id: str | None = None,
    retry_after: str | None = None,
    fallback_message: str,
) -> AIRuntimeError:
    """Build an AIRuntimeError from an error envelope, or from a fallback message."""
    code = "internal_error"
    message = fallback_message
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            raw_code = error.get("code")
            raw_message = error.get("message")
            raw_request_id = error.get("request_id")
            if isinstance(raw_code, str) and raw_code:
                code = raw_code
            if isinstance(raw_message, str) and raw_message:
                message = raw_message
            if isinstance(raw_request_id, str) and raw_request_id:
                request_id = raw_request_id
    return AIRuntimeError(
        code=code,
        message=message,
        status_code=status_code,
        request_id=request_id,
        retry_after=retry_after,
    )

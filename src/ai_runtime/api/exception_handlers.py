"""Map application and framework exceptions to the API error envelope."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.schemas.errors import ErrorDetailSchema, ErrorResponseSchema
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.providers.openai.errors import ProviderError


def _error_response(*, status_code: int, code: ErrorCode, message: str, request_id: str | None = None) -> JSONResponse:
    """Build a JSON response using the standard error envelope."""
    payload = ErrorResponseSchema(
        error=ErrorDetailSchema(code=code, message=message, request_id=request_id),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(exclude_none=True))


def _format_validation_message(err: RequestValidationError) -> str:
    """Summarize the first validation failure in a client-safe message."""
    errors = err.errors()
    if not errors:
        return "The request is invalid."
    first = errors[0]
    location = ".".join(str(part) for part in first["loc"] if part != "body")
    if location:
        return f"Invalid value for '{location}': {first['msg']}."
    return f"Invalid request: {first['msg']}."


async def api_error_handler(_request: Request, err: Exception) -> JSONResponse:
    """Return a pre-built client-facing API error."""
    assert isinstance(err, APIError)
    return _error_response(status_code=err.status_code, code=err.code, message=err.message)


async def validation_error_handler(_request: Request, err: Exception) -> JSONResponse:
    """Normalize FastAPI request validation failures."""
    assert isinstance(err, RequestValidationError)
    return _error_response(
        status_code=422,
        code=ErrorCode.INVALID_REQUEST,
        message=_format_validation_message(err),
    )


async def domain_validation_error_handler(_request: Request, err: Exception) -> JSONResponse:
    """Normalize domain validation failures raised at the HTTP boundary."""
    assert isinstance(err, DomainValidationError)
    return _error_response(status_code=422, code=ErrorCode.INVALID_REQUEST, message=str(err))


async def provider_error_handler(_request: Request, err: Exception) -> JSONResponse:
    """Normalize upstream provider failures."""
    assert isinstance(err, ProviderError)
    return _error_response(status_code=502, code=ErrorCode.PROVIDER_ERROR, message=str(err))


async def unhandled_error_handler(_request: Request, _err: Exception) -> JSONResponse:
    """Return a safe response for unexpected server failures."""
    return _error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach standardized exception handlers to a FastAPI application."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DomainValidationError, domain_validation_error_handler)
    app.add_exception_handler(ProviderError, provider_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

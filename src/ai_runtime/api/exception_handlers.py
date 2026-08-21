"""Map application and framework exceptions to the API error envelope."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.middleware.request_context import REQUEST_ID_HEADER, get_request_id
from ai_runtime.api.schemas.errors import ErrorDetailSchema, ErrorResponseSchema
from ai_runtime.application.routing.model_router import ProviderNotRegisteredError
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.idempotency import IdempotencyConflictError
from ai_runtime.domain.organization_policy import ModelNotAvailableError, QuotaExceededError
from ai_runtime.domain.rate_limit import RateLimitExceededError
from ai_runtime.domain.routing import UnsupportedModelError
from ai_runtime.providers.errors import ProviderError


def _error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSON response using the standard error envelope."""
    payload = ErrorResponseSchema(
        error=ErrorDetailSchema(code=code, message=message, request_id=request_id),
    )
    response = JSONResponse(status_code=status_code, content=payload.model_dump(exclude_none=True))
    if request_id is not None:
        response.headers[REQUEST_ID_HEADER] = request_id
    if headers:
        for name, value in headers.items():
            response.headers[name] = value
    return response


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


async def api_error_handler(request: Request, err: Exception) -> JSONResponse:
    """Return a pre-built client-facing API error."""
    assert isinstance(err, APIError)
    return _error_response(
        status_code=err.status_code,
        code=err.code,
        message=err.message,
        request_id=get_request_id(request),
        headers=err.headers,
    )


async def validation_error_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize FastAPI request validation failures."""
    assert isinstance(err, RequestValidationError)
    return _error_response(
        status_code=422,
        code=ErrorCode.INVALID_REQUEST,
        message=_format_validation_message(err),
        request_id=get_request_id(request),
    )


async def domain_validation_error_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize domain validation failures raised at the HTTP boundary."""
    assert isinstance(err, DomainValidationError)
    return _error_response(
        status_code=422,
        code=ErrorCode.INVALID_REQUEST,
        message=str(err),
        request_id=get_request_id(request),
    )


async def rate_limit_exceeded_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize organization rate-limit denials to HTTP 429."""
    assert isinstance(err, RateLimitExceededError)
    return _error_response(
        status_code=429,
        code=ErrorCode.RATE_LIMITED,
        message=str(err),
        request_id=get_request_id(request),
        headers={"Retry-After": str(err.retry_after_seconds)},
    )


async def quota_exceeded_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize monthly quota denials to HTTP 429."""
    assert isinstance(err, QuotaExceededError)
    return _error_response(
        status_code=429,
        code=ErrorCode.QUOTA_EXCEEDED,
        message=str(err),
        request_id=get_request_id(request),
        headers={"Retry-After": str(err.retry_after_seconds)},
    )


async def model_not_available_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize model entitlement denials to HTTP 403."""
    assert isinstance(err, ModelNotAvailableError)
    return _error_response(
        status_code=403,
        code=ErrorCode.MODEL_NOT_AVAILABLE,
        message=str(err),
        request_id=get_request_id(request),
    )


async def unsupported_model_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize unknown catalog models to HTTP 400."""
    assert isinstance(err, UnsupportedModelError)
    return _error_response(
        status_code=400,
        code=ErrorCode.UNSUPPORTED_MODEL,
        message=str(err),
        request_id=get_request_id(request),
    )


async def idempotency_conflict_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize in-flight idempotency conflicts to HTTP 409."""
    assert isinstance(err, IdempotencyConflictError)
    return _error_response(
        status_code=409,
        code=ErrorCode.CONFLICT,
        message=str(err),
        request_id=get_request_id(request),
    )


async def provider_not_registered_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize catalog routes whose provider adapter is not configured."""
    assert isinstance(err, ProviderNotRegisteredError)
    return _error_response(
        status_code=503,
        code=ErrorCode.PROVIDER_ERROR,
        message=str(err),
        request_id=get_request_id(request),
    )


async def provider_error_handler(request: Request, err: Exception) -> JSONResponse:
    """Normalize upstream provider failures."""
    assert isinstance(err, ProviderError)
    return _error_response(
        status_code=502,
        code=ErrorCode.PROVIDER_ERROR,
        message=str(err),
        request_id=get_request_id(request),
    )


async def unhandled_error_handler(request: Request, _err: Exception) -> JSONResponse:
    """Return a safe response for unexpected server failures."""
    return _error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred.",
        request_id=get_request_id(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach standardized exception handlers to a FastAPI application."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DomainValidationError, domain_validation_error_handler)
    app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)
    app.add_exception_handler(QuotaExceededError, quota_exceeded_handler)
    app.add_exception_handler(ModelNotAvailableError, model_not_available_handler)
    app.add_exception_handler(UnsupportedModelError, unsupported_model_handler)
    app.add_exception_handler(ProviderNotRegisteredError, provider_not_registered_handler)
    app.add_exception_handler(IdempotencyConflictError, idempotency_conflict_handler)
    app.add_exception_handler(ProviderError, provider_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

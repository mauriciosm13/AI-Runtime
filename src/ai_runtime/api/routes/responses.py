"""Provider-neutral model response endpoint."""

import re
from typing import Annotated
from fastapi import APIRouter, Header
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, CreateResponseDep, RequestIdDep
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.responses import CreateResponseRequest, ResponseSchema
from ai_runtime.application.responses.create_response import CreateResponseCommand

router = APIRouter(tags=["responses"])

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def _parse_idempotency_key(raw: str | None) -> str | None:
    """Validate an optional Idempotency-Key header value."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        raise APIError(
            code=ErrorCode.INVALID_REQUEST,
            message="Idempotency-Key must not be blank.",
            status_code=422,
        )
    if _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise APIError(
            code=ErrorCode.INVALID_REQUEST,
            message="Idempotency-Key must be 1-128 characters using [A-Za-z0-9._:-].",
            status_code=422,
        )
    return value


@router.post(
    "/responses",
    response_model=ResponseSchema,
    responses={
        400: {"model": ErrorResponseSchema, "description": "Requested model is not in the routing catalog"},
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        403: {"model": ErrorResponseSchema, "description": "Organization suspended or model not entitled"},
        409: {"model": ErrorResponseSchema, "description": "Idempotency key already in progress"},
        422: {"model": ErrorResponseSchema, "description": "Invalid request"},
        429: {"model": ErrorResponseSchema, "description": "Organization rate limit exceeded"},
        502: {"model": ErrorResponseSchema, "description": "Provider failure"},
    },
)
async def post_responses(
    body: CreateResponseRequest,
    use_case: CreateResponseDep,
    principal: AuthenticatedPrincipalDep,
    request_id: RequestIdDep,
    idempotency_key_header: Annotated[str | None, Header(alias=_IDEMPOTENCY_KEY_HEADER)] = None,
) -> ResponseSchema:
    """Create a provider-neutral model response and record usage accounting."""
    result = await use_case.execute(
        CreateResponseCommand(
            request=body.to_domain(),
            request_id=request_id,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            idempotency_key=_parse_idempotency_key(idempotency_key_header),
        )
    )
    return ResponseSchema.from_domain(result)

"""Provider-neutral model response endpoint."""

import json
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, CreateResponseDep, RequestIdDep
from ai_runtime.api.errors import APIError, ErrorCode
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.responses import CreateResponseRequest, ResponseSchema
from ai_runtime.application.responses.create_response import CreateResponseCommand
from ai_runtime.domain.generation import GenerationDelta, GenerationStreamEvent
from ai_runtime.providers.errors import ProviderError

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


def _sse_message(event: str, payload: dict[str, Any]) -> str:
    """Serialize one Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'), ensure_ascii=True)}\n\n"


def _format_stream_event(event: GenerationStreamEvent) -> str:
    """Map a domain stream event to an SSE frame."""
    if isinstance(event, GenerationDelta):
        return _sse_message(
            "response.delta",
            {"id": event.id, "model": event.model, "delta": {"content": event.content}},
        )
    return _sse_message("response.completed", ResponseSchema.from_domain(event).model_dump())


def _format_stream_error(err: ProviderError, request_id: str) -> str:
    """Map a post-start provider failure to a response.error SSE frame."""
    return _sse_message(
        "response.error",
        {
            "error": {
                "code": ErrorCode.PROVIDER_ERROR.value,
                "message": str(err),
                "request_id": request_id,
            }
        },
    )


@router.post(
    "/responses",
    response_model=None,
    responses={
        200: {"model": ResponseSchema, "description": "Completed non-streaming response or SSE stream"},
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
) -> ResponseSchema | StreamingResponse:
    """Create a provider-neutral model response and record usage accounting."""
    command = CreateResponseCommand(
        request=body.to_domain(),
        request_id=request_id,
        organization_id=principal.organization_id,
        api_key_id=principal.api_key_id,
        idempotency_key=_parse_idempotency_key(idempotency_key_header),
    )
    if not body.stream:
        result = await use_case.execute(command)
        return ResponseSchema.from_domain(result)

    iterator = use_case.stream(command)
    try:
        first = await anext(iterator)
    except StopAsyncIteration as err:
        raise ProviderError("Provider stream completed without a response") from err

    async def events() -> AsyncIterator[str]:
        pending: GenerationStreamEvent | None = first
        try:
            while pending is not None:
                yield _format_stream_event(pending)
                try:
                    pending = await anext(iterator)
                except StopAsyncIteration:
                    pending = None
        except ProviderError as err:
            yield _format_stream_error(err, request_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

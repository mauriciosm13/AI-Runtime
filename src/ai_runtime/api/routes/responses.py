"""Provider-neutral model response endpoint."""

from fastapi import APIRouter
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, CreateResponseDep, RequestIdDep
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.responses import CreateResponseRequest, ResponseSchema
from ai_runtime.application.responses.create_response import CreateResponseCommand

router = APIRouter(tags=["responses"])


@router.post(
    "/responses",
    response_model=ResponseSchema,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        403: {"model": ErrorResponseSchema, "description": "Organization suspended"},
        422: {"model": ErrorResponseSchema, "description": "Invalid request"},
        502: {"model": ErrorResponseSchema, "description": "Provider failure"},
    },
)
async def post_responses(
    body: CreateResponseRequest,
    use_case: CreateResponseDep,
    principal: AuthenticatedPrincipalDep,
    request_id: RequestIdDep,
) -> ResponseSchema:
    """Create a provider-neutral model response and record usage accounting."""
    result = await use_case.execute(
        CreateResponseCommand(
            request=body.to_domain(),
            request_id=request_id,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
        )
    )
    return ResponseSchema.from_domain(result)

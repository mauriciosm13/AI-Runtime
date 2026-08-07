"""Provider-neutral model response endpoint."""

from fastapi import APIRouter
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, CreateResponseDep
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.responses import CreateResponseRequest, ResponseSchema

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
    _principal: AuthenticatedPrincipalDep,
) -> ResponseSchema:
    """Create a provider-neutral model response."""
    result = await use_case.execute(body.to_domain())
    return ResponseSchema.from_domain(result)

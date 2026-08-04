"""Provider-neutral model response endpoint."""

from fastapi import APIRouter, HTTPException
from ai_runtime.api.dependencies import CreateResponseDep
from ai_runtime.api.schemas.responses import CreateResponseRequest, ResponseSchema
from ai_runtime.providers.openai.errors import ProviderError

router = APIRouter(tags=["responses"])


@router.post("/responses", response_model=ResponseSchema)
async def post_responses(body: CreateResponseRequest, use_case: CreateResponseDep) -> ResponseSchema:
    """Create a provider-neutral model response."""
    try:
        domain_request = body.to_domain()
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    try:
        result = await use_case.execute(domain_request)
    except ProviderError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    return ResponseSchema.from_domain(result)

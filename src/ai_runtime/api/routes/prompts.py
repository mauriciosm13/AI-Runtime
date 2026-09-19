"""Organization-scoped prompt template endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends
from ai_runtime.api.dependencies import AuthenticatedPrincipalDep, get_create_prompt_version, get_prompt_versions
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.prompts import CreatePromptRequest, PromptVersionSchema, PromptVersionsSchema
from ai_runtime.application.prompts.create_prompt_version import CreatePromptVersion
from ai_runtime.application.prompts.get_prompt_versions import GetPromptVersions

router = APIRouter(tags=["prompts"])


@router.post(
    "/prompts",
    status_code=201,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        409: {"model": ErrorResponseSchema, "description": "Concurrent version creation"},
        422: {"model": ErrorResponseSchema, "description": "Invalid request"},
    },
)
async def post_prompts(
    body: CreatePromptRequest,
    principal: AuthenticatedPrincipalDep,
    use_case: Annotated[CreatePromptVersion, Depends(get_create_prompt_version)],
) -> PromptVersionSchema:
    """Create the next immutable version of a named prompt template."""
    template = await use_case.execute(principal.organization_id, body.name, [item.to_domain() for item in body.messages])
    return PromptVersionSchema.from_domain(template)


@router.get(
    "/prompts/{name}",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid API key"},
        404: {"model": ErrorResponseSchema, "description": "Prompt not found"},
    },
)
async def get_prompts(
    name: str,
    principal: AuthenticatedPrincipalDep,
    use_case: Annotated[GetPromptVersions, Depends(get_prompt_versions)],
) -> PromptVersionsSchema:
    """List every version of a named prompt template."""
    versions = await use_case.execute(principal.organization_id, name)
    return PromptVersionsSchema(versions=[PromptVersionSchema.from_domain(item) for item in versions])

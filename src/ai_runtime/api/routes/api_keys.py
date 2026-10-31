"""Operator-only API key administration endpoints."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from ai_runtime.api.dependencies import (
    OperatorDep,
    get_create_api_key,
    get_list_api_keys,
    get_revoke_api_key,
    get_rotate_api_key,
)
from ai_runtime.api.schemas.api_keys import ApiKeyListSchema, ApiKeySchema, CreateApiKeyRequest, CreateApiKeyResponse
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.application.api_keys.create_api_key import CreateApiKey, CreateApiKeyCommand
from ai_runtime.application.api_keys.list_api_keys import ListApiKeysForOrganization
from ai_runtime.application.api_keys.revoke_api_key import RevokeApiKey
from ai_runtime.application.api_keys.rotate_api_key import RotateApiKey

router = APIRouter(tags=["api_keys"])


@router.post(
    "/api_keys",
    status_code=201,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        404: {"model": ErrorResponseSchema, "description": "Organization not found"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def post_api_keys(
    body: CreateApiKeyRequest,
    _operator: OperatorDep,
    use_case: Annotated[CreateApiKey, Depends(get_create_api_key)],
) -> CreateApiKeyResponse:
    """Create an API key and return the one-time plaintext secret."""
    result = await use_case.execute(CreateApiKeyCommand(organization_id=body.organization_id, name=body.name))
    metadata = ApiKeySchema.from_domain(result.api_key)
    return CreateApiKeyResponse(**metadata.model_dump(), secret=result.secret)


@router.get(
    "/api_keys",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        404: {"model": ErrorResponseSchema, "description": "Organization not found"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def get_api_keys(
    organization_id: Annotated[UUID, Query()],
    _operator: OperatorDep,
    use_case: Annotated[ListApiKeysForOrganization, Depends(get_list_api_keys)],
) -> ApiKeyListSchema:
    """List API key metadata for an organization."""
    keys = await use_case.execute(organization_id)
    return ApiKeyListSchema(api_keys=[ApiKeySchema.from_domain(item) for item in keys])


@router.delete(
    "/api_keys/{key_id}",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        404: {"model": ErrorResponseSchema, "description": "API key not found"},
        409: {"model": ErrorResponseSchema, "description": "API key already revoked"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def delete_api_key(
    key_id: UUID,
    _operator: OperatorDep,
    use_case: Annotated[RevokeApiKey, Depends(get_revoke_api_key)],
) -> ApiKeySchema:
    """Revoke an API key."""
    metadata = await use_case.execute(key_id)
    return ApiKeySchema.from_domain(metadata)


@router.post(
    "/api_keys/{key_id}/rotate",
    status_code=201,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        404: {"model": ErrorResponseSchema, "description": "API key not found"},
        409: {"model": ErrorResponseSchema, "description": "API key already revoked"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def post_rotate_api_key(
    key_id: UUID,
    _operator: OperatorDep,
    use_case: Annotated[RotateApiKey, Depends(get_rotate_api_key)],
) -> CreateApiKeyResponse:
    """Revoke an active key and issue a replacement with a new secret."""
    result = await use_case.execute(key_id)
    metadata = ApiKeySchema.from_domain(result.api_key)
    return CreateApiKeyResponse(**metadata.model_dump(), secret=result.secret)

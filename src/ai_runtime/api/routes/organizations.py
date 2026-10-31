"""Operator-only organization administration endpoints."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from ai_runtime.api.dependencies import OperatorDep, get_create_organization, get_organization
from ai_runtime.api.schemas.errors import ErrorResponseSchema
from ai_runtime.api.schemas.organizations import CreateOrganizationRequest, OrganizationSchema
from ai_runtime.application.organizations.create_organization import CreateOrganization, CreateOrganizationCommand
from ai_runtime.application.organizations.get_organization import GetOrganization

router = APIRouter(tags=["organizations"])


@router.post(
    "/organizations",
    status_code=201,
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        409: {"model": ErrorResponseSchema, "description": "Organization slug already exists"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def post_organizations(
    body: CreateOrganizationRequest,
    _operator: OperatorDep,
    use_case: Annotated[CreateOrganization, Depends(get_create_organization)],
) -> OrganizationSchema:
    """Create a new organization tenant."""
    organization = await use_case.execute(CreateOrganizationCommand(name=body.name, slug=body.slug))
    return OrganizationSchema.from_domain(organization)


@router.get(
    "/organizations/{organization_id}",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Missing or invalid operator credentials"},
        403: {"model": ErrorResponseSchema, "description": "Tenant API key cannot access operator routes"},
        404: {"model": ErrorResponseSchema, "description": "Organization not found"},
        503: {"model": ErrorResponseSchema, "description": "Operator API is not configured"},
    },
)
async def get_organizations_by_id(
    organization_id: UUID,
    _operator: OperatorDep,
    use_case: Annotated[GetOrganization, Depends(get_organization)],
) -> OrganizationSchema:
    """Retrieve an organization by identifier."""
    organization = await use_case.execute(organization_id)
    return OrganizationSchema.from_domain(organization)

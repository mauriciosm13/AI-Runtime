"""Operational liveness endpoint."""

from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness response confirming the process can serve HTTP."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return process liveness status."""
    return HealthResponse(status="ok")

"""Interfaces for external capabilities required by application use cases."""

from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.ports.organization_repository import OrganizationRepository

__all__ = ["ModelProvider", "OrganizationRepository"]

"""Port for invoking text generation against a model provider."""

from typing import Protocol, runtime_checkable
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse


@runtime_checkable
class ModelProvider(Protocol):
    """Async contract that provider adapters must satisfy for text generation."""

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a model response for the given provider-neutral request."""
        ...

"""Port for invoking text generation against a model provider."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, GenerationStreamEvent


@runtime_checkable
class ModelProvider(Protocol):
    """Async contract that provider adapters must satisfy for text generation."""

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a model response for the given provider-neutral request."""
        ...

    def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationStreamEvent]:
        """Yield incremental deltas and a terminal GenerationResponse."""
        ...

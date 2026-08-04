"""Use case for creating a provider-neutral model response."""

from ai_runtime.domain.generation import GenerationRequest, GenerationResponse
from ai_runtime.ports.model_provider import ModelProvider


class CreateResponse:
    """Coordinate response generation through an injected model provider."""

    def __init__(self, model_provider: ModelProvider) -> None:
        self._model_provider = model_provider

    async def execute(self, request: GenerationRequest) -> GenerationResponse:
        """Generate a response for ``request`` using the configured provider."""
        return await self._model_provider.generate(request)

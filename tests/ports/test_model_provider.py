"""Unit tests for the ModelProvider port contract."""

import asyncio
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole, TokenUsage
from ai_runtime.ports.model_provider import ModelProvider


class FakeModelProvider:
    """Deterministic stand-in that satisfies ModelProvider."""

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            id="fake_1",
            model=request.model,
            output=Message(role=MessageRole.ASSISTANT, content="fake reply"),
            usage=TokenUsage(input_tokens=1, output_tokens=1),
        )


def test_fake_provider_satisfies_model_provider_contract() -> None:
    """A structural fake is accepted as ModelProvider and can generate."""
    provider: ModelProvider = FakeModelProvider()
    assert isinstance(provider, ModelProvider)
    request = GenerationRequest(
        model="fake-model",
        messages=(Message(role=MessageRole.USER, content="ping"),),
    )
    response = asyncio.run(provider.generate(request))
    assert response.model == "fake-model"
    assert response.output.role is MessageRole.ASSISTANT
    assert response.output.content == "fake reply"

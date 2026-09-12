"""Unit tests for the ModelProvider port contract."""

import asyncio
from collections.abc import AsyncIterator
from ai_runtime.domain.generation import GenerationDelta, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import GenerationStreamEvent, Message, MessageRole, TokenUsage
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

    async def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationStreamEvent]:
        response = await self.generate(request)
        yield GenerationDelta(id=response.id, model=response.model, content=response.output.content)
        yield response


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
    events = asyncio.run(_collect_stream(provider, request))
    assert len(events) == 2
    completed = events[-1]
    assert isinstance(completed, GenerationResponse)
    assert completed.output.content == "fake reply"


async def _collect_stream(provider: ModelProvider, request: GenerationRequest) -> list[GenerationStreamEvent]:
    return [event async for event in provider.stream(request)]

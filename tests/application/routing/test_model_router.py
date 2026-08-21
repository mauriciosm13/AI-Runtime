"""Unit tests for ModelRouter."""

import asyncio
import pytest
from ai_runtime.application.routing.model_router import ModelRouter, ProviderNotRegisteredError
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole
from ai_runtime.domain.routing import UnsupportedModelError
from ai_runtime.ports.model_provider import ModelProvider


class FakeModelProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            id=f"resp-{self.name}",
            model=request.model,
            output=Message(role=MessageRole.ASSISTANT, content=self.name),
        )


def test_resolve_binds_catalog_model_to_registered_adapter() -> None:
    openai = FakeModelProvider("openai")
    router = ModelRouter(providers={"openai": openai})
    resolved = router.resolve("gpt-4o-mini")
    assert resolved.provider_name == "openai"
    assert resolved.provider is openai
    assert resolved.route.model == "gpt-4o-mini"


def test_resolve_selects_provider_from_injected_catalog() -> None:
    openai = FakeModelProvider("openai")
    anthropic = FakeModelProvider("anthropic")
    router = ModelRouter(
        providers={"openai": openai, "anthropic": anthropic},
        catalog={"gpt-4o-mini": "openai", "claude-sonnet": "anthropic"},
    )
    assert router.resolve("claude-sonnet").provider is anthropic
    assert router.resolve("gpt-4o-mini").provider is openai


def test_resolve_raises_for_unknown_model() -> None:
    router = ModelRouter(providers={"openai": FakeModelProvider("openai")})
    with pytest.raises(UnsupportedModelError) as exc_info:
        router.resolve("not-a-model")
    assert exc_info.value.model == "not-a-model"


def test_resolve_raises_when_provider_adapter_missing() -> None:
    router = ModelRouter(providers={}, catalog={"gpt-4o-mini": "openai"})
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        router.resolve("gpt-4o-mini")
    assert exc_info.value.provider == "openai"


def test_resolved_provider_satisfies_model_provider_port() -> None:
    openai = FakeModelProvider("openai")
    router = ModelRouter(providers={"openai": openai})
    resolved = router.resolve("gpt-4o")
    assert isinstance(resolved.provider, ModelProvider)
    request = GenerationRequest(model="gpt-4o", messages=(Message(role=MessageRole.USER, content="Hi"),))
    response = asyncio.run(resolved.provider.generate(request))
    assert response.output.content == "openai"
    assert openai.requests == [request]

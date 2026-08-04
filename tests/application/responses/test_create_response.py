"""Unit tests for the CreateResponse use case."""

import asyncio

import pytest
from ai_runtime.application.responses.create_response import CreateResponse
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole
from ai_runtime.ports.model_provider import ModelProvider


class FakeProviderError(Exception):
    """Failure raised by the fake provider during a generation call."""


class FakeModelProvider:
    """Deterministic provider fake that records the request it receives."""

    def __init__(self, response: GenerationResponse | None = None, error: Exception | None = None) -> None:
        self.requests: list[GenerationRequest] = []
        self._response = response
        self._error = error

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _request() -> GenerationRequest:
    return GenerationRequest(model="fake-model", messages=(Message(role=MessageRole.USER, content="Hello"),))


def _response() -> GenerationResponse:
    return GenerationResponse(
        id="response-1",
        model="fake-model",
        output=Message(role=MessageRole.ASSISTANT, content="Hi"),
    )


def test_create_response_delegates_request_and_returns_provider_response() -> None:
    """The use case forwards the exact request and returns the provider result."""
    request = _request()
    response = _response()
    provider = FakeModelProvider(response=response)
    use_case = CreateResponse(provider)

    result = asyncio.run(use_case.execute(request))

    assert provider.requests == [request]
    assert result is response


def test_create_response_propagates_provider_failure() -> None:
    """Provider failures remain visible to the caller for outer-layer mapping."""
    error = FakeProviderError("generation failed")
    use_case = CreateResponse(FakeModelProvider(error=error))

    with pytest.raises(FakeProviderError, match="generation failed"):
        asyncio.run(use_case.execute(_request()))


def test_create_response_accepts_model_provider_protocol() -> None:
    """The injected fake satisfies the ModelProvider protocol structurally."""
    provider: ModelProvider = FakeModelProvider(response=_response())
    assert isinstance(provider, ModelProvider)
    assert isinstance(CreateResponse(provider), CreateResponse)

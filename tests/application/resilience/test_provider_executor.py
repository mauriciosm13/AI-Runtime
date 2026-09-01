"""Unit tests for ProviderExecutor retries and failover."""

import asyncio
import pytest
from ai_runtime.application.resilience.provider_executor import ProviderExecutor
from ai_runtime.application.routing.model_router import ModelRouter, ProviderNotRegisteredError
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, Message, MessageRole
from ai_runtime.domain.organization_policy import ModelNotAvailableError
from ai_runtime.domain.routing import ModelRoute, UnsupportedModelError
from ai_runtime.providers.errors import ProviderError


class FakeModelProvider:
    """Provider fake that can fail a fixed number of times before succeeding."""

    def __init__(
        self,
        *,
        name: str,
        response: GenerationResponse | None = None,
        errors: tuple[Exception, ...] = (),
    ) -> None:
        self.name = name
        self.requests: list[GenerationRequest] = []
        self._response = response
        self._errors = list(errors)

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        if self._errors:
            raise self._errors.pop(0)
        assert self._response is not None
        return self._response


def _request(*, model: str = "gpt-4o-mini") -> GenerationRequest:
    return GenerationRequest(model=model, messages=(Message(role=MessageRole.USER, content="Hello"),))


def _response(*, model: str = "gpt-4o-mini") -> GenerationResponse:
    return GenerationResponse(
        id="resp-1",
        model=model,
        output=Message(role=MessageRole.ASSISTANT, content="ok"),
        usage=None,
    )


def test_execute_returns_primary_provider_response() -> None:
    openai = FakeModelProvider(name="openai", response=_response())
    router = ModelRouter(providers={"openai": openai})
    executor = ProviderExecutor(router, failover_enabled=False)

    result = asyncio.run(executor.execute(requested_model="gpt-4o-mini", request=_request()))

    assert result.provider_name == "openai"
    assert openai.requests == [_request()]
    assert result.response.output.content == "ok"


def test_execute_retries_transient_provider_errors() -> None:
    openai = FakeModelProvider(
        name="openai",
        response=_response(),
        errors=(ProviderError.transient("temporary"), ProviderError.transient("temporary")),
    )
    router = ModelRouter(providers={"openai": openai})
    executor = ProviderExecutor(router, max_retries=2, retry_base_delay_seconds=0, failover_enabled=False)

    result = asyncio.run(executor.execute(requested_model="gpt-4o-mini", request=_request()))

    assert result.provider_name == "openai"
    assert len(openai.requests) == 3


def test_execute_does_not_retry_non_retryable_errors() -> None:
    openai = FakeModelProvider(
        name="openai",
        response=_response(),
        errors=(ProviderError.from_http_status("bad request", 400),),
    )
    router = ModelRouter(providers={"openai": openai})
    executor = ProviderExecutor(router, max_retries=2, retry_base_delay_seconds=0, failover_enabled=False)

    with pytest.raises(ProviderError, match="bad request"):
        asyncio.run(executor.execute(requested_model="gpt-4o-mini", request=_request()))

    assert len(openai.requests) == 1


def test_execute_fails_over_to_registered_provider() -> None:
    openai = FakeModelProvider(
        name="openai",
        response=_response(model="gpt-4o-mini"),
        errors=(ProviderError.from_http_status("upstream down", 503),),
    )
    anthropic = FakeModelProvider(name="anthropic", response=_response(model="claude-3-5-sonnet-20241022"))
    router = ModelRouter(providers={"openai": openai, "anthropic": anthropic})
    executor = ProviderExecutor(router, max_retries=0, failover_enabled=True)

    result = asyncio.run(
        executor.execute(
            requested_model="gpt-4o-mini",
            request=_request(model="gpt-4o-mini"),
        )
    )

    assert result.provider_name == "anthropic"
    assert anthropic.requests == [_request(model="claude-3-5-sonnet-20241022")]
    assert len(openai.requests) == 1


def test_execute_skips_failover_target_without_entitlement() -> None:
    openai = FakeModelProvider(
        name="openai",
        response=_response(model="gpt-4o"),
        errors=(ProviderError.from_http_status("upstream down", 503),),
    )
    anthropic = FakeModelProvider(name="anthropic", response=_response(model="claude-3-5-sonnet-20241022"))
    router = ModelRouter(providers={"openai": openai, "anthropic": anthropic})
    executor = ProviderExecutor(router, max_retries=0, failover_enabled=True)

    async def before_route(route: ModelRoute) -> None:
        if route.model != "gpt-4o":
            raise ModelNotAvailableError(model=route.model)

    with pytest.raises(ProviderError, match="upstream down"):
        asyncio.run(
            executor.execute(
                requested_model="gpt-4o",
                request=_request(model="gpt-4o"),
                before_route=before_route,
            )
        )

    assert len(openai.requests) == 1
    assert anthropic.requests == []


def test_execute_skips_unregistered_failover_provider() -> None:
    openai = FakeModelProvider(
        name="openai",
        response=_response(model="gpt-4o-mini"),
        errors=(ProviderError.from_http_status("upstream down", 503),),
    )
    router = ModelRouter(providers={"openai": openai})
    executor = ProviderExecutor(router, max_retries=0, failover_enabled=True)

    with pytest.raises(ProviderError, match="upstream down"):
        asyncio.run(executor.execute(requested_model="gpt-4o-mini", request=_request()))

    assert len(openai.requests) == 1


def test_execute_raises_for_unknown_model() -> None:
    router = ModelRouter(providers={"openai": FakeModelProvider(name="openai", response=_response())})
    executor = ProviderExecutor(router, failover_enabled=False)

    with pytest.raises(UnsupportedModelError):
        asyncio.run(
            executor.execute(
                requested_model="unknown",
                request=GenerationRequest(model="unknown", messages=(Message(role=MessageRole.USER, content="Hello"),)),
            )
        )


def test_execute_raises_when_primary_provider_not_registered() -> None:
    router = ModelRouter(providers={}, catalog={"gpt-4o-mini": "openai"})
    executor = ProviderExecutor(router, failover_enabled=False)

    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        asyncio.run(executor.execute(requested_model="gpt-4o-mini", request=_request()))

    assert exc_info.value.provider == "openai"

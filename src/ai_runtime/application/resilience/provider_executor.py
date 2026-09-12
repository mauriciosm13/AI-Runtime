"""Execute provider generation with bounded retries and cross-provider failover."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from ai_runtime.application.routing.model_router import ModelRouter, ProviderNotRegisteredError
from ai_runtime.domain.generation import GenerationRequest, GenerationResponse, GenerationStreamEvent
from ai_runtime.domain.organization_policy import ModelNotAvailableError
from ai_runtime.domain.routing import DEFAULT_FAILOVER_CATALOG, ModelRoute, resolve_model_route, resolve_route_chain
from ai_runtime.ports.model_provider import ModelProvider
from ai_runtime.providers.errors import ProviderError

RouteHook = Callable[[ModelRoute], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult:
    """Successful provider generation bound to the route that served it."""

    response: GenerationResponse
    route: ModelRoute

    @property
    def provider_name(self) -> str:
        """Provider identifier recorded on usage and cost estimates."""
        return self.route.provider


@dataclass(frozen=True, slots=True)
class ProviderStreamEvent:
    """A streamed generation event bound to the route that produced it."""

    payload: GenerationStreamEvent
    route: ModelRoute

    @property
    def provider_name(self) -> str:
        """Provider identifier recorded on usage and cost estimates."""
        return self.route.provider


class ProviderExecutor:
    """Retry transient provider failures and fail over across catalog routes."""

    def __init__(
        self,
        model_router: ModelRouter,
        *,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 0.25,
        failover_enabled: bool = True,
        failover_catalog: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._model_router = model_router
        self._max_retries = max_retries
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._failover_enabled = failover_enabled
        self._failover_catalog = DEFAULT_FAILOVER_CATALOG if failover_catalog is None else failover_catalog

    async def execute(
        self,
        *,
        requested_model: str,
        request: GenerationRequest,
        before_route: RouteHook | None = None,
    ) -> ProviderExecutionResult:
        """Generate a response, retrying transient failures and failing over when configured."""
        routes = self._routes_for(requested_model)
        last_error: ProviderError | None = None
        skipped_unavailable: list[str] = []
        skipped_unregistered: list[str] = []
        for route in routes:
            if before_route is not None:
                try:
                    await before_route(route)
                except ModelNotAvailableError:
                    skipped_unavailable.append(route.model)
                    continue
            try:
                resolved = self._model_router.resolve(route.model)
            except ProviderNotRegisteredError as err:
                skipped_unregistered.append(err.provider)
                continue
            route_request = request if route.model == request.model else replace(request, model=route.model)
            try:
                response = await self._generate_with_retries(resolved.provider, route_request)
            except ProviderError as err:
                last_error = err
                continue
            return ProviderExecutionResult(response=response, route=resolved.route)
        if last_error is not None:
            raise last_error
        if skipped_unavailable and len(skipped_unavailable) == len(routes):
            raise ModelNotAvailableError(model=requested_model)
        if skipped_unregistered:
            raise ProviderNotRegisteredError(provider=skipped_unregistered[0])
        raise ProviderNotRegisteredError(provider=routes[0].provider)

    async def stream(
        self,
        *,
        requested_model: str,
        request: GenerationRequest,
        before_route: RouteHook | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Stream generation events, retrying and failing over only before the first event."""
        routes = self._routes_for(requested_model)
        last_error: ProviderError | None = None
        skipped_unavailable: list[str] = []
        skipped_unregistered: list[str] = []
        for route in routes:
            if before_route is not None:
                try:
                    await before_route(route)
                except ModelNotAvailableError:
                    skipped_unavailable.append(route.model)
                    continue
            try:
                resolved = self._model_router.resolve(route.model)
            except ProviderNotRegisteredError as err:
                skipped_unregistered.append(err.provider)
                continue
            route_request = request if route.model == request.model else replace(request, model=route.model)
            started = False
            try:
                async for event in self._stream_with_retries(resolved.provider, route_request):
                    started = True
                    yield ProviderStreamEvent(payload=event, route=resolved.route)
                return
            except ProviderError as err:
                if started:
                    raise
                last_error = err
                continue
        if last_error is not None:
            raise last_error
        if skipped_unavailable and len(skipped_unavailable) == len(routes):
            raise ModelNotAvailableError(model=requested_model)
        if skipped_unregistered:
            raise ProviderNotRegisteredError(provider=skipped_unregistered[0])
        raise ProviderNotRegisteredError(provider=routes[0].provider)

    def _routes_for(self, requested_model: str) -> tuple[ModelRoute, ...]:
        catalog = self._model_router.catalog
        if not self._failover_enabled:
            return (resolve_model_route(requested_model, catalog),)
        return resolve_route_chain(requested_model, catalog, self._failover_catalog)

    async def _generate_with_retries(
        self,
        provider: ModelProvider,
        request: GenerationRequest,
    ) -> GenerationResponse:
        attempt = 0
        while True:
            try:
                return await provider.generate(request)
            except ProviderError as err:
                if not err.retryable or attempt >= self._max_retries:
                    raise
                attempt += 1
                if self._retry_base_delay_seconds > 0:
                    await asyncio.sleep(self._retry_base_delay_seconds * attempt)

    async def _stream_with_retries(
        self,
        provider: ModelProvider,
        request: GenerationRequest,
    ) -> AsyncIterator[GenerationStreamEvent]:
        attempt = 0
        while True:
            started = False
            try:
                async for event in provider.stream(request):
                    started = True
                    yield event
                return
            except ProviderError as err:
                if started or not err.retryable or attempt >= self._max_retries:
                    raise
                attempt += 1
                if self._retry_base_delay_seconds > 0:
                    await asyncio.sleep(self._retry_base_delay_seconds * attempt)

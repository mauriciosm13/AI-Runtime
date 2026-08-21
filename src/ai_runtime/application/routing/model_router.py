"""Select a model provider from an explicit routing catalog."""

from collections.abc import Mapping
from dataclasses import dataclass
from ai_runtime.domain.routing import DEFAULT_MODEL_CATALOG, ModelRoute, resolve_model_route
from ai_runtime.ports.model_provider import ModelProvider


class ProviderNotRegisteredError(Exception):
    """Raised when a catalog route names a provider with no adapter registered."""

    def __init__(self, *, provider: str) -> None:
        self.provider = provider
        super().__init__("The selected provider is not registered.")


@dataclass(frozen=True, slots=True)
class ResolvedRoute:
    """A catalog route bound to a live provider adapter."""

    route: ModelRoute
    provider: ModelProvider

    @property
    def provider_name(self) -> str:
        """Provider identifier recorded on usage and cost estimates."""
        return self.route.provider


class ModelRouter:
    """Resolve a requested model to a registered ModelProvider adapter."""

    def __init__(
        self,
        providers: Mapping[str, ModelProvider],
        catalog: Mapping[str, str] | None = None,
    ) -> None:
        self._providers = providers
        self._catalog = DEFAULT_MODEL_CATALOG if catalog is None else catalog

    def resolve(self, requested_model: str) -> ResolvedRoute:
        """Return the provider adapter for ``requested_model``.

        Raises ``UnsupportedModelError`` when the model is absent from the catalog.
        Raises ``ProviderNotRegisteredError`` when the catalog provider has no adapter.
        """
        route = resolve_model_route(requested_model, self._catalog)
        adapter = self._providers.get(route.provider)
        if adapter is None:
            raise ProviderNotRegisteredError(provider=route.provider)
        return ResolvedRoute(route=route, provider=adapter)

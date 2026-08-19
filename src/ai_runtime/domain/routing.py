"""Provider-neutral model routing catalog and resolution rules."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from ai_runtime.domain.generation import DomainValidationError


class UnsupportedModelError(Exception):
    """Raised when the requested model is not in the routing catalog."""

    def __init__(self, *, model: str) -> None:
        self.model = model
        super().__init__("The requested model is not supported.")


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """A model served by a named provider."""

    model: str
    provider: str

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")
        _require_non_blank(self.provider, "provider")


DEFAULT_MODEL_CATALOG: Mapping[str, str] = MappingProxyType(
    {
        "gpt-4o-mini": "openai",
        "gpt-4o": "openai",
    }
)


def resolve_model_route(requested_model: str, catalog: Mapping[str, str]) -> ModelRoute:
    """Return the catalog route for ``requested_model``.

    Raises ``UnsupportedModelError`` when the model is not listed.
    """
    _require_non_blank(requested_model, "requested_model")
    provider = catalog.get(requested_model)
    if provider is None:
        raise UnsupportedModelError(model=requested_model)
    return ModelRoute(model=requested_model, provider=provider)

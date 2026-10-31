"""Static embedding model catalog and resolution rules."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from ai_runtime.domain.generation import DomainValidationError
from ai_runtime.domain.routing import UnsupportedModelError


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{field_name} must not be empty or blank")


@dataclass(frozen=True, slots=True)
class EmbeddingRoute:
    """An embedding model served by a named provider."""

    model: str
    provider: str

    def __post_init__(self) -> None:
        _require_non_blank(self.model, "model")
        _require_non_blank(self.provider, "provider")


DEFAULT_EMBEDDING_CATALOG: Mapping[str, str] = MappingProxyType(
    {
        "text-embedding-3-small": "openai",
        "text-embedding-3-large": "openai",
    }
)

DEFAULT_RAG_EMBEDDING_MODEL = "text-embedding-3-small"


def resolve_embedding_route(requested_model: str, catalog: Mapping[str, str]) -> EmbeddingRoute:
    """Return the catalog route for ``requested_model``.

    Raises ``UnsupportedModelError`` when the model is not listed.
    """
    _require_non_blank(requested_model, "requested_model")
    provider = catalog.get(requested_model)
    if provider is None:
        raise UnsupportedModelError(model=requested_model)
    return EmbeddingRoute(model=requested_model, provider=provider)

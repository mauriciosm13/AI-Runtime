"""Context budget contracts for assembled generation requests."""

from dataclasses import dataclass
from ai_runtime.domain.generation import DomainValidationError


class ContextLimitExceededError(Exception):
    """Raised when the assembled input cannot fit the model context budget."""

    def __init__(self) -> None:
        super().__init__("The request does not fit the model context window.")


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """Client-chosen context handling: optional lower budget and opt-in truncation."""

    max_input_tokens: int | None = None
    truncate: bool = False

    def __post_init__(self) -> None:
        if self.max_input_tokens is not None and self.max_input_tokens <= 0:
            raise DomainValidationError("max_input_tokens must be greater than zero")

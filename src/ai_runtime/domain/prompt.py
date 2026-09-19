"""Prompt template contracts: versioned, organization-scoped message templates."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from ai_runtime.domain.generation import DomainValidationError, Message, MessageRole

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TEMPLATE_ROLES = frozenset({MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT})


class PromptNotFoundError(Exception):
    """Raised when a prompt template name or version does not exist for the organization."""

    def __init__(self, *, name: str, version: int | None) -> None:
        self.name = name
        self.version = version
        super().__init__("The requested prompt was not found.")


class PromptVersionConflictError(Exception):
    """Raised when a concurrent writer already created the requested prompt version."""

    def __init__(self) -> None:
        super().__init__("A prompt version was created concurrently; retry the request.")


def validate_prompt_name(name: str) -> None:
    """Reject names that are not 1-64 characters of ``[A-Za-z0-9._-]``."""
    if _NAME_PATTERN.fullmatch(name) is None:
        raise DomainValidationError("prompt name must be 1-64 characters using [A-Za-z0-9._-]")


@dataclass(frozen=True, slots=True)
class PromptMessageTemplate:
    """One templated message. ``content`` may contain ``{{variable}}`` placeholders."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in _TEMPLATE_ROLES:
            raise DomainValidationError("prompt template roles must be system, user, or assistant")
        if not self.content.strip():
            raise DomainValidationError("content must not be empty or blank")

    @property
    def placeholders(self) -> frozenset[str]:
        """Variable names referenced by this message."""
        return frozenset(_PLACEHOLDER_PATTERN.findall(self.content))


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """An immutable version of a named prompt owned by one organization."""

    id: UUID
    organization_id: UUID
    name: str
    version: int
    messages: tuple[PromptMessageTemplate, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        validate_prompt_name(self.name)
        if self.version < 1:
            raise DomainValidationError("version must be at least 1")
        if not self.messages:
            raise DomainValidationError("messages must contain at least one message")

    @property
    def placeholders(self) -> frozenset[str]:
        """Variable names referenced anywhere in this template."""
        names: set[str] = set()
        for message in self.messages:
            names |= message.placeholders
        return frozenset(names)

    def render(self, variables: Mapping[str, str]) -> tuple[Message, ...]:
        """Substitute ``variables`` into the template in a single literal pass.

        The provided variable names must equal the template placeholders. Values
        are inserted verbatim and never re-scanned, so a value that contains
        ``{{x}}`` is not expanded.
        """
        expected = self.placeholders
        provided = frozenset(variables)
        missing = sorted(expected - provided)
        unknown = sorted(provided - expected)
        if missing:
            raise DomainValidationError(f"missing prompt variables: {', '.join(missing)}")
        if unknown:
            raise DomainValidationError(f"unknown prompt variables: {', '.join(unknown)}")
        return tuple(
            Message(role=message.role, content=_PLACEHOLDER_PATTERN.sub(lambda match: variables[match.group(1)], message.content))
            for message in self.messages
        )


@dataclass(frozen=True, slots=True)
class PromptReference:
    """A request to use a stored template. ``version=None`` selects the latest version."""

    name: str
    variables: Mapping[str, str]
    version: int | None = None

    def __post_init__(self) -> None:
        validate_prompt_name(self.name)
        if self.version is not None and self.version < 1:
            raise DomainValidationError("version must be at least 1")

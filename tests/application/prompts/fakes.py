"""In-memory PromptRepository fake shared by application and API tests."""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4
from ai_runtime.application.prompts.resolve_prompt import ResolvePrompt
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptTemplate


class FakePromptRepository:
    """Store prompt versions in memory, scoped by organization and name."""

    def __init__(self) -> None:
        self.templates: list[PromptTemplate] = []

    async def create_version(self, organization_id: UUID, name: str, messages: Sequence[PromptMessageTemplate]) -> PromptTemplate:
        version = len([item for item in self.templates if item.organization_id == organization_id and item.name == name]) + 1
        template = PromptTemplate(
            id=uuid4(),
            organization_id=organization_id,
            name=name,
            version=version,
            messages=tuple(messages),
            created_at=datetime.now(UTC),
        )
        self.templates.append(template)
        return template

    async def get(self, organization_id: UUID, name: str, version: int | None) -> PromptTemplate | None:
        matches = [item for item in self.templates if item.organization_id == organization_id and item.name == name]
        if version is not None:
            matches = [item for item in matches if item.version == version]
        return max(matches, key=lambda item: item.version) if matches else None

    async def list_versions(self, organization_id: UUID, name: str) -> tuple[PromptTemplate, ...]:
        matches = [item for item in self.templates if item.organization_id == organization_id and item.name == name]
        return tuple(sorted(matches, key=lambda item: item.version))


def override_resolve_prompt(repository: FakePromptRepository) -> Callable[[], Awaitable[ResolvePrompt]]:
    """Build a FastAPI dependency override that resolves prompts from ``repository``."""

    async def _override() -> ResolvePrompt:
        return ResolvePrompt(repository)

    return _override

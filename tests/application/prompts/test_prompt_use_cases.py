"""Prompt template use case tests."""

import asyncio
from uuid import uuid4
import pytest
from ai_runtime.application.prompts.create_prompt_version import CreatePromptVersion
from ai_runtime.application.prompts.get_prompt_versions import GetPromptVersions
from ai_runtime.application.prompts.resolve_prompt import ResolvePrompt
from ai_runtime.domain.generation import DomainValidationError, MessageRole
from ai_runtime.domain.prompt import PromptMessageTemplate, PromptNotFoundError, PromptReference
from tests.application.prompts.fakes import FakePromptRepository

_USER = PromptMessageTemplate(role=MessageRole.USER, content="Hello {{name}}")


def test_create_increments_version_per_name() -> None:
    async def scenario() -> None:
        repository = FakePromptRepository()
        org = uuid4()
        create = CreatePromptVersion(repository)
        first = await create.execute(org, "greet", [_USER])
        second = await create.execute(org, "greet", [_USER])
        other = await create.execute(org, "other", [_USER])
        assert (first.version, second.version, other.version) == (1, 2, 1)

    asyncio.run(scenario())


def test_create_rejects_invalid_name_and_empty_messages() -> None:
    async def scenario() -> None:
        create = CreatePromptVersion(FakePromptRepository())
        with pytest.raises(DomainValidationError):
            await create.execute(uuid4(), "bad name", [_USER])
        with pytest.raises(DomainValidationError):
            await create.execute(uuid4(), "ok", [])

    asyncio.run(scenario())


def test_resolve_uses_latest_version_by_default_and_pinned_when_given() -> None:
    async def scenario() -> None:
        repository = FakePromptRepository()
        org = uuid4()
        create = CreatePromptVersion(repository)
        await create.execute(org, "greet", [PromptMessageTemplate(role=MessageRole.USER, content="v1 {{name}}")])
        await create.execute(org, "greet", [PromptMessageTemplate(role=MessageRole.USER, content="v2 {{name}}")])
        resolve = ResolvePrompt(repository)
        latest = await resolve.execute(org, PromptReference(name="greet", variables={"name": "Ana"}))
        pinned = await resolve.execute(org, PromptReference(name="greet", variables={"name": "Ana"}, version=1))
        assert latest[0].content == "v2 Ana"
        assert pinned[0].content == "v1 Ana"

    asyncio.run(scenario())


def test_resolve_is_isolated_between_organizations() -> None:
    async def scenario() -> None:
        repository = FakePromptRepository()
        owner, intruder = uuid4(), uuid4()
        await CreatePromptVersion(repository).execute(owner, "secret", [_USER])
        with pytest.raises(PromptNotFoundError):
            await ResolvePrompt(repository).execute(intruder, PromptReference(name="secret", variables={"name": "x"}))
        with pytest.raises(PromptNotFoundError):
            await GetPromptVersions(repository).execute(intruder, "secret")

    asyncio.run(scenario())


def test_resolve_missing_version_and_variable_mismatch() -> None:
    async def scenario() -> None:
        repository = FakePromptRepository()
        org = uuid4()
        await CreatePromptVersion(repository).execute(org, "greet", [_USER])
        resolve = ResolvePrompt(repository)
        with pytest.raises(PromptNotFoundError):
            await resolve.execute(org, PromptReference(name="greet", variables={"name": "x"}, version=9))
        with pytest.raises(DomainValidationError):
            await resolve.execute(org, PromptReference(name="greet", variables={}))

    asyncio.run(scenario())


def test_get_versions_returns_ascending_order() -> None:
    async def scenario() -> None:
        repository = FakePromptRepository()
        org = uuid4()
        create = CreatePromptVersion(repository)
        await create.execute(org, "greet", [_USER])
        await create.execute(org, "greet", [_USER])
        versions = await GetPromptVersions(repository).execute(org, "greet")
        assert [item.version for item in versions] == [1, 2]

    asyncio.run(scenario())

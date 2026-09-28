"""Tests for the prompt routes."""

import httpx
from ai_runtime_sdk import PromptList, PromptVersion
from tests.http import BASE_URL, async_client, client, json_body

_CREATED_AT = "2026-09-27T12:00:00Z"


def _version() -> dict[str, object]:
    return {
        "name": "support.reply",
        "version": 2,
        "messages": [{"role": "system", "content": "Hello {{name}}"}],
        "variables": ["name"],
        "created_at": _CREATED_AT,
    }


def test_create_and_list_prompts() -> None:
    """Creating a prompt posts the template, and listing it escapes the name into one path segment."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json=_version(), headers={"X-Request-ID": "req_p"})
        return httpx.Response(200, json={"versions": [_version()]}, headers={"X-Request-ID": "req_l"})

    with client(handler) as runtime:
        created = runtime.prompts.create(name="support.reply", messages=[{"role": "system", "content": "Hello {{name}}"}])
        listed = runtime.prompts.list("a/b")

    assert json_body(seen[0]) == {"name": "support.reply", "messages": [{"role": "system", "content": "Hello {{name}}"}]}
    assert str(seen[1].url) == f"{BASE_URL}/v1/prompts/a%2Fb"
    assert created == PromptVersion.model_validate({**_version(), "request_id": "req_p"})
    assert listed == PromptList.model_validate({"versions": [_version()], "request_id": "req_l"})


def test_async_prompt_list() -> None:
    """The async client lists prompt versions."""
    import asyncio

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer ")
        return httpx.Response(200, json={"versions": [_version()]})

    async def _run() -> PromptList:
        runtime = async_client(handler)
        try:
            return await runtime.prompts.list("support.reply")
        finally:
            await runtime._http.aclose()

    listed = asyncio.run(_run())
    assert listed.versions[0].version == 2

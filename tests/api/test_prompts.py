"""Prompt template endpoints and prompt/context use on POST /v1/responses."""

from typing import Any
from ai_runtime.application.auth.authenticate_api_key import AuthenticatedPrincipal
from ai_runtime.domain.generation import Message, MessageRole
from tests.api.test_responses import FakeModelProvider, _client_with_provider, _fake_principal, _success_response
from tests.application.prompts.fakes import FakePromptRepository
from tests.application.responses.test_create_response import FakeResponseCache

_TEMPLATE = {
    "name": "support.reply",
    "messages": [
        {"role": "system", "content": "You help {{company}}."},
        {"role": "user", "content": "Customer {{name}} asks: {{question}}"},
    ],
}
_VARIABLES = {"company": "Acme", "name": "Ana", "question": "Where is my order?"}


def _client(principal: AuthenticatedPrincipal | None = None, prompts: FakePromptRepository | None = None, **kwargs: Any) -> Any:
    provider = FakeModelProvider(response=_success_response())
    client = _client_with_provider(provider, principal=principal or _fake_principal(), prompts=prompts, **kwargs)
    return client, provider


def test_create_and_list_prompt_versions() -> None:
    client, _provider = _client()
    first = client.post("/v1/prompts", json=_TEMPLATE)
    second = client.post("/v1/prompts", json=_TEMPLATE)
    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert first.json()["variables"] == ["company", "name", "question"]
    assert second.json()["version"] == 2
    listed = client.get("/v1/prompts/support.reply")
    assert listed.status_code == 200
    assert [item["version"] for item in listed.json()["versions"]] == [1, 2]


def test_create_prompt_rejects_invalid_name_and_role() -> None:
    client, _provider = _client()
    assert client.post("/v1/prompts", json={**_TEMPLATE, "name": "bad name"}).status_code == 422
    tool_role = {"name": "x", "messages": [{"role": "tool", "content": "y"}]}
    response = client.post("/v1/prompts", json=tool_role)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_get_unknown_prompt_returns_404_envelope() -> None:
    client, _provider = _client()
    response = client.get("/v1/prompts/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "prompt_not_found"


def test_prompts_are_isolated_between_organizations() -> None:
    shared = FakePromptRepository()
    owner, _ = _client(prompts=shared)
    intruder, _ = _client(prompts=shared, principal=_fake_principal())
    assert owner.post("/v1/prompts", json=_TEMPLATE).status_code == 201
    assert intruder.get("/v1/prompts/support.reply").status_code == 404


def test_responses_with_prompt_matches_equivalent_raw_messages() -> None:
    client, provider = _client()
    client.post("/v1/prompts", json=_TEMPLATE)
    response = client.post("/v1/responses", json={"model": "gpt-4o-mini", "prompt": {"name": "support.reply", "variables": _VARIABLES}})
    assert response.status_code == 200
    assert provider.requests[0].messages == (
        Message(role=MessageRole.SYSTEM, content="You help Acme."),
        Message(role=MessageRole.USER, content="Customer Ana asks: Where is my order?"),
    )


def test_responses_with_pinned_version() -> None:
    client, provider = _client()
    client.post("/v1/prompts", json={"name": "p", "messages": [{"role": "user", "content": "v1"}]})
    client.post("/v1/prompts", json={"name": "p", "messages": [{"role": "user", "content": "v2"}]})
    client.post("/v1/responses", json={"model": "gpt-4o-mini", "prompt": {"name": "p", "version": 1}})
    assert provider.requests[0].messages[0].content == "v1"


def test_responses_prompt_errors() -> None:
    client, _provider = _client()
    client.post("/v1/prompts", json=_TEMPLATE)
    missing = client.post("/v1/responses", json={"model": "gpt-4o-mini", "prompt": {"name": "nope"}})
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "prompt_not_found")
    mismatch = client.post("/v1/responses", json={"model": "gpt-4o-mini", "prompt": {"name": "support.reply", "variables": {"name": "x"}}})
    assert (mismatch.status_code, mismatch.json()["error"]["code"]) == (422, "invalid_request")


def test_responses_requires_exactly_one_of_messages_or_prompt() -> None:
    client, _provider = _client()
    both = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "prompt": {"name": "p"}}
    neither = {"model": "gpt-4o-mini"}
    for body in (both, neither):
        response = client.post("/v1/responses", json=body)
        assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_request")


def test_responses_context_budget_rejects_then_truncates() -> None:
    client, provider = _client()
    messages = [
        {"role": "user", "content": "a" * 300},
        {"role": "assistant", "content": "b" * 300},
        {"role": "user", "content": "c" * 30},
    ]
    body: dict[str, Any] = {"model": "gpt-4o-mini", "messages": messages, "context": {"max_input_tokens": 60}}
    rejected = client.post("/v1/responses", json=body)
    assert (rejected.status_code, rejected.json()["error"]["code"]) == (422, "context_length_exceeded")
    body["context"] = {"max_input_tokens": 60, "truncate": True}
    accepted = client.post("/v1/responses", json=body)
    assert accepted.status_code == 200
    assert [item.content for item in provider.requests[0].messages] == ["c" * 30]


def test_responses_without_prompt_or_context_is_not_budgeted() -> None:
    client, provider = _client()
    huge = [{"role": "user", "content": "x" * 1_000_000}]
    assert client.post("/v1/responses", json={"model": "gpt-4o-mini", "messages": huge}).status_code == 200
    assert len(provider.requests) == 1


def test_prompt_request_shares_cache_entry_with_equivalent_raw_messages() -> None:
    cache = FakeResponseCache()
    principal = _fake_principal()
    client, provider = _client(response_cache=cache, principal=principal)
    client.post("/v1/prompts", json={"name": "p", "messages": [{"role": "user", "content": "Hello {{n}}"}]})
    prompt_body = {"model": "gpt-4o-mini", "cache": True, "prompt": {"name": "p", "variables": {"n": "Ana"}}}
    raw_body = {"model": "gpt-4o-mini", "cache": True, "messages": [{"role": "user", "content": "Hello Ana"}]}
    via_prompt = client.post("/v1/responses", json=prompt_body)
    via_raw = client.post("/v1/responses", json=raw_body)
    assert via_prompt.status_code == via_raw.status_code == 200
    assert via_raw.json()["cached"] is True
    assert len(provider.requests) == 1


def test_prompt_content_is_never_logged(capfd: Any) -> None:
    client, _provider = _client()
    client.post("/v1/prompts", json={"name": "p", "messages": [{"role": "user", "content": "TOP-SECRET-TEMPLATE {{v}}"}]})
    client.post("/v1/responses", json={"model": "gpt-4o-mini", "prompt": {"name": "p", "variables": {"v": "SECRET-VALUE-XYZ"}}})
    captured = capfd.readouterr()
    assert "request_completed" in captured.out + captured.err
    assert "TOP-SECRET-TEMPLATE" not in captured.out + captured.err
    assert "SECRET-VALUE-XYZ" not in captured.out + captured.err




def test_prompt_works_with_streaming_and_tools() -> None:
    client, provider = _client()
    client.post("/v1/prompts", json={"name": "p", "messages": [{"role": "user", "content": "Hi {{n}}"}]})
    stream_body = {"model": "gpt-4o-mini", "stream": True, "prompt": {"name": "p", "variables": {"n": "Ana"}}}
    streamed = client.post("/v1/responses", json=stream_body)
    assert streamed.status_code == 200
    assert "response.completed" in streamed.text
    tool = {"name": "lookup", "description": "d", "parameters": {"type": "object"}}
    tools_body = {"model": "gpt-4o-mini", "tools": [tool], "prompt": {"name": "p", "variables": {"n": "Bo"}}}
    with_tools = client.post("/v1/responses", json=tools_body)
    assert with_tools.status_code == 200
    assert provider.requests[-1].tools[0].name == "lookup"

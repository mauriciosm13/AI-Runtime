"""Request bodies for the public HTTP API."""

from collections.abc import Mapping, Sequence
from typing import Any
from ai_runtime_sdk.models import Context, Message, PromptMessage, PromptReference, ToolDefinition

JsonObject = dict[str, Any]
MessageInput = Message | Mapping[str, Any]
PromptInput = PromptReference | Mapping[str, Any]
ContextInput = Context | Mapping[str, Any]
ToolInput = ToolDefinition | Mapping[str, Any]
PromptMessageInput = PromptMessage | Mapping[str, Any]


def build_headers(api_key: str, *, idempotency_key: str | None = None, request_id: str | None = None) -> dict[str, str]:
    """Headers for an authenticated API call. The key is not copied anywhere else."""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers


def message_payload(message: MessageInput) -> JsonObject:
    """Serialize one generation message, omitting tool fields the API leaves out when unset."""
    model = message if isinstance(message, Message) else Message.model_validate(message)
    payload: JsonObject = {"role": model.role.value, "content": model.content}
    if model.tool_calls:
        payload["tool_calls"] = [{"id": item.id, "name": item.name, "arguments": item.arguments} for item in model.tool_calls]
    if model.tool_call_id is not None:
        payload["tool_call_id"] = model.tool_call_id
    if model.name is not None:
        payload["name"] = model.name
    return payload


def prompt_reference_payload(prompt: PromptInput) -> JsonObject:
    """Serialize a prompt reference. ``version`` is omitted so the server uses the latest."""
    model = prompt if isinstance(prompt, PromptReference) else PromptReference.model_validate(prompt)
    payload: JsonObject = {"name": model.name, "variables": dict(model.variables)}
    if model.version is not None:
        payload["version"] = model.version
    return payload


def context_payload(context: ContextInput) -> JsonObject:
    """Serialize a context budget. An empty object still enables the server-side check."""
    model = context if isinstance(context, Context) else Context.model_validate(context)
    payload: JsonObject = {}
    if model.max_input_tokens is not None:
        payload["max_input_tokens"] = model.max_input_tokens
    if model.truncate:
        payload["truncate"] = True
    return payload


def tool_payload(tool: ToolInput) -> JsonObject:
    """Serialize a tool definition."""
    model = tool if isinstance(tool, ToolDefinition) else ToolDefinition.model_validate(tool)
    return {"name": model.name, "description": model.description, "parameters": dict(model.parameters)}


def prompt_message_payload(message: PromptMessageInput) -> JsonObject:
    """Serialize one stored prompt message."""
    model = message if isinstance(message, PromptMessage) else PromptMessage.model_validate(message)
    return {"role": model.role.value, "content": model.content}


def build_response_payload(
    *,
    model: str,
    messages: Sequence[MessageInput] | None,
    prompt: PromptInput | None,
    context: ContextInput | None,
    temperature: float | None,
    max_output_tokens: int | None,
    tools: Sequence[ToolInput] | None,
    cache: bool,
    stream: bool,
) -> JsonObject:
    """Build a POST /v1/responses body. Exactly one of messages or prompt is sent."""
    if (messages is None) == (prompt is None):
        raise ValueError("provide exactly one of messages or prompt")
    if messages is not None and len(messages) == 0:
        raise ValueError("messages must not be empty")
    body: JsonObject = {"model": model}
    if messages is not None:
        body["messages"] = [message_payload(item) for item in messages]
    else:
        assert prompt is not None
        body["prompt"] = prompt_reference_payload(prompt)
    if context is not None:
        body["context"] = context_payload(context)
    if temperature is not None:
        body["temperature"] = temperature
    if max_output_tokens is not None:
        body["max_output_tokens"] = max_output_tokens
    if tools:
        body["tools"] = [tool_payload(item) for item in tools]
    if cache:
        body["cache"] = True
    if stream:
        body["stream"] = True
    return body


def build_prompt_payload(*, name: str, messages: Sequence[PromptMessageInput]) -> JsonObject:
    """Build a POST /v1/prompts body."""
    if len(messages) == 0:
        raise ValueError("messages must not be empty")
    return {"name": name, "messages": [prompt_message_payload(item) for item in messages]}

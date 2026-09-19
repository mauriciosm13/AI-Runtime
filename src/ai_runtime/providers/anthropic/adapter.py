"""Anthropic Messages API adapter implementing ModelProvider."""

from collections.abc import AsyncIterator
from typing import Any
import json
import httpx
from ai_runtime.domain.generation import GenerationDelta, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import Message, MessageRole, TokenUsage, ToolCall
from ai_runtime.providers.anthropic.errors import AnthropicProviderError
from ai_runtime.providers.sse import iter_sse_events

_DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_OUTPUT_TOKENS = 1024


def _split_system_messages(request: GenerationRequest) -> tuple[str | None, list[Message]]:
    """Extract system messages for Anthropic's ``system`` field; return the rest."""
    system_parts: list[str] = []
    conversation: list[Message] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            system_parts.append(message.content)
        else:
            conversation.append(message)
    system = "\n\n".join(system_parts) if system_parts else None
    return system, conversation


def _to_anthropic_body(request: GenerationRequest, *, stream: bool = False) -> dict[str, Any]:
    """Map a GenerationRequest to an Anthropic Messages JSON body."""
    system, conversation = _split_system_messages(request)
    if not conversation:
        raise AnthropicProviderError("messages must contain at least one non-system message")
    max_tokens = request.max_output_tokens if request.max_output_tokens is not None else _DEFAULT_MAX_OUTPUT_TOKENS
    body: dict[str, Any] = {
        "model": request.model,
        "max_tokens": max_tokens,
        "messages": [_to_anthropic_message(message) for message in conversation],
    }
    if system is not None:
        body["system"] = system
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.tools:
        body["tools"] = [{"name": tool.name, "description": tool.description, "input_schema": tool.parameters} for tool in request.tools]
    if stream:
        body["stream"] = True
    return body


def _to_anthropic_message(message: Message) -> dict[str, Any]:
    """Map one domain message to an Anthropic Messages item."""
    if message.role is MessageRole.TOOL:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            ],
        }
    if message.role is MessageRole.ASSISTANT and message.tool_calls:
        blocks: list[dict[str, Any]] = []
        if message.content.strip():
            blocks.append({"type": "text", "text": message.content})
        for call in message.tool_calls:
            try:
                tool_input = json.loads(call.arguments)
            except json.JSONDecodeError as err:
                raise AnthropicProviderError("tool call arguments must be valid JSON") from err
            if not isinstance(tool_input, dict):
                raise AnthropicProviderError("tool call arguments must be a JSON object")
            blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": tool_input})
        return {"role": "assistant", "content": blocks}
    return {"role": message.role.value, "content": message.content}


def _usage_from_anthropic_payload(usage_payload: object) -> TokenUsage | None:
    """Parse Anthropic usage when both token counts are present and valid."""
    if not isinstance(usage_payload, dict):
        return None
    input_tokens = usage_payload.get("input_tokens")
    output_tokens = usage_payload.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise AnthropicProviderError("Anthropic response usage is invalid")
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _text_from_content_blocks(content_blocks: object) -> str:
    """Join Anthropic text blocks into a single assistant string."""
    if not isinstance(content_blocks, list) or not content_blocks:
        raise AnthropicProviderError("Anthropic response is missing content")
    parts: list[str] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            raise AnthropicProviderError("Anthropic response content block is invalid")
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if not isinstance(text, str):
            raise AnthropicProviderError("Anthropic response text block is missing text")
        parts.append(text)
    return "".join(parts)


def _tool_calls_from_anthropic(content_blocks: object) -> tuple[ToolCall, ...]:
    """Parse Anthropic tool_use blocks into domain ToolCall values."""
    if not isinstance(content_blocks, list):
        return ()
    calls: list[ToolCall] = []
    for block in content_blocks:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        call_id = block.get("id")
        name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(tool_input, dict):
            raise AnthropicProviderError("Anthropic response tool_use block is invalid")
        calls.append(ToolCall(id=call_id, name=name, arguments=json.dumps(tool_input, separators=(",", ":"), ensure_ascii=True)))
    return tuple(calls)


def _from_anthropic_payload(
    payload: dict[str, Any],
    request: GenerationRequest,
) -> GenerationResponse:
    """Map an Anthropic Messages JSON payload to GenerationResponse."""
    try:
        response_id = payload.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            raise AnthropicProviderError("Anthropic response is missing a valid id")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        content_blocks = payload.get("content")
        content = _text_from_content_blocks(content_blocks)
        tool_calls = _tool_calls_from_anthropic(content_blocks)
        if not content.strip() and not tool_calls:
            raise AnthropicProviderError("Anthropic response is missing text content")
        usage = _usage_from_anthropic_payload(payload.get("usage"))
        return GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls),
            usage=usage,
        )
    except AnthropicProviderError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise AnthropicProviderError("Anthropic response payload is malformed") from err


class AnthropicModelProvider:
    """ModelProvider adapter for Anthropic Messages over HTTP."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = _DEFAULT_ANTHROPIC_BASE_URL,
    ) -> None:
        if not api_key.strip():
            raise AnthropicProviderError("api_key must not be empty or blank")
        if not base_url.strip():
            raise AnthropicProviderError("base_url must not be empty or blank")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Invoke Anthropic Messages and return a GenerationResponse."""
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        body = _to_anthropic_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise AnthropicProviderError.transient("Anthropic HTTP request failed") from err
        if response.status_code >= 400:
            raise AnthropicProviderError.from_http_status(
                f"Anthropic HTTP request failed with status {response.status_code}",
                response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise AnthropicProviderError("Anthropic response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise AnthropicProviderError("Anthropic response body must be a JSON object")
        return _from_anthropic_payload(payload, request)

    async def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationDelta | GenerationResponse]:
        """Invoke Anthropic Messages streaming and yield domain events."""
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        body = _to_anthropic_body(request, stream=True)
        try:
            async with self._http_client.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise AnthropicProviderError.from_http_status(
                        f"Anthropic HTTP request failed with status {response.status_code}",
                        response.status_code,
                    )
                response_id = ""
                model = request.model
                assembled: list[str] = []
                input_tokens: int | None = None
                output_tokens: int | None = None
                async for event_name, data in iter_sse_events(response):
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as err:
                        raise AnthropicProviderError("Anthropic stream chunk is not valid JSON") from err
                    if not isinstance(payload, dict):
                        raise AnthropicProviderError("Anthropic stream chunk must be a JSON object")
                    event_type = event_name or payload.get("type")
                    if event_type == "message_start":
                        message = payload.get("message")
                        if not isinstance(message, dict):
                            raise AnthropicProviderError("Anthropic stream message_start is invalid")
                        chunk_id = message.get("id")
                        if isinstance(chunk_id, str) and chunk_id.strip():
                            response_id = chunk_id
                        chunk_model = message.get("model")
                        if isinstance(chunk_model, str) and chunk_model.strip():
                            model = chunk_model
                        usage_payload = message.get("usage")
                        if isinstance(usage_payload, dict):
                            raw_input = usage_payload.get("input_tokens")
                            if isinstance(raw_input, int):
                                input_tokens = raw_input
                    elif event_type == "content_block_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, dict) and delta.get("type") == "text_delta":
                            text = delta.get("text")
                            if isinstance(text, str) and text:
                                if not response_id.strip():
                                    raise AnthropicProviderError("Anthropic stream is missing a valid id")
                                assembled.append(text)
                                yield GenerationDelta(id=response_id, model=model, content=text)
                    elif event_type == "message_delta":
                        usage_payload = payload.get("usage")
                        if isinstance(usage_payload, dict):
                            raw_output = usage_payload.get("output_tokens")
                            if isinstance(raw_output, int):
                                output_tokens = raw_output
        except AnthropicProviderError:
            raise
        except httpx.HTTPError as err:
            raise AnthropicProviderError.transient("Anthropic HTTP request failed") from err
        if not response_id.strip():
            raise AnthropicProviderError("Anthropic stream is missing a valid id")
        usage = None
        if input_tokens is not None and output_tokens is not None:
            usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        elif input_tokens is not None or output_tokens is not None:
            raise AnthropicProviderError("Anthropic response usage is invalid")
        yield GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content="".join(assembled)),
            usage=usage,
        )

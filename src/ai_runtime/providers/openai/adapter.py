"""OpenAI Chat Completions adapter implementing ModelProvider."""

from collections.abc import AsyncIterator
from typing import Any
import json
import httpx
from ai_runtime.domain.generation import GenerationDelta, GenerationRequest, GenerationResponse
from ai_runtime.domain.generation import GenerationStreamEvent, Message, MessageRole, TokenUsage, ToolCall
from ai_runtime.providers.openai.errors import OpenAIProviderError
from ai_runtime.providers.sse import iter_sse_events

_DEFAULT_OPENAI_API_URL = "https://api.openai.com/v1"


def _to_openai_message(message: Message) -> dict[str, Any]:
    """Map one domain message to an OpenAI Chat Completions message."""
    if message.role is MessageRole.TOOL:
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["content"] = message.content if message.content.strip() else None
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return payload


def _to_openai_body(request: GenerationRequest, *, stream: bool = False) -> dict[str, Any]:
    """Map a GenerationRequest to an OpenAI Chat Completions JSON body."""
    body: dict[str, Any] = {
        "model": request.model,
        "messages": [_to_openai_message(message) for message in request.messages],
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.max_output_tokens is not None:
        body["max_tokens"] = request.max_output_tokens
    if request.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in request.tools
        ]
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


def _tool_calls_from_openai(raw_calls: object) -> tuple[ToolCall, ...]:
    """Parse OpenAI tool_calls into domain ToolCall values."""
    if raw_calls is None:
        return ()
    if not isinstance(raw_calls, list):
        raise OpenAIProviderError("OpenAI response tool_calls is invalid")
    calls: list[ToolCall] = []
    for item in raw_calls:
        if not isinstance(item, dict):
            raise OpenAIProviderError("OpenAI response tool_calls is invalid")
        call_id = item.get("id")
        function = item.get("function")
        if not isinstance(call_id, str) or not call_id.strip() or not isinstance(function, dict):
            raise OpenAIProviderError("OpenAI response tool_calls is invalid")
        name = function.get("name")
        arguments = function.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, str):
            raise OpenAIProviderError("OpenAI response tool_calls is invalid")
        calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
    return tuple(calls)


def _usage_from_openai_payload(usage_payload: object) -> TokenUsage | None:
    """Parse OpenAI usage when both token counts are present and valid."""
    if not isinstance(usage_payload, dict):
        return None
    prompt_tokens = usage_payload.get("prompt_tokens")
    completion_tokens = usage_payload.get("completion_tokens")
    if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
        raise OpenAIProviderError("OpenAI response usage is invalid")
    return TokenUsage(input_tokens=prompt_tokens, output_tokens=completion_tokens)


def _from_openai_payload(
    payload: dict[str, Any],
    request: GenerationRequest,
) -> GenerationResponse:
    """Map an OpenAI Chat Completions JSON payload to GenerationResponse."""
    try:
        response_id = payload["id"]
        if not isinstance(response_id, str) or not response_id.strip():
            raise OpenAIProviderError("OpenAI response is missing a valid id")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            model = request.model
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenAIProviderError("OpenAI response is missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise OpenAIProviderError("OpenAI response choice is invalid")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise OpenAIProviderError("OpenAI response choice is missing message")
        content = message.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise OpenAIProviderError("OpenAI response message is missing content")
        tool_calls = _tool_calls_from_openai(message.get("tool_calls"))
        if not content.strip() and not tool_calls:
            raise OpenAIProviderError("OpenAI response message is missing content")
        usage = _usage_from_openai_payload(payload.get("usage"))
        return GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls),
            usage=usage,
        )
    except OpenAIProviderError:
        raise
    except (KeyError, TypeError, ValueError) as err:
        raise OpenAIProviderError("OpenAI response payload is malformed") from err


class OpenAIModelProvider:
    """ModelProvider adapter for OpenAI Chat Completions over HTTP."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        base_url: str = _DEFAULT_OPENAI_API_URL,
    ) -> None:
        if not api_key.strip():
            raise OpenAIProviderError("api_key must not be empty or blank")
        if not base_url.strip():
            raise OpenAIProviderError("base_url must not be empty or blank")
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Invoke OpenAI Chat Completions and return a GenerationResponse."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = _to_openai_body(request)
        try:
            response = await self._http_client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise OpenAIProviderError.transient("OpenAI HTTP request failed") from err
        if response.status_code >= 400:
            raise OpenAIProviderError.from_http_status(
                f"OpenAI HTTP request failed with status {response.status_code}",
                response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise OpenAIProviderError("OpenAI response body is not valid JSON") from err
        if not isinstance(payload, dict):
            raise OpenAIProviderError("OpenAI response body must be a JSON object")
        return _from_openai_payload(payload, request)

    async def stream(self, request: GenerationRequest) -> AsyncIterator[GenerationStreamEvent]:
        """Invoke OpenAI Chat Completions streaming and yield domain events."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = _to_openai_body(request, stream=True)
        try:
            async with self._http_client.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise OpenAIProviderError.from_http_status(
                        f"OpenAI HTTP request failed with status {response.status_code}",
                        response.status_code,
                    )
                response_id = ""
                model = request.model
                assembled: list[str] = []
                usage: TokenUsage | None = None
                async for _event_name, data in iter_sse_events(response):
                    if data == "[DONE]":
                        break
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as err:
                        raise OpenAIProviderError("OpenAI stream chunk is not valid JSON") from err
                    if not isinstance(payload, dict):
                        raise OpenAIProviderError("OpenAI stream chunk must be a JSON object")
                    chunk_id = payload.get("id")
                    if isinstance(chunk_id, str) and chunk_id.strip():
                        response_id = chunk_id
                    chunk_model = payload.get("model")
                    if isinstance(chunk_model, str) and chunk_model.strip():
                        model = chunk_model
                    choices = payload.get("choices")
                    if isinstance(choices, list) and choices:
                        first_choice = choices[0]
                        if not isinstance(first_choice, dict):
                            raise OpenAIProviderError("OpenAI stream choice is invalid")
                        delta = first_choice.get("delta")
                        if isinstance(delta, dict):
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                if not response_id.strip():
                                    raise OpenAIProviderError("OpenAI stream is missing a valid id")
                                assembled.append(content)
                                yield GenerationDelta(id=response_id, model=model, content=content)
                    if "usage" in payload:
                        usage = _usage_from_openai_payload(payload.get("usage"))
        except OpenAIProviderError:
            raise
        except httpx.HTTPError as err:
            raise OpenAIProviderError.transient("OpenAI HTTP request failed") from err
        if not response_id.strip():
            raise OpenAIProviderError("OpenAI stream is missing a valid id")
        yield GenerationResponse(
            id=response_id,
            model=model,
            output=Message(role=MessageRole.ASSISTANT, content="".join(assembled)),
            usage=usage,
        )

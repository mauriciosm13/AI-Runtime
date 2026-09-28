"""Sync and async clients for the AI Runtime HTTP API."""

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast
from urllib.parse import quote
import httpx
from pydantic import ValidationError
from ai_runtime_sdk._payload import (
    ContextInput,
    MessageInput,
    PromptInput,
    PromptMessageInput,
    ToolInput,
    build_headers,
    build_prompt_payload,
    build_response_payload,
)
from ai_runtime_sdk._sse import SseParser, parse_stream_frame
from ai_runtime_sdk.errors import AIRuntimeConnectionError, AIRuntimeError, error_from_body
from ai_runtime_sdk.models import PromptList, PromptVersion, Response, ResponseDelta

_JSON = dict[str, Any]


def _require_text(value: str, field_name: str) -> str:
    """Reject a blank credential or base URL."""
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped


def _request_id_header(response: httpx.Response) -> str | None:
    """Read the correlation id from the response, when the server sent one."""
    request_id = response.headers.get("x-request-id")
    return request_id or None


def _raise_for_status(response: httpx.Response) -> None:
    """Raise AIRuntimeError when the response is an HTTP error."""
    if response.status_code < 400:
        return
    request_id = _request_id_header(response)
    retry_after = response.headers.get("retry-after")
    try:
        payload: Any = response.json()
    except json.JSONDecodeError:
        payload = None
    fallback = response.text.strip() or f"HTTP {response.status_code}"
    raise error_from_body(
        payload,
        status_code=response.status_code,
        request_id=request_id,
        retry_after=retry_after,
        fallback_message=fallback,
    )


def _require_event_stream(response: httpx.Response) -> None:
    """Reject a 2xx body that is not the documented SSE stream."""
    if "text/event-stream" in response.headers.get("content-type", ""):
        return
    raise AIRuntimeError(
        code="invalid_response",
        message="Expected a server-sent event stream.",
        status_code=response.status_code,
        request_id=_request_id_header(response),
    )


def _json_object(response: httpx.Response) -> _JSON:
    """Decode a successful JSON object."""
    request_id = _request_id_header(response)
    try:
        payload: Any = response.json()
    except json.JSONDecodeError as err:
        raise AIRuntimeError(
            code="invalid_response",
            message="Response was not JSON.",
            status_code=response.status_code,
            request_id=request_id,
        ) from err
    if not isinstance(payload, dict):
        raise AIRuntimeError(
            code="invalid_response",
            message="Response was not a JSON object.",
            status_code=response.status_code,
            request_id=request_id,
        )
    return payload


def _stamp_request_id[T: Response | ResponseDelta | PromptVersion | PromptList](model: T, request_id: str | None) -> T:
    """Attach the HTTP correlation id without treating it as part of the JSON body."""
    if request_id is None:
        return model
    return cast(T, model.model_copy(update={"request_id": request_id}))


def _parse_model[T: Response | PromptVersion | PromptList](model_type: type[T], response: httpx.Response) -> T:
    """Validate a successful JSON body and attach ``X-Request-ID``."""
    payload = _json_object(response)
    request_id = _request_id_header(response)
    try:
        parsed = cast(T, model_type.model_validate(payload))
    except ValidationError as err:
        raise AIRuntimeError(
            code="invalid_response",
            message="Response did not match the API contract.",
            status_code=response.status_code,
            request_id=request_id,
        ) from err
    return _stamp_request_id(parsed, request_id)


def _iter_frames(lines: Iterator[str]) -> Iterator[tuple[str, str]]:
    """Yield completed SSE frames from a line iterator."""
    parser = SseParser()
    for line in lines:
        frame = parser.feed(line)
        if frame is not None:
            yield frame
    trailing = parser.finish()
    if trailing is not None:
        yield trailing


async def _aiter_frames(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, str]]:
    """Yield completed SSE frames from an async line iterator."""
    parser = SseParser()
    async for line in lines:
        frame = parser.feed(line)
        if frame is not None:
            yield frame
    trailing = parser.finish()
    if trailing is not None:
        yield trailing


def _prompt_path(name: str) -> str:
    """Path for one named prompt. The name is escaped so it stays in one segment."""
    return "/v1/prompts/" + quote(name, safe="")


class Responses:
    """POST /v1/responses."""

    def __init__(self, client: "AIRuntime") -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: Sequence[MessageInput] | None = None,
        prompt: PromptInput | None = None,
        context: ContextInput | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: Sequence[ToolInput] | None = None,
        cache: bool = False,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> Response:
        """Create a non-streaming model response."""
        body = build_response_payload(
            model=model,
            messages=messages,
            prompt=prompt,
            context=context,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            cache=cache,
            stream=False,
        )
        response = self._client._send(
            "POST",
            "/v1/responses",
            json_body=body,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _parse_model(Response, response)

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[MessageInput] | None = None,
        prompt: PromptInput | None = None,
        context: ContextInput | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: Sequence[ToolInput] | None = None,
        request_id: str | None = None,
    ) -> Iterator[ResponseDelta | Response]:
        """Yield text deltas and then the completed response.

        A ``response.error`` event, or a JSON error before the stream starts, raises
        ``AIRuntimeError``. Idempotency and response cache are not available on this call.
        """
        body = build_response_payload(
            model=model,
            messages=messages,
            prompt=prompt,
            context=context,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            cache=False,
            stream=True,
        )
        try:
            with self._client._http.stream(
                "POST",
                self._client._url("/v1/responses"),
                json=body,
                headers=self._client._headers(request_id=request_id),
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    _raise_for_status(response)
                _require_event_stream(response)
                request_header_id = _request_id_header(response)
                for event, data in _iter_frames(response.iter_lines()):
                    yield _stamp_request_id(parse_stream_frame(event, data, request_id=request_header_id), request_header_id)
        except httpx.HTTPError as err:
            raise AIRuntimeConnectionError("Could not reach AI Runtime.") from err


class Prompts:
    """POST /v1/prompts and GET /v1/prompts/{name}."""

    def __init__(self, client: "AIRuntime") -> None:
        self._client = client

    def create(
        self,
        *,
        name: str,
        messages: Sequence[PromptMessageInput],
        request_id: str | None = None,
    ) -> PromptVersion:
        """Create the next immutable version of a named prompt."""
        response = self._client._send(
            "POST",
            "/v1/prompts",
            json_body=build_prompt_payload(name=name, messages=messages),
            request_id=request_id,
        )
        return _parse_model(PromptVersion, response)

    def list(self, name: str, *, request_id: str | None = None) -> PromptList:
        """List every version of a named prompt."""
        response = self._client._send("GET", _prompt_path(name), request_id=request_id)
        return _parse_model(PromptList, response)


class AIRuntime:
    """Synchronous client. Use it as a context manager so the HTTP connection closes."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = _require_text(api_key, "api_key")
        self._base_url = _require_text(base_url, "base_url").rstrip("/")
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.Client(timeout=timeout)
        self.responses = Responses(self)
        self.prompts = Prompts(self)

    def __repr__(self) -> str:
        return f"AIRuntime(base_url={self._base_url!r})"

    def close(self) -> None:
        """Close the HTTP client when this instance created it."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "AIRuntime":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _headers(self, *, idempotency_key: str | None = None, request_id: str | None = None) -> dict[str, str]:
        return build_headers(self._api_key, idempotency_key=idempotency_key, request_id=request_id)

    def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: _JSON | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> httpx.Response:
        try:
            response = self._http.request(
                method,
                self._url(path),
                json=json_body,
                headers=self._headers(idempotency_key=idempotency_key, request_id=request_id),
            )
        except httpx.HTTPError as err:
            raise AIRuntimeConnectionError("Could not reach AI Runtime.") from err
        _raise_for_status(response)
        return response


class AsyncResponses:
    """Async POST /v1/responses."""

    def __init__(self, client: "AsyncAIRuntime") -> None:
        self._client = client

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[MessageInput] | None = None,
        prompt: PromptInput | None = None,
        context: ContextInput | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: Sequence[ToolInput] | None = None,
        cache: bool = False,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> Response:
        """Create a non-streaming model response."""
        body = build_response_payload(
            model=model,
            messages=messages,
            prompt=prompt,
            context=context,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            cache=cache,
            stream=False,
        )
        response = await self._client._send(
            "POST",
            "/v1/responses",
            json_body=body,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _parse_model(Response, response)

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[MessageInput] | None = None,
        prompt: PromptInput | None = None,
        context: ContextInput | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        tools: Sequence[ToolInput] | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[ResponseDelta | Response]:
        """Yield text deltas and then the completed response.

        A ``response.error`` event, or a JSON error before the stream starts, raises
        ``AIRuntimeError``. Idempotency and response cache are not available on this call.
        """
        body = build_response_payload(
            model=model,
            messages=messages,
            prompt=prompt,
            context=context,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=tools,
            cache=False,
            stream=True,
        )
        try:
            async with self._client._http.stream(
                "POST",
                self._client._url("/v1/responses"),
                json=body,
                headers=self._client._headers(request_id=request_id),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    _raise_for_status(response)
                _require_event_stream(response)
                request_header_id = _request_id_header(response)
                async for event, data in _aiter_frames(response.aiter_lines()):
                    yielded = parse_stream_frame(event, data, request_id=request_header_id)
                    yield _stamp_request_id(yielded, request_header_id)
        except httpx.HTTPError as err:
            raise AIRuntimeConnectionError("Could not reach AI Runtime.") from err


class AsyncPrompts:
    """Async prompt routes."""

    def __init__(self, client: "AsyncAIRuntime") -> None:
        self._client = client

    async def create(
        self,
        *,
        name: str,
        messages: Sequence[PromptMessageInput],
        request_id: str | None = None,
    ) -> PromptVersion:
        """Create the next immutable version of a named prompt."""
        response = await self._client._send(
            "POST",
            "/v1/prompts",
            json_body=build_prompt_payload(name=name, messages=messages),
            request_id=request_id,
        )
        return _parse_model(PromptVersion, response)

    async def list(self, name: str, *, request_id: str | None = None) -> PromptList:
        """List every version of a named prompt."""
        response = await self._client._send("GET", _prompt_path(name), request_id=request_id)
        return _parse_model(PromptList, response)


class AsyncAIRuntime:
    """Asynchronous client. Use it as an async context manager so the HTTP connection closes."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = _require_text(api_key, "api_key")
        self._base_url = _require_text(base_url, "base_url").rstrip("/")
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.AsyncClient(timeout=timeout)
        self.responses = AsyncResponses(self)
        self.prompts = AsyncPrompts(self)

    def __repr__(self) -> str:
        return f"AsyncAIRuntime(base_url={self._base_url!r})"

    async def aclose(self) -> None:
        """Close the HTTP client when this instance created it."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncAIRuntime":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _headers(self, *, idempotency_key: str | None = None, request_id: str | None = None) -> dict[str, str]:
        return build_headers(self._api_key, idempotency_key=idempotency_key, request_id=request_id)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: _JSON | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method,
                self._url(path),
                json=json_body,
                headers=self._headers(idempotency_key=idempotency_key, request_id=request_id),
            )
        except httpx.HTTPError as err:
            raise AIRuntimeConnectionError("Could not reach AI Runtime.") from err
        _raise_for_status(response)
        return response

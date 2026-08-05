"""Request correlation middleware: request_id resolution, headers, and structured logs."""

import logging
import re
import time
import uuid
from collections.abc import MutableMapping
from typing import Any
from fastapi import FastAPI, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from ai_runtime.telemetry.logging import REQUEST_LOGGER_NAME

REQUEST_ID_HEADER = "X-Request-ID"
SERVER_ID_PREFIX = "req_"
_VALID_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_request_logger = logging.getLogger(REQUEST_LOGGER_NAME)


def generate_request_id() -> str:
    """Return a new server-generated correlation identifier."""
    return f"{SERVER_ID_PREFIX}{uuid.uuid4()}"


def resolve_request_id(header: str | None) -> str:
    """Accept a client-provided request id or generate a new one when invalid."""
    if header is not None:
        candidate = header.strip()
        if candidate and _VALID_CLIENT_REQUEST_ID.fullmatch(candidate):
            return candidate
    return generate_request_id()


def get_request_id(request: Request) -> str | None:
    """Return the correlation identifier stored on the request, if present."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return None


def _header_value(scope: Scope, name: bytes) -> str | None:
    """Return a decoded request header value when present."""
    for header_name, header_value in scope.get("headers", ()):
        if header_name.lower() == name:
            decoded: str = header_value.decode("latin-1")
            return decoded
    return None


class RequestContextMiddleware:
    """ASGI middleware for request correlation and structured request logging."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(_header_value(scope, b"x-request-id"))
        state: MutableMapping[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        method = scope["method"]
        path = scope["path"]
        started_at = time.perf_counter()
        status_code = 500
        completed_logged = False

        _request_logger.info(
            "request_started",
            extra={"request_id": request_id, "method": method, "path": path},
        )

        def log_request_completed() -> None:
            nonlocal completed_logged
            if completed_logged:
                return
            completed_logged = True
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            _request_logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"x-request-id" for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                log_request_completed()

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            log_request_completed()
            raise


def register_request_context_middleware(app: FastAPI) -> None:
    """Attach request correlation and structured request logging to the application."""
    app.add_middleware(RequestContextMiddleware)

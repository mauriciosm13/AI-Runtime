"""Structured JSON logging configuration for AI Runtime."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

REQUEST_LOGGER_NAME = "ai_runtime.request"
_STRUCTURED_FIELDS = frozenset({"request_id", "method", "path", "status_code", "duration_ms"})


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str) -> None:
    """Configure the ai_runtime request logger with JSON output."""
    normalized = level.upper()
    if normalized not in logging.getLevelNamesMapping():
        normalized = "INFO"
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
    request_logger.handlers.clear()
    request_logger.addHandler(handler)
    request_logger.setLevel(normalized)
    request_logger.propagate = False

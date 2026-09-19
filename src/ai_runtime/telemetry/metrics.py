"""In-process counters and summaries rendered as Prometheus text."""

from collections import defaultdict
from ai_runtime.ports.metrics import LabelMap

_HELP = {
    "http_requests_total": "HTTP requests completed.",
    "http_request_duration_seconds": "HTTP request duration in seconds.",
    "generation_requests_total": "Generation attempts by result.",
    "generation_tokens_total": "Tokens reported on successful provider generations.",
}


def _freeze(labels: LabelMap | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    parts = [f'{key}="{value.replace("\\", "\\\\").replace('"', '\\"')}"' for key, value in labels]
    return "{" + ",".join(parts) + "}"


class InProcessMetrics:
    """Thread-unsafe process-local metrics store (asyncio request path)."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._counts: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)

    def increment(self, name: str, labels: LabelMap | None = None, *, amount: float = 1.0) -> None:
        """Add ``amount`` to a named counter."""
        self._counters[(name, _freeze(labels))] += amount

    def observe(self, name: str, value: float, labels: LabelMap | None = None) -> None:
        """Accumulate a summary sample as sum and count."""
        key = (name, _freeze(labels))
        self._sums[key] += value
        self._counts[key] += 1

    def render_prometheus(self) -> str:
        """Return Prometheus 0.0.4 text exposition."""
        lines: list[str] = []
        seen_help: set[str] = set()
        for (name, labels), value in sorted(self._counters.items(), key=lambda item: (item[0][0], item[0][1])):
            if name not in seen_help:
                lines.append(f"# HELP {name} {_HELP.get(name, name)}")
                lines.append(f"# TYPE {name} counter")
                seen_help.add(name)
            lines.append(f"{name}{_format_labels(labels)} {value}")
        seen_summary: set[str] = set()
        for (name, labels), total in sorted(self._sums.items(), key=lambda item: (item[0][0], item[0][1])):
            if name not in seen_summary:
                lines.append(f"# HELP {name} {_HELP.get(name, name)}")
                lines.append(f"# TYPE {name} summary")
                seen_summary.add(name)
            label_text = _format_labels(labels)
            lines.append(f"{name}_sum{label_text} {total}")
            lines.append(f"{name}_count{label_text} {self._counts[(name, labels)]}")
        lines.append("")
        return "\n".join(lines)

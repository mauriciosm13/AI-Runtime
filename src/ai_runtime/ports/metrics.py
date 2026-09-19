"""Port for process-local operational metrics."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

LabelMap = Mapping[str, str]


@runtime_checkable
class Metrics(Protocol):
    """Increment counters and observe numeric samples."""

    def increment(self, name: str, labels: LabelMap | None = None, *, amount: float = 1.0) -> None:
        """Add ``amount`` to a counter identified by name and labels."""
        ...

    def observe(self, name: str, value: float, labels: LabelMap | None = None) -> None:
        """Record a numeric sample (stored as sum and count)."""
        ...

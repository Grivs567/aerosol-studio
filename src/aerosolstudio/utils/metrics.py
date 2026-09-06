"""Disabled-by-default local runtime metrics helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class LocalMetrics:
    """In-memory metrics store for optional debug use.

    This object performs no telemetry and writes nothing unless a caller asks
    for the snapshot and stores it locally.
    """

    enabled: bool = False
    timings: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @contextmanager
    def time_block(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        start = perf_counter()
        try:
            yield
        finally:
            self.timings[name].append(perf_counter() - start)

    def increment(self, name: str, amount: int = 1) -> None:
        if self.enabled:
            self.counters[name] += amount

    def snapshot(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "timings": {k: list(v) for k, v in self.timings.items()},
            "counters": dict(self.counters),
        }

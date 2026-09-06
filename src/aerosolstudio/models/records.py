"""Immutable record types for non-live runtime metadata.

These dataclasses intentionally do not wrap Bokeh objects or the live
``self.instruments`` dictionaries in the application controller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatasetDescriptor:
    """Metadata about a loaded or benchmark dataset."""

    name: str
    path: str | None
    file_format: str
    rows: int | None = None
    columns: int | None = None
    size_bytes: int | None = None


@dataclass(frozen=True)
class FitResultRecord:
    """Serializable fit result point metadata."""

    fit_type: str
    time_ms: float
    diameter_m: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkDescriptor:
    """Metadata for a benchmark run or planned benchmark input."""

    dataset: DatasetDescriptor
    action: str
    expected_metric: str
    notes: str = ""

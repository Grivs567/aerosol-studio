"""Typed structures for passive state metadata.

These types describe serialized/passive records only. They do not replace the
live mutable instrument dictionaries in the canonical app.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class FitPointDict(TypedDict, total=False):
    time: float
    diam: float
    mean: float
    sigma: float
    amplitude: float
    r2: float


class GrowthRateDict(TypedDict, total=False):
    growth_rate_nm_per_hr: float
    r2: float
    source_name: str
    fit_key: str


class PolygonSessionDict(TypedDict, total=False):
    x: list[float]
    y: list[float]
    label: str
    growth_rates: dict[str, GrowthRateDict]


class InstrumentSessionDict(TypedDict, total=False):
    polygons: list[PolygonSessionDict]
    selected_poly: int | None
    var_overlays: list[dict[str, Any]]
    file_format: str
    loaded_path: str


class HasDataMapping(Protocol):
    data: dict[str, Any]

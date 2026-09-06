"""Immutable snapshots for future undo/autosave/session stabilization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aerosolstudio.io.fit_points import restore_fit_points
from aerosolstudio.io.json_utils import json_safe


@dataclass(frozen=True)
class ROIGeometrySnapshot:
    x: tuple[float, ...]
    y: tuple[float, ...]
    label: str = ""


@dataclass(frozen=True)
class GrowthRateSnapshot:
    fit_key: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolygonSnapshot:
    geometry: ROIGeometrySnapshot
    fit_points: dict[str, tuple[dict[str, Any], ...]] = field(default_factory=dict)
    growth_rates: dict[str, GrowthRateSnapshot] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionMetadataSnapshot:
    schema: str
    software: str
    version: str | None = None
    created: str | None = None


def snapshot_roi_geometry(polygon: dict[str, Any]) -> ROIGeometrySnapshot:
    """Create an immutable ROI geometry snapshot from a polygon dictionary."""

    return ROIGeometrySnapshot(
        x=tuple(float(v) for v in polygon.get("x", []) or []),
        y=tuple(float(v) for v in polygon.get("y", []) or []),
        label=str(polygon.get("label", "") or ""),
    )


def snapshot_polygon(polygon: dict[str, Any]) -> PolygonSnapshot:
    """Create an immutable snapshot of polygon geometry, fits, and GR records."""

    fit_points: dict[str, tuple[dict[str, Any], ...]] = {}
    growth_rates: dict[str, GrowthRateSnapshot] = {}
    for key, value in polygon.items():
        if key.startswith("fit_"):
            fit_points[key] = tuple(json_safe(p) for p in restore_fit_points(value))
    for fit_key, values in (polygon.get("growth_rates", {}) or {}).items():
        growth_rates[str(fit_key)] = GrowthRateSnapshot(str(fit_key), json_safe(values))
    return PolygonSnapshot(
        geometry=snapshot_roi_geometry(polygon),
        fit_points=fit_points,
        growth_rates=growth_rates,
    )


def snapshot_session_metadata(meta: dict[str, Any]) -> SessionMetadataSnapshot:
    """Create an immutable session metadata snapshot."""

    return SessionMetadataSnapshot(
        schema=str(meta.get("schema", "")),
        software=str(meta.get("software", "")),
        version=str(meta["version"]) if meta.get("version") is not None else None,
        created=str(meta["created"]) if meta.get("created") is not None else None,
    )

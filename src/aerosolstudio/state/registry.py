"""Passive mutation containment helpers.

These helpers operate on plain dictionaries/lists and return records that make
ownership explicit. They do not mutate Bokeh documents directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aerosolstudio.io.fit_points import restore_fit_points
from aerosolstudio.io.json_utils import json_safe
from aerosolstudio.state.identity import RendererMetadata, polygon_id, tag_renderer_metadata
from aerosolstudio.state.snapshots import snapshot_polygon


@dataclass(frozen=True)
class RegistrationResult:
    identifier: str
    payload: dict[str, Any]


def register_polygon_record(polygon: dict[str, Any]) -> RegistrationResult:
    """Return a passive polygon registration record."""

    identifier = polygon.get("polygon_id") or polygon_id(polygon)
    payload = json_safe({**polygon, "polygon_id": identifier})
    return RegistrationResult(identifier=identifier, payload=payload)


def register_fit_points(polygon_identifier: str, fit_key: str, points: Any) -> RegistrationResult:
    """Return a passive fit-point group registration record."""

    restored = restore_fit_points(points)
    identifier = f"{polygon_identifier}:{fit_key}"
    return RegistrationResult(
        identifier=identifier,
        payload={
            "polygon_id": polygon_identifier,
            "fit_key": fit_key,
            "points": json_safe(restored),
        },
    )


def register_growth_rate(
    polygon_identifier: str, fit_key: str, values: dict[str, Any]
) -> RegistrationResult:
    """Return a passive growth-rate registration record."""

    identifier = f"{polygon_identifier}:{fit_key}:growth"
    return RegistrationResult(
        identifier=identifier,
        payload={
            "polygon_id": polygon_identifier,
            "fit_key": fit_key,
            "growth_rate": json_safe(values),
        },
    )


def register_renderer(
    category: str,
    owner_instrument: str,
    *,
    polygon_identifier: str | None = None,
    fit_key: str | None = None,
) -> RendererMetadata:
    """Return passive renderer metadata for future tagging."""

    return tag_renderer_metadata(
        category,
        owner_instrument,
        polygon_identifier=polygon_identifier,
        fit_key=fit_key,
    )


def session_snapshot_write(polygons: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Return immutable-session-ready polygon snapshot payloads."""

    snapshots = []
    for polygon in polygons:
        snap = snapshot_polygon(polygon)
        snapshots.append(
            {
                "polygon_id": polygon.get("polygon_id") or polygon_id(polygon),
                "x": list(snap.geometry.x),
                "y": list(snap.geometry.y),
                "label": snap.geometry.label,
                "fit_keys": sorted(snap.fit_points),
                "growth_rate_keys": sorted(snap.growth_rates),
            }
        )
    return tuple(snapshots)

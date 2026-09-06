"""Pure helpers for shaping fit-apply payloads.

The canonical app still mutates Bokeh sources and renderers.  These functions
only prepare plain dictionaries and copied state used by that apply phase.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from aerosolstudio.utils.time import time_value_to_ms


def normalize_peak_record(point: Mapping[str, Any]) -> dict[str, Any]:
    """Return a plain mutable peak record."""

    return dict(point)


def fit_glyph_payload(
    polygons: Sequence[Mapping[str, Any]],
    storage_key: str,
) -> dict[str, list[Any]]:
    """Build the source payload for fit marker glyphs."""

    t: list[Any] = []
    d: list[Any] = []
    for polygon in polygons:
        for point in polygon.get(storage_key, []):
            t.append(point["time"])
            d.append(point["diam"])
    return {"t": t, "d": d}


def empty_distribution_payload() -> dict[str, list[Any]]:
    """Return the cleared distribution-marker source payload."""

    return {"x": [], "y": [], "color": []}


def undo_delete_snapshot(
    polygon_idx: int,
    fit_key: str,
    fit_storage_key: str,
    before_points: Sequence[Mapping[str, Any]],
    before_growth_rates: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the undo-stack record for fit-point deletion."""

    return {
        "action": "delete_fit_points",
        "polygon_idx": polygon_idx,
        "fit_key": fit_key,
        "fit_storage_key": fit_storage_key,
        "before_points": copy.deepcopy(list(before_points)),
        "before_growth_rates": copy.deepcopy(dict(before_growth_rates)),
    }


def split_fit_points_for_delete(
    points: Sequence[Mapping[str, Any]],
    selected_pairs: Sequence[tuple[float, float]],
) -> tuple[list[Mapping[str, Any]], int]:
    """Split fit points into kept points and deleted count for selected glyphs."""

    kept: list[Mapping[str, Any]] = []
    deleted = 0
    for point in points:
        try:
            point_t = time_value_to_ms(point["time"])
            point_d = float(point["diam"])
        except (KeyError, TypeError, ValueError):
            kept.append(point)
            continue

        matches_selected = any(
            np.isclose(point_t, sel_t, rtol=0, atol=1e-6)
            and np.isclose(point_d, sel_d, rtol=1e-9, atol=1e-18)
            for sel_t, sel_d in selected_pairs
        )
        if matches_selected:
            deleted += 1
        else:
            kept.append(point)
    return kept, deleted


def shift_renderer_index_keys(
    renderer_map: Mapping[Any, Any],
    deleted_idx: int,
) -> dict[Any, Any]:
    """Return renderer/source maps with polygon index keys shifted after delete."""

    shifted: dict[Any, Any] = {}
    for key, value in renderer_map.items():
        if isinstance(key, tuple) and key[0] > deleted_idx:
            shifted[(key[0] - 1, key[1])] = value
        else:
            shifted[key] = value
    return shifted

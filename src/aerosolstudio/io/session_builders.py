"""Pure builders for session payload fragments.

The canonical app still owns file dialogs, widget reads, Bokeh notifications,
and renderer refreshes.  These helpers only shape plain dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aerosolstudio.io.fit_points import restore_fit_points
from aerosolstudio.io.json_utils import json_safe

FitTypeMetadata = Mapping[str, Mapping[str, Any]]


def fit_storage_keys(fit_types: FitTypeMetadata) -> tuple[str, ...]:
    """Return the polygon storage keys used by the fit registry."""

    return tuple(str(props["fit_key"]) for props in fit_types.values())


def build_polygon_export(
    polygon: Mapping[str, Any],
    fit_types: FitTypeMetadata,
) -> dict[str, Any]:
    """Build the saved-session polygon shape from plain polygon state."""

    poly_out: dict[str, Any] = {
        "x": polygon.get("x", []),
        "y": polygon.get("y", []),
        "label": polygon.get("label", ""),
    }
    for storage_key in fit_storage_keys(fit_types):
        poly_out[storage_key] = restore_fit_points(polygon.get(storage_key, []))
    poly_out["growth_rates"] = polygon.get("growth_rates", {})
    return poly_out


def normalize_overlay_export(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Return the persisted overlay record after widget values have been read."""

    return {
        "line_id": overlay.get("line_id"),
        "method": overlay.get("method"),
        "dmin_nm": overlay.get("dmin_nm"),
        "dmax_nm": overlay.get("dmax_nm"),
        "color": overlay.get("color"),
        "style": overlay.get("style"),
        "thickness": overlay.get("thickness"),
        "visible": overlay.get("visible"),
        "ymin": overlay.get("ymin"),
        "ymax": overlay.get("ymax"),
    }


def build_instrument_export(
    instrument: Mapping[str, Any],
    fit_types: FitTypeMetadata,
    *,
    var_overlays: Sequence[Mapping[str, Any]] | None = None,
    loaded_path: str = "",
) -> dict[str, Any]:
    """Build the saved-session instrument shape from plain state."""

    return {
        "polygons": [
            build_polygon_export(polygon, fit_types)
            for polygon in instrument.get("polygons", [])
            if isinstance(polygon, Mapping)
        ],
        "selected_poly": instrument.get("selected_poly"),
        "var_overlays": [
            normalize_overlay_export(overlay)
            for overlay in (var_overlays or [])
            if isinstance(overlay, Mapping)
        ],
        "file_format": instrument.get("type"),
        "loaded_path": loaded_path,
    }


def restore_polygon_session(
    polygon_state: Mapping[str, Any],
    fit_types: FitTypeMetadata,
) -> dict[str, Any] | None:
    """Restore a saved polygon record into the current plain polygon shape."""

    if "x" not in polygon_state or "y" not in polygon_state:
        return None

    xs = polygon_state.get("x", [])
    ys = polygon_state.get("y", [])
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) < 3 or len(ys) < 3:
        return None

    polygon: dict[str, Any] = {
        "x": [float(v) for v in xs],
        "y": [float(v) for v in ys],
        "label": polygon_state.get("label", ""),
    }
    for storage_key in fit_storage_keys(fit_types):
        polygon[storage_key] = restore_fit_points(polygon_state.get(storage_key, []))
    polygon["growth_rates"] = polygon_state.get("growth_rates", {})
    return polygon


def json_safe_payload(payload: Any) -> Any:
    """Convert a session payload to strict JSON-safe values."""

    return json_safe(payload)

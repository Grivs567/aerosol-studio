"""Disabled-by-default observability helpers for runtime audits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InstrumentRuntimeSummary:
    name: str
    polygon_count: int
    renderer_count: int
    fit_line_count: int
    undo_depth: int
    selected_polygon: int | None
    dataframe_rows: int | None = None
    dataframe_columns: int | None = None
    dataframe_memory_bytes: int | None = None


def summarize_instrument(name: str, inst: dict[str, Any]) -> InstrumentRuntimeSummary:
    """Return a compact summary of live instrument state without mutation."""

    fig = inst.get("fig")
    renderers = getattr(fig, "renderers", []) if fig is not None else []
    df = inst.get("df")
    rows = getattr(df, "shape", (None, None))[0] if df is not None else None
    columns = getattr(df, "shape", (None, None))[1] if df is not None else None
    memory = None
    if df is not None:
        memory_usage = getattr(df, "memory_usage", None)
        if callable(memory_usage):
            try:
                memory = int(memory_usage(deep=True).sum())
            except Exception:
                memory = None
    return InstrumentRuntimeSummary(
        name=name,
        polygon_count=len(inst.get("polygons", []) or []),
        renderer_count=len(renderers),
        fit_line_count=len(inst.get("fit_line_renderers", {}) or {}),
        undo_depth=len(inst.get("undo_stack", []) or []),
        selected_polygon=inst.get("selected_poly"),
        dataframe_rows=rows,
        dataframe_columns=columns,
        dataframe_memory_bytes=memory,
    )


def summarize_app_state(instruments: dict[str, dict[str, Any]]) -> list[InstrumentRuntimeSummary]:
    """Return summaries for all instruments."""

    return [summarize_instrument(name, inst) for name, inst in instruments.items()]


def renderer_count_by_name(instruments: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Return figure renderer counts by instrument name."""

    return {summary.name: summary.renderer_count for summary in summarize_app_state(instruments)}


def session_integrity_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, mutation-free summary of a session payload."""

    instruments = payload.get("instruments", {}) if isinstance(payload, dict) else {}
    if not isinstance(instruments, dict):
        return {"instrument_count": 0, "polygon_count": 0, "fit_record_count": 0}
    polygon_count = 0
    fit_record_count = 0
    for inst in instruments.values():
        if not isinstance(inst, dict):
            continue
        polygons = inst.get("polygons", [])
        if not isinstance(polygons, list):
            continue
        polygon_count += len(polygons)
        for polygon in polygons:
            if not isinstance(polygon, dict):
                continue
            for key, value in polygon.items():
                if key.startswith("fit_") and isinstance(value, list):
                    fit_record_count += len(value)
    return {
        "instrument_count": len(instruments),
        "polygon_count": polygon_count,
        "fit_record_count": fit_record_count,
    }


def roi_consistency_dump(inst: dict[str, Any]) -> dict[str, Any]:
    """Return debug-only ROI consistency information."""

    polygons = inst.get("polygons", []) or []
    poly_src = inst.get("poly_bg_src")
    source_data = getattr(poly_src, "data", {}) if poly_src is not None else {}
    return {
        "polygon_records": len(polygons),
        "source_xs": len(source_data.get("xs", []) or []),
        "source_ys": len(source_data.get("ys", []) or []),
        "selected_poly": inst.get("selected_poly"),
    }


def callback_count_hint(model: Any) -> dict[str, int]:
    """Return best-effort callback counts for a Bokeh-like model."""

    js_callbacks = getattr(model, "js_property_callbacks", {}) or {}
    py_callbacks = getattr(model, "_callbacks", {}) or {}
    event_callbacks = getattr(model, "subscribed_events", set()) or set()
    return {
        "js_property_callback_groups": len(js_callbacks),
        "python_callback_groups": len(py_callbacks),
        "subscribed_event_types": len(event_callbacks),
    }


def renderer_ownership_dump(name: str, inst: dict[str, Any]) -> dict[str, Any]:
    """Return local renderer ownership information without mutation."""

    fig = inst.get("fig")
    renderers = list(getattr(fig, "renderers", []) or []) if fig is not None else []
    fit_renderers = inst.get("fit_renderers", {}) or {}
    fit_line_renderers = inst.get("fit_line_renderers", {}) or {}
    return {
        "instrument": name,
        "figure_renderer_count": len(renderers),
        "fit_renderer_keys": sorted(str(k) for k in fit_renderers),
        "fit_line_renderer_keys": sorted(str(k) for k in fit_line_renderers),
        "unmapped_renderer_count": max(
            0, len(renderers) - len(fit_renderers) - len(fit_line_renderers)
        ),
    }

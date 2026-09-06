"""Optional runtime state assertions.

These helpers are side-effect free and disabled unless called by tests or a
future debug mode. They do not mutate Bokeh models or scientific data.
"""

from __future__ import annotations

from typing import Any


def assert_polygon_source_consistency(
    polygons: list[dict[str, Any]], source_data: dict[str, Any]
) -> None:
    """Assert polygon records and patch source arrays have compatible shapes."""

    xs = source_data.get("xs", [])
    ys = source_data.get("ys", [])
    if len(xs) != len(ys):
        raise AssertionError("Polygon source xs and ys lengths differ.")
    if len(xs) not in (0, len(polygons)):
        raise AssertionError("Polygon source count does not match polygon records.")
    for index, polygon in enumerate(polygons):
        px = polygon.get("x", [])
        py = polygon.get("y", [])
        if len(px) != len(py):
            raise AssertionError(f"Polygon {index} has mismatched x/y coordinate lengths.")


def assert_polygon_ownership_consistency(
    selected_poly: int | None, polygons: list[dict[str, Any]]
) -> None:
    """Assert selected polygon state points at an existing polygon or nothing."""

    if selected_poly is None:
        return
    if not isinstance(selected_poly, int) or selected_poly < 0 or selected_poly >= len(polygons):
        raise AssertionError("Selected polygon index is outside polygon records.")


def assert_fit_line_index_valid(
    polygons: list[dict[str, Any]], key: tuple[int, str] | None
) -> None:
    """Assert a fit-line renderer key points at a valid polygon."""

    if key is None:
        return
    polygon_index, fit_key = key
    if not isinstance(polygon_index, int) or polygon_index < 0 or polygon_index >= len(polygons):
        raise AssertionError("Fit-line renderer references an invalid polygon index.")
    if not isinstance(fit_key, str) or not fit_key:
        raise AssertionError("Fit-line renderer references an empty fit key.")


def assert_fit_point_consistency(points: list[dict[str, Any]]) -> None:
    """Assert fit points contain numeric time and diameter where present."""

    for index, point in enumerate(points):
        if not isinstance(point, dict):
            raise AssertionError(f"Fit point {index} is not a dictionary.")
        for key in ("time", "diam"):
            if key in point and point[key] is not None:
                try:
                    float(point[key])
                except (TypeError, ValueError) as exc:
                    raise AssertionError(f"Fit point {index} has non-numeric {key}.") from exc


def assert_renderer_source_alignment(renderers: dict[str, Any], sources: dict[str, Any]) -> None:
    """Assert renderer/source registries share compatible keys."""

    renderer_keys = set(renderers)
    source_keys = set(sources)
    missing_sources = renderer_keys - source_keys
    if missing_sources:
        raise AssertionError(f"Renderers without matching sources: {sorted(missing_sources)}")


def assert_no_duplicate_ownership(owner_map: dict[str, str]) -> None:
    """Assert passive ownership map has no duplicate owner assignment per object."""

    seen: dict[str, str] = {}
    for object_id, owner in owner_map.items():
        if object_id in seen and seen[object_id] != owner:
            raise AssertionError(f"Object {object_id!r} has duplicate owners.")
        seen[object_id] = owner


def assert_no_orphan_renderers(renderer_ids: set[str], source_ids: set[str]) -> None:
    """Assert every renderer ID has a matching source/metadata ID."""

    orphans = renderer_ids - source_ids
    if orphans:
        raise AssertionError(f"Orphan renderers: {sorted(orphans)}")


def assert_roi_array_dimensionality(
    data_shape: tuple[int, ...], mask_shape: tuple[int, ...]
) -> None:
    """Assert an ROI mask can be applied to the data array."""

    if len(data_shape) != 2:
        raise AssertionError("ROI data array must be two-dimensional.")
    if data_shape != mask_shape:
        raise AssertionError("ROI mask shape must match data shape.")


def assert_undo_stack_integrity(undo_stack: list[dict[str, Any]]) -> None:
    """Assert undo records have enough structure to restore state."""

    for index, record in enumerate(undo_stack):
        if not isinstance(record, dict):
            raise AssertionError(f"Undo record {index} is not a dictionary.")
        if not record:
            raise AssertionError(f"Undo record {index} is empty.")
        if "type" not in record and "action" not in record and "before_points" not in record:
            raise AssertionError(f"Undo record {index} has no recognizable action marker.")


def assert_linked_axis_identity(figures: list[Any]) -> None:
    """Assert linked figures share the same x_range object identity."""

    if len(figures) < 2:
        return
    first = getattr(figures[0], "x_range", None)
    for figure in figures[1:]:
        if getattr(figure, "x_range", None) is not first:
            raise AssertionError("Linked figures do not share the same x_range object.")

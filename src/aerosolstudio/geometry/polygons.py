"""Pure polygon containment and validation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from aerosolstudio.geometry.coordinates import normalize_polygon


def validate_polygon(x: Iterable[Any], y: Iterable[Any], *, min_vertices: int = 3) -> list[str]:
    """Return validation errors for polygon coordinate arrays."""

    errors: list[str] = []
    try:
        xs, ys = normalize_polygon(x, y)
    except ValueError as exc:
        return [str(exc)]
    if len(xs) < min_vertices:
        errors.append(f"Polygon needs at least {min_vertices} finite vertices.")
    if len(np.unique(np.column_stack([xs, ys]), axis=0)) < min_vertices:
        errors.append("Polygon has too few unique finite vertices.")
    return errors


def point_in_polygon(
    x: float, y: float, polygon_x: Iterable[Any], polygon_y: Iterable[Any]
) -> bool:
    """Return whether one point lies inside a polygon using ray casting."""

    xs, ys = normalize_polygon(polygon_x, polygon_y)
    if validate_polygon(xs, ys):
        return False
    inside = False
    j = len(xs) - 1
    for i in range(len(xs)):
        yi = ys[i]
        yj = ys[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            x_intersect = (xs[j] - xs[i]) * (y - yi) / (yj - yi) + xs[i]
            if x < x_intersect:
                inside = not inside
        j = i
    return bool(inside)


def points_in_polygon(
    x_points: Iterable[Any],
    y_points: Iterable[Any],
    polygon_x: Iterable[Any],
    polygon_y: Iterable[Any],
) -> np.ndarray:
    """Return a boolean mask for points inside a polygon."""

    xp = np.asarray(list(x_points), dtype=float).reshape(-1)
    yp = np.asarray(list(y_points), dtype=float).reshape(-1)
    if xp.shape != yp.shape:
        raise ValueError("Point x and y arrays must have the same length.")
    return np.asarray(
        [point_in_polygon(x, y, polygon_x, polygon_y) for x, y in zip(xp, yp, strict=True)],
        dtype=bool,
    )


def polygon_mask(
    time_values: Iterable[Any],
    diameter_values: Iterable[Any],
    polygon_x: Iterable[Any],
    polygon_y: Iterable[Any],
) -> np.ndarray:
    """Return a 2D mask for a time-by-diameter grid inside a polygon."""

    t = np.asarray(list(time_values), dtype=float).reshape(-1)
    d = np.asarray(list(diameter_values), dtype=float).reshape(-1)
    tt, dd = np.meshgrid(t, d, indexing="ij")
    return points_in_polygon(tt.ravel(), dd.ravel(), polygon_x, polygon_y).reshape(tt.shape)

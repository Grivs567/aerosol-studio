"""Pure coordinate normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from aerosolstudio.utils.time import time_value_to_ms


def finite_float_array(values: Iterable[Any]) -> np.ndarray:
    """Return a one-dimensional float array from arbitrary coordinate values."""

    return np.asarray(list(values), dtype=float).reshape(-1)


def normalize_polygon(x: Iterable[Any], y: Iterable[Any]) -> tuple[np.ndarray, np.ndarray]:
    """Return finite x/y polygon coordinate arrays with matching lengths."""

    xs = finite_float_array(x)
    ys = finite_float_array(y)
    if xs.shape != ys.shape:
        raise ValueError("Polygon x and y coordinate arrays must have the same length.")
    finite = np.isfinite(xs) & np.isfinite(ys)
    return xs[finite], ys[finite]


def bounding_box(x: Iterable[Any], y: Iterable[Any]) -> tuple[float, float, float, float] | None:
    """Return ``(xmin, xmax, ymin, ymax)`` for finite polygon coordinates."""

    xs, ys = normalize_polygon(x, y)
    if len(xs) == 0:
        return None
    return float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())


def time_diameter_points(
    times: Iterable[Any], diameters: Iterable[Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize time and diameter arrays into geometry units.

    Times are returned as epoch milliseconds, matching Bokeh datetime-axis
    coordinates. Diameters are returned as finite floats in their input unit.
    """

    t_ms = np.asarray([time_value_to_ms(value) for value in times], dtype=float).reshape(-1)
    d = finite_float_array(diameters)
    if t_ms.shape != d.shape:
        raise ValueError("Time and diameter point arrays must have the same length.")
    return t_ms, d

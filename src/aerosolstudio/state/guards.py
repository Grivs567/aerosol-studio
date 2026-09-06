"""Warning-oriented runtime guards for optional diagnostics."""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np

from aerosolstudio.geometry import validate_polygon
from aerosolstudio.io.session_schema import SESSION_SCHEMA_VERSION


def warn_readonly_array(values: Any, *, context: str = "array") -> bool:
    """Warn when an ndarray is read-only; return True when warning emitted."""

    arr = np.asarray(values)
    if not arr.flags.writeable:
        warnings.warn(
            f"{context} is read-only; copy before in-place mutation.", RuntimeWarning, stacklevel=2
        )
        return True
    return False


def warn_invalid_roi_geometry(polygon: dict[str, Any], *, context: str = "ROI") -> list[str]:
    """Warn for invalid ROI geometry and return validation errors."""

    errors = validate_polygon(polygon.get("x", []), polygon.get("y", []))
    for error in errors:
        warnings.warn(f"{context}: {error}", RuntimeWarning, stacklevel=2)
    return errors


def warn_nan_fit_payload(points: list[dict[str, Any]], *, context: str = "fit") -> int:
    """Warn when fit-point payload contains NaN/inf numeric values."""

    count = 0
    for index, point in enumerate(points):
        for key, value in point.items():
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                count += 1
                warnings.warn(
                    f"{context} point {index} has non-finite {key}.", RuntimeWarning, stacklevel=2
                )
    return count


def warn_duplicate_renderer_insertion(existing: set[str], renderer_id: str) -> bool:
    """Warn if a passive renderer ID already exists."""

    if renderer_id in existing:
        warnings.warn(
            f"Duplicate renderer metadata id: {renderer_id}", RuntimeWarning, stacklevel=2
        )
        return True
    return False


def warn_invalid_session_schema_version(version: str | None) -> bool:
    """Warn if a session schema version differs from the current helper version."""

    if version and str(version) != SESSION_SCHEMA_VERSION:
        warnings.warn(
            f"Session schema {version} differs from current {SESSION_SCHEMA_VERSION}; migration required.",
            RuntimeWarning,
            stacklevel=2,
        )
        return True
    return False

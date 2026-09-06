"""Pure helpers for serialized fit-point records."""

from __future__ import annotations

from typing import Any

from aerosolstudio.models.records import FitResultRecord

FLOAT_FIELDS = {"time", "diam", "mean", "sigma", "amplitude", "t_min", "t_max", "k", "r2"}


def restore_fit_points(points: Any) -> list[dict[str, Any]]:
    """Normalize fit-point records loaded from JSON."""

    restored: list[dict[str, Any]] = []
    if not isinstance(points, list):
        return restored
    for item in points:
        if not isinstance(item, dict):
            continue
        clean: dict[str, Any] = {}
        for key, value in item.items():
            if value is None:
                clean[key] = value
            elif key in FLOAT_FIELDS:
                try:
                    clean[key] = float(value)
                except (TypeError, ValueError):
                    clean[key] = value
            else:
                clean[key] = value
        restored.append(clean)
    return restored


def fit_point_to_record(fit_type: str, point: dict[str, Any]) -> FitResultRecord:
    """Convert a fit-point dictionary into an immutable passive record."""

    time_ms = float(point.get("time", point.get("time_ms", 0.0)) or 0.0)
    diameter_m = float(point.get("diam", point.get("diam_m", 0.0)) or 0.0)
    params = {k: v for k, v in point.items() if k not in {"time", "time_ms", "diam", "diam_m"}}
    return FitResultRecord(fit_type=fit_type, time_ms=time_ms, diameter_m=diameter_m, params=params)


def summarize_fit_points(points: Any) -> dict[str, float | int | None]:
    """Return a compact summary for restored fit-point dictionaries."""

    restored = restore_fit_points(points)
    if not restored:
        return {
            "count": 0,
            "time_min": None,
            "time_max": None,
            "diameter_min": None,
            "diameter_max": None,
        }
    times = [float(p["time"]) for p in restored if "time" in p and p["time"] is not None]
    diams = [float(p["diam"]) for p in restored if "diam" in p and p["diam"] is not None]
    return {
        "count": len(restored),
        "time_min": min(times) if times else None,
        "time_max": max(times) if times else None,
        "diameter_min": min(diams) if diams else None,
        "diameter_max": max(diams) if diams else None,
    }

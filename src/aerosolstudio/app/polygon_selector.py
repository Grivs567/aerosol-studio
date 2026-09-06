"""Package-owned polygon selector lifecycle helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def update_polygon_dropdown(inst: dict[str, Any]) -> None:
    """Refresh the polygon selector options for an instrument."""

    options = [("Selected", "Selected")]
    for idx, polygon in enumerate(inst["polygons"]):
        label = polygon.get("label", f"Polygon {idx}")
        options.append((str(idx), f"{idx} — {label}"))

    raw = inst.get("fit_line_poly_raw") or inst.get("fit_line_poly")
    if raw is not None:
        raw.options = options
        raw.value = "Selected"


def update_polygon_label(inst: dict[str, Any], name: str) -> str:
    """Apply the current label input to the selected polygon."""

    if inst["selected_poly"] is None:
        return "⚠ No polygon selected"

    new_label = inst["poly_label_input"].value.strip()
    if not new_label:
        return "⚠ Label cannot be empty"

    inst["polygons"][inst["selected_poly"]]["label"] = new_label
    update_polygon_dropdown(inst)
    return f"✅ Updated label for {name}"


def select_polygon_from_dropdown(
    inst: dict[str, Any],
    value: str,
    *,
    on_selected: Callable[[], None],
) -> bool:
    """Select a polygon from the dropdown and run caller-owned UI updates."""

    if value == "Selected":
        return False

    try:
        idx = int(value)
    except ValueError:
        return False

    if not 0 <= idx < len(inst["polygons"]):
        return False

    inst["selected_poly"] = idx
    on_selected()
    return True

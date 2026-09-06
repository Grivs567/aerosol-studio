"""Package-owned fit-line renderer lifecycle helpers."""

from __future__ import annotations

from typing import Any


def clear_fit_line_renderer(inst: dict[str, Any], polygon_idx: int, fit_key: str) -> None:
    """Remove one growth-rate fit-line renderer and source from an instrument."""

    key = (polygon_idx, fit_key)
    if key in inst.get("fit_line_srcs", {}):
        del inst["fit_line_srcs"][key]
    if key in inst.get("fit_line_renderers", {}):
        renderer = inst["fit_line_renderers"].pop(key)
        if renderer in inst["fig"].renderers:
            inst["fig"].renderers.remove(renderer)


def shift_fit_line_renderer_indices_after_delete(
    inst: dict[str, Any],
    deleted_idx: int,
) -> None:
    """Shift fit-line renderer/source keys after a polygon index is deleted."""

    if "fit_line_srcs" not in inst or "fit_line_renderers" not in inst:
        return

    for store_name in ("fit_line_srcs", "fit_line_renderers"):
        shifted = {}
        for key, value in inst[store_name].items():
            if isinstance(key, tuple) and key[0] > deleted_idx:
                shifted[(key[0] - 1, key[1])] = value
            else:
                shifted[key] = value
        inst[store_name] = shifted


def clear_fit_line_renderers_for_polygon(inst: dict[str, Any], polygon_idx: int) -> None:
    """Remove all growth-rate fit-line renderers and sources for one polygon."""

    if "fit_line_srcs" not in inst:
        return

    keys_to_delete = [
        key
        for key in inst["fit_line_srcs"]
        if isinstance(key, tuple) and key[0] == polygon_idx
    ]
    for polygon_key, fit_key in keys_to_delete:
        clear_fit_line_renderer(inst, polygon_key, fit_key)


def clear_all_fit_line_renderers(inst: dict[str, Any]) -> None:
    """Remove all growth-rate fit-line renderers and clear lifecycle stores."""

    for renderer in list(inst.get("fit_line_renderers", {}).values()):
        if renderer in inst["fig"].renderers:
            inst["fig"].renderers.remove(renderer)
    inst.setdefault("fit_line_srcs", {}).clear()
    inst.setdefault("fit_line_renderers", {}).clear()

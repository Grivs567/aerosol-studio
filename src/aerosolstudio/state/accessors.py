"""Read-only accessors for canonical instrument dictionaries.

The helpers in this module intentionally do not create runtime objects or move
ownership away from ``self.instruments``.  They are thin dictionary wrappers for
places where spelling out the boundary makes the existing state shape clearer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aerosolstudio.state.keys import (
    DF_KEY,
    FIG_KEY,
    FIT_LINE_RENDERERS_KEY,
    FIT_LINE_SRCS_KEY,
    MAPPER_KEY,
    MODE_MULTI_SRC_KEY,
    MODE_SUM_SRC_KEY,
    OVERLAY_KEY,
    POLY_BG_SRC_KEY,
    POLY_SRC_KEY,
    POLYGON_KEY,
    SELECTED_POLY_KEY,
    SRC_DIST_KEY,
    SRC_IMG_KEY,
)


def get_instrument_fig(inst: Mapping[str, Any]) -> Any:
    """Return the heatmap figure owned by an instrument dictionary."""

    return inst[FIG_KEY]


def get_polygon_state(inst: Mapping[str, Any]) -> Any:
    """Return the live polygon list owned by an instrument dictionary."""

    return inst[POLYGON_KEY]


def get_selected_polygon_index(inst: Mapping[str, Any]) -> int | None:
    """Return the selected polygon index, if any."""

    selected = inst.get(SELECTED_POLY_KEY)
    return selected if isinstance(selected, int) or selected is None else None


def get_fit_state(inst: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the embedded fit state container.

    Fit sources and undo state are still stored directly on the instrument dict,
    so this returns the same mapping instead of introducing a nested container.
    """

    return inst


def get_overlay_state(inst: Mapping[str, Any]) -> Any:
    """Return concentration overlay records/widgets owned by the instrument."""

    return inst.get(OVERLAY_KEY, [])


def get_distribution_state(inst: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the embedded distribution-plot state container."""

    return inst


def get_heatmap_state(inst: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the embedded heatmap state container."""

    return inst


def get_dataframe(inst: Mapping[str, Any]) -> Any:
    """Return the instrument dataframe payload."""

    return inst.get(DF_KEY)


def get_fit_line_sources(inst: Mapping[str, Any]) -> Any:
    """Return fit-line source mapping when present."""

    return inst.get(FIT_LINE_SRCS_KEY, {})


def get_fit_line_renderers(inst: Mapping[str, Any]) -> Any:
    """Return fit-line renderer mapping when present."""

    return inst.get(FIT_LINE_RENDERERS_KEY, {})


def get_fit_source(inst: Mapping[str, Any], source_key: str) -> Any:
    """Return a fit source by its canonical registry suffix."""

    return inst[source_key]


def get_distribution_source(inst: Mapping[str, Any], source_key: str) -> Any:
    """Return a distribution source by its canonical registry suffix."""

    return inst[source_key]


def get_distribution_curve_source(inst: Mapping[str, Any]) -> Any:
    """Return the raw distribution curve source."""

    return inst[SRC_DIST_KEY]


def get_mode_multi_source(inst: Mapping[str, Any]) -> Any:
    """Return the multi-mode distribution curve source."""

    return inst[MODE_MULTI_SRC_KEY]


def get_mode_sum_source(inst: Mapping[str, Any]) -> Any:
    """Return the summed mode distribution curve source."""

    return inst[MODE_SUM_SRC_KEY]


def get_heatmap_source(inst: Mapping[str, Any]) -> Any:
    """Return the heatmap image source."""

    return inst[SRC_IMG_KEY]


def get_polygon_source(inst: Mapping[str, Any]) -> Any:
    """Return the active polygon draw source."""

    return inst[POLY_SRC_KEY]


def get_polygon_background_source(inst: Mapping[str, Any]) -> Any:
    """Return the rendered polygon background source."""

    return inst[POLY_BG_SRC_KEY]


def get_heatmap_mapper(inst: Mapping[str, Any]) -> Any:
    """Return the heatmap color mapper."""

    return inst[MAPPER_KEY]

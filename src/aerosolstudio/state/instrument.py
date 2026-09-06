"""Structural contracts for instrument runtime state.

These types document the current ``self.instruments[name]`` dictionary shape.
They are not runtime containers yet; the canonical app still owns and mutates
the instrument dictionaries directly.
"""

from __future__ import annotations

from typing import Any, TypedDict


class InstrumentDataState(TypedDict, total=False):
    """Plain data and loader state stored for an instrument."""

    df: Any
    type: str
    path_input: Any
    load_btn: Any
    loaded_path: str


class InstrumentViewState(TypedDict, total=False):
    """Bokeh view objects owned by the instrument entry."""

    fig: Any
    fig_dist: Any
    fig_strip: Any
    mapper: Any
    src_img: Any
    poly_src: Any
    poly_bg_src: Any
    tabs: Any
    _heatmap_refresh_pending: bool


class InstrumentFitState(TypedDict, total=False):
    """Fit glyph sources, fit-line renderers, and undo state."""

    maxconc_src: Any
    app_src: Any
    mode_src: Any
    gauss_src: Any
    gmm_src: Any
    maxconc_dist_src: Any
    app_dist_src: Any
    mode_dist_src: Any
    gauss_dist_src: Any
    gmm_dist_src: Any
    fit_line_srcs: dict[tuple[int, str], Any]
    fit_line_renderers: dict[tuple[int, str], Any]
    undo_stack: list[dict[str, Any]]


class InstrumentROIState(TypedDict, total=False):
    """ROI polygon state and selection state."""

    polygons: list[dict[str, Any]]
    selected_poly: int | None
    poly_src: Any
    poly_bg_src: Any

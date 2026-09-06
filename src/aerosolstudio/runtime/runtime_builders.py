"""Pure grouping helpers for existing renderer runtime references."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aerosolstudio.runtime.renderers import (
    DistributionRuntime,
    FitGlyphRuntime,
    HeatmapRuntime,
    OverlayRuntime,
    PolygonRuntime,
)
from aerosolstudio.state.keys import (
    ADD_OVERLAY_VAR_BTN_KEY,
    COLORBAR_KEY,
    OVERLAY_VAR_CONTAINER_KEY,
    FIG_DIST_KEY,
    FIG_KEY,
    FIT_LINE_RENDERERS_KEY,
    FIT_LINE_SRCS_KEY,
    FIT_RENDERERS_KEY,
    FIT_TYPES_KEY,
    IMG_RENDERER_KEY,
    MAPPER_KEY,
    MODE_FIT_RENDERER_KEY,
    MODE_MULTI_SRC_KEY,
    MODE_SUM_SRC_KEY,
    OVERLAY_KEY,
    POLY_BG_SRC_KEY,
    POLY_SRC_KEY,
    POLYGON_KEY,
    RECT_SRC_KEY,
    SRC_DIST_KEY,
    SRC_IMG_KEY,
    UNDO_STACK_KEY,
)


def _registry_sources(inst: Mapping[str, Any], suffix_key: str) -> dict[str, Any]:
    fit_types = inst.get(FIT_TYPES_KEY, {})
    sources: dict[str, Any] = {}
    for fit_key, props in fit_types.items():
        source_key = props.get(suffix_key)
        if source_key in inst:
            sources[fit_key] = inst[source_key]
    return sources


def build_heatmap_runtime(inst: Mapping[str, Any]) -> HeatmapRuntime:
    """Group already-created heatmap references."""

    return HeatmapRuntime(
        figure=inst[FIG_KEY],
        source=inst[SRC_IMG_KEY],
        renderer=inst[IMG_RENDERER_KEY],
        mapper=inst[MAPPER_KEY],
        colorbar=inst[COLORBAR_KEY],
    )


def build_polygon_runtime(inst: Mapping[str, Any]) -> PolygonRuntime:
    """Group already-created polygon references."""

    return PolygonRuntime(
        source=inst[POLY_SRC_KEY],
        background_source=inst[POLY_BG_SRC_KEY],
        rect_source=inst[RECT_SRC_KEY],
        polygons=inst[POLYGON_KEY],
    )


def build_fit_runtime(inst: Mapping[str, Any]) -> FitGlyphRuntime:
    """Group already-created fit glyph references."""

    return FitGlyphRuntime(
        sources=_registry_sources(inst, "src_suffix"),
        distribution_sources=_registry_sources(inst, "dist_src_suffix"),
        renderers=inst[FIT_RENDERERS_KEY],
        fit_line_sources=inst[FIT_LINE_SRCS_KEY],
        fit_line_renderers=inst[FIT_LINE_RENDERERS_KEY],
        undo_stack=inst[UNDO_STACK_KEY],
    )


def build_distribution_runtime(inst: Mapping[str, Any]) -> DistributionRuntime:
    """Group already-created distribution plot references."""

    return DistributionRuntime(
        figure=inst[FIG_DIST_KEY],
        source=inst[SRC_DIST_KEY],
        fit_sources=_registry_sources(inst, "dist_src_suffix"),
        mode_multi_source=inst[MODE_MULTI_SRC_KEY],
        mode_sum_source=inst[MODE_SUM_SRC_KEY],
        mode_renderer=inst[MODE_FIT_RENDERER_KEY],
    )


def build_overlay_runtime(inst: Mapping[str, Any]) -> OverlayRuntime:
    """Group already-created overlay references."""

    return OverlayRuntime(
        overlay_var_lines=inst[OVERLAY_KEY],
        container=inst[OVERLAY_VAR_CONTAINER_KEY],
        add_button=inst[ADD_OVERLAY_VAR_BTN_KEY],
    )

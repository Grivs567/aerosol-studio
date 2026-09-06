"""Passive renderer runtime containers.

These dataclasses only group references that are already owned by an
instrument dictionary.  They do not create plot objects, register callbacks,
mutate documents, or own widget lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeatmapRuntime:
    """References for the heatmap figure and image renderer."""

    figure: Any
    source: Any
    renderer: Any
    mapper: Any
    colorbar: Any


@dataclass(frozen=True)
class PolygonRuntime:
    """References for ROI polygon render state."""

    source: Any
    background_source: Any
    rect_source: Any
    polygons: list[dict[str, Any]]


@dataclass(frozen=True)
class FitGlyphRuntime:
    """References for fit marker sources and renderer bookkeeping."""

    sources: dict[str, Any]
    distribution_sources: dict[str, Any]
    renderers: list[Any]
    fit_line_sources: dict[Any, Any]
    fit_line_renderers: dict[Any, Any]
    undo_stack: list[dict[str, Any]]


@dataclass(frozen=True)
class DistributionRuntime:
    """References for the distribution plot and fit-distribution overlays."""

    figure: Any
    source: Any
    fit_sources: dict[str, Any]
    mode_multi_source: Any
    mode_sum_source: Any
    mode_renderer: Any


@dataclass(frozen=True)
class OverlayRuntime:
    """References for concentration overlay state."""

    overlay_var_lines: list[dict[str, Any]]
    container: Any
    add_button: Any

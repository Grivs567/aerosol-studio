"""Package-owned construction for distribution plot controls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bokeh.models import ColumnDataSource, CustomJSHover, Toggle

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.fitting.types import FIT_TYPE_METADATA
from aerosolstudio.runtime.distribution_construction import (
    build_distribution_axis_defaults,
    build_distribution_figure_kwargs,
    build_distribution_hover_config,
    build_distribution_renderer_kwargs,
    build_distribution_source_payloads,
    build_distribution_tool_config,
    build_distribution_visibility_defaults,
)
from aerosolstudio.runtime.safe_renderer_factories import (
    DistributionRendererBundle,
    construct_distribution_renderer_bundle,
)
from aerosolstudio.themes.colors import THEME
from aerosolstudio.ui.tooltip_manager import TooltipManager


@dataclass(frozen=True)
class DistributionControls:
    """Bokeh models used by the per-instrument distribution plot area."""

    bundle: DistributionRendererBundle
    fig_dist: Any
    src_dist: ColumnDataSource
    hover_dist: Any
    mode_multi_src: ColumnDataSource
    mode_fit_renderer: Any
    mode_sum_src: ColumnDataSource
    sum_line: Any
    dist_sources: dict[str, ColumnDataSource]
    dist_marker_renderers: dict[str, Any]
    toggle_modes: Toggle
    toggle_modes_: Any
    toggle_sum: Toggle
    toggle_sum_: Any
    nm_formatter: CustomJSHover


def build_distribution_controls(
    name: str,
    *,
    theme: Mapping[str, str] = THEME,
    fit_metadata: Mapping[str, Mapping[str, Any]] = FIT_TYPE_METADATA,
    callback_seam: CallbackSeam | None = None,
    on_modes_toggle: Callable[..., Any] | None = None,
    on_sum_toggle: Callable[..., Any] | None = None,
) -> DistributionControls:
    """Build distribution plot models, recording callbacks through ``CallbackSeam``."""

    fit_types = {key: dict(value) for key, value in fit_metadata.items()}
    dist_cfg = {
        "figure_kwargs": build_distribution_figure_kwargs(name, dict(theme)),
        "source_payloads": build_distribution_source_payloads(),
        "renderer_kwargs": build_distribution_renderer_kwargs(dict(theme), fit_types),
        "hover_config": build_distribution_hover_config(),
        "tool_config": build_distribution_tool_config(),
        "visibility_defaults": build_distribution_visibility_defaults(),
        "axis_defaults": build_distribution_axis_defaults(),
    }
    nm_formatter = CustomJSHover(code="""
            return (value * 1e9).toFixed(2) + ' nm';
        """)
    bundle = construct_distribution_renderer_bundle(dist_cfg, nm_formatter, dict(theme))

    dist_sources: dict[str, ColumnDataSource] = {"mode_multi_src": bundle.mode_multi_src}
    dist_marker_renderers: dict[str, Any] = {}
    for fit_key, props in fit_metadata.items():
        dist_src = ColumnDataSource(data=dict(x=[], y=[], color=[]))
        dist_sources[str(props["dist_src_suffix"])] = dist_src
        dist_marker_renderers[fit_key] = bundle.fig_dist.scatter(
            x="x",
            y="y",
            source=dist_src,
            size=props["size"] + 2,
            marker=props["dist_marker"],
            color="color",
            line_color="black",
            line_width=0.5,
            alpha=0.8,
        )

    toggle_modes = Toggle(label="Modes", active=True)
    toggle_modes_ = TooltipManager.add_to_widget(toggle_modes, "toggle_modes")
    dist_sources["mode_sum_src"] = bundle.mode_sum_src
    toggle_sum = Toggle(label="Σ Modes", active=False, width=90)
    toggle_sum_ = TooltipManager.add_to_widget(toggle_sum, "toggle_sum")

    if callback_seam is not None:
        callback_seam.on_change(
            toggle_modes,
            "active",
            on_modes_toggle
            if on_modes_toggle is not None
            else lambda attr, old, new: setattr(bundle.mode_fit_renderer, "visible", new),
            label="mode-toggle-active",
        )
        callback_seam.on_change(
            toggle_sum,
            "active",
            on_sum_toggle
            if on_sum_toggle is not None
            else lambda attr, old, new: setattr(bundle.sum_line, "visible", new),
            label="sum-toggle-active",
        )

    return DistributionControls(
        bundle=bundle,
        fig_dist=bundle.fig_dist,
        src_dist=bundle.src_dist,
        hover_dist=bundle.hover_dist,
        mode_multi_src=bundle.mode_multi_src,
        mode_fit_renderer=bundle.mode_fit_renderer,
        mode_sum_src=bundle.mode_sum_src,
        sum_line=bundle.sum_line,
        dist_sources=dist_sources,
        dist_marker_renderers=dist_marker_renderers,
        toggle_modes=toggle_modes,
        toggle_modes_=toggle_modes_,
        toggle_sum=toggle_sum,
        toggle_sum_=toggle_sum_,
        nm_formatter=nm_formatter,
    )

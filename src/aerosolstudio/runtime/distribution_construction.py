"""Passive distribution construction-preparation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DistributionSourcePayloads:
    raw: dict[str, list[Any]]
    marker: dict[str, list[Any]]
    mode_multi: dict[str, list[Any]]
    mode_sum: dict[str, list[Any]]


@dataclass(frozen=True)
class DistributionRendererKwargs:
    raw_line: dict[str, Any]
    mode_line: dict[str, Any]
    sum_line: dict[str, Any]
    marker_by_fit: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class DistributionHoverConfig:
    tooltips: tuple[tuple[str, str], ...]
    formatter_key: str
    mode: str
    visible: bool


@dataclass(frozen=True)
class DistributionToolConfig:
    tools: str
    hover_enabled: bool


@dataclass(frozen=True)
class DistributionVisibilityDefaults:
    modes_active: bool
    sum_active: bool
    sum_line_visible: bool


@dataclass(frozen=True)
class DistributionAxisDefaults:
    x_label: str
    y_label: str
    grid_alpha: float


def build_distribution_figure_kwargs(name: str, theme: dict[str, str]) -> dict[str, Any]:
    return {
        "height": 240,
        "x_axis_type": "log",
        "title": f"{name}  ·  Size Distribution",
        "sizing_mode": "stretch_width",
        "tools": "pan,box_zoom,wheel_zoom,reset,save",
        "background_fill_color": theme["plot_bg"],
        "border_fill_color": theme["panel"],
        "outline_line_color": theme["plot_border"],
    }


def build_distribution_source_payloads() -> DistributionSourcePayloads:
    return DistributionSourcePayloads(
        raw={"x": [], "y": []},
        marker={"x": [], "y": [], "color": []},
        mode_multi={"xs": [], "ys": [], "color": []},
        mode_sum={"x": [], "y": []},
    )


def build_distribution_renderer_kwargs(
    theme: dict[str, str],
    fit_types: dict[str, dict[str, Any]],
) -> DistributionRendererKwargs:
    return DistributionRendererKwargs(
        raw_line={"line_width": 2, "color": theme["accent"], "line_alpha": 0.9},
        mode_line={
            "line_width": 2.5,
            "line_alpha": 0.8,
            "line_dash": "dashed",
        },
        sum_line={
            "line_color": "black",
            "line_width": 3,
            "line_dash": "dashed",
            "visible": False,
        },
        marker_by_fit={
            fit_key: {
                "size": props["size"] + 2,
                "marker": props["dist_marker"],
                "color": "color",
                "line_color": "black",
                "line_width": 0.5,
                "alpha": 0.8,
            }
            for fit_key, props in fit_types.items()
        },
    )


def build_distribution_hover_config() -> DistributionHoverConfig:
    return DistributionHoverConfig(
        tooltips=(("Diameter", "@x{0.0e}"), ("Conc", "@y{0e}")),
        formatter_key="@x",
        mode="mouse",
        visible=True,
    )


def build_distribution_tool_config() -> DistributionToolConfig:
    return DistributionToolConfig(
        tools="pan,box_zoom,wheel_zoom,reset,save",
        hover_enabled=True,
    )


def build_distribution_visibility_defaults() -> DistributionVisibilityDefaults:
    return DistributionVisibilityDefaults(
        modes_active=True,
        sum_active=False,
        sum_line_visible=False,
    )


def build_distribution_axis_defaults() -> DistributionAxisDefaults:
    return DistributionAxisDefaults(
        x_label="Diameter (m)",
        y_label="dN/dlogDp (cm⁻³)",
        grid_alpha=0.4,
    )


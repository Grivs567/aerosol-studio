"""Package-owned construction for diameter strip plot controls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bokeh.models import Button, Checkbox, CheckboxGroup, Div, TextInput

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.fitting.types import FIT_TYPE_METADATA
from aerosolstudio.runtime.safe_renderer_factories import (
    StripRendererBundle,
    construct_strip_renderer_bundle,
)
from aerosolstudio.themes.colors import THEME


@dataclass(frozen=True)
class StripAxisConfig:
    x_label: str
    y_label: str
    grid_alpha: float


@dataclass(frozen=True)
class StripRendererSpec:
    figure_kwargs: dict[str, Any]
    raw_line_kwargs: dict[str, Any]
    fit_line_kwargs: dict[str, Any]
    fit_point_kwargs: dict[str, Any]
    multi_fit_kwargs: dict[str, Any]
    multi_point_kwargs: dict[str, Any]
    polygon_span_kwargs: dict[str, Any]
    time_marker_kwargs: dict[str, Any]


@dataclass(frozen=True)
class StripControls:
    """Bokeh models used by the per-instrument diameter strip plot area."""

    bundle: StripRendererBundle
    fig_strip: Any
    src_strip_raw: Any
    src_strip_fit: Any
    src_strip_point: Any
    src_strip_fits: Any
    src_strip_points: Any
    poly_span: Any
    strip_time_marker: Any
    strip_diameter_input: TextInput
    btn_plot_strip: Button
    chk_show_fit: Checkbox
    chk_follow_cursor: Checkbox
    fit_checkboxes: CheckboxGroup
    fit_overlay_legend: Div
    fit_checkbox_keys: tuple[str, ...]


def build_strip_source_payload(kind: str = "line") -> dict[str, list[Any]]:
    """Return the legacy strip source schemas."""

    if kind == "multi_line":
        return {"xs": [], "ys": [], "color": []}
    if kind == "point":
        return {"t": [], "y": [], "color": []}
    return {"t": [], "y": []}


def build_strip_axis_config() -> StripAxisConfig:
    """Return strip axis labels and grid alpha matching the monolith."""

    return StripAxisConfig(
        x_label="Time (UTC)",
        y_label="Concentration (cm⁻³)",
        grid_alpha=0.4,
    )


def build_strip_renderer_spec(name: str, theme: Mapping[str, str] = THEME) -> StripRendererSpec:
    """Return strip renderer spec consumed by the tracked safe renderer factory."""

    return StripRendererSpec(
        figure_kwargs={
            "height": 240,
            "x_axis_type": "datetime",
            "y_axis_type": "log",
            "title": f"{name}  ·  Diameter Time Series",
            "sizing_mode": "stretch_width",
            "tools": "pan,box_zoom,wheel_zoom,save,reset",
            "background_fill_color": theme["plot_bg"],
            "border_fill_color": theme["panel"],
            "outline_line_color": theme["plot_border"],
        },
        raw_line_kwargs={"line_width": 2, "color": "steelblue"},
        fit_line_kwargs={"line_width": 2, "color": "crimson", "line_dash": "dashed"},
        fit_point_kwargs={"size": 8, "color": "crimson", "marker": "circle"},
        multi_fit_kwargs={"line_width": 2, "line_dash": "dashed"},
        multi_point_kwargs={"size": 8},
        polygon_span_kwargs={
            "left": None,
            "right": None,
            "fill_alpha": 0.15,
            "fill_color": "#0072b2",
            "line_color": "#0072b2",
            "line_width": 1,
            "line_dash": "dashed",
            "visible": False,
        },
        time_marker_kwargs={
            "location": None,
            "dimension": "height",
            "line_color": theme["accent"],
            "line_dash": "dashed",
            "line_width": 1.5,
        },
    )


def build_strip_controls(
    name: str,
    *,
    theme: Mapping[str, str] = THEME,
    fit_metadata: Mapping[str, Mapping[str, Any]] = FIT_TYPE_METADATA,
    callback_seam: CallbackSeam | None = None,
    on_plot_strip: Callable[..., Any] | None = None,
    on_fit_checkboxes_change: Callable[..., Any] | None = None,
) -> StripControls:
    """Build strip plot models, recording callbacks through ``CallbackSeam``."""

    bundle = construct_strip_renderer_bundle(
        build_strip_renderer_spec(name, theme),
        build_strip_axis_config(),
        dict(theme),
        build_strip_source_payload,
    )

    strip_diameter_input = TextInput(title="Diameter (nm)", value="", width=120)
    btn_plot_strip = Button(label="Plot Strip", button_type="primary", width=100)
    chk_show_fit = Checkbox(label="Overlay fit", active=True, width=100)
    chk_follow_cursor = Checkbox(label="Follow cursor", active=True, width=120)
    fit_checkbox_keys = tuple(fit_metadata)
    fit_checkboxes = CheckboxGroup(
        labels=[f"■ {props['display_name']}" for props in fit_metadata.values()],
        active=list(range(len(fit_metadata))),
        inline=True,
        sizing_mode="stretch_width",
    )
    fit_overlay_legend = Div(
        text="".join(
            f"<span style='display:inline-flex;align-items:center;margin-right:12px;"
            f"font-size:11px;color:{theme['text_secondary']};'>"
            f"<span style='width:9px;height:9px;border-radius:2px;"
            f"background:{props['color']};display:inline-block;margin-right:4px;"
            f"border:1px solid rgba(0,0,0,0.25);'></span>"
            f"{props['display_name']}</span>"
            for props in fit_metadata.values()
        ),
        sizing_mode="stretch_width",
    )

    if callback_seam is not None:
        callback_seam.on_click(
            btn_plot_strip,
            on_plot_strip if on_plot_strip is not None else (lambda: None),
            label="plot-strip-click",
        )
        callback_seam.on_change(
            fit_checkboxes,
            "active",
            on_fit_checkboxes_change if on_fit_checkboxes_change is not None else (lambda attr, old, new: None),
            label="fit-checkboxes-active",
        )

    return StripControls(
        bundle=bundle,
        fig_strip=bundle.fig_strip,
        src_strip_raw=bundle.src_strip_raw,
        src_strip_fit=bundle.src_strip_fit,
        src_strip_point=bundle.src_strip_point,
        src_strip_fits=bundle.src_strip_fits,
        src_strip_points=bundle.src_strip_points,
        poly_span=bundle.poly_span,
        strip_time_marker=bundle.strip_time_marker,
        strip_diameter_input=strip_diameter_input,
        btn_plot_strip=btn_plot_strip,
        chk_show_fit=chk_show_fit,
        chk_follow_cursor=chk_follow_cursor,
        fit_checkboxes=fit_checkboxes,
        fit_overlay_legend=fit_overlay_legend,
        fit_checkbox_keys=fit_checkbox_keys,
    )

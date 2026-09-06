"""Package-owned construction for heatmap figures and renderers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from bokeh.models import (
    ColorBar,
    ColumnDataSource,
    CustomJS,
    CustomJSHover,
    Div,
    HoverTool,
    LogColorMapper,
    Range1d,
    Select,
    TextInput,
    Toggle,
)
from bokeh.palettes import Cividis256, Inferno256, Magma256, Turbo256, Viridis256, brewer
from bokeh.plotting import figure

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.science.numeric import discrete_to_continuous
from aerosolstudio.themes.colors import THEME
from aerosolstudio.ui.tooltip_manager import TooltipManager

PALETTES = {
    "Turbo": Turbo256,
    "Viridis": Viridis256,
    "Magma": Magma256,
    "Inferno": Inferno256,
    "Cividis": Cividis256,
    "RdYlBu11": brewer["RdYlBu"][11][::-1],
    "RdYlBu": discrete_to_continuous(brewer["RdYlBu"][11], 256),
}

HEATMAP_HOVER_JS = """
        const data = datasrc.data;
        const geom = cb_data.geometry;
        const hx = geom.x;
        const hy = geom.y;
        const img   = data['img'][0];
        const x0    = data['x'][0];
        const y0    = data['y'][0];
        const dw    = data['dw'][0];
        const dh    = data['dh'][0];
        let nrows = data['nrows'] && data['nrows'].length ? data['nrows'][0] : 0;
        let ncols = data['ncols'] && data['ncols'].length ? data['ncols'][0] : 0;
        if (!nrows || !ncols) {
            nrows = img.length || 0;
            ncols = img[0] && img[0].length ? img[0].length : 0;
        }
        const fx = (hx - x0) / dw;
        const fy = (hy - y0) / dh;
        if (fx < 0 || fx > 1 || fy < 0 || fy > 1 || !nrows || !ncols) return;
        let col = Math.floor(fx * ncols);
        let row = Math.floor(fy * nrows);
        col = Math.max(0, Math.min(col, ncols-1));
        row = Math.max(0, Math.min(row, nrows-1));
        let val = NaN;
        if (Array.isArray(img[row]) || ArrayBuffer.isView(img[row])) {
            val = img[row][col];
        } else {
            val = img[row * ncols + col];
            if (!Number.isFinite(val)) {
                val = img[col * nrows + row];
            }
        }
        const d_nm = (hy * 1e9).toFixed(1);
        const t_ms = hx;
        const dt   = new Date(t_ms);
        const pad  = n => String(n).padStart(2,'0');
        const tstr = dt.getUTCFullYear()+'-'+pad(dt.getUTCMonth()+1)+'-'+pad(dt.getUTCDate())
                    +' '+pad(dt.getUTCHours())+':'+pad(dt.getUTCMinutes());
        const vstr = Number.isFinite(val) ? val.toExponential(2) : '—';
        info_div.text = (
            "<b>Time:</b> " + tstr +
            " &nbsp;|&nbsp; <b>Dp:</b> " + d_nm + " nm" +
            " &nbsp;|&nbsp; <b>dN/dlogDp:</b> " + vstr + " cm⁻³"
        );
        """


@dataclass(frozen=True)
class HeatmapControls:
    """Bokeh models used by the per-instrument heatmap area."""

    mapper: LogColorMapper
    colorbar: ColorBar
    pal_select: Select
    clim_low: TextInput
    clim_high: TextInput
    clim_auto: Toggle
    clim_auto_: Any
    fig: Any
    src_img: ColumnDataSource
    img_renderer: Any
    nm_formatter: CustomJSHover
    pointer_info_src: ColumnDataSource
    pointer_info_div: Any
    hover_img: HoverTool
    cb_toggle: Toggle
    cb_toggle_: Any


def build_heatmap_controls(
    name: str,
    *,
    palette_name: str = "RdYlBu",
    theme: Mapping[str, str] = THEME,
    palettes: Mapping[str, Sequence[str]] = PALETTES,
    callback_seam: CallbackSeam | None = None,
    on_x_range_start: Callable[..., Any] | None = None,
    on_x_range_end: Callable[..., Any] | None = None,
) -> HeatmapControls:
    """Build heatmap Bokeh models, recording callbacks through ``CallbackSeam``."""

    mapper = LogColorMapper(palette=palettes[palette_name], low=1000, high=100000)
    colorbar = ColorBar(
        color_mapper=mapper,
        location=(0, 0),
        orientation="horizontal",
        major_label_text_font_size="8pt",
        height=15,
        width=400,
    )

    pal_select = Select(value=palette_name, options=list(palettes.keys()), width=120)
    clim_low = TextInput(value="1000", width=140)
    clim_high = TextInput(value="100000", width=140)
    # Auto-recomputes on data/representation change while active; typing in
    # clim_low/clim_high flips it off so a manually chosen range sticks
    # instead of being overwritten on the next refresh (see studio.py's
    # _recompute_color_limits and its _clim_auto_updating guard).
    clim_auto = Toggle(label="🔓 Auto", active=True, width=90)

    fig = figure(
        height=370,
        y_axis_type="log",
        x_axis_type="datetime",
        x_range=Range1d(start=pd.to_datetime("1970-01-01"), end=pd.to_datetime("1970-01-02")),
        title=f"{name}  ·  Particle Size Distribution",
        sizing_mode="stretch_width",
        reset_policy="event_only",
        tools="",
        background_fill_color=theme["plot_bg"],
        border_fill_color=theme["panel"],
        outline_line_color=theme["plot_border"],
    )
    fig.title.text_font_size = "13px"
    fig.title.text_color = theme["text"]
    fig.title.text_font_style = "normal"
    fig.xaxis.axis_label = "Time (UTC)"
    fig.yaxis.axis_label = "Diameter (m)"
    fig.xaxis.axis_label_text_color = theme["text_secondary"]
    fig.yaxis.axis_label_text_color = theme["text_secondary"]
    fig.xaxis.major_label_text_color = theme["text_secondary"]
    fig.yaxis.major_label_text_color = theme["text_secondary"]
    fig.xaxis.axis_line_color = theme["border_strong"]
    fig.yaxis.axis_line_color = theme["border_strong"]
    fig.xgrid.grid_line_color = theme["border"]
    fig.ygrid.grid_line_color = theme["border"]
    fig.xgrid.grid_line_alpha = 0.5
    fig.ygrid.grid_line_alpha = 0.5

    src_img = ColumnDataSource(data={
        "img": [np.zeros((10, 10))],
        "x": [0],
        "y": [0],
        "dw": [1],
        "dh": [1],
        "nrows": [10],
        "ncols": [10],
    })
    img_renderer = fig.image(image="img", source=src_img, color_mapper=mapper)
    fig.add_layout(colorbar, "above")
    colorbar.visible = True

    nm_formatter = CustomJSHover(code="""
            return (value * 1e9).toFixed(2) + ' nm';
        """)
    pointer_info_src = ColumnDataSource(data=dict(text=["—"]))
    pointer_info_div = Div(
        text="<span style='color:#8aafc8;'>Hover over heatmap to see values</span>",
        sizing_mode="stretch_width",
        styles={
            "font-family": "monospace",
            "font-size": "11px",
            "background": theme["surface"],
            "border-left": f"3px solid {theme['accent2']}",
            "border-radius": "0 4px 4px 0",
            "padding": "5px 10px",
            "color": theme["text"],
            "min-height": "24px",
        },
    )
    hover_img = HoverTool(
        tooltips=None,
        mode="mouse",
        visible=True,
        renderers=[img_renderer],
    )
    hover_img.callback = CustomJS(
        args=dict(datasrc=src_img, info_div=pointer_info_div),
        code=HEATMAP_HOVER_JS,
    )
    fig.toolbar_location = "above"

    cb_toggle = Toggle(label="🟦", active=True, width=40)
    cb_toggle_ = TooltipManager.add_to_button(cb_toggle, "colorbar_toggle")
    clim_auto_ = TooltipManager.add_to_button(clim_auto, "color_limits_auto")

    if callback_seam is not None:
        callback_seam.on_change(
            pal_select,
            "value",
            lambda attr, old, new: setattr(mapper, "palette", palettes[new]),
            label="palette-select-value",
        )

        def _update_clim(attr: str, old: Any, new: Any) -> None:
            try:
                mapper.low = float(clim_low.value)
                mapper.high = float(clim_high.value)
            except ValueError:
                pass

        callback_seam.on_change(clim_low, "value", _update_clim, label="color-limit-low-value")
        callback_seam.on_change(clim_high, "value", _update_clim, label="color-limit-high-value")
        callback_seam.on_change(
            cb_toggle,
            "active",
            lambda attr, old, new: setattr(colorbar, "visible", new),
            label="colorbar-toggle-active",
        )
        callback_seam.on_change(
            clim_auto,
            "active",
            lambda attr, old, new: setattr(clim_auto, "label", "🔓 Auto" if new else "🔒 Locked"),
            label="color-limits-auto-active",
        )
        if on_x_range_start is not None:
            callback_seam.on_change(fig.x_range, "start", on_x_range_start, label="heatmap-range-start")
        if on_x_range_end is not None:
            callback_seam.on_change(fig.x_range, "end", on_x_range_end, label="heatmap-range-end")

    return HeatmapControls(
        mapper=mapper,
        colorbar=colorbar,
        pal_select=pal_select,
        clim_low=clim_low,
        clim_high=clim_high,
        clim_auto=clim_auto,
        clim_auto_=clim_auto_,
        fig=fig,
        src_img=src_img,
        img_renderer=img_renderer,
        nm_formatter=nm_formatter,
        pointer_info_src=pointer_info_src,
        pointer_info_div=pointer_info_div,
        hover_img=hover_img,
        cb_toggle=cb_toggle,
        cb_toggle_=cb_toggle_,
    )

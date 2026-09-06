"""Narrow safe renderer construction helpers.

These helpers construct only deterministic safe-domain Bokeh objects and return
grouped references. They do not register callbacks, access application state,
touch linked ranges, own lifecycle, or perform cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from bokeh.models import BoxAnnotation, ColorBar, ColumnDataSource, HoverTool, LogColorMapper, Span
from bokeh.plotting import figure


@dataclass(frozen=True)
class HeatmapRendererBundle:
    fig: Any
    src_img: Any
    mapper: Any
    colorbar: Any
    img_renderer: Any
    hover_img: Any


@dataclass(frozen=True)
class DistributionRendererBundle:
    fig_dist: Any
    src_dist: Any
    hover_dist: Any
    mode_multi_src: Any
    mode_fit_renderer: Any
    mode_sum_src: Any
    sum_line: Any


@dataclass(frozen=True)
class StripRendererBundle:
    fig_strip: Any
    src_strip_raw: Any
    src_strip_fit: Any
    src_strip_point: Any
    src_strip_fits: Any
    src_strip_points: Any
    poly_span: Any
    strip_time_marker: Any


def construct_heatmap_renderer_bundle(
    heatmap_cfg: dict[str, Any],
    heatmap_colorbar_config: Any,
    heatmap_axis_labels: Any,
    heatmap_grid_alpha: float,
    theme: dict[str, str],
) -> HeatmapRendererBundle:
    mapper = LogColorMapper(**heatmap_cfg["mapper_kwargs"])
    colorbar = ColorBar(
        color_mapper=mapper,
        location=heatmap_colorbar_config.location,
        orientation=heatmap_colorbar_config.orientation,
        major_label_text_font_size=heatmap_colorbar_config.major_label_text_font_size,
        height=heatmap_colorbar_config.height,
        width=heatmap_colorbar_config.width,
    )
    fig = figure(**heatmap_cfg["figure_kwargs"])
    fig.title.text_font_size = "13px"
    fig.title.text_color = theme["text"]
    fig.title.text_font_style = "normal"
    fig.xaxis.axis_label = heatmap_axis_labels.x
    fig.yaxis.axis_label = heatmap_axis_labels.y
    fig.xaxis.axis_label_text_color = theme["text_secondary"]
    fig.yaxis.axis_label_text_color = theme["text_secondary"]
    fig.xaxis.major_label_text_color = theme["text_secondary"]
    fig.yaxis.major_label_text_color = theme["text_secondary"]
    fig.xaxis.axis_line_color = theme["border_strong"]
    fig.yaxis.axis_line_color = theme["border_strong"]
    fig.xgrid.grid_line_color = theme["border"]
    fig.ygrid.grid_line_color = theme["border"]
    fig.xgrid.grid_line_alpha = heatmap_grid_alpha
    fig.ygrid.grid_line_alpha = heatmap_grid_alpha

    payload = heatmap_cfg["source_payload"]
    src_img = ColumnDataSource(data={
        "img": [np.full((payload.rows, payload.cols), payload.fill_value)],
        "x": [payload.x],
        "y": [payload.y],
        "dw": [payload.dw],
        "dh": [payload.dh],
        "nrows": [payload.rows],
        "ncols": [payload.cols],
    })
    img_renderer = fig.image(**heatmap_cfg["renderer_kwargs"], source=src_img, color_mapper=mapper)
    fig.add_layout(colorbar, heatmap_colorbar_config.layout_location)
    colorbar.visible = heatmap_colorbar_config.visible

    hover_config = heatmap_cfg["hover_config"]
    hover_img = HoverTool(
        tooltips=None,
        mode=hover_config.mode,
        visible=hover_config.visible,
        renderers=[img_renderer],
    )
    fig.toolbar_location = heatmap_cfg["tool_config"].toolbar_location
    return HeatmapRendererBundle(
        fig=fig,
        src_img=src_img,
        mapper=mapper,
        colorbar=colorbar,
        img_renderer=img_renderer,
        hover_img=hover_img,
    )


def construct_distribution_renderer_bundle(
    dist_cfg: dict[str, Any],
    nm_formatter: Any,
    theme: dict[str, str],
) -> DistributionRendererBundle:
    payloads = dist_cfg["source_payloads"]
    renderer_kwargs = dist_cfg["renderer_kwargs"]
    hover_config = dist_cfg["hover_config"]
    axis_defaults = dist_cfg["axis_defaults"]

    src_dist = ColumnDataSource(data=payloads.raw)
    fig_dist = figure(**dist_cfg["figure_kwargs"])
    fig_dist.title.text_font_size = "12px"
    fig_dist.title.text_color = theme["text"]
    fig_dist.title.text_font_style = "normal"
    fig_dist.xaxis.axis_label = axis_defaults.x_label
    fig_dist.yaxis.axis_label = axis_defaults.y_label
    fig_dist.xaxis.axis_label_text_color = theme["text_secondary"]
    fig_dist.yaxis.axis_label_text_color = theme["text_secondary"]
    fig_dist.xaxis.major_label_text_color = theme["text_secondary"]
    fig_dist.yaxis.major_label_text_color = theme["text_secondary"]
    fig_dist.xaxis.axis_line_color = theme["border_strong"]
    fig_dist.yaxis.axis_line_color = theme["border_strong"]
    fig_dist.xgrid.grid_line_color = theme["border"]
    fig_dist.ygrid.grid_line_color = theme["border"]
    fig_dist.xgrid.grid_line_alpha = axis_defaults.grid_alpha
    fig_dist.ygrid.grid_line_alpha = axis_defaults.grid_alpha
    fig_dist.line("x", "y", source=src_dist, **renderer_kwargs.raw_line)

    hover_dist = HoverTool(
        tooltips=list(hover_config.tooltips),
        formatters={hover_config.formatter_key: nm_formatter},
        mode=hover_config.mode,
        visible=hover_config.visible,
    )
    fig_dist.add_tools(hover_dist)

    mode_multi_src = ColumnDataSource(data=payloads.mode_multi)
    mode_fit_renderer = fig_dist.multi_line(
        xs="xs",
        ys="ys",
        color="color",
        source=mode_multi_src,
        **renderer_kwargs.mode_line,
    )
    mode_sum_src = ColumnDataSource(data=payloads.mode_sum)
    sum_line = fig_dist.line("x", "y", source=mode_sum_src, **renderer_kwargs.sum_line)
    return DistributionRendererBundle(
        fig_dist=fig_dist,
        src_dist=src_dist,
        hover_dist=hover_dist,
        mode_multi_src=mode_multi_src,
        mode_fit_renderer=mode_fit_renderer,
        mode_sum_src=mode_sum_src,
        sum_line=sum_line,
    )


def construct_strip_renderer_bundle(
    strip_renderer_spec: Any,
    strip_axis_config: Any,
    theme: dict[str, str],
    source_payload_builder: Any,
) -> StripRendererBundle:
    fig_strip = figure(**strip_renderer_spec.figure_kwargs)
    fig_strip.title.text_font_size = "12px"
    fig_strip.title.text_color = theme["text"]
    fig_strip.title.text_font_style = "normal"
    fig_strip.xaxis.axis_label = strip_axis_config.x_label
    fig_strip.yaxis.axis_label = strip_axis_config.y_label
    fig_strip.xaxis.axis_label_text_color = theme["text_secondary"]
    fig_strip.yaxis.axis_label_text_color = theme["text_secondary"]
    fig_strip.xaxis.major_label_text_color = theme["text_secondary"]
    fig_strip.yaxis.major_label_text_color = theme["text_secondary"]
    fig_strip.xaxis.axis_line_color = theme["border_strong"]
    fig_strip.yaxis.axis_line_color = theme["border_strong"]
    fig_strip.xgrid.grid_line_color = theme["border"]
    fig_strip.ygrid.grid_line_color = theme["border"]
    fig_strip.xgrid.grid_line_alpha = strip_axis_config.grid_alpha
    fig_strip.ygrid.grid_line_alpha = strip_axis_config.grid_alpha

    src_strip_raw = ColumnDataSource(data=source_payload_builder())
    src_strip_fit = ColumnDataSource(data=source_payload_builder())
    src_strip_point = ColumnDataSource(data=source_payload_builder())
    fig_strip.line("t", "y", source=src_strip_raw, **strip_renderer_spec.raw_line_kwargs)
    fig_strip.line("t", "y", source=src_strip_fit, **strip_renderer_spec.fit_line_kwargs)
    fig_strip.scatter("t", "y", source=src_strip_point, **strip_renderer_spec.fit_point_kwargs)

    src_strip_fits = ColumnDataSource(data=source_payload_builder("multi_line"))
    src_strip_points = ColumnDataSource(data=source_payload_builder("point"))
    fig_strip.multi_line(
        xs="xs",
        ys="ys",
        color="color",
        source=src_strip_fits,
        **strip_renderer_spec.multi_fit_kwargs,
    )
    fig_strip.scatter(
        "t",
        "y",
        color="color",
        source=src_strip_points,
        **strip_renderer_spec.multi_point_kwargs,
    )
    poly_span = BoxAnnotation(**strip_renderer_spec.polygon_span_kwargs)
    fig_strip.add_layout(poly_span)
    strip_time_marker = Span(**strip_renderer_spec.time_marker_kwargs)
    fig_strip.add_layout(strip_time_marker)
    return StripRendererBundle(
        fig_strip=fig_strip,
        src_strip_raw=src_strip_raw,
        src_strip_fit=src_strip_fit,
        src_strip_point=src_strip_point,
        src_strip_fits=src_strip_fits,
        src_strip_points=src_strip_points,
        poly_span=poly_span,
        strip_time_marker=strip_time_marker,
    )

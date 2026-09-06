"""Package-owned variable overlay runtime component."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pandas as pd
from bokeh.layouts import column, row
from bokeh.models import (
    Button,
    ColorPicker,
    ColumnDataSource,
    Div,
    LogAxis,
    Range1d,
    Select,
    Slider,
    TextInput,
    Toggle,
)
from scipy.signal import medfilt

from aerosolstudio.science import auto_range_log
from aerosolstudio.utils.time import time_value_to_ms


def sync_axis_color(axis: Any, color: str) -> None:
    """Synchronize overlay axis line, label, and tick colors."""
    for attr in [
        "axis_line_color",
        "axis_label_text_color",
        "major_label_text_color",
        "major_tick_line_color",
        "minor_tick_line_color",
    ]:
        setattr(axis, attr, color)


def _wrap_widget(tooltip_manager: Any, widget: Any, tooltip_key: str):
    if tooltip_manager is None:
        return widget
    return tooltip_manager.add_to_widget(widget, tooltip_key)


def _wrap_button(tooltip_manager: Any, button: Button, tooltip_key: str):
    if tooltip_manager is None:
        return button
    return tooltip_manager.add_to_button(button, tooltip_key)


class OverlayVarLine:
    """Own one variable overlay renderer, axis, widgets, callbacks, and state."""

    def __init__(
        self,
        fig: Any,
        df_getter: Callable[[], Any],
        overlay_var_methods: Mapping[str, Callable],
        line_id: str,
        *,
        color: str = "red",
        tooltip_manager: Any = None,
        diameter_labels: Mapping[str, tuple[tuple | None, tuple | None]] | None = None,
        on_method_changed: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.fig = fig
        self.df_getter = df_getter
        self.overlay_var_methods = overlay_var_methods
        self.line_id = line_id
        self.diameter_labels = diameter_labels or {}
        # Fires after every method switch (in addition to this line's own
        # _sync_diameter_controls/update) so the caller can react to a
        # change that isn't local to this one line - e.g. studio.py uses it
        # to show/hide the per-instrument "Interpolate PSD" toggle, which
        # only makes sense while at least one line on the instrument has a
        # PM method selected, not just this one.
        self._on_method_changed_cb = on_method_changed
        # Fires when update() can't produce a plot (blank/invalid diameter
        # box, or the method returned no data) - previously this failed
        # completely silently (an empty plot with zero explanation, e.g.
        # "Concentration" whose dmin/dmax boxes have no default and are
        # blank on first selection). The caller (studio.py) surfaces this on
        # the shared system status line; the plot button also flips to a
        # visible error state locally so it's clear *which* line failed.
        self._on_error_cb = on_error

        self.source = ColumnDataSource(data=dict(t=[], y=[]))
        fig.extra_y_ranges[line_id] = Range1d(start=1, end=100)
        self.line = fig.line(
            "t",
            "y",
            source=self.source,
            y_range_name=line_id,
            line_width=2,
            color=color,
            visible=True,
        )
        self.axis = LogAxis(y_range_name=line_id, visible=True)
        fig.add_layout(self.axis, "right")

        self.dmin_input = TextInput(placeholder="Dmin (nm)", width=80)
        self.dmax_input = TextInput(placeholder="Dmax (nm)", width=80)
        self.method_select = Select(
            value="Select Method",
            options=list(overlay_var_methods.keys()),
            width=160,
        )
        self.plot_button = Button(label="Plot", button_type="primary", width=60)
        self.toggle = Toggle(label="Show", active=True, width=60)
        self.color_picker = ColorPicker(color=color, width=60)
        self.style_select = Select(
            value="solid",
            options=["solid", "dashed", "dotted", "dotdash"],
            width=90,
        )
        self.thickness_slider = Slider(start=1, end=8, value=2, step=1, width=80)
        self.ymin_input = TextInput(placeholder="Y min", width=100)
        self.ymax_input = TextInput(placeholder="Y max", width=100)
        self.apply_y_btn = Button(label="Update var Y range", width=70)
        self.fit_y_btn = Button(label="Y", button_type="light", width=45)
        self.download_btn = Button(label="⬇", button_type="light", width=36)
        self.remove_btn = Button(label="X", button_type="danger", width=36)

        self.apply_y_btn.on_click(self._apply_manual_y_range)

        self.plot_button.on_click(lambda: self.update(auto_axis=True))
        self.method_select.on_change("value", self._on_method_changed)
        self._sync_diameter_controls()
        self.toggle.on_change("active", self._set_visible)
        self.color_picker.on_change("color", self._set_color)
        self.style_select.on_change("value", self._set_style)
        self.thickness_slider.on_change("value", self._set_thickness)

        row1 = row(
            Div(
                text=(
                    "<span style='font-size:10px;font-weight:700;color:#0072b2;'>"
                    f"{line_id}</span>"
                ),
                width=60,
            ),
            _wrap_widget(tooltip_manager, self.dmin_input, "var_dmin"),
            _wrap_widget(tooltip_manager, self.dmax_input, "var_dmax"),
            _wrap_widget(tooltip_manager, self.method_select, "var_method"),
            _wrap_button(tooltip_manager, self.plot_button, "var_plot"),
            _wrap_button(tooltip_manager, self.toggle, "var_toggle"),
            self.download_btn,
            self.remove_btn,
        )
        row2 = row(
            Div(text="<span style='font-size:9px;color:#888;'>Style:</span>", width=32),
            _wrap_widget(tooltip_manager, self.style_select, "var_style"),
            _wrap_widget(tooltip_manager, self.color_picker, "var_color"),
            self.thickness_slider,
            _wrap_widget(tooltip_manager, self.ymin_input, "var_ymin"),
            _wrap_widget(tooltip_manager, self.ymax_input, "var_ymax"),
            _wrap_button(tooltip_manager, self.apply_y_btn, "var_apply_y"),
            self.fit_y_btn,
        )
        self.controls = column(
            row1,
            row2,
            sizing_mode="stretch_width",
            styles={
                "border-left": "3px solid #56b4e9",
                "padding": "4px 6px",
                "margin-bottom": "4px",
                "background": "#f0f4f8",
                "border-radius": "0 4px 4px 0",
            },
        )

    def _visible_df(self, df: Any, max_rows: int = 5000):
        start = self.fig.x_range.start
        end = self.fig.x_range.end
        try:
            start = pd.to_datetime(time_value_to_ms(start), unit="ms")
            end = pd.to_datetime(time_value_to_ms(end), unit="ms")
            if start > end:
                start, end = end, start
            view = df.loc[(df.index >= start) & (df.index <= end)]
        except (TypeError, ValueError, OverflowError, KeyError) as exc:
            raise ValueError("Unable to compute visible overlay time range") from exc

        if view.empty:
            view = df
        if len(view) > max_rows:
            sample_idx = np.linspace(0, len(view) - 1, max_rows).astype(int)
            sample_idx = np.unique(sample_idx)
            view = view.iloc[sample_idx]
        return view

    @staticmethod
    def _display_series(t: np.ndarray, y: np.ndarray, max_points: int = 1800):
        if len(y) > max_points:
            sample_idx = np.linspace(0, len(y) - 1, max_points).astype(int)
            sample_idx = np.unique(sample_idx)
            t = t[sample_idx]
            y = y[sample_idx]
        return t, y

    _DEFAULT_DIAMETER_SPECS = (("Dmin (nm)", "nm", None), ("Dmax (nm)", "nm", None))

    def _diameter_specs(self) -> tuple[tuple | None, tuple | None]:
        """(dmin_spec, dmax_spec) for the current method - each is None (box
        unused) or (label, unit, default), unit being "nm" (an actual
        diameter, converted to metres) or "raw" (e.g. PM's density in
        g/cm^3 - passed through unconverted). Methods absent from
        diameter_labels (or "Select Method") fall back to the generic
        enabled nm/nm pair."""
        return self.diameter_labels.get(self.method_select.value, self._DEFAULT_DIAMETER_SPECS)

    def read_dmin_dmax_m(self) -> tuple[float, float] | None:
        """Parse dmin/dmax, skipping the parse entirely for whichever box is
        disabled/unused by the current method (see _sync_diameter_controls)
        - a disabled box is intentionally left blank, so requiring it to
        parse as a float would make every method that ignores dmin and/or
        dmax (Condensation Sink, ...) permanently fail to plot. A box whose
        spec says unit "raw" (PM's density) is passed through as a plain
        float with no nm-to-metres conversion - despite arriving through the
        dmin/dmax slots, it isn't a diameter. Returns None if a box that IS
        used for the current method fails to parse. Public because
        app/studio.py's export path (_download_overlay_var_line) needs the
        exact same parsing - see as_state()'s "read_dmin_dmax_m" entry."""
        dmin_spec, dmax_spec = self._diameter_specs()
        try:
            dmin = self._parse_diameter_box(self.dmin_input, dmin_spec)
            dmax = self._parse_diameter_box(self.dmax_input, dmax_spec)
        except ValueError:
            return None
        return dmin, dmax

    @staticmethod
    def _parse_diameter_box(widget: TextInput, spec) -> float:
        if spec is None:
            return 0.0
        _label, unit, _default = spec
        value = float(widget.value)
        return value * 1e-9 if unit == "nm" else value

    def _set_plot_button_ok(self) -> None:
        self.plot_button.button_type = "primary"
        self.plot_button.label = "Plot"

    def _set_plot_button_error(self, reason: str) -> None:
        self.plot_button.button_type = "danger"
        self.plot_button.label = "⚠"
        if self._on_error_cb is not None:
            self._on_error_cb(f"{self.line_id} ({self.method_select.value}): {reason}")

    def update(self, auto_axis: bool = True) -> None:
        self._set_plot_button_ok()
        df = self.df_getter()
        if df is None or self.method_select.value == "Select Method":
            return

        parsed = self.read_dmin_dmax_m()
        if parsed is None:
            self._set_plot_button_error(
                "enter a value in Dmin/Dmax before plotting"
            )
            return
        dmin, dmax = parsed

        method = self.overlay_var_methods[self.method_select.value]
        conc_df = method(self._visible_df(df), dmin, dmax)
        if conc_df is None or conc_df.empty:
            self._set_plot_button_error(
                "no data for this Dmin/Dmax range in the loaded dataset"
            )
            return

        t = pd.to_datetime(conc_df.index).to_numpy()
        raw_y = conc_df.values.flatten()
        kernel = min(5, len(raw_y))
        if kernel % 2 == 0:
            kernel = max(1, kernel - 1)
        y = medfilt(raw_y, kernel) if kernel >= 3 else raw_y

        t_display, y_display = self._display_series(t, y)
        self.source.data = dict(t=t_display, y=y_display)
        if not auto_axis:
            self.axis.axis_label = self.method_select.value
            sync_axis_color(self.axis, self.line.glyph.line_color)
            return

        manual_ymin = None
        manual_ymax = None
        try:
            if self.ymin_input.value.strip():
                manual_ymin = float(self.ymin_input.value)
        except ValueError:
            pass
        try:
            if self.ymax_input.value.strip():
                manual_ymax = float(self.ymax_input.value)
        except ValueError:
            pass

        auto_ymin, auto_ymax = auto_range_log(y_display)
        final_ymin = manual_ymin if manual_ymin is not None else auto_ymin
        final_ymax = manual_ymax if manual_ymax is not None else auto_ymax
        self.fig.extra_y_ranges[self.line_id].start = final_ymin
        self.fig.extra_y_ranges[self.line_id].end = final_ymax

        if manual_ymin is None:
            self.ymin_input.value = f"{auto_ymin:.1e}"
        if manual_ymax is None:
            self.ymax_input.value = f"{auto_ymax:.1e}"

        self.axis.axis_label = self.method_select.value
        sync_axis_color(self.axis, self.line.glyph.line_color)

    def refresh_view(self) -> None:
        self.update(auto_axis=False)

    def _apply_manual_y_range(self) -> None:
        """Apply the typed Y min/max boxes to the axis range.

        Deliberately a server-side click handler, not js_on_click: a
        client-side-only CustomJS here previously updated the Range1d
        object correctly but the renderer didn't reliably repaint from it
        without an unrelated redraw (e.g. toggling Show/Hide) forcing one -
        matches this app's established pattern of client-only range/style
        updates being unreliable (see the reverted pure-JS fit-method color
        swap in studio.py's update_fit_ui).
        """
        try:
            lo = float(self.ymin_input.value)
            hi = float(self.ymax_input.value)
        except (TypeError, ValueError):
            return
        if not (np.isfinite(lo) and np.isfinite(hi) and lo < hi):
            return
        if self.line_id not in self.fig.extra_y_ranges:
            return
        self.fig.extra_y_ranges[self.line_id].start = lo
        self.fig.extra_y_ranges[self.line_id].end = hi

    def fit_y(self) -> None:
        """Fit this overlay's Y-axis (and the Y min/max boxes) to the data
        currently visible on the shared time axis.

        Recomputes from a fresh _visible_df() rather than reusing whatever
        is already in self.source.data, so panning/zooming the time axis
        and then clicking this button reflects the *current* view, not
        whatever was visible at the last Plot click. Always overwrites the
        Y min/max boxes - unlike update()'s auto-fit, which respects a
        manually-typed value so it doesn't fight the user on every replot,
        this button's entire purpose is "reset to auto".
        """

        if self.line_id not in self.fig.extra_y_ranges:
            return

        df = self.df_getter()
        if df is None or self.method_select.value == "Select Method":
            return
        parsed = self.read_dmin_dmax_m()
        if parsed is None:
            return
        dmin, dmax = parsed

        method = self.overlay_var_methods[self.method_select.value]
        conc_df = method(self._visible_df(df), dmin, dmax)
        if conc_df is None or conc_df.empty:
            return

        y = conc_df.to_numpy(dtype=float).flatten()
        y = y[np.isfinite(y) & (y > 0)]
        if len(y) == 0:
            return

        ymin_log, ymax_log = auto_range_log(y)
        self.fig.extra_y_ranges[self.line_id].start = ymin_log
        self.fig.extra_y_ranges[self.line_id].end = ymax_log
        self.ymin_input.value = f"{ymin_log:.1e}"
        self.ymax_input.value = f"{ymax_log:.1e}"

    def _on_method_changed(self, attr: str, old: str, new: str) -> None:
        self._sync_diameter_controls()
        self.update(auto_axis=True)
        if self._on_method_changed_cb is not None:
            self._on_method_changed_cb()

    def _sync_diameter_controls(self) -> None:
        """Relabel/disable the dmin/dmax boxes for whatever method is
        selected - see diameter_labels (overlay_var_diameter_labels /
        PM_DIAMETER_LABELS). A box with no effect for the current method
        (e.g. both are ignored by "Condensation Sink") is disabled and says
        so, instead of always showing a "Dmin (nm)" / "Dmax (nm)" pair
        that's misleading for methods that don't actually use a diameter
        range. A box whose spec carries a default (PM's density, so a fresh
        line always has a sane density to compute with instead of silently
        refusing to plot until the user notices and fills it in) gets that
        default pre-filled the moment it becomes relevant, but only if it's
        currently blank - never overwrites a value already typed in."""
        dmin_spec, dmax_spec = self._diameter_specs()
        for widget, spec in ((self.dmin_input, dmin_spec), (self.dmax_input, dmax_spec)):
            if spec is None:
                widget.placeholder = "(not used)"
                widget.disabled = True
                continue
            label, _unit, default = spec
            widget.placeholder = label
            widget.disabled = False
            if default is not None and not widget.value.strip():
                widget.value = default

    def _set_visible(self, _attr: str, _old: bool, new: bool) -> None:
        self.line.visible = new
        self.axis.visible = new

    def _set_color(self, _attr: str, _old: str, new: str) -> None:
        self.line.glyph.line_color = new
        sync_axis_color(self.axis, new)

    def _set_style(self, _attr: str, _old: str, new: str) -> None:
        self.line.glyph.line_dash = new

    def _set_thickness(self, _attr: str, _old: int, new: int) -> None:
        self.line.glyph.line_width = new

    def destroy(self, fig: Any) -> None:
        """Detach this overlay's renderer, axis, and y-range from a figure."""

        self.line.visible = False
        self.axis.visible = False

        if self.line in fig.renderers:
            fig.renderers.remove(self.line)
        if self.axis in fig.right:
            fig.right.remove(self.axis)
        fig.extra_y_ranges.pop(self.line_id, None)

    def as_state(self) -> dict[str, Any]:
        """Return the overlay record shape consumed by the canonical app."""
        return {
            "source": self.source,
            "line": self.line,
            "axis": self.axis,
            "line_id": self.line_id,
            "destroy": self.destroy,
            "fit_y_btn": self.fit_y_btn,
            "download_btn": self.download_btn,
            "remove_btn": self.remove_btn,
            "controls": self.controls,
            "update": self.update,
            "refresh_view": self.refresh_view,
            "fit_y": self.fit_y,
            "read_dmin_dmax_m": self.read_dmin_dmax_m,
            "method_select": self.method_select,
            "dmin_input": self.dmin_input,
            "dmax_input": self.dmax_input,
            "color_picker": self.color_picker,
            "style_select": self.style_select,
            "thickness_slider": self.thickness_slider,
            "toggle": self.toggle,
            "ymin_input": self.ymin_input,
            "ymax_input": self.ymax_input,
        }


def make_overlay_var_line(
    fig: Any,
    df_getter: Callable[[], Any],
    overlay_var_methods: Mapping[str, Callable],
    line_id: str,
    *,
    color: str = "red",
    tooltip_manager: Any = None,
    diameter_labels: Mapping[str, tuple[tuple | None, tuple | None]] | None = None,
    on_method_changed: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Create one package-owned concentration overlay record."""
    return OverlayVarLine(
        fig,
        df_getter,
        overlay_var_methods,
        line_id,
        color=color,
        tooltip_manager=tooltip_manager,
        diameter_labels=diameter_labels,
        on_method_changed=on_method_changed,
        on_error=on_error,
    ).as_state()

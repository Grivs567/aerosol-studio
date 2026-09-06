"""Package-owned AerosolStudio application controller."""

"""
Aerosol Studio - Interactive visualization and analysis tool for aerosol particle size distribution data
"""




import os
import json
import base64
import io
import copy
import html
import threading
from datetime import datetime
from functools import partial

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.path import Path


from bokeh.io import curdoc
from bokeh.layouts import column, row, Spacer

from bokeh.models import (
    AutocompleteInput, BoxEditTool, BoxSelectTool, BoxZoomTool, Button, Checkbox,
    ColumnDataSource, CustomJS,
    Div, FreehandDrawTool, LassoSelectTool,
    PanTool, Range1d, ResetTool, Scatter, Select, Span,
    SaveTool, TabPanel, Tabs, TextInput, Toggle, InlineStyleSheet,
    WheelZoomTool
)
from bokeh.models.dom import HTML
from bokeh.plotting import figure
from bokeh.events import DoubleTap, PanEnd, Reset, SelectionGeometry
from bokeh.palettes import Category10

from aerosolstudio.app.cancellation import FitCancellationToken
from aerosolstudio.utils.tz import (
    DEFAULT_TIMEZONE,
    detect_local_timezone,
    is_valid_timezone,
    list_timezones,
    localize_naive_index_to_utc,
)
from aerosolstudio.science import distribution as psd_distribution
from aerosolstudio.science.pm import PM_DIAMETER_LABELS, build_pm_methods
from aerosolstudio.utils.units import (
    DATA_TYPE_OPTIONS,
    DEFAULT_DATA_TYPE,
    DEFAULT_DIAMETER_UNIT,
    DIAMETER_UNIT_OPTIONS,
    detect_diameter_unit_from_attrs,
    diameter_unit_to_metres_factor,
    validate_diameter_magnitude,
)
from aerosolstudio.app.loader import LoaderOverlay
from aerosolstudio.app.fit_line_lifecycle import (
    clear_all_fit_line_renderers,
    clear_fit_line_renderer,
    clear_fit_line_renderers_for_polygon,
    shift_fit_line_renderer_indices_after_delete,
)
from aerosolstudio.app.overlay import make_overlay_var_line
from aerosolstudio.app.overlay_manager import next_overlay_var_id
from aerosolstudio.app.polygon_selector import (
    select_polygon_from_dropdown,
    update_polygon_dropdown,
    update_polygon_label,
)
from aerosolstudio.app.sidebar import SidebarToggle
from aerosolstudio.instrument.heatmap_controls import PALETTES
from aerosolstudio.instrument.state import live_instrument_state
from aerosolstudio.io.session_schema import default_meta, normalize_session_payload
from aerosolstudio.science.overlay_var import overlay_var_diameter_labels, overlay_var_methods
from aerosolstudio.science.numeric import auto_range_log, discrete_to_continuous  # noqa: F401
from aerosolstudio.themes.colors import THEME
from aerosolstudio.ui.cards import create_card, create_color_badge, create_info_box
from aerosolstudio.ui.tooltip_manager import TOOLTIPS, TooltipManager
from aerosolstudio.utils.time import datetime_index_to_epoch_ms, ms_to_datetime, time_value_to_ms
from aerosolstudio.fitting.registry import run_fit
from aerosolstudio.fitting.types import FitRequest, FitSnapshot, bind_fit_type_methods

import aerosol.fitting as afi


class AerosolStudio:
    # Fit methods temporarily hidden from user-facing selectors (Fit Method
    # dropdown, Fit Line Using dropdown, diameter-strip checkboxes) while
    # remaining fully functional everywhere else - self.FIT_TYPES itself,
    # saved ROI files, keyboard shortcuts, glyph renderers, and badge colors
    # are all still built from the complete self.FIT_TYPES (see the loops in
    # __init__/create_instrument_entry/_restore_fit_points callers) and never
    # consult this set. See _visible_fit_types(). Meant to be temporary -
    # set back to an empty set to re-expose in the UI.
    HIDDEN_FIT_TYPES = {"maxconc"}

    def __init__(self, doc=None):
        self._doc = doc or curdoc()

        self.FIT_TYPES = bind_fit_type_methods(self)
        
        # Create automatic reverse mappings
        self.SRC_TO_FIT = {}  # Maps src_suffix -> fit_key
        self.FIT_KEY_TO_SRC = {}  # Maps fit_key -> src_suffix

        
        for fit_key, props in self.FIT_TYPES.items():
            self.SRC_TO_FIT[props["src_suffix"]] = fit_key
            self.FIT_KEY_TO_SRC[fit_key] = props["src_suffix"]

        
    

        # ========== STATE ==============
        self.apply_global_styles()
        self._doc.add_root(self.global_css)
        self.instruments = {} # Master registry       
        self.cache = {} 
        # FitCancellationToken wraps a threading.Event, the correct primitive
        # for inter-thread signalling. .request() signals cancellation,
        # .is_requested() checks it, .reset() resets it. The dict approach was
        # unreliable because the GIL doesn't guarantee dict reads/writes are
        # atomic in all Python implementations.
        self.cancel_flag = FitCancellationToken()
        
        self.layout = None        
        self.sidebar = None
        self.tabs = Tabs(tabs=[])
        self.center_container = column(sizing_mode="stretch_both")        
        self.create_widgets()
        # Single global keyboard listener, created once here.
        self._init_keyboard_listener()
        self.init_default_instruments() # Initialize default CSV and NetCDF dataset panels
        self.update_master_options()
        
        self.tabs.tabs = self._generate_tabs()

        if self.show_tab_manager.active:
            self.tab_manager_container.children = [self.build_tab_manager()]
        self.last_active_instrument = None # track which dataset panel was clicked last            

        self.setup_layout()

    def _visible_fit_types(self):
        """self.FIT_TYPES minus HIDDEN_FIT_TYPES - the only thing the three
        user-facing fit-type selectors (Fit Method dropdown, Fit Line Using
        dropdown, diameter-strip checkboxes) should ever be built from.
        Nothing else in the app should call this - every other consumer of
        FIT_TYPES needs the complete set regardless of what's hidden (glyph/
        renderer creation, saved-ROI restore, keyboard shortcuts, badge
        colors), so they keep reading self.FIT_TYPES directly."""
        return {
            key: props
            for key, props in self.FIT_TYPES.items()
            if key not in self.HIDDEN_FIT_TYPES
        }

    @staticmethod
    def _format_mcc_results_html(results):
        if not results:
            return (
                "<div style='font-size:11px; color:#8aafc8; line-height:1.55;'>"
                "No MCC runs yet. Select an ROI, set Fit Dp min/max, then run MCC."
                "</div>"
            )

        rows = []
        for idx, entry in enumerate(results, start=1):
            ok = bool(entry.get("ok"))
            status = "OK" if ok else "Failed"
            status_color = "#2ecc71" if ok else "#ff6b6b"
            gr = entry.get("growth_rate_nm_per_hr")
            gr_txt = f"{gr:.2f}" if isinstance(gr, (int, float)) else "-"
            dmin = entry.get("dmin_nm")
            dmax = entry.get("dmax_nm")
            range_txt = (
                f"{dmin:.1f}-{dmax:.1f}"
                if isinstance(dmin, (int, float)) and isinstance(dmax, (int, float))
                else "-"
            )
            region = html.escape(str(entry.get("region_label") or "-"))
            reason = html.escape(str(entry.get("reason") or ""))
            tau = entry.get("tau_window_hr")
            smoothing = entry.get("smoothing_window_hr")
            divisions = entry.get("number_of_divisions")
            # Older stored runs (from before these were exposed) won't have
            # these keys at all - show "-" rather than crash formatting them.
            params_txt = (
                f"{tau:g}h / {smoothing:g}h / {divisions}"
                if isinstance(tau, (int, float))
                and isinstance(smoothing, (int, float))
                and isinstance(divisions, (int, float))
                else "-"
            )
            rows.append(
                "<tr>"
                f"<td>{idx}</td>"
                f"<td style='color:{status_color}; font-weight:700;'>{status}</td>"
                f"<td>{gr_txt}</td>"
                f"<td>{range_txt}</td>"
                f"<td>{params_txt}</td>"
                f"<td>{region}</td>"
                f"<td>{reason}</td>"
                "</tr>"
            )

        return (
            "<table style='width:100%; border-collapse:collapse; font-size:11px; line-height:1.45;'>"
            "<thead><tr style='color:#8aafc8; text-align:left;'>"
            "<th>#</th><th>Status</th><th>GR<br>(nm/hr)</th><th>Dp<br>(nm)</th>"
            "<th>Tau / Smooth /<br>Divisions</th><th>Region</th><th>Reason</th>"
            "</tr></thead>"
            "<tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )

    def _refresh_mcc_panel(self, name):
        inst = self.instruments.get(name)
        if not inst or "mcc_results_div" not in inst:
            return
        inst["mcc_results_div"].text = self._format_mcc_results_html(inst.get("mcc_results", []))

    def _run_mcc_fit(self, name):
        inst = self.instruments[name]
        if "fit_type_select" in inst:
            options = {
                option[0] if isinstance(option, tuple) else option
                for option in inst["fit_type_select"].options
            }
        else:
            options = set()
        if "mcc" in options:
            inst["fit_type_select"].value = "mcc"
        self.update_mcc_diagnostic(name)
        self.run_fit_by_type(name, "mcc")

    def _init_keyboard_listener(self):
        """
        Create ONE shared keyboard source + ONE JS listener for the whole app.
        Previously each instrument created its own document.addEventListener, causing
        N duplicate Python callbacks per keypress (one per instrument).
        Called once from __init__, after create_widgets().
        """
        self.key_src = ColumnDataSource(data=dict(key=[]))
        self.key_src.on_change("data", self.on_keypress)

        self._key_listener_js = CustomJS(
            args=dict(source=self.key_src),
            code="""
            // Guard: attach only once using a window flag (idempotent)
            if (window._aerosolKeyListenerAttached) return;
            window._aerosolKeyListenerAttached = true;

            document.addEventListener('keydown', function(event) {
                const loweredKey = String(event.key || '').toLowerCase();
                if (
                    loweredKey === 'x' ||
                    event.key === 'Delete' ||
                    event.key === 'Backspace' ||
                    loweredKey === 'z'
                ) {
                    // Ignore shortcuts when user is typing or editing a widget.
                    // Bokeh widgets render inside nested shadow roots, so
                    // event.target here would be retargeted to an outer shadow
                    // host (never the real <input>). composedPath()[0] gives the
                    // true originating element, piercing shadow boundaries.
                    const path = (typeof event.composedPath === 'function') ? event.composedPath() : [];
                    const target = path.length ? path[0] : (event.target || null);
                    const tag = ((target || {}).tagName || '').toUpperCase();
                    const isEditable =
                        tag === 'INPUT' ||
                        tag === 'TEXTAREA' ||
                        tag === 'SELECT' ||
                        Boolean(target && target.isContentEditable) ||
                        Boolean(target && target.closest && target.closest(
                            'input, textarea, select, [contenteditable="true"], .bk-input'
                        ));
                    if (isEditable) return;

                    source.data = { key: [...source.data.key, event.key] };
                    source.change.emit();
                    event.preventDefault();
                }
            });
            """
        )

    def apply_global_styles(self):
        """Apply global CSS styles to improve aesthetics"""
        self.global_css = InlineStyleSheet(css=f"""
            /* ── Global reset ── */
            .bk-root {{
                background-color: {THEME['bg']};
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 13px;
                color: {THEME['text']};
            }}

            /* ── Sidebar ── */
            .bk-root .sidebar {{
                background: linear-gradient(180deg, {THEME['sidebar']} 0%, #162535 100%);
                border-right: 2px solid {THEME['border_strong']};
                box-shadow: 3px 0 12px rgba(0,0,0,0.15);
            }}

            /* ── Top-level tabs header ── */
            .bk-root .bk-tabs-header {{
                background-color: {THEME['surface']};
                border-bottom: 2px solid {THEME['accent']};
            }}
            .bk-root .bk-tab {{
                background-color: {THEME['surface']};
                color: {THEME['text_secondary']};
                border: 1px solid {THEME['border']};
                border-bottom: none;
                padding: 7px 16px;
                font-weight: 500;
                font-size: 13px;
                border-radius: 6px 6px 0 0;
                margin-right: 3px;
                transition: background 0.15s;
            }}
            .bk-root .bk-tab:hover {{
                background-color: {THEME['accent2']};
                color: #fff;
            }}
            .bk-root .bk-tab.bk-active {{
                background-color: {THEME['accent']};
                color: #fff;
                border-color: {THEME['accent']};
                font-weight: 600;
            }}

            /* ── Buttons ── */
            .bk-root .bk-btn {{
                border-radius: 5px;
                font-weight: 500;
                font-size: 12px;
                transition: all 0.15s ease;
                box-shadow: 0 1px 3px rgba(0,0,0,0.12);
                border: 1px solid transparent;
            }}
            .bk-root .bk-btn:hover {{
                transform: translateY(-1px);
                box-shadow: 0 3px 8px rgba(0,0,0,0.18);
                filter: brightness(1.08);
            }}
            .bk-root .bk-btn:active {{
                transform: translateY(0);
                filter: brightness(0.95);
            }}
            .bk-root .bk-btn-primary {{
                background: linear-gradient(135deg, {THEME['accent']}, {THEME['accent_hover']});
                color: #fff;
            }}
            .bk-root .bk-btn-success {{
                background: linear-gradient(135deg, {THEME['success']}, #007a58);
                color: #fff;
            }}
            .bk-root .bk-btn-warning {{
                background: linear-gradient(135deg, {THEME['warning']}, #c4880a);
                color: #fff;
            }}
            .bk-root .bk-btn-danger {{
                background: linear-gradient(135deg, {THEME['error']}, #b04800);
                color: #fff;
            }}
            .bk-root .bk-btn-light {{
                background: {THEME['surface']};
                color: {THEME['text']};
                border-color: {THEME['border']};
            }}

            /* ── Input fields ── */
            .bk-root .bk-input {{
                background-color: {THEME['panel']};
                border: 1px solid {THEME['border_strong']};
                color: {THEME['text']};
                border-radius: 4px;
                padding: 5px 9px;
                font-size: 12px;
                transition: border-color 0.15s, box-shadow 0.15s;
            }}
            .bk-root .bk-input:focus {{
                border-color: {THEME['accent']};
                box-shadow: 0 0 0 2px rgba(0,114,178,0.18);
                outline: none;
            }}
            .bk-root select.bk-input {{
                padding: 4px 8px;
            }}

            /* ── Card containers ── */
            .aerosol-card {{
                background: {THEME['panel']};
                border-radius: 8px;
                border: 1px solid {THEME['border']};
                box-shadow: 0 1px 4px rgba(0,0,0,0.07);
                padding: 14px 16px;
                margin-bottom: 10px;
            }}
            .aerosol-card-title {{
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.9px;
                text-transform: uppercase;
                color: {THEME['accent']};
                border-bottom: 1px solid {THEME['border']};
                padding-bottom: 5px;
                margin-bottom: 10px;
            }}

            /* ── Sidebar card titles ── */
            .sidebar-card-title {{
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.9px;
                text-transform: uppercase;
                color: {THEME['accent2']};
                border-bottom: 1px solid rgba(255,255,255,0.12);
                padding-bottom: 5px;
                margin-bottom: 8px;
            }}

            /* ── Scrollbars ── */
            .bk-root ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
            .bk-root ::-webkit-scrollbar-track {{ background: {THEME['surface']}; border-radius: 3px; }}
            .bk-root ::-webkit-scrollbar-thumb {{ background: {THEME['border_strong']}; border-radius: 3px; }}
            .bk-root ::-webkit-scrollbar-thumb:hover {{ background: {THEME['accent']}; }}

            /* ── Slider ── */
            .bk-root .bk-slider-horizontal {{
                background-color: {THEME['surface']};
                border-radius: 4px;
                padding: 6px 8px;
            }}

            /* ── Loader overlay ── */
            .loader-overlay {{
                position: fixed; top: 0; left: 0;
                width: 100%; height: 100%;
                background: rgba(30,45,61,0.65);
                z-index: 9999; display: none;
                justify-content: center; align-items: center;
                flex-direction: column;
                backdrop-filter: blur(4px);
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}

            /* ── Help button ── */
            .bk-root .bk-btn-light[title] {{
                opacity: 0.75;
            }}
            .bk-root .bk-btn-light[title]:hover {{
                opacity: 1;
            }}

            /* ── Status / result divs ── */
            .status-box {{
                background: {THEME['surface']};
                border-left: 3px solid {THEME['accent']};
                border-radius: 0 4px 4px 0;
                padding: 8px 10px;
                font-size: 12px;
                color: {THEME['text']};
            }}
            .system-box {{
                background: {THEME['surface']};
                border-left: 3px solid {THEME['success']};
                border-radius: 0 4px 4px 0;
                padding: 6px 10px;
                font-size: 11px;
                color: {THEME['text']};
            }}
        """)
        
    def _create_card(self, title, widgets, sidebar=False):
        return create_card(THEME, title, widgets, sidebar)

    def _create_info_box(self, label, value, bg_color=None, sidebar=False):
        return create_info_box(THEME, label, value, bg_color, sidebar)

    def _create_color_badge(self, color):
        return create_color_badge(color)

    def create_widgets(self):

        # 1. Loading & Dataset Panel Management
        self.new_inst_name = TooltipManager.add_to_widget(TextInput(title="Dataset Name", value="Dataset_1", width=150), "instrument_name")
        self.new_inst_type = TooltipManager.add_to_widget(
            Select(
                title="File Format",
                value="csv",
                options=[("csv", "CSV"), ("nais(.nc)", "NetCDF (.nc)")],
                width=120,
            ),
            "instrument_type",
        )
        self.btn_add_inst = Button(label="➕ Add Dataset", button_type="success", width=150)
        self.btn_add_inst_ = TooltipManager.add_to_button(self.btn_add_inst, "add_instrument")


        # 2. View & Axis Logic
        self.view_mode = TooltipManager.add_to_widget(Select(title="Layout", value="Tabs", options=["Tabs", "Combined (Stacked)"]), "view_mode")
        self.link_axes = Toggle(label="🔓 Link X-Axes", active=False, button_type="primary", width=60)   
        self.sync_btn = Button(label="🔄 Match Time Ranges", button_type="warning", width=80)
        self.sync_btn_ = TooltipManager.add_to_button(self.sync_btn, "match_time_ranges")

        # 3. Heatmap Appearance (New Feature)
        self.pal_select = TooltipManager.add_to_widget(Select(title="Color Palette", value="RdYlBu", options=list(PALETTES.keys())), "color_palette")
        self.clim_low = TooltipManager.add_to_widget(TextInput(value="1000", title="Color Min", width=110), "color_min")
        self.clim_high = TooltipManager.add_to_widget(TextInput(value="100000", title="Color Max", width=110), "color_max")
        
        # 4. Loading
        self.species_sel = TooltipManager.add_to_widget(Select(title="NetCDF Variable", value="neg_ions", 
                                                   options=["neg_ions", "pos_ions", "neg_particles", "pos_particles"]), "nais_species")


        # 5. ROI Buttons
        self.btn_save_roi = Button(label="Save ROIs", button_type="primary", width=120)
        self.btn_load_roi = Button(label="Load ROIs", button_type="primary", width=120)
        
        #6. Div
              
        self.system_div = Div(
            text="<span style='color:#009e73;font-weight:600;'>● Ready</span>",
            height=72, sizing_mode="stretch_width",
            styles={
                "overflow-y": "auto",
                "color": THEME["text_light"],
                "background": "rgba(255,255,255,0.06)",
                "padding": "8px 10px",
                "border-left": f"3px solid {THEME['success']}",
                "border-radius": "0 4px 4px 0",
                "font-size": "11px",
                "line-height": "1.5",
            }
        )

        self.status_div = Div(
            text="<span style='opacity:0.6'>No dataset active</span>",
            height=100,
            sizing_mode="stretch_width",
            styles={
                "overflow-y": "auto",
                "background": "rgba(255,255,255,0.05)",
                "color": THEME["text_light"],
                "padding": "8px 10px",
                "border-left": f"3px solid {THEME['accent2']}",
                "border-radius": "0 4px 4px 0",
                "font-size": "11px",
                "line-height": "1.6",
            }
        )

        self.hotkey_div = Div(
            text="""
            <div style='font-size:10px; color:rgba(255,255,255,0.45);
                        padding:6px 0; line-height:1.85;'>
                <b style='color:rgba(255,255,255,0.65); font-size:10px;
                           text-transform:uppercase; letter-spacing:0.7px;'>
                    ⌨ Keyboard Shortcuts</b><br>
                <kbd style='background:rgba(255,255,255,0.12); border-radius:3px;
                             padding:1px 5px; font-size:10px;'>x</kbd>
                &nbsp;Delete the <i>selected polygon</i> + all its fit points<br>
                <kbd style='background:rgba(255,255,255,0.12); border-radius:3px;
                             padding:1px 5px; font-size:10px;'>Del</kbd> / <kbd
                       style='background:rgba(255,255,255,0.12); border-radius:3px;
                             padding:1px 5px; font-size:10px;'>Backspace</kbd>
                &nbsp;Delete <i>currently box/lasso-selected fit points</i>
                       (use Box Select or Lasso first)<br>
                <kbd style='background:rgba(255,255,255,0.12); border-radius:3px;
                             padding:1px 5px; font-size:10px;'>z</kbd>
                &nbsp;Undo last Del — restores deleted fit points
            </div>""",
            sizing_mode="stretch_width"
        )
                                    
        #fit mode number 
        
        self.fit_modes_input = TooltipManager.add_to_widget(TextInput(value="1", title="Num Modes", width=80), "num_modes")
        
        self.master_select = TooltipManager.add_to_widget(Select(title="X-Axis Master", value="Auto", options=["Auto"], width=120 ),"master_axis")

        self.tab_manager_container = column(Spacer(height=1))

        self.show_tab_manager = Toggle(
                    label="📑 Hide Tab Manager",
                    active=True,
                    button_type="primary",
                    width=200
                )
        self.show_tab_manager.on_click(self.toggle_tab_manager)

        self.tab_manager_container.children = [self.build_tab_manager()] 
        
        from bokeh.models import Checkbox

        self.save_df_checkbox = Checkbox(
            label="Also export data CSV",
            active=False, width=140,
        )
        self.load_df_checkbox = Checkbox(
            label="Also load paired CSV",
            active=True, width=140,
        )

        # Loader overlay: owned by aerosolstudio.app.loader.LoaderOverlay.
        # cancel_btn and div are accessed via self.loader.cancel_btn / self.loader.div.
        self.loader = LoaderOverlay(THEME, self.cancel_flag, self.request_cancel_fit)
        self.cancel_btn = self.loader.cancel_btn
        self.quit_btn = Button(label="Quit Server", button_type="danger", width=180)
        self.quit_btn.on_click(self.request_server_shutdown)

        # ── Sidebar toggle button (pure JS, zero Python round-trip) ──
        self.sidebar_toggle = SidebarToggle(self._toggle_sidebar)
        self.sidebar_toggle_btn = self.sidebar_toggle.button
        

        
        # Callbacks

        self.species_sel.on_change("value", self.update_species)
        self.view_mode.on_change('value', self.update_view_mode)
        self.link_axes.on_change('active', self.toggle_axis_linking)
        self.sync_btn.on_click(self.match_time_ranges)
        self.btn_add_inst.on_click(self.add_new_instrument_callback)
        self.pal_select.on_change('value', self.update_visuals)
        self.clim_low.on_change('value', self.update_visuals)
        self.clim_high.on_change('value', self.update_visuals)
        self.btn_save_roi.on_click(self.save_rois)
        self.btn_load_roi.on_click(self.load_rois)    
        
        # loader_div alias: self.loader.div is the canonical Bokeh Div owned by LoaderOverlay.
        # setup_layout() references self.loader_div; this alias keeps that unchanged.
        self.loader_div = self.loader.div

    def show_loader(self, message="Processing...", submessage="Please wait"):
        self.loader.show(message, submessage)
        if getattr(self, "cancel_bar", None) is not None:
            self.cancel_bar.visible = True

    def _update_loader_progress(self, message):
        self.loader.update_progress(message)

    def hide_loader(self):
        self.loader.hide()
        if getattr(self, "cancel_bar", None) is not None:
            self.cancel_bar.visible = False

    def _toggle_sidebar(self):
        """Toggle sidebar visibility by swapping it in/out of the main row.
        This is the only 100% reliable approach — JS DOM manipulation gets
        wiped by Bokeh re-renders; this goes through Bokeh's model system.
        """
        self.sidebar_toggle.toggle(getattr(self, "_main_row", None), self.sidebar)

    def request_cancel_fit(self):
        """Called by the real Bokeh Button — sets flag, fit thread checks it each bin."""
        self.cancel_flag.request()   # signals the fit thread to stop
        self.system_div.text = "⚠ Cancel requested — stopping after current bin…"


    def request_server_shutdown(self):
        """Stop the Bokeh server from inside the GUI when running via bokeh serve.

        Requires two clicks: the first only arms it (relabels the button and
        auto-disarms itself after 4s via _disarm_quit_confirm) so a single
        accidental click - this button lives in the always-visible top bar
        now, right next to the sidebar toggle, precisely so it's no longer
        buried at the bottom of a long scrollable sidebar - can't instantly
        kill the whole session with zero warning. The second click within
        that window is the real confirmation and proceeds exactly as before.
        """
        if getattr(self, "_server_shutdown_requested", False):
            self.system_div.text = "<b>System:</b> Shutdown already requested."
            return

        if not getattr(self, "_quit_confirm_armed", False):
            self._quit_confirm_armed = True
            self.quit_btn.label = "Click again to Quit"
            self.system_div.text = (
                "<b>System:</b> Click Quit Server again within 4s to confirm - "
                "this closes the app immediately."
            )
            curdoc().add_timeout_callback(self._disarm_quit_confirm, 4000)
            return

        self._server_shutdown_requested = True
        self.quit_btn.disabled = True
        self.quit_btn.label = "Closing..."
        self.system_div.text = "<b>System:</b> Quit requested. Closing Bokeh server..."
        if hasattr(self, "cancel_flag"):
            self.cancel_flag.request()
        curdoc().add_next_tick_callback(lambda: os._exit(0))

    def _disarm_quit_confirm(self):
        """Revert the armed Quit Server button back to its normal label if
        the second (confirming) click never came within the 4s window."""
        if getattr(self, "_server_shutdown_requested", False):
            return
        self._quit_confirm_armed = False
        self.quit_btn.label = "Quit Server"

    def init_default_instruments(self):
        
        self.create_instrument_entry("CSV_1", "csv")
        self.create_instrument_entry("NetCDF_1", "nais(.nc)")



    def create_instrument_entry(self, name, ftype):
        """Standardized way to create an instrument object and its plot."""
        
        from aerosolstudio.events.callbacks import CallbackSeam
        from aerosolstudio.instrument.heatmap_controls import build_heatmap_controls

        heatmap_seam = CallbackSeam()
        heatmap_controls = build_heatmap_controls(
            name,
            palette_name=self.pal_select.value,
            theme=THEME,
            palettes=PALETTES,
            callback_seam=heatmap_seam,
            on_x_range_start=lambda attr, old, new, n=name: self._schedule_heatmap_view_refresh(n),
            on_x_range_end=lambda attr, old, new, n=name: self._schedule_heatmap_view_refresh(n),
        )
        heatmap_seam.bind()
        self._mark_heatmap_range_refresh_bound(name, heatmap_controls.fig.x_range)

        # Manually editing Min/Max means the user wants that range to stick -
        # flip Auto off so _recompute_color_limits() stops overwriting it.
        # Skipped while _recompute_color_limits() itself is the one writing
        # the value (see its _clim_auto_updating guard).
        def _lock_clim_auto_on_manual_edit(attr, old, new, n=name):
            if getattr(self, "_clim_auto_updating", False):
                return
            inst = self.instruments.get(n)
            if inst is not None and inst["clim_auto"].active:
                inst["clim_auto"].active = False

        heatmap_controls.clim_low.on_change("value", _lock_clim_auto_on_manual_edit)
        heatmap_controls.clim_high.on_change("value", _lock_clim_auto_on_manual_edit)

        mapper = heatmap_controls.mapper
        colorbar = heatmap_controls.colorbar
        pal_select = heatmap_controls.pal_select
        clim_low = heatmap_controls.clim_low
        clim_high = heatmap_controls.clim_high
        clim_auto = heatmap_controls.clim_auto
        clim_auto_ = heatmap_controls.clim_auto_
        fig = heatmap_controls.fig
        src_img = heatmap_controls.src_img
        img_renderer = heatmap_controls.img_renderer
        nm_formatter = heatmap_controls.nm_formatter
        pointer_info_src = heatmap_controls.pointer_info_src
        pointer_info_div = heatmap_controls.pointer_info_div
        hover_img = heatmap_controls.hover_img
        cb_toggle = heatmap_controls.cb_toggle
        cb_toggle_ = heatmap_controls.cb_toggle_

        # Live heatmap representation toggle (dN/dlogDp <-> N <-> surface <->
        # volume density). Display-layer only: transforms what's drawn in
        # refresh_heatmap_view()/update_image()'s color-limit calc. The
        # canonical inst["df"] (and therefore every fit, ROI mask, and
        # growth-rate calc that reads it) is never touched by this toggle -
        # see _apply_heatmap_view_transform().
        heatmap_view_select = TooltipManager.add_to_widget(
            Select(
                title="Heatmap View",
                value="dN/dlogDp (raw)",
                options=[
                    "dN/dlogDp (raw)",
                    "Number Concentration (N)",
                    "Surface Density (dS/dlogDp)",
                    "Volume Density (dV/dlogDp)",
                ],
                width=190,
            ),
            "heatmap_view",
        )
        heatmap_view_select.on_change(
            "value", lambda attr, old, new, n=name: self._on_heatmap_view_changed(n)
        )

        poly_src = ColumnDataSource(data=dict(xs=[], ys=[]))
        poly_draw = fig.patches('xs', 'ys', source=poly_src, fill_alpha=0.3, color="white")
        rect_src = ColumnDataSource(data=dict(x=[], y=[], width=[], height=[]))
        rect_draw = fig.rect(
            x="x", y="y",
            width="width", height="height",
            source=rect_src,
            fill_alpha=0.12,
            fill_color=THEME["warning"],
            line_color=THEME["warning"],
            line_width=2,
        )
        poly_bg_src = ColumnDataSource(data=dict(xs=[], ys=[], fill_color=[], fill_alpha=[], line_color=[], line_alpha=[]))
        zero_image = np.zeros((10, 10))
        zero_image_mask = np.empty(zero_image.shape, dtype=np.uint32)
        view = zero_image_mask.view(dtype=np.uint8).reshape((zero_image.shape[0], zero_image.shape[1], 4))
        view.fill(0)
        
        mask_src = ColumnDataSource(data={'img': [zero_image_mask], 'x':[pd.to_datetime("1970-01-01")], 'y':[0], 'dw':[pd.Timedelta(days=1)], 'dh':[1]})

        poly_bg_renderer = fig.patches(
            'xs', 'ys',
            source=poly_bg_src,
            fill_color="fill_color",
            fill_alpha="fill_alpha",
            line_color="line_color",
        )
        fig.image_rgba(image="img", source=mask_src,  x="x", y="y", dw="dw", dh="dh",  level="overlay")


    

       
       
        path_input = TooltipManager.add_to_widget(
            TextInput(placeholder="Enter file path or browse...", width=400),
            "file_path"
        )
        browse_btn = Button(label="📁 Browse", button_type="primary", width=100)
        # Source timezone: the raw timestamps in any CSV/NetCDF file are just
        # naive clock readings with no reliable way to know what timezone
        # they were recorded in (CSV never carries this; NetCDF sometimes
        # does but not consistently). Pre-fill with the machine's own local
        # timezone as a starting guess, but always require the user to see
        # and (if needed) correct it before Load actually applies it - see
        # load_from_path()/handle_file_upload(), which localize the raw
        # index to this zone and convert to UTC once, at load time.
        tz_input = TooltipManager.add_to_widget(
            AutocompleteInput(
                title="Source Timezone",
                value=detect_local_timezone(),
                completions=list_timezones(),
                min_characters=1,
                width=170,
                case_sensitive=False,
            ),
            "source_timezone",
        )
        # Diameter unit + data-type declaration: mirrors the Source Timezone
        # pattern above. Neither CSV headers nor NetCDF attrs reliably state
        # whether diameter columns are nm/um/m or whether values are
        # dN/dlogDp vs per-bin number concentration N - see utils/units.py.
        # Defaults assume the common case (nm, dN/dlogDp); NetCDF attrs are
        # checked as a best-effort cross-check at load time (load_from_path),
        # but the user-visible box always wins and is always editable.
        diam_unit_input = TooltipManager.add_to_widget(
            Select(
                title="Diameter Unit",
                value=DEFAULT_DIAMETER_UNIT,
                options=DIAMETER_UNIT_OPTIONS,
                width=80,
            ),
            "diameter_unit",
        )
        data_type_input = TooltipManager.add_to_widget(
            Select(
                title="Data Type",
                value=DEFAULT_DATA_TYPE,
                options=DATA_TYPE_OPTIONS,
                width=170,
            ),
            "data_type",
        )
        load_btn = Button(label="Load", button_type="default", width=80)
        self._style_load_button(load_btn, "idle")

        def browse_file():
            from tkinter import Tk, filedialog
            root = Tk()
            file_path = filedialog.askopenfilename(title=f"Select file for {name}")
            root.withdraw()
            root.destroy()
            if file_path:
                path_input.value = file_path

        browse_btn.on_click(browse_file)
        path_input.on_change("value", lambda attr, old, new: self._style_load_button(
            load_btn,
            "pending" if str(new).strip() else "idle"
        ))
        load_btn.on_click(lambda n=name, path=path_input: self.load_from_path(n, path.value))
        

        


        from aerosolstudio.instrument.distribution_controls import build_distribution_controls
        distribution_controls = build_distribution_controls(
            name,
            theme=THEME,
            fit_metadata=self.FIT_TYPES,
        )
        src_dist = distribution_controls.src_dist
        fig_dist = distribution_controls.fig_dist
        hover_dist = distribution_controls.hover_dist

        # Store ALL fit-related items in a structured way
        fit_sources = {}      # src_suffix -> ColumnDataSource
        fit_renderers = {}    # src_suffix -> renderer
        dist_sources = dict(distribution_controls.dist_sources)     # dist_src_suffix -> ColumnDataSource

        mode_multi_src = distribution_controls.mode_multi_src
 
        mode_fit_renderer = distribution_controls.mode_fit_renderer
        
        toggle_modes = distribution_controls.toggle_modes

        toggle_modes.on_change("active", lambda a, o, n: setattr(mode_fit_renderer, "visible", n))
        toggle_modes_ = distribution_controls.toggle_modes_

        
        mode_sum_src = distribution_controls.mode_sum_src
        sum_line = distribution_controls.sum_line
        toggle_sum = distribution_controls.toggle_sum
        toggle_sum.on_change("active", lambda a, o, n: setattr(sum_line, "visible", n))
        toggle_sum_ = distribution_controls.toggle_sum_
                            

        poly_src.on_change('data', lambda attr, old, new, n=name: self.on_poly_added(n, attr, old, new))
        fig.on_event('tap', lambda e, n=name: self.on_tap_instrument(n, e))
        fig.on_event(DoubleTap, lambda e, n=name: self.finish_poly_draw(n))
        fig.on_event(PanEnd, lambda e, n=name: self.finish_rect_draw(n))
        fig.on_event(SelectionGeometry, lambda e, n=name: self.on_roi_box_selected(n, e))


        
        # SINGLE loop to create everything
        for fit_key, props in self.FIT_TYPES.items():
            # 1. Heatmap source and glyph
            src = ColumnDataSource(data=dict(t=[], d=[]))
            fit_sources[props["src_suffix"]] = src
            
            glyph = Scatter(
                x="t", y="d", 
                size=props["size"], 
                marker=props["marker"], 
                fill_color=props["fill_color"], 
                line_color=props["line_color"]
            )
            renderer = fig.add_glyph(src, glyph)
            fit_renderers[props["src_suffix"]] = renderer
            
        # 3. ROI drawing and fit-point selection tools.
        draw_tool = FreehandDrawTool(renderers=[poly_draw])

        # BoxEditTool: drag a rectangle to create a rectangular ROI.
        # PolyDrawTool backend callbacks are kept for compatibility with older
        # sessions/code paths, but the visible toolbar exposes only freehand and box ROI drawing.
        from bokeh.models import PolyDrawTool
        vertex_src = ColumnDataSource(dict(x=[], y=[]))
        vertex_renderer = fig.scatter(
            "x", "y", source=vertex_src,
            size=10, color=THEME["warning"],
            line_color=THEME["accent"], line_width=1.5,
            fill_alpha=0.8,
        )
        poly_draw_tool = PolyDrawTool(
            renderers=[poly_draw],
            vertex_renderer=vertex_renderer,
        )
        rect_draw_tool = BoxEditTool(
            renderers=[rect_draw],
            dimensions="both",
            num_objects=0,
        )

        # Box ROI creation uses BoxSelectTool exclusively: a single plain drag
        # commits a rectangle straight into the polygon list, the same way
        # FreehandDrawTool commits a freehand path. It owns no renderers; the
        # ROI is built from its SelectionGeometry payload in
        # on_roi_box_selected() -> on_rect_roi_added().
        #
        # BoxEditTool (rect_draw_tool/rect_src below) used to be a second,
        # separate box-drawing tool (shift+drag to create). Its commit path
        # relies on fig.toolbar.active_drag, which this app never sets, so it
        # silently drops every box. Rather than fix a second, redundant tool,
        # it's been dropped from the toolbar; the backing code is left in
        # place (still covered by tests) pending outright removal.
        roi_box_tool = BoxSelectTool(
            renderers=[],
            persistent=False,
            description="Draw box ROI (drag)",
        )

        lasso_select = LassoSelectTool(renderers=list(fit_renderers.values()))

        fig.add_tools(
            PanTool(),
            WheelZoomTool(),
            BoxZoomTool(),
            draw_tool,
            roi_box_tool,
            lasso_select,
            ResetTool(),
            SaveTool(),
            hover_img,
        )
        # rect_draw_tool (BoxEditTool) is intentionally NOT added to the
        # toolbar - see comment above roi_box_tool's construction. It still
        # exists as a model (inst["rect_draw_tool"], set further below) so
        # existing tests that assert on its shape keep passing until the
        # dedicated cleanup commit removes it outright.
        # --- FITTING BUTTONS ---
        # === NEW DROPDOWN INTERFACE ===
        # Create fit type dropdown
        fit_type_options = list(self._visible_fit_types().keys())
        fit_type_select = Select(
            title="Fit Method",
            value=fit_type_options[0],
            options=[(key, self.FIT_TYPES[key]["display_name"]) for key in fit_type_options],
            width=140
        )

        initial_key = fit_type_select.value
        initial_props = self.FIT_TYPES[initial_key]

        # Create color badge that updates with selection - must track
        # fit_type_select's actual (possibly HIDDEN_FIT_TYPES-shifted)
        # default rather than a hardcoded key, or it shows the wrong color
        # the moment the default stops being "maxconc".
        badge = self._create_color_badge(initial_props["color"])

        # Create single Run and Clear buttons
        btn_fit = Button(label="▶ Run Fit", button_type="default", width=90)
        btn_clear = Button(label="🗑 Clear", button_type="default", width=90)

        # Add tooltips using existing keys
        #btn_fit_ = TooltipManager.add_to_button(btn_fit, "fit_maxconc")
        #btn_clear_ = TooltipManager.add_to_button(btn_clear, "clear_max")

        fit_button_css = """
        .bk-btn {
            background-color: var(--fit-color) !important;
            border-color: var(--fit-color) !important;
            color: #111111 !important;
            font-weight: 700 !important;
        }
        """
        btn_fit.stylesheets = [fit_button_css]
        btn_clear.stylesheets = [fit_button_css]
        btn_fit.styles = {"--fit-color": initial_props["color"]}
        btn_clear.styles = {"--fit-color": initial_props["color"]}

        btn_fit_ = TooltipManager.add_to_button( btn_fit,  initial_props["tooltip_fit"] )
        btn_clear_ = TooltipManager.add_to_button(btn_clear, initial_props["tooltip_clear"])



        # Attempted a pure client-side CustomJS for this (matching
        # SidebarToggle's zero-round-trip pattern) since the color swap is
        # the one thing a user visibly sees flash the instant they pick a
        # method. Reverted: live testing couldn't confirm js_on_change
        # actually fired reliably (Select's DOM <option> value differs from
        # its Bokeh-model value in a way that made verification genuinely
        # ambiguous), and the underlying "problem" - a Python round-trip on
        # localhost - is normally imperceptible anyway. Not worth shipping
        # an unverified interaction against an unconfirmed benefit; this
        # plain on_change callback is the proven-working version.
        def update_fit_ui(attr, old, new):
            props = self.FIT_TYPES[new]

            color_style = {"--fit-color": props["color"]}
            btn_fit.styles = color_style
            btn_clear.styles = color_style
            btn_fit_line.styles = color_style

            badge.text = f"""
            <div style='
                width: 12px;
                height: 12px;
                background-color: {props['color']};
                border-radius: 50%;
                display: inline-block;
                border: 1px solid white;
                box-shadow: 0 0 4px rgba(0,0,0,0.3);
            '></div>
            """

            btn_fit_.children[1].tooltip.content = HTML(
                TOOLTIPS[self.FIT_TYPES[new]["tooltip_fit"]]
            )
            btn_clear_.children[1].tooltip.content = HTML(
                TOOLTIPS[self.FIT_TYPES[new]["tooltip_clear"]]
            )

        fit_type_select.on_change("value", update_fit_ui)

        # Button callbacks
        btn_fit.on_click(lambda: self.run_fit_by_type(name, fit_type_select.value))
        btn_clear.on_click(lambda: self.clear_fit_by_type(name, fit_type_select.value))


        fit_line_options = [
            (key, props["display_name"])
            for key, props in self._visible_fit_types().items()
        ]
        fit_line_source_raw = Select(
            title="Fit Line Using",
            options=fit_line_options,
            value=fit_line_options[0][0] if fit_line_options else "maxconc",
            width=140,
        )
        fit_line_source = TooltipManager.add_to_widget(fit_line_source_raw, "gr_source")
               

        fit_line_poly_raw = Select(title="Polygon", options=["Selected"], value="Selected", width=100)
        fit_line_poly_raw.on_change("value", lambda a, o, n, nm=name: self._on_polygon_dropdown_change(nm, a, o, n))
        fit_line_poly = TooltipManager.add_to_widget(fit_line_poly_raw, "gr_polygon")

        btn_fit_line = Button(label="📈 Fit Line", button_type="primary", width=100)
        
        btn_fit_line.stylesheets = [fit_button_css]
        btn_fit_line.styles = {"--fit-color": initial_props["color"]}
        
        btn_fit_line_ = TooltipManager.add_to_button(btn_fit_line, "fit_line_button")

                
        btn_fit_line.on_click(lambda n=name: self.fit_line_in_polygon(n))

        # Create text inputs for diameter range
        gr_dmin_input  = TooltipManager.add_to_widget(TextInput(
            title="Fit Dp min (nm)", 
            value="3.0", 
            width=100,
            placeholder="min (nm)"
        ), "gr_dmin")
        
        gr_dmax_input = TooltipManager.add_to_widget(TextInput(
            title="Fit Dp max (nm)", 
            value="25.0", 
            width=100,
            placeholder="max (nm)"
        ), "gr_dmax")
        
        reset_btn = Button(label="🗑 Clear gr line", button_type="default", width=100)

        def clear_dp_limit():
            self.clear_fit_line(name)

        reset_btn.on_click(clear_dp_limit)
        reset_btn_ = TooltipManager.add_to_button(reset_btn, "gr_clear")


        # Create a row with all controls
        dp_controls = row(
            #Div(text="<b>Dp limit:</b>", styles={"color": THEME["accent"], "margin": "5px"}),
            gr_dmin_input,
            gr_dmax_input,
            reset_btn_,
            sizing_mode="stretch_width"
        )

        # Cross-correlation (MCC) growth rate used to be a standalone
        # button here with its own "Whole dataset / Selected ROI" toggle
        # (defaulting to "Whole dataset", and even in "Selected ROI" mode
        # only cropping by a raw time bounding box on the unmasked
        # dataframe - not the actual polygon shape). It's now just another
        # "Fit Method" option (see FIT_TYPES["mcc"] / fit_cross_correlation)
        # so it always runs on the same properly ROI-masked data as every
        # other method, via the same Run Fit button and Fit Dp min/max
        # fields (gr_dmin_input/gr_dmax_input above) - no separate control.

        fig.on_event(Reset, partial(self.on_reset, name=name))
        
        # key_src and the JS keydown listener are created ONCE in __init__
        # (see self._init_keyboard_listener()) and shared across all dataset panels.
        # We still attach the JS to each figure's tap event so the listener script
        # runs once in the browser when the page first renders any figure.
        if hasattr(self, '_key_listener_js'):
            fig.js_on_event('tap', self._key_listener_js)

    



        overlay_var_lines = []
        overlay_var_container = column(
            sizing_mode="stretch_width",
            styles={
                "max-height": "280px",
                "overflow-y": "auto",
                "overflow-x": "auto",
            }
        )
        btn_add_overlay_var = Button(label="➕ Add Var Line", button_type="success", width=200)       
        btn_add_overlay_var_ = TooltipManager.add_to_button(btn_add_overlay_var, "add_overlay_var_line")

        # Off by default: PM is computed only from what was actually
        # measured (truncating silently at the data's own max diameter, same
        # as always). On, a PM cutoff past the measured range has its tail
        # extrapolated via a lognormal-mode fit (Whitby 1978; Hinds 1999) -
        # see science/distribution.py's extend_distribution_to_diameter and
        # science/pm.py's build_pm_methods(interpolate_getter=...).
        # Only relevant while at least one overlay line on this instrument
        # has a PM method selected - starts hidden (no lines exist yet) and
        # is toggled by _sync_pm_interpolate_visibility, called whenever any
        # line's method changes or a line is added/removed.
        pm_interpolate_toggle = Toggle(label="↗ Interpolate PSD", active=False, width=130)
        pm_interpolate_input = TooltipManager.add_to_button(pm_interpolate_toggle, "pm_interpolate")
        pm_interpolate_input.visible = False
        pm_data_max_div = Div(
            text="<span style='font-size:10px; color:#8aafc8;'>Data max: —</span>",
            width=140,
        )

        btn_add_overlay_var.on_click(lambda n=name: self.add_overlay_var_line(n))

        results_div = Div(
            text="<span style='color:#8aafc8; font-size:11px;'>No results yet — run a fit to see output.</span>",
            css_classes=["qa-results-div"],
            height=160,
            sizing_mode="stretch_width",
            styles={
                "overflow-y": "auto",
                "background-color": THEME["surface"],
                "color": THEME["text"],
                "padding": "10px 12px",
                "border": f"1px solid {THEME['border']}",
                "border-left": f"3px solid {THEME['accent']}",
                "border-radius": "0 5px 5px 0",
                "font-family": "'JetBrains Mono', 'Fira Mono', 'Consolas', monospace",
                "font-size": "11.5px",
                "line-height": "1.6",
            }
        )
               
        

        poly_label_input = TooltipManager.add_to_widget(TextInput(title="Polygon Label", placeholder="Enter label...", width=150), "polygon_label")
        btn_update_label = Button(label="Update Label", button_type="primary", width=120)
       
        btn_update_label.on_click(lambda n=name: self.update_polygon_label(n))
        


        # ----- Diameter Strip Plot -----

        from aerosolstudio.instrument.strip_controls import build_strip_controls
        strip_controls = build_strip_controls(
            name,
            theme=THEME,
            fit_metadata=self._visible_fit_types(),
        )
        fig_strip = strip_controls.fig_strip
        src_strip_raw = strip_controls.src_strip_raw
        src_strip_fit = strip_controls.src_strip_fit
        src_strip_point = strip_controls.src_strip_point
        strip_diameter_input = strip_controls.strip_diameter_input
        btn_plot_strip = strip_controls.btn_plot_strip
        chk_show_fit = strip_controls.chk_show_fit
        chk_follow_cursor = strip_controls.chk_follow_cursor
        btn_plot_strip.on_click(lambda n=name: self.update_strip_plot(n))
        fit_checkboxes = strip_controls.fit_checkboxes
        fit_checkboxes.on_change('active', lambda attr, old, new: self.update_strip_plot(name))
        fit_overlay_legend = strip_controls.fit_overlay_legend
        src_strip_fits = strip_controls.src_strip_fits
        src_strip_points = strip_controls.src_strip_points
        poly_span = strip_controls.poly_span
        strip_time_marker = strip_controls.strip_time_marker

        mcc_results_div = Div(
            text=self._format_mcc_results_html([]),
            height=110,
            sizing_mode="stretch_width",
            styles={
                "overflow-y": "auto",
                "background-color": THEME["surface"],
                "color": THEME["text"],
                "padding": "10px 12px",
                "border": f"1px solid {THEME['border']}",
                "border-radius": "5px",
            },
        )
        btn_run_mcc = Button(label="Run MCC", button_type="danger", width=120)
        btn_run_mcc.on_click(lambda n=name: self._run_mcc_fit(n))
        btn_run_mcc_ = TooltipManager.add_to_button(btn_run_mcc, "run_mcc")

        # Method parameters - previously hardcoded to compute_cross_
        # correlation_gr's defaults (which match the published method) with
        # no way to change them. nan_threshold is deliberately NOT exposed
        # here - see growth_rate.py's NaN-threshold footgun note; it stays
        # fixed at the safe 1.0 (effectively disabled) that module already
        # defaults to. (aerosol-functions 0.1.16 merged the old
        # row_threshold/col_threshold into that single nan_threshold kwarg.)
        mcc_tau_window_input = TooltipManager.add_to_widget(
            TextInput(title="Tau window (hr)", value="22.0", width=110),
            "mcc_tau_window",
        )
        mcc_smoothing_window_input = TooltipManager.add_to_widget(
            TextInput(title="Smoothing window (hr)", value="3.0", width=110),
            "mcc_smoothing_window",
        )
        mcc_num_divisions_input = TooltipManager.add_to_widget(
            TextInput(title="Dp divisions", value="1", width=90),
            "mcc_num_divisions",
        )

        mcc_diag_src_low = ColumnDataSource(data=dict(t=[], y=[]))
        mcc_diag_src_high = ColumnDataSource(data=dict(t=[], y=[]))
        fig_mcc_diag = figure(
            height=280,
            x_axis_type="datetime",
            title=f"{name}  ·  MCC diagnostic",
            sizing_mode="stretch_width",
            tools="pan,box_zoom,wheel_zoom,save,reset",
            background_fill_color=THEME["plot_bg"],
            border_fill_color=THEME["panel"],
            outline_line_color=THEME["plot_border"],
        )
        fig_mcc_diag.title.text_font_size = "12px"
        fig_mcc_diag.title.text_color = THEME["text"]
        fig_mcc_diag.title.text_font_style = "normal"
        fig_mcc_diag.xaxis.axis_label = "Time (UTC)"
        fig_mcc_diag.yaxis.axis_label = "Normalized signal"
        for axis in (fig_mcc_diag.xaxis, fig_mcc_diag.yaxis):
            axis.axis_label_text_color = THEME["text_secondary"]
            axis.major_label_text_color = THEME["text_secondary"]
            axis.axis_line_color = THEME["border_strong"]
        fig_mcc_diag.xgrid.grid_line_color = THEME["border"]
        fig_mcc_diag.ygrid.grid_line_color = THEME["border"]
        fig_mcc_diag.xgrid.grid_line_alpha = 0.35
        fig_mcc_diag.ygrid.grid_line_alpha = 0.35
        fig_mcc_diag.line(
            "t", "y", source=mcc_diag_src_low,
            line_width=2, color="#2a9d8f", legend_label="lower Dp",
        )
        fig_mcc_diag.line(
            "t", "y", source=mcc_diag_src_high,
            line_width=2, color="#e76f51", legend_label="upper Dp",
        )
        fig_mcc_diag.legend.location = "top_left"
        fig_mcc_diag.legend.click_policy = "hide"
        mcc_diag_marker = Span(
            location=None,
            dimension="height",
            line_color=THEME["accent"],
            line_dash="dashed",
            line_width=1.5,
        )
        fig_mcc_diag.add_layout(mcc_diag_marker)

    

            



        self.instruments[name] = {
            # ---- plots ----
            "fig": fig,
            "pointer_info_div": pointer_info_div,
            "mapper": mapper,
            "colorbar": colorbar,
            "cb_toggle": cb_toggle,
            "cb_toggle_": cb_toggle_,            
            "pal_select": pal_select,
            "clim_low": clim_low,
            "clim_high": clim_high,
            "clim_auto": clim_auto,
            "clim_auto_": clim_auto_,
            "heatmap_view_select": heatmap_view_select,
            "src_img": src_img,
            "_heatmap_refresh_pending": False,

            # ---- data ----
            "df": None,
            "type": ftype,
            #"file_input": file_input,
            
            "path_input": path_input,
            "browse_btn": browse_btn,
            "tz_input": tz_input,
            "diam_unit_input": diam_unit_input,
            "data_type_input": data_type_input,
            "load_btn": load_btn,

            # distribution plot
            "src_dist": src_dist,
            "fig_dist": fig_dist,

            # ROI / fits
            "poly_src": poly_src,
            "poly_bg_src": poly_bg_src,
            "rect_src": rect_src,
            "rect_draw_tool": rect_draw_tool,
            "roi_box_tool": roi_box_tool,
            "_last_rect_roi_signature": None,
            "polygons": [],
            "selected_poly": None,

            # overlays
            "mask_src": mask_src,
            "mode_multi_src": mode_multi_src,

            "mode_sum_src": mode_sum_src,
            "mode_sum_line": sum_line,
            "toggle_sum": toggle_sum,
            "toggle_modes": toggle_modes,
            "toggle_modes_": toggle_modes_,
            "toggle_sum_": toggle_sum_,
            "fit_type_select": fit_type_select,
            "fit_badge": badge,
            "btn_fit": btn_fit,
            "btn_fit_": btn_fit_,
            "btn_clear": btn_clear,
            "btn_clear_": btn_clear_,



            
            "mode_fit_renderer": mode_fit_renderer,

            # Store all sources by their registry names
            **fit_sources,      # Unpack: "maxconc_src": src, etc.
            **dist_sources,     # Unpack: "maxconc_dist_src": dist_src, etc.
            
            # Store renderers for tool management
            "fit_renderers": fit_renderers,
            
            # Keep the registry reference for lookups
            "fit_types": self.FIT_TYPES,

            
            "results_div": results_div,
            
            "overlay_var_lines": overlay_var_lines,
            "overlay_var_container": overlay_var_container,
            "btn_add_overlay_var": btn_add_overlay_var,
            "btn_add_overlay_var_": btn_add_overlay_var_,
            "pm_interpolate_toggle": pm_interpolate_toggle,
            "pm_interpolate_input": pm_interpolate_input,
            "pm_data_max_div": pm_data_max_div,
            "undo_stack": [],
            
            "img_renderer": img_renderer,
            "fit_line_source": fit_line_source,
            "fit_line_source_raw": fit_line_source_raw,
            "fit_line_poly": fit_line_poly,
            "fit_line_srcs": {},
            "fit_line_renderers": {},


            "fit_dp_controls" : dp_controls,
            "fit_dmin_input" : gr_dmin_input,
            "fit_dmax_input" : gr_dmax_input,
            "btn_fit_line_": btn_fit_line_,
            "btn_fit_line": btn_fit_line,
            "reset_btn": reset_btn,
            "fit_line_poly_raw": fit_line_poly_raw,

            "mcc_results": [],  # per-instrument Cross-Correlation results
            # (MCC) results; the old cross-instrument "Growth Rate Analysis"
            # tab that used to read this list was removed - each result is
            # now shown directly in this instrument's own results_div only.
            "mcc_results_div": mcc_results_div,
            "btn_run_mcc": btn_run_mcc,
            "btn_run_mcc_": btn_run_mcc_,
            "fig_mcc_diag": fig_mcc_diag,
            "mcc_diag_src_low": mcc_diag_src_low,
            "mcc_diag_src_high": mcc_diag_src_high,
            "mcc_diag_marker": mcc_diag_marker,
            "mcc_tau_window_input": mcc_tau_window_input,
            "mcc_smoothing_window_input": mcc_smoothing_window_input,
            "mcc_num_divisions_input": mcc_num_divisions_input,
            
            "btn_update_label": btn_update_label,
            "poly_label_input": poly_label_input,
            
            
            "fig_strip": fig_strip,
            "src_strip_raw": src_strip_raw,
            "src_strip_fit": src_strip_fit,
            "src_strip_point": src_strip_point,
            "strip_diameter_input": strip_diameter_input,
            "btn_plot_strip": btn_plot_strip,
            
            "chk_show_fit": chk_show_fit,
            "chk_follow_cursor": chk_follow_cursor,
            "fit_checkboxes" : fit_checkboxes, 
            "fit_overlay_legend": fit_overlay_legend,
            "src_strip_fits" : src_strip_fits,
            "src_strip_points" : src_strip_points,
            "poly_span": poly_span,
            # Must come from strip_controls.fit_checkbox_keys (not a fresh
            # list(self.FIT_TYPES...)) - this maps CheckboxGroup.active index
            # -> fit_key (see update_strip_plot's active_indices/fit_keys
            # loop), so it has to be built from the exact same (possibly
            # HIDDEN_FIT_TYPES-filtered) mapping the checkboxes themselves
            # were rendered from, or indices silently point at the wrong
            # fit type the moment the two sets differ.
            "fit_checkbox_keys": list(strip_controls.fit_checkbox_keys),
            "strip_time_marker" : strip_time_marker,

        }
        

  
    def update_polygon_label(self, name):
        inst = self.instruments[name]
        self.system_div.text = update_polygon_label(inst, name)

    def clear_fit_line(self, name):
        inst = self.instruments[name]

        # --- check selection ---
        if inst["selected_poly"] is None:
            self.system_div.text = "⚠ No polygon selected"
            return

        choice = inst["fit_line_poly_raw"].value
        if choice == "Selected":
            idx = inst["selected_poly"]
        else:
            idx = int(choice)

        fit_key = inst["fit_line_source_raw"].value
        key = (idx, fit_key)

        # --- remove renderer if exists ---
        if key in inst.get("fit_line_renderers", {}):
            renderer = inst["fit_line_renderers"].pop(key)
            inst["fig"].renderers.remove(renderer)

        # --- remove stored source ---
        if key in inst.get("fit_line_srcs", {}):
            inst["fit_line_srcs"].pop(key)

        if 0 <= idx < len(inst.get("polygons", [])):
            inst["polygons"][idx].setdefault("growth_rates", {}).pop(fit_key, None)

        # --- clear results panel if it matches this polygon ---
        inst["results_div"].text = ""
        self.system_div.text = f"🗑 Cleared fit for polygon {idx} ({fit_key})"

            
    def on_reset(self, event, name):
        inst = self.instruments[name]
        state = live_instrument_state(inst, name=name)
        df = state.data_frame

        if df is None or df.empty:
            return

        fig = inst["fig"]

        # Reset view to actual data extent
        fig.x_range.start = df.index.min()
        fig.x_range.end   = df.index.max()

        fig.y_range.start = float(df.columns.min())
        fig.y_range.end   = float(df.columns.max())

        self.system_div.text = f"<b>System:</b> Reset view for {name}"
        


    def _get_point_source(self, inst, fit_key):
        """Get point source for a fit key directly from registry"""
        props = self.FIT_TYPES.get(fit_key)
        if not props:
            print(f"WARNING: No fit type found for key '{fit_key}'")
            return None
        return inst.get(props["src_suffix"])



    def _points_in_polygon(self, poly, t_ms, d):
        """Test which (t, d) points fall inside a polygon.

        Coordinate unit note:
          t_ms : time in milliseconds since Unix epoch (int64), matching
                 poly["x"] which comes from Bokeh event.x on a datetime axis.
          d    : diameter in metres (float), matching poly["y"].
        Both axes are already in the same units as the polygon vertices so
        no conversion is needed before the geometric containment test.
        """
        pts = np.column_stack([t_ms, d])
        poly_xy = np.column_stack([poly["x"], poly["y"]])
        mask = Path(poly_xy).contains_points(pts)
        return mask


            
    def fit_line_in_polygon(self, name):
        
        inst = self.instruments[name]

        if inst["selected_poly"] is None:
            self.system_div.text = "❌ No polygon selected"
            return

        # Get polygon index from dropdown
        choice = inst["fit_line_poly_raw"].value        
        
        if choice == "Selected":
            idx = inst["selected_poly"]
        else:
            try:
                idx = int(choice)
            except ValueError:
                self.system_div.text = f"❌ Invalid polygon selection: {choice} 🐛"
                return
        
  
        poly = inst["polygons"][idx]

        # Get source points
        fit_key = inst["fit_line_source_raw"].value
        src = self._get_point_source(inst, fit_key)

        if src is None or not src.data["t"]:
            fit_type_name = self.FIT_TYPES.get(fit_key, {}).get("name", fit_key)
            self.system_div.text = (
                f"❌ No {fit_type_name} points to fit — run the '{fit_type_name}' fit "
                f"in this ROI first (check its status message if that produced 0 points)"
            )
            return

        # ---- extract glyph data ----
        t_raw = np.array(src.data["t"])
        d_raw = np.array(src.data["d"])
        

        # ---- ms ----
        t_ms = (
            datetime_index_to_epoch_ms(t_raw)
            if isinstance(t_raw[0], (pd.Timestamp, np.datetime64))
            else t_raw.astype(float)
        )
            

        mask = self._points_in_polygon(poly, t_ms, d_raw)

        if mask.sum() < 2:
            self.system_div.text = "❌ Not enough points inside polygon"
            return
            
        # ---- DIAMETER RANGE RESTRICTION ----
        gr_dmin_input = inst.get("fit_dmin_input")
        gr_dmax_input = inst.get("fit_dmax_input")
        
        d_mask = np.ones_like(mask, dtype=bool)
        d_restriction_active = False
        
        if gr_dmin_input and gr_dmax_input:
            try:
                d_min = float(gr_dmin_input.value) * 1e-9  # convert nm to m
                d_max = float(gr_dmax_input.value) * 1e-9  # convert nm to m
                
                if d_min > 0 and d_max > 0 and d_min < d_max:
                    d_mask = (d_raw >= d_min) & (d_raw <= d_max)
                    d_restriction_active = True
            except ValueError:
                pass
        
        # Apply both polygon mask AND diameter mask
        combined_mask = mask & d_mask

        
        if combined_mask.sum() < 2:
            if d_restriction_active:
                self.system_div.text = f"❌ Not enough points in polygon with Dp {float(gr_dmin_input.value):.1f}-{float(gr_dmax_input.value):.1f} nm"
            else:
                self.system_div.text = f"❌ Not enough points inside polygon after applying Dp restriction ({gr_dmin_input.value}–{gr_dmax_input.value} nm)"

            return

        # ---- fit (seconds ONLY here) ----
        t_sec = t_ms[combined_mask] / 1000.0
        d_fit = d_raw[combined_mask]

        m, c = np.polyfit(t_sec, d_fit, 1)
        

        
        # ---- Calculate growth rate in nm/hr ----
        gr_nm_per_hr = m * 3600 * 1e9  # convert m/s → nm/hr
        r2 = self._calc_r2(t_sec, d_fit, m, c)
        
        key = (idx, fit_key)
        self._draw_fit_line(inst, key, t_ms[combined_mask], m, c)
        t_line_ms = np.linspace(t_ms[combined_mask].min(), t_ms[combined_mask].max(), 50)
        d_line = m * (t_line_ms / 1000.0) + c
        keep_line = d_line > 0
        poly.setdefault("growth_rates", {})[fit_key] = {
            "fit_key": fit_key,
            "source_name": self.FIT_TYPES[fit_key]["name"],
            "slope_m_per_s": float(m),
            "intercept_m": float(c),
            "growth_rate_nm_per_hr": float(gr_nm_per_hr),
            "r2": float(r2),
            "n_points": int(len(t_sec)),
            "dp_min_nm": float(d_fit.min() * 1e9),
            "dp_max_nm": float(d_fit.max() * 1e9),
            "time_start_ms": float(t_ms[combined_mask].min()),
            "time_end_ms": float(t_ms[combined_mask].max()),
            "line_t_ms": t_line_ms[keep_line].astype(float).tolist(),
            "line_d_m": d_line[keep_line].astype(float).tolist(),
            "diameter_filter_min_nm": float(gr_dmin_input.value) if d_restriction_active else None,
            "diameter_filter_max_nm": float(gr_dmax_input.value) if d_restriction_active else None,
        }
        
        # ---- PRINT RESULTS TO RESULTS DIV ----
        d_range_text = ""
        if d_restriction_active:
            d_range_text = f" (Dp: {float(gr_dmin_input.value):.1f}-{float(gr_dmax_input.value):.1f} nm)"
        
        result_text = f"""
        <b>Growth Rate Fit Results{d_range_text}:</b><br>
        • Growth rate: {gr_nm_per_hr:.2f} nm/hr<br>
        • R²: {r2:.3f}<br>
        • Source: {self.FIT_TYPES[fit_key]["name"]}<br>
        • Polygon: {idx}<br>
        • N points: {len(t_sec)}<br>
        • Fit: d = {m*1e9:.3e} nm/s · t + {c*1e9:.3e} nm<br>
        • Time range: {ms_to_datetime(t_ms[combined_mask].min())} to {ms_to_datetime(t_ms[combined_mask].max())}<br>
        • Dp range: {d_fit.min()*1e9:.1f} - {d_fit.max()*1e9:.1f} nm
        """
        
        inst["results_div"].text = result_text
        self.system_div.text = f"✅ Growth rate: {gr_nm_per_hr:.2f} nm/hr"
        
    def _calc_r2(self, x, y, m, c):
        """Calculate R² for linear fit.

        When ss_tot == 0 (constant y), returns 1.0 if the fit is also
        perfect, otherwise 0.0 — avoids division by zero and a misleading
        '0' result.
        """
        y_pred = m * x + c
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot == 0:
            return 1.0 if ss_res == 0 else 0.0
        return 1 - (ss_res / ss_tot)

    def _coerce_datetime_range_value(self, value):
        """Convert Bokeh datetime range values to pandas timestamps."""
        if value is None:
            return None
        try:
            if isinstance(value, (int, float, np.integer, np.floating)):
                return pd.to_datetime(value, unit="ms")
            return pd.to_datetime(value)
        except Exception:
            return None

    def _make_heatmap_view(self, df, x_start=None, x_end=None, max_cols=1800):
        """Return a display-sized slice/downsample of df for browser heatmap rendering.

        The full DataFrame remains available for fitting and analysis. This method
        only limits what is sent to Bokeh's image glyph.
        """
        if df is None or df.empty:
            return df

        view = df
        start = self._coerce_datetime_range_value(x_start)
        end = self._coerce_datetime_range_value(x_end)
        if start is not None and end is not None:
            if start > end:
                start, end = end, start
            try:
                view = df.loc[(df.index >= start) & (df.index <= end)]
            except Exception:
                view = df

        if view.empty:
            view = df.iloc[: min(len(df), max_cols)]

        if len(view) > max_cols:
            # Use evenly spaced samples for responsive display. Full-resolution
            # data remain in inst["df"] for fitting, ROI masks, strips, and dists.
            sample_idx = np.linspace(0, len(view) - 1, max_cols).astype(int)
            sample_idx = np.unique(sample_idx)
            view = view.iloc[sample_idx]

        return view

    def _apply_heatmap_view_transform(self, df, heatmap_view_select):
        """Display-layer-only PSD representation transform for the heatmap.

        Transforms only what gets drawn (the image glyph + auto color
        limits, via this one shared helper called from both
        refresh_heatmap_view() and update_image()/_on_heatmap_view_changed()
        through _recompute_color_limits()). The canonical inst["df"] this is
        derived from is never mutated or replaced - every fit, ROI mask,
        growth-rate calc, and overlay line continues to read the original
        dN/dlogDp-in-metres data exactly as before. This is what makes the
        live toggle safe: switching the view can never change what a fit
        computes.
        """
        if df is None or df.empty or heatmap_view_select is None:
            return df
        mode = heatmap_view_select.value
        try:
            if mode == "Number Concentration (N)":
                return psd_distribution.dndlogdp_to_number(df)
            if mode == "Surface Density (dS/dlogDp)":
                return psd_distribution.dndlogdp_to_surface_area(df)
            if mode == "Volume Density (dV/dlogDp)":
                return psd_distribution.dndlogdp_to_volume(df)
        except ValueError:
            # Degenerate/unsortable diameters (e.g. a single-column df) -
            # fall back to the raw representation rather than crash.
            return df
        return df

    @staticmethod
    def _format_clim_value(v):
        """Format a color-limit bound for the editable Min/Max text boxes.

        str(int(v)) - the original formatting - silently truncates to "0"
        for anything smaller than 1, which is fine for the dN/dlogDp view
        (values are typically 10^2-10^5) but always fires for Surface/
        Volume Density (m^2/cm^3, m^3/cm^3 - typically 10^-10 to 10^-20 for
        real atmospheric data): both boxes would show "0" to "0" regardless
        of the actual data, even though inst["mapper"].low/high (set from
        the same vmin/vmax just before this is called) were already
        correct - only this display formatting was wrong. Falls back to
        scientific notation for anything that would otherwise round to 0.
        """
        if v == 0:
            return "0"
        if abs(v) >= 1:
            return str(int(v))
        return f"{v:.3g}"

    def _recompute_color_limits(self, name, transformed_df):
        """Auto color-limit calc, extracted from update_image() so the
        heatmap-view toggle can reuse it on the currently-loaded data
        without duplicating the min/max/rounding logic."""
        inst = self.instruments[name]
        if not inst["clim_auto"].active:
            return
        if transformed_df is None or transformed_df.empty:
            return
        vals = transformed_df.values
        vals = vals[np.isfinite(vals)]
        vals = vals[vals > 0]
        if len(vals) == 0:
            return

        vmin = np.nanmin(vals)
        vmax = np.nanmax(vals)

        # round to nearest 10
        vmin = 10 * np.floor(vmin / 10)
        vmax = 10 * np.ceil(vmax / 10)

        # prevent invalid log values - fall back to the unrounded raw
        # min/max instead of crashing if nothing clears 10 (routine for
        # surface/volume density views, which can be << 10 for small
        # particles; the original dN/dlogDp-only code here assumed values
        # > 10 were always available and had no fallback for that case).
        if vmin <= 0:
            pool = vals[vals > 10]
            if len(pool) > 0:
                vmin = np.min(pool)
            else:
                vmin = np.nanmin(vals)
                vmax = np.nanmax(vals)

        inst["mapper"].low = vmin
        inst["mapper"].high = vmax
        self._clim_auto_updating = True
        try:
            inst["clim_low"].value = self._format_clim_value(vmin)
            inst["clim_high"].value = self._format_clim_value(vmax)
        finally:
            self._clim_auto_updating = False

    def _on_heatmap_view_changed(self, name):
        """Callback for the 'Heatmap View' toggle: re-render the heatmap
        image and recompute color limits for the new representation.
        Purely a display refresh - see _apply_heatmap_view_transform()."""
        if name not in self.instruments:
            return
        inst = self.instruments[name]
        state = live_instrument_state(inst, name=name)
        df = state.data_frame
        if df is None or df.empty:
            return
        self.refresh_heatmap_view(name)
        transformed = self._apply_heatmap_view_transform(df, inst.get("heatmap_view_select"))
        self._recompute_color_limits(name, transformed)

    def refresh_heatmap_view(self, name):
        """Refresh only the browser-displayed heatmap image for the current viewport."""
        if name not in self.instruments:
            return
        inst = self.instruments[name]
        state = live_instrument_state(inst, name=name)
        df = state.data_frame
        if df is None or df.empty:
            return

        fig = inst["fig"]
        view = self._make_heatmap_view(df, fig.x_range.start, fig.x_range.end)
        if view is None or view.empty:
            return

        view = self._apply_heatmap_view_transform(view, inst.get("heatmap_view_select"))

        x = view.index.values
        y = view.columns.values.astype(float)
        if len(x) < 1 or len(y) < 1:
            return

        img_array = view.values.T
        if len(x) == 1:
            dw = pd.Timedelta(seconds=1)
        else:
            dw = x[-1] - x[0]

        inst["src_img"].data = {
            "img": [img_array],
            "x": [x[0]],
            "y": [y[0]],
            "dw": [dw],
            "dh": [y[-1] - y[0]],
            "nrows": [img_array.shape[0]],
            "ncols": [img_array.shape[1]],
        }

    def _schedule_heatmap_view_refresh(self, name):
        """Debounce viewport heatmap refreshes during pan/zoom."""
        if name not in self.instruments:
            return
        inst = self.instruments[name]
        if inst.get("_heatmap_refresh_pending"):
            return
        inst["_heatmap_refresh_pending"] = True

        def _run():
            try:
                self.refresh_heatmap_view(name)
                for cl in self.instruments[name].get("overlay_var_lines", []):
                    try:
                        cl["refresh_view"]()
                    except Exception:
                        pass
            finally:
                if name in self.instruments:
                    self.instruments[name]["_heatmap_refresh_pending"] = False

        curdoc().add_timeout_callback(_run, 150)

    def _mark_heatmap_range_refresh_bound(self, name, x_range):
        bindings = getattr(self, "_heatmap_range_refresh_bindings", None)
        if bindings is None:
            bindings = set()
            self._heatmap_range_refresh_bindings = bindings
        bindings.add((name, id(x_range)))

    def _ensure_heatmap_range_refresh_bound(self, name):
        inst = self.instruments.get(name)
        if not inst:
            return
        x_range = inst["fig"].x_range
        bindings = getattr(self, "_heatmap_range_refresh_bindings", None)
        if bindings is None:
            bindings = set()
            self._heatmap_range_refresh_bindings = bindings
        key = (name, id(x_range))
        if key in bindings:
            return
        x_range.on_change("start", lambda attr, old, new, n=name: self._schedule_heatmap_view_refresh(n))
        x_range.on_change("end", lambda attr, old, new, n=name: self._schedule_heatmap_view_refresh(n))
        bindings.add(key)

    def _get_fit_key_from_source(self, src_name):
        """Automatically determine fit_key from source name using FIT_TYPES registry"""
        return self.SRC_TO_FIT.get(src_name)



    def _fit_color(self, fit_key):
        props = self.FIT_TYPES.get(fit_key)
        return props["color"] if props else "red"

        

    def _draw_fit_line(self, inst, key, t_ms, m, c):

        polygon_idx, fit_key = key


        if "fit_line_srcs" not in inst:
            inst["fit_line_srcs"] = {}
            inst["fit_line_renderers"] = {}

        if key not in inst["fit_line_srcs"]:
            src = ColumnDataSource(data=dict(t=[], d=[]))
            inst["fit_line_srcs"][key] = src
            gr_fit_line_renderer = inst["fig"].line(
                "t", "d",
                source=src,
                line_width=4,
                color=self._fit_color(fit_key),
                line_alpha=1,  
                line_dash="solid",
                level="overlay"
            )
            inst["fit_line_renderers"][key] = gr_fit_line_renderer

        else:
            src = inst["fit_line_srcs"][key]
            


        t_plot_ms = np.linspace(t_ms.min(), t_ms.max(), 50)
        d_plot = m * (t_plot_ms / 1000.0) + c


        keep = d_plot > 0
        t_plot_ms = t_plot_ms[keep]
        d_plot = d_plot[keep]

        if len(t_plot_ms) < 2:
            self.system_div.text = "⚠️ Fit line outside range"
            return

        src.data = dict(
            t=pd.to_datetime(t_plot_ms, unit="ms"),
            d=d_plot
        )

    def _restore_growth_rate_lines(self, name):
        """Redraw saved growth-rate lines from lightweight per-polygon records."""
        if name not in self.instruments:
            return
        inst = self.instruments[name]
        for idx, poly in enumerate(inst.get("polygons", [])):
            growth_rates = poly.get("growth_rates", {})
            if not isinstance(growth_rates, dict):
                continue
            for fit_key, rec in growth_rates.items():
                if not isinstance(rec, dict):
                    continue
                t_line = rec.get("line_t_ms", [])
                d_line = rec.get("line_d_m", [])
                if len(t_line) < 2 or len(d_line) < 2:
                    continue
                key = (idx, fit_key)
                if key not in inst["fit_line_srcs"]:
                    src = ColumnDataSource(data=dict(t=[], d=[]))
                    inst["fit_line_srcs"][key] = src
                    renderer = inst["fig"].line(
                        "t", "d",
                        source=src,
                        line_width=4,
                        color=self._fit_color(fit_key),
                        line_alpha=1,
                        line_dash="solid",
                        level="overlay",
                    )
                    inst["fit_line_renderers"][key] = renderer
                inst["fit_line_srcs"][key].data = dict(
                    t=pd.to_datetime(np.array(t_line, dtype=float), unit="ms"),
                    d=np.array(d_line, dtype=float),
                )
        

    def add_new_instrument_callback(self):
        requested_name = self.new_inst_name.value.strip()
        if requested_name:
            name = requested_name
            suffix = 2
            while name in self.instruments:
                name = f"{requested_name}_{suffix}"
                suffix += 1
            self.create_instrument_entry(name, self.new_inst_type.value)
            self.update_master_options()
            self.tabs.tabs = self._generate_tabs()
            self.update_view_mode(None, None, self.view_mode.value)
            if self.show_tab_manager.active:
                self.tab_manager_container.children = [self.build_tab_manager()]
            if name == requested_name:
                self.system_div.text = f"<b>System:</b> Added {name}"
            else:
                self.system_div.text = (
                    f"<b>System:</b> '{requested_name}' already exists; added '{name}' instead"
                )
        else:
            self.system_div.text = "<b>System:</b> Dataset name cannot be empty"


            
    def get_master_name(self):
        if self.master_select.value != "Auto":
            return self.master_select.value
        return list(self.instruments.keys())[0]

            
    def _is_master(self, name):
        """Returns True if this instrument is the x-axis master."""
        if not self.instruments:
            return True
        return name == list(self.instruments.keys())[0]
        
    def update_master_options(self):
        opts = ["Auto"] + list(self.instruments.keys())
        self.master_select.options = opts
        if self.master_select.value not in opts:
            self.master_select.value = "Auto"

    
    def get_active_instrument_name(self):
        if not hasattr(self, "tabs"):
            return None

        # Tabs view → resolve by the tab's tag (stable name), not insertion
        # index: list(self.instruments.keys())[idx] breaks after tabs are
        # reordered, because the dict order no longer matches the visual tab
        # order. Tags are authoritative.
        if isinstance(self.tabs, Tabs):
            idx = self.tabs.active
            if idx is None:
                return None
            try:
                active_tab = self.tabs.tabs[idx]
                name = self.get_stable_name(active_tab)
                if name and name in self.instruments:
                    return name
            except IndexError:
                pass
            # Fallback: first instrument
            names = list(self.instruments.keys())
            return names[0] if names else None

        # Stacked view → return master / first instrument
        names = list(self.instruments.keys())
        return names[0] if names else None
        
        


        
    def _start_load_step(self):
        from time import perf_counter
        return perf_counter()

    def _record_load_step(self, name, started):
        timings = getattr(self, "_active_load_timings", None)
        if timings is not None:
            timings[name] = self._start_load_step() - started

    def _finish_load_timings(self, name, file_path, df, started):
        timings = getattr(self, "_active_load_timings", {})
        timings["total"] = self._start_load_step() - started
        self.last_load_timings = {
            "instrument": name,
            "path": str(file_path),
            "shape": tuple(df.shape) if df is not None else None,
            "seconds": dict(timings),
        }
        self._active_load_timings = None

        if os.environ.get("AEROSOL_STUDIO_PROFILE_LOAD") == "1":
            summary = ", ".join(
                f"{step}={seconds:.6f}s"
                for step, seconds in self.last_load_timings["seconds"].items()
            )
            print(f"[aerosolstudio.load] {name} {file_path}: {summary}")

    def update_image(self, name, df):
        """
        Centralized heatmap update logic.
        Safe for file upload, species switch, reprocessing, etc.

        Range values are updated IN-PLACE rather than rebinding to a new
        Range1d - rebinding breaks axis linking, since linked axes share the
        same object reference.
        """
        inst = self.instruments[name]
        fig = inst["fig"]

        step_started = self._start_load_step()
        from aerosolstudio.instrument.state import InstrumentState
        state = inst.setdefault("_state", InstrumentState.bind_live(inst, name=name))
        state.set_loaded_data(df)
        self._record_load_step("state_store", step_started)

        step_started = self._start_load_step()
        x = df.index.values
        y = df.columns.values
        ymin = float(np.nanmin(y))
        ymax = float(np.nanmax(y))

        # Update range values in-place (preserves object identity → keeps axis links intact)
        fig.x_range.start = x[0]
        fig.x_range.end   = x[-1]
        fig.y_range.start = ymin
        fig.y_range.end   = ymax
        self._record_load_step("range_update", step_started)

        # Surfaced so a PM cutoff wider than what was actually measured is
        # visible before the user hits it - see pm_interpolate_input's
        # tooltip for why that matters (PM1 on data maxing out at 600nm is
        # really PM0.6 unless interpolation is switched on).
        data_max_div = inst.get("pm_data_max_div")
        if data_max_div is not None:
            data_max_div.text = (
                f"<span style='font-size:10px; color:#8aafc8;'>"
                f"Data max: {ymax * 1e9:.0f} nm</span>"
            )

        step_started = self._start_load_step()
        self.refresh_heatmap_view(name)
        self._record_load_step("heatmap_refresh", step_started)
        
        # ---------- AUTO COLOR LIMITS ----------
        step_started = self._start_load_step()
        transformed_for_limits = self._apply_heatmap_view_transform(df, inst.get("heatmap_view_select"))
        self._recompute_color_limits(name, transformed_for_limits)
        self._record_load_step("color_limits", step_started)
        
      
        
        step_started = self._start_load_step()
        inst["mask_src"].data = {
            'img': inst["mask_src"].data['img'],
            'x': [x[0]],
            'y': [ymin],
            'dw': [x[-1] - x[0]],
            'dh': [ymax - ymin]
        }
        self._record_load_step("mask_extent", step_started)

        # Auto-refresh any existing concentration overlay lines
        step_started = self._start_load_step()
        for cl in inst.get("overlay_var_lines", []):
            try:
                cl["update"]()
            except Exception:
                pass
        self._record_load_step("overlay_refresh", step_started)




    def update_species(self, attr, old, new):
        name = self.get_active_instrument_name()
        if name is None:
            return

        if name not in self.cache:
            return
        if new not in self.cache[name]:
            return

        df = self.cache[name][new]
        self.update_image(name, df)
        self.system_div.text = f"<b>System:</b> {name} species → {new}"

    def _style_load_button(self, button, state):
        colors = {
            "idle": ("#e5e7eb", "#9ca3af", "#374151"),
            "pending": ("#fbbf24", "#d97706", "#111827"),
            "loaded": ("#009e73", "#007a59", "#ffffff"),
            "error": ("#d55e00", "#a84400", "#ffffff"),
        }
        bg, border, text = colors.get(state, colors["idle"])
        button.stylesheets = [f"""
        .bk-btn {{
            background-color: {bg} !important;
            border-color: {border} !important;
            color: {text} !important;
            font-weight: 700 !important;
        }}
        """]
         
    def load_from_path(self, name, file_path):
        if self.link_axes.active:
            self.link_axes.active = False

        inst = self.instruments[name]
        if not file_path or not os.path.isfile(file_path):
            self._style_load_button(inst["load_btn"], "error")
            self.system_div.text = f"<b>Error:</b> File not found: {file_path}"
            return

        tz_name = (inst["tz_input"].value or "").strip()
        if not is_valid_timezone(tz_name):
            self._style_load_button(inst["load_btn"], "error")
            self.system_div.text = (
                f"<b>Error:</b> '{tz_name}' is not a recognized timezone. "
                f"Pick one from the Source Timezone box (e.g. 'UTC', "
                f"'Europe/Helsinki', 'Asia/Kolkata') before loading."
            )
            return

        self._active_load_timings = {}
        self._tz_rows_dropped = 0
        self._diam_unit_note = ""
        load_started = self._start_load_step()
        df = None
        try:
            self._style_load_button(inst["load_btn"], "pending")
            if inst["type"] == "nais(.nc)":
                # NetCDF file
                read_started = self._start_load_step()
                with xr.open_dataset(file_path) as ds:
                    # Timestamps in the file are naive wall-clock readings;
                    # reinterpret them as local time in the user-declared
                    # Source Timezone and convert to naive-but-UTC, matching
                    # what the rest of the app (epoch-ms conversions, ROI
                    # polygons, fits) assumes. Replaces the old hardcoded
                    # +5:30 (IST) shift that used to apply unconditionally.
                    t, dropped = localize_naive_index_to_utc(ds['time'].values, tz_name)
                    self._tz_rows_dropped += dropped
                    d = ds['diameter'].values.astype(float)

                    # Diameter unit: cross-check the user's declared unit
                    # against the file's own attrs when present (NetCDF
                    # sometimes states this, unlike CSV). File attrs win for
                    # THIS load when recognized - the declared box is then
                    # updated to match so it stays visibly correct; if
                    # nothing recognizable is present, the declared value is
                    # used as-is, same as timezone.
                    diam_unit_name = (inst["diam_unit_input"].value or DEFAULT_DIAMETER_UNIT).strip()
                    diameter_var = ds['diameter'] if 'diameter' in ds else None
                    detected_unit = detect_diameter_unit_from_attrs(getattr(diameter_var, 'attrs', None))
                    if detected_unit and detected_unit != diam_unit_name:
                        self._diam_unit_note = (
                            f" — diameter unit detected as '{detected_unit}' from file "
                            f"attrs (declared box updated; was '{diam_unit_name}')"
                        )
                        diam_unit_name = detected_unit
                        inst["diam_unit_input"].value = detected_unit
                    diam_factor = diameter_unit_to_metres_factor(diam_unit_name)
                    if diam_factor is None:
                        raise ValueError(
                            f"Unrecognized Diameter Unit '{diam_unit_name}'. "
                            f"Choose one of {DIAMETER_UNIT_OPTIONS} before loading."
                        )
                    magnitude_issue = validate_diameter_magnitude(d, diam_unit_name)
                    if magnitude_issue:
                        raise ValueError(magnitude_issue)
                    d = d * diam_factor

                    data_type_name = (inst["data_type_input"].value or DEFAULT_DATA_TYPE).strip()

                    if name not in self.cache:
                        self.cache[name] = {}
                    self.cache[name].clear()
                    for s in ["neg_ions", "pos_ions", "neg_particles", "pos_particles"]:
                        if s in ds:
                            species_df = pd.DataFrame(ds[s].values.copy(), index=t, columns=d)
                            if data_type_name == "Number Concentration (N)":
                                try:
                                    species_df = psd_distribution.number_to_dndlogdp(species_df)
                                except ValueError:
                                    pass  # degenerate/unsortable diameters - keep as-loaded rather than crash
                            self.cache[name][s] = species_df

                self._record_load_step("file_read_decode", read_started)
                normalize_started = self._start_load_step()
                df = self.cache[name][self.species_sel.value]
                df = df.sort_index()
                if not df.index.is_unique:
                    df = df.groupby(df.index).mean()
                df.columns = df.columns.astype(float)
                self._record_load_step("normalize", normalize_started)
            else:
                # CSV file
                step_started = self._start_load_step()
                df = pd.read_csv(file_path, index_col=0, parse_dates=True)
                self._record_load_step("file_read_decode", step_started)
                step_started = self._start_load_step()
                df.index, dropped = localize_naive_index_to_utc(df.index, tz_name)
                self._tz_rows_dropped += dropped
                if dropped:
                    df = df[df.index.notna()]
                # CSV headers never carry a units string, so no file-based
                # detection is possible here (unlike NetCDF attrs above) -
                # the declared Diameter Unit box is authoritative.
                diam_unit_name = (inst["diam_unit_input"].value or DEFAULT_DIAMETER_UNIT).strip()
                diam_factor = diameter_unit_to_metres_factor(diam_unit_name)
                if diam_factor is None:
                    raise ValueError(
                        f"Unrecognized Diameter Unit '{diam_unit_name}'. "
                        f"Choose one of {DIAMETER_UNIT_OPTIONS} before loading."
                    )
                raw_diam_values = df.columns.astype(float)
                magnitude_issue = validate_diameter_magnitude(raw_diam_values, diam_unit_name)
                if magnitude_issue:
                    raise ValueError(magnitude_issue)
                df.columns = raw_diam_values * diam_factor
                df = df.sort_index()
                if not df.index.is_unique:
                    df = df.groupby(df.index).mean()
                data_type_name = (inst["data_type_input"].value or DEFAULT_DATA_TYPE).strip()
                if data_type_name == "Number Concentration (N)":
                    try:
                        df = psd_distribution.number_to_dndlogdp(df)
                    except ValueError:
                        pass  # degenerate/unsortable diameters - keep as-loaded rather than crash
                self._record_load_step("normalize", step_started)

            step_started = self._start_load_step()
            self.update_image(name, df)
            self._record_load_step("document_update", step_started)
            self._style_load_button(inst["load_btn"], "loaded")
            tz_note = (
                f" — {self._tz_rows_dropped} row(s) dropped: ambiguous local "
                f"time under '{tz_name}' DST transition"
                if self._tz_rows_dropped else ""
            )
            self.system_div.text = (
                f"<b>System:</b> {name} loaded ({df.shape[0]} × {df.shape[1]}), "
                f"timestamps interpreted as {tz_name}{tz_note}"
                f"{getattr(self, '_diam_unit_note', '')}"
            )
        except Exception as e:
            self._style_load_button(inst["load_btn"], "error")
            self.system_div.text = f"<b>Error:</b> {str(e)}"
        finally:
            self._finish_load_timings(name, file_path, df, load_started)
        
    def handle_file_upload(self, name, payload):
        # not working for larger files so commented for a while
        

        if self.link_axes.active:
            self.link_axes.active = False

        inst = self.instruments[name]
        raw = base64.b64decode(payload)
        tz_name = (inst["tz_input"].value or "").strip()
        if not is_valid_timezone(tz_name):
            tz_name = DEFAULT_TIMEZONE

        try:
            if inst["type"] == "nais(.nc)":
                try:
                    ds = xr.open_dataset(io.BytesIO(raw), engine="netcdf4")
                except Exception:
                    ds = xr.open_dataset(io.BytesIO(raw), engine="h5netcdf")

                try:
                    t, _dropped = localize_naive_index_to_utc(ds['time'].values, tz_name)
                    d = ds['diameter'].values

                    if name not in self.cache:
                        self.cache[name] = {}
                    self.cache[name].clear()
                    for s in ["neg_ions", "pos_ions", "neg_particles", "pos_particles"]:
                        if s in ds:
                            self.cache[name][s] = pd.DataFrame(ds[s].values.copy(), index=t, columns=d)

                    df = self.cache[name][self.species_sel.value]
                    df = df.sort_index()
                    if not df.index.is_unique:
                        df = df.groupby(df.index).mean()
                    df.columns = df.columns.astype(float)
                finally:
                    ds.close()
                
                
            else:

                
                df = pd.read_csv(io.StringIO(raw.decode('utf-8')),
                                index_col=0, parse_dates=True)
                df.index, _dropped = localize_naive_index_to_utc(df.index, tz_name)
                if _dropped:
                    df = df[df.index.notna()]
                df.columns = df.columns.astype(float)
                df = df.sort_index()
                if not df.index.is_unique:
                    df = df.groupby(df.index).mean()

            self.update_image(name, df)

            self.system_div.text = (
                f"<b>System:</b> {name} loaded "
                f"({df.shape[0]} × {df.shape[1]})"
            )

        except Exception as e:
            self.system_div.text = f"<b>Error:</b> {str(e)}"
            
            
            
    def _overlay_var_methods_for(self, inst):
        """overlay_var_methods plus this instrument's PM1/PM2.5/PM10/PM(custom)
        overlay entries. Built fresh each call since it's cheap (a handful of
        closures). Density is no longer read from a per-instrument widget -
        each PM overlay line supplies its own via its dmin box (relabeled
        "Density (g/cm³)", see PM_DIAMETER_LABELS) - only the interpolate
        toggle is still a per-instrument setting read here."""
        interpolate_toggle = inst.get("pm_interpolate_toggle")
        interpolate_getter = (
            (lambda: interpolate_toggle.active) if interpolate_toggle is not None else None
        )
        return {**overlay_var_methods, **build_pm_methods(interpolate_getter)}

    def _overlay_var_diameter_labels(self):
        """What each overlay method's generic dmin/dmax boxes mean, if
        anything - see overlay_var_diameter_labels/PM_DIAMETER_LABELS.
        Static (unlike _overlay_var_methods_for, doesn't depend on inst)."""
        return {**overlay_var_diameter_labels, **PM_DIAMETER_LABELS}

    def _sync_pm_interpolate_visibility(self, name):
        """Show the Interpolate PSD toggle only while at least one overlay
        line on this instrument has a PM method selected - it has no effect
        on any other method, so leaving it visible unconditionally was
        clutter. Called on every line's method change and whenever a line
        is added/removed (see add_overlay_var_line/_remove_overlay_var_line)."""
        inst = self.instruments.get(name)
        if inst is None or "pm_interpolate_input" not in inst:
            return
        any_pm_selected = any(
            cl["method_select"].value in PM_DIAMETER_LABELS
            for cl in inst.get("overlay_var_lines", [])
        )
        inst["pm_interpolate_input"].visible = any_pm_selected

    def add_overlay_var_line(self, name):
        inst = self.instruments[name]

        df_getter = lambda n=name: live_instrument_state(self.instruments[n], name=n).data_frame

        line_id = next_overlay_var_id(inst["overlay_var_lines"])

        conc = make_overlay_var_line(
            inst["fig"],
            df_getter,
            self._overlay_var_methods_for(inst), line_id,
            color=Category10[10][len(inst["overlay_var_lines"]) % 10],
            tooltip_manager=TooltipManager,
            diameter_labels=self._overlay_var_diameter_labels(),
            on_method_changed=lambda n=name: self._sync_pm_interpolate_visibility(n),
            on_error=lambda msg: setattr(self.system_div, "text", f"<b>Warning:</b> {msg}"),
        )

        def _remove(cl=conc, n=name, lid=line_id):
            self._remove_overlay_var_line(n, lid)
        conc["remove_btn"].on_click(_remove)

        def _fit_y(lid=line_id, n=name):
            self._fit_y_axis_to_data(n, lid)
        conc["fit_y_btn"].on_click(_fit_y)

        # Wire the download button: exports the FULL, non-decimated series
        # for whatever method is currently selected - deliberately recomputed
        # from the raw dataframe rather than reading conc["source"], because
        # that source is a display buffer (viewport-limited to the figure's
        # current x-range, row-capped at 5000, then decimated to <=1800
        # points and median-filtered for plotting - see OverlayVarLine.update()
        # / _visible_df() in overlay.py). A CSV built from that would silently
        # be a lossy, view-dependent subset, not the actual computed variable.
        def _download(lid=line_id, n=name, cl=conc):
            self._download_overlay_var_line(n, lid, cl)
        conc["download_btn"].on_click(_download)

        inst["overlay_var_lines"].append(conc)
        inst["overlay_var_container"].children.append(conc["controls"])
        self._sync_pm_interpolate_visibility(name)

    def _download_overlay_var_line(self, name, line_id, conc):
        """Export the full (not display-decimated) computed overlay series to CSV."""
        method_name = conc["method_select"].value
        if method_name == "Select Method":
            self.system_div.text = f"⚠ {line_id}: choose a variable and click Plot first"
            return

        # Reuses OverlayVarLine.read_dmin_dmax_m() itself (same object the
        # live Plot button calls) rather than re-parsing dmin/dmax here -
        # two independent parsers previously had to agree on which box means
        # a diameter (nm, converted) vs. something else (PM's density, raw)
        # per method, and that's exactly the kind of thing that quietly
        # drifts out of sync (see the fit_checkbox_keys fix earlier this
        # session for a concrete example of that failure mode).
        parsed = conc["read_dmin_dmax_m"]()
        if parsed is None:
            self.system_div.text = f"❌ {line_id}: set a valid dmin/dmax before exporting"
            return
        dmin, dmax = parsed

        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        if df is None or df.empty:
            self.system_div.text = f"❌ {line_id}: no data loaded for {name}"
            return

        try:
            result_df = self._overlay_var_methods_for(inst)[method_name](df, dmin, dmax)
        except Exception as exc:
            self.system_div.text = f"❌ {line_id}: failed to compute {method_name} — {exc}"
            return

        if result_df is None or result_df.empty:
            self.system_div.text = f"⚠ {line_id}: {method_name} produced no data to export"
            return

        export_df = pd.DataFrame({
            "time": pd.to_datetime(result_df.index),
            method_name: result_df.values.flatten(),
        })

        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        default_name = f"{name}_{method_name.replace(' ', '_')}_{line_id}.csv"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=default_name,
            title=f"Export {method_name} ({line_id})",
        )
        root.destroy()
        if not file_path:
            self.system_div.text = f"{line_id}: export cancelled"
            return

        export_df.to_csv(file_path, index=False)
        self.system_div.text = f"✅ {line_id}: exported {len(export_df)} rows of {method_name} to {file_path}"

    def _remove_overlay_var_line(self, name, line_id):
        """Remove a concentration overlay line and its axis."""
        inst = self.instruments[name]
        fig  = inst["fig"]

        # Find and remove from list
        to_remove = [cl for cl in inst["overlay_var_lines"] if cl.get("line_id") == line_id]
        for cl in to_remove:
            cl["destroy"](fig)
            inst["overlay_var_lines"].remove(cl)

        # Rebuild the controls container
        inst["overlay_var_container"].children = [cl["controls"] for cl in inst["overlay_var_lines"]]
        self._sync_pm_interpolate_visibility(name)
        self.system_div.text = f"🗑 Removed overlay {line_id}"
        


        
        
    def clear_fit_by_type(self, name, fit_key):
        """Clear fit based on dropdown selection"""
        props = self.FIT_TYPES[fit_key]
        
        inst = self.instruments[name]
        if inst["selected_poly"] is None:
            self.system_div.text = "⚠ No polygon selected"
            return
        
        # Clear only the selected fit type from the selected polygon
        inst["polygons"][inst["selected_poly"]][props["fit_key"]].clear()
        
        # Update ONLY the glyphs for this fit type
        self._update_fit_glyphs(name, fit_key)
        
        self.update_status(name)
        self.system_div.text = f"🗑 Cleared {props['name']} points"


    def _update_poly_span(self, name):
        """Update the BoxAnnotation shading on the strip plot.
        Shows the time extent of the selected polygon, or hides if none selected.
        Called after every tap so the shade tracks polygon selection correctly.
        """
        inst = self.instruments[name]
        poly_span = inst.get("poly_span")
        if poly_span is None:
            return
        if inst["selected_poly"] is not None:
            poly = inst["polygons"][inst["selected_poly"]]
            if poly.get("x"):
                x_arr = np.array(poly["x"])
                poly_span.left  = pd.to_datetime(x_arr.min(), unit="ms")
                poly_span.right = pd.to_datetime(x_arr.max(), unit="ms")
                poly_span.visible = True
        else:
            poly_span.left  = None
            poly_span.right = None
            poly_span.visible = False

    def select_polygon(self, name, event):
        inst = self.instruments[name]

        for i, p in enumerate(inst["polygons"]):
            if Path(np.column_stack((p["x"], p["y"]))).contains_point((event.x, event.y)):
                inst["selected_poly"] = i
                self.last_active_instrument = name
                self.update_polygon_renderers(name)
                inst["fit_line_poly_raw"].value = str(i)
                return

        inst["selected_poly"] = None        
        self.update_polygon_renderers(name)
        inst["fit_line_poly_raw"].value = "Selected"
        
        
    def update_strip_plot(self, name):
        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        if df is None or df.empty:  
            return
        # --- 1. Get target diameter from input ---
        try:
            d_target_nm = float(inst['strip_diameter_input'].value)
            d_target = d_target_nm * 1e-9   # nm -> m
        except ValueError:
            self.system_div.text = "Invalid diameter"
            return

        # --- 2. Update polygon time span annotation ---
        poly_span = inst.get("poly_span")
        if poly_span and inst["selected_poly"] is not None:
            poly = inst["polygons"][inst["selected_poly"]]
            x_vals = np.array(poly["x"])
            poly_span.left = pd.to_datetime(x_vals.min(), unit="ms")
            poly_span.right = pd.to_datetime(x_vals.max(), unit="ms")
            poly_span.visible = True
        else:
            # No polygon selected — hide the annotation completely
            if poly_span:
                poly_span.left  = None
                poly_span.right = None
                poly_span.visible = False

        # --- 3. Find nearest diameter column ---
        cols = df.columns.values
        idx = np.argmin(np.abs(cols - d_target))
        d_actual = cols[idx]
        d_actual_nm = d_actual * 1e9
        
        inst["fig_strip"].title.text = f"[{name}] nearest available {d_actual_nm:.2f} nm dim Time Series"
        
        if abs(d_actual - d_target) > 1e-8:
            self.system_div.text = f"Closest diameter: {d_actual*1e9:.2f} nm"

        # --- 4. Extract time series for that diameter ---
        series = df.iloc[:, idx]
        t = series.index.values          # datetime64, resolution varies
        y = series.values.astype(float)

        t_ms = datetime_index_to_epoch_ms(t) # milliseconds

        # Clamp the y-axis to the actual measured signal, with a small
        # margin - not left to Bokeh's default auto-range, which considers
        # every renderer including the fit curve drawn below. A sigmoid
        # (appearance-time) fit can't exceed the raw data (it's built from
        # y.max() directly), but a Gaussian fit's amplitude is a free
        # parameter with no such guarantee; on a noisy/overfit ROI it can
        # come back larger than anything actually observed, stretching the
        # axis and visually squashing the real signal. Set from the raw
        # data alone so that can never happen, regardless of what the fit
        # curve does.
        finite_y = y[np.isfinite(y)]
        if finite_y.size > 0:
            y_min = float(finite_y.min())
            y_max = float(finite_y.max())
            margin = (y_max - y_min) * 0.1 if y_max > y_min else max(abs(y_max), 1.0) * 0.1
            inst["fig_strip"].y_range.start = y_min - margin
            inst["fig_strip"].y_range.end = y_max + margin

        # --- 5. Update raw data source ---
        # Keep interpolation and axis limits above on the full series, but only
        # send a display-sized trace to Bokeh. The strip plot is small; sending
        # hundreds of thousands of points makes heatmap clicks feel sticky.
        t_display, y_display = self._display_time_series(t, y)
        inst['src_strip_raw'].data = dict(t=t_display, y=y_display)

        # --- 6. Prepare containers for multiple fit curves and points ---
        xs_list = []   # for multi‑line: list of datetime arrays
        ys_list = []   # for multi‑line: list of y arrays
        colors = []    # for multi‑line: line colors
        pt_t = []      # for scatter: times (datetime)
        pt_y = []      # for scatter: y values
        pt_color = []  # for scatter: marker colors

        # --- 7. If fit overlay is enabled and a polygon is selected ---
        if inst["chk_show_fit"].active and inst['selected_poly'] is not None:
            poly = inst['polygons'][inst['selected_poly']]

            # --- 7a. Determine which fit types to show from checkboxes ---
            active_indices = inst.get('fit_checkboxes').active if inst.get('fit_checkboxes') else []
            fit_keys = inst['fit_checkbox_keys']   # list of fit keys in order
            tol = 0.5e-9   # 0.5 nm tolerance

            for idx_active in active_indices:
                fit_key = fit_keys[idx_active]
                props = self.FIT_TYPES[fit_key]
                fit_points = poly.get(props['fit_key'], [])

                for fp in fit_points:
                    # Check if this fit point matches the current diameter
                    if abs(fp['diam'] - d_actual) > tol:
                        continue

                    color = props['color']

                    # ----- Marker -----
                    # Interpolate concentration at the fitted time
                    y_marker = np.interp(fp['time'], t_ms, y)
                    pt_t.append(pd.to_datetime(fp['time'], unit='ms'))
                    pt_y.append(y_marker)
                    pt_color.append(color)

                    # ----- Curve reconstruction (if available) -----
                    # Only if the fit point contains time limits
                    if 't_min' in fp and 't_max' in fp:
                        t_min_ms = fp['t_min']
                        t_max_ms = fp['t_max']

                        # Create time axis limited to the fitted range
                        t_curve_ms = np.linspace(t_min_ms, t_max_ms, 200)

                        if fit_key == 'appearance' and 'k' in fp:
                            # Appearance fit: sigmoid in hours
                            t0_ms = fp['time']
                            k = fp['k']
                            y_max = np.nanmax(y)

                            # Convert to hours (same as fitting)
                            t_curve_hr = t_curve_ms / (1000 * 60 * 60)
                            t0_hr = t0_ms / (1000 * 60 * 60)

                            y_curve = y_max / (1 + np.exp(-k * (t_curve_hr - t0_hr)))

                            t_curve_dt = pd.to_datetime(t_curve_ms, unit='ms')
                            xs_list.append(t_curve_dt)
                            ys_list.append(y_curve)
                            colors.append(color)

                        elif fit_key == 'maxconc_gaussian' and 'sigma' in fp:
                            # Gaussian LSQ fit: Gaussian curve
                            A = fp['amplitude']
                            t0 = fp['mean']
                            sigma = fp['sigma']
                            if sigma > 0:
                                y_curve = A * np.exp(-0.5 * ((t_curve_ms - t0) / sigma) ** 2)
                                t_curve_dt = pd.to_datetime(t_curve_ms, unit='ms')
                                xs_list.append(t_curve_dt)
                                ys_list.append(y_curve)
                                colors.append(color)
                                
                                break

                        # Future: add other fit types (GMM, mode, etc.) if they have curve definitions

                    # No break – we want to include all fit points for this diameter (if multiple)

        # --- 8. Update the multi‑line and scatter sources ---
        inst['src_strip_fits'].data = dict(xs=xs_list, ys=ys_list, color=colors)
        inst['src_strip_points'].data = dict(t=pt_t, y=pt_y, color=pt_color)

    @staticmethod
    def _display_time_series(t, y, max_points=1800):
        if len(y) <= max_points:
            return t, y
        sample_idx = np.linspace(0, len(y) - 1, max_points).astype(int)
        sample_idx = np.unique(sample_idx)
        return t[sample_idx], y[sample_idx]

    @staticmethod
    def _normalize_mcc_diag_series(series):
        y = np.asarray(series, dtype=float)
        finite = np.isfinite(y)
        if not finite.any():
            return np.full_like(y, np.nan, dtype=float)
        ymin = float(np.nanmin(y[finite]))
        ymax = float(np.nanmax(y[finite]))
        if ymax == ymin:
            out = np.zeros_like(y, dtype=float)
            out[~finite] = np.nan
            return out
        return (y - ymin) / (ymax - ymin)

    def update_mcc_diagnostic(self, name, x_ms=None):
        inst = self.instruments[name]
        if x_ms is not None and "mcc_diag_marker" in inst:
            inst["mcc_diag_marker"].location = pd.to_datetime(x_ms, unit="ms")

        if not all(key in inst for key in ("mcc_diag_src_low", "mcc_diag_src_high", "fig_mcc_diag")):
            return

        df = live_instrument_state(inst, name=name).data_frame
        if df is None or df.empty:
            inst["mcc_diag_src_low"].data = dict(t=[], y=[])
            inst["mcc_diag_src_high"].data = dict(t=[], y=[])
            return

        try:
            dmin_nm = float(inst["fit_dmin_input"].value)
            dmax_nm = float(inst["fit_dmax_input"].value)
        except (KeyError, TypeError, ValueError):
            inst["fig_mcc_diag"].title.text = f"{name}  ·  MCC diagnostic: set Fit Dp min/max"
            return

        diameters = df.columns.to_numpy(dtype=float)
        if diameters.size == 0:
            return

        dmin_m = dmin_nm * 1e-9
        dmax_m = dmax_nm * 1e-9
        low_idx = int(np.argmin(np.abs(diameters - dmin_m)))
        high_idx = int(np.argmin(np.abs(diameters - dmax_m)))
        low_actual_nm = diameters[low_idx] * 1e9
        high_actual_nm = diameters[high_idx] * 1e9

        t = df.index.values
        low_y = self._normalize_mcc_diag_series(df.iloc[:, low_idx].values)
        high_y = self._normalize_mcc_diag_series(df.iloc[:, high_idx].values)
        t_low, low_y = self._display_time_series(t, low_y)
        t_high, high_y = self._display_time_series(t, high_y)
        inst["mcc_diag_src_low"].data = dict(
            t=t_low,
            y=low_y,
        )
        inst["mcc_diag_src_high"].data = dict(
            t=t_high,
            y=high_y,
        )
        inst["fig_mcc_diag"].title.text = (
            f"{name}  ·  MCC diagnostic: {low_actual_nm:.1f} nm vs {high_actual_nm:.1f} nm"
        )

    def on_tap_instrument(self, name, event):
        """Handle tap on a heatmap.

        When axes are linked, updates all dataset-panel distributions so the
        shared stacked-view figure shows the same time slice from every
        dataset panel.
        """
        inst = self.instruments[name]

        # Always update the tapped instrument
        self.update_dists(name, event.x)
        self.select_polygon(name, event)
        self.update_mode_dist_fits(name, event.x)
        self.update_dist_glyphs(name, event.x)
        self.update_mcc_diagnostic(name, event.x)
        self.update_status(name)

        # If axes linked, propagate the time click to all other instruments too
        if self.link_axes.active:
            for other_name in self.instruments:
                if other_name != name:
                    try:
                        self.update_dists(other_name, event.x)
                    except Exception:
                        pass

        # Always update the polygon span highlight (regardless of follow_cursor)
        self._update_poly_span(name)

        # Update strip plot diameter from clicked y (m → nm) if follow_cursor on
        if inst.get('chk_follow_cursor', Checkbox(active=True)).active:
            inst['strip_diameter_input'].value = f"{event.y * 1e9:.2f}"
            self.update_strip_plot(name)
            inst["strip_time_marker"].location = pd.to_datetime(event.x, unit="ms")
           
            
  
        
        
    def delete_selected_fit_points(self, name):
        """Delete box/lasso-selected fit points for the currently active fit
        type on this instrument's selected polygon.

        Shared by the "Delete" keyboard shortcut (on_keypress) and the
        explicit "🗑 Delete Selected" button - same action, two triggers.
        Requires "Fit Method" (fit_type_select) to match whatever fit type's
        points are actually selected on the heatmap; if it doesn't, the
        matching ColumnDataSource has no selection and there is nothing to
        delete, which is reported rather than silently doing nothing.
        """
        inst = self.instruments[name]
        current_fit_key = inst["fit_type_select"].value
        src_suffix = self.FIT_KEY_TO_SRC[current_fit_key]
        src = inst.get(src_suffix)
        props = self.FIT_TYPES[current_fit_key]

        if not src or not src.selected.indices:
            self.system_div.text = (
                f"⚠ No selected {props['display_name']} points to delete — "
                f"use Box Select or Lasso Select on the heatmap first, and "
                f"check that 'Fit Method' above matches the points you selected."
            )
            return 0

        sel = list(src.selected.indices)
        idx = inst.get("selected_poly")
        if idx is None or idx >= len(inst.get("polygons", [])):
            self.system_div.text = "⚠ No polygon selected"
            return 0

        poly = inst["polygons"][idx]
        before_points = copy.deepcopy(poly.get(props["fit_key"], []))
        before_growth_rates = copy.deepcopy(poly.get("growth_rates", {}))

        deleted_count = self._delete_fit_points(inst, src_suffix, sel)
        if deleted_count:
            inst["undo_stack"].append({
                "action": "delete_fit_points",
                "polygon_idx": idx,
                "fit_key": current_fit_key,
                "fit_storage_key": props["fit_key"],
                "before_points": before_points,
                "before_growth_rates": before_growth_rates,
            })
            self.system_div.text = f"<b>System:</b> Deleted {deleted_count} selected fit point(s)"
        else:
            # Previously silent: nothing visibly happened and there was no
            # way to tell why. The heatmap glyph for a fit type shows points
            # from EVERY polygon on this instrument merged into one source
            # (see _update_fit_glyphs) - selecting is purely visual and works
            # regardless of which polygon a point came from, but deleting
            # only searches the currently-SELECTED polygon's own stored
            # points (poly[props["fit_key"]]). If your lasso caught points
            # that actually belong to a different polygon than the one
            # selected in the polygon dropdown, this is exactly what you get:
            # a clean-looking selection that deletes nothing.
            self.system_div.text = (
                f"⚠ {len(sel)} point(s) were selected but none matched "
                f"{props['display_name']} points on the currently selected "
                f"polygon (#{idx}). If you have more than one ROI drawn, "
                f"check the polygon dropdown — points from every polygon are "
                f"drawn together on the heatmap, but delete only acts on "
                f"whichever polygon is currently selected."
            )

        src.selected.indices = []
        return deleted_count

    def _delete_fit_points(self, inst, src_name, selected_indices):
        """Delete selected fit markers from the selected polygon's stored fit data."""
        fit_key = self._get_fit_key_from_source(src_name)
        if not fit_key:
            print(f"Warning: Unknown source name {src_name}")
            return 0
        idx = inst.get("selected_poly")
        if idx is None or idx >= len(inst.get("polygons", [])):
            return 0

        src = inst.get(src_name)
        if src is None:
            return 0

        selected_pairs = []
        source_data = src.data
        for src_idx in selected_indices:
            try:
                selected_pairs.append((
                    time_value_to_ms(source_data["t"][src_idx]),
                    float(source_data["d"][src_idx]),
                ))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        if not selected_pairs:
            return 0
        
        props = self.FIT_TYPES[fit_key]
        poly = inst["polygons"][idx]
        
        kept = []
        deleted = 0
        for point in poly.get(props["fit_key"], []):
            try:
                point_t = time_value_to_ms(point["time"])
                point_d = float(point["diam"])
            except (KeyError, TypeError, ValueError):
                kept.append(point)
                continue

            matches_selected = any(
                np.isclose(point_t, sel_t, rtol=0, atol=1e-6)
                and np.isclose(point_d, sel_d, rtol=1e-9, atol=1e-18)
                for sel_t, sel_d in selected_pairs
            )
            if matches_selected:
                deleted += 1
            else:
                kept.append(point)

        if deleted == 0:
            return 0

        poly[props["fit_key"]] = kept
        growth_rates = poly.get("growth_rates")
        if isinstance(growth_rates, dict):
            growth_rates.pop(fit_key, None)
        self._clear_fit_line_renderer(inst, idx, fit_key)
        
        # Resolve instrument name from the inst dict itself, not from
        # self.last_active_instrument — which could point to a different
        # instrument if the user box-selects on an instrument that wasn't
        # last tapped.
        inst_name = None
        for name, registered_inst in self.instruments.items():
            if registered_inst is inst:
                inst_name = name
                break
        if inst_name is None:
            inst_name = self.last_active_instrument  # safe fallback
        if inst_name:
            self._update_fit_glyphs(inst_name, fit_key)
        return deleted
             
            

        
            
    def on_keypress(self, attr, old, new):
        if not new["key"]:
            return

        key = new["key"][-1]

        name = self.last_active_instrument or self.get_active_instrument_name()
        if name is None:
            self.key_src.data = dict(key=[])
            return

        inst = self.instruments[name]

        # ======================================================
        # 1️⃣ DELETE ROI POLYGON  (key = 'x')  ← ORIGINAL LOGIC
        # ======================================================
        if key.lower() == "x":
            idx = inst.get("selected_poly")
            if idx is None:
                self.key_src.data = dict(key=[])
                return

            inst["undo_stack"].append({
                "action": "delete_polygon",
                "polygon_idx": idx,
                "polygon": copy.deepcopy(inst["polygons"][idx]),
            })

            # Remove polygon
            del inst["polygons"][idx]
            inst["selected_poly"] = None
            
            # Update polygon selector options
            self._update_polygon_dropdown(inst)

            
            for fit_type in self.FIT_TYPES:
                self._update_fit_glyphs(name, fit_type)
                
            # Clear distribution glyphs
            for props in self.FIT_TYPES.values():
                inst[props["dist_src_suffix"]].data = dict(x=[], y=[], color=[])

            
            # Remove associated fit lines
            self._clear_fit_line_renderers(inst, idx)
            self._shift_fit_line_renderer_indices_after_delete(inst, idx)

            self.update_polygon_renderers(name)
            self.update_status(name)
            try:
                self.update_strip_plot(name)
            except Exception:
                pass
            self.system_div.text = "<b>System:</b> ROI polygon and its fit points deleted"
            self.key_src.data = dict(key=[])
            return

        # ======================================================
        # 2️⃣ DELETE SELECTED FIT GLYPHS (Delete or Backspace)
        # ======================================================
        if key in ("Delete", "Backspace"):
            self.delete_selected_fit_points(name)
            self.key_src.data = dict(key=[])
            return
            
        # ======================================================
        # 2️⃣ Undo DELETED FIT GLYPHS
        # ======================================================            
                
        if key.lower() == "z":
            if inst["undo_stack"]:
                last = inst["undo_stack"].pop()
                if last.get("action") == "delete_polygon":
                    idx = last.get("polygon_idx")
                    polygon = last.get("polygon")
                    if isinstance(idx, int) and 0 <= idx <= len(inst.get("polygons", [])) and polygon:
                        inst["polygons"].insert(idx, copy.deepcopy(polygon))
                        inst["selected_poly"] = idx
                        clear_all_fit_line_renderers(inst)
                        self._update_polygon_dropdown(inst)
                        self.update_polygon_renderers(name)
                        for fit_type in self.FIT_TYPES:
                            self._update_fit_glyphs(name, fit_type)
                        self._restore_growth_rate_lines(name)
                        self.update_status(name)
                        try:
                            self.update_strip_plot(name)
                        except Exception:
                            pass
                        self.system_div.text = "<b>System:</b> Undo ROI polygon delete"
                    else:
                        self.system_div.text = "<b>System:</b> Nothing to undo"
                elif last.get("action") == "delete_fit_points":
                    idx = last.get("polygon_idx")
                    fit_key = last.get("fit_key")
                    storage_key = last.get("fit_storage_key")
                    if idx is not None and idx < len(inst.get("polygons", [])) and fit_key and storage_key:
                        poly = inst["polygons"][idx]
                        poly[storage_key] = copy.deepcopy(last.get("before_points", []))
                        poly["growth_rates"] = copy.deepcopy(last.get("before_growth_rates", {}))
                        self._update_fit_glyphs(name, fit_key)
                        self._restore_growth_rate_lines(name)
                        src_suffix = self.FIT_KEY_TO_SRC.get(fit_key)
                        if src_suffix and src_suffix in inst:
                            inst[src_suffix].selected.indices = []
                        self.system_div.text = "<b>System:</b> Undo last fit-point delete"
                    else:
                        self.system_div.text = "<b>System:</b> Nothing to undo"
            self.key_src.data = dict(key=[])
            return
                

        # ======================================================
        # cleanup (always clear key buffer)
        # ======================================================
        self.key_src.data = dict(key=[])





    def roi_mask(self, name, poly_idx):
        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        poly = inst["polygons"][poly_idx]

        # meshgrid of data coordinates
        T, D = np.meshgrid(
            datetime_index_to_epoch_ms(df.index),   # time in ms
            df.columns.values,        # diameter
            indexing="ij"
        )

        points = np.column_stack([T.ravel(), D.ravel()])
        roi_path = Path(np.column_stack([poly["x"], poly["y"]]))

        mask = roi_path.contains_points(points)
        return mask.reshape(T.shape)
        
    def get_roi_dataframe(self, name):
        """Return a copy of df with values outside the selected polygon set to NaN.

        FIX: df.copy() from xarray/netcdf data can have a read-only underlying
        numpy array, making direct assignment to .values raise ValueError.
        Use np.where() which always allocates a fresh writable array.
        """
        inst = self.instruments[name]
        idx = inst["selected_poly"]

        if idx is None:
            self.system_div.text = "❌ No ROI selected"
            return None

        df = live_instrument_state(inst, name=name).data_frame
        mask = self.roi_mask(name, idx)

        # np.where allocates a new array — no read-only issue regardless of source
        new_values = np.where(mask, df.values, np.nan)
        roi = pd.DataFrame(new_values, index=df.index.copy(), columns=df.columns.copy())
        return roi
        

        
    def _update_fit_glyphs(self, name, fit_key):
        """Update glyphs for a specific fit type - uses FIT_TYPES registry"""
        inst = self.instruments[name]
        props = self.FIT_TYPES[fit_key]
        
        # Get source using the registry key
        src = inst[props["src_suffix"]]
        
        
        # Collect points from all polygons
        t, d = [], []
        for p in inst["polygons"]:
            for f in p[props["fit_key"]]:
                t.append(f["time"])
                d.append(f["diam"])
        
        src.data = dict(t=t, d=d)
        # Clear distribution markers
        inst[props["dist_src_suffix"]].data = dict(x=[], y=[], color=[])

        
    def _update_polygon_dropdown(self, inst):
        update_polygon_dropdown(inst)

    def _on_polygon_dropdown_change(self, name, attr, old, new):
        """Selecting a polygon from the dropdown highlights it on the heatmap."""
        inst = self.instruments[name]

        def on_selected():
            self.last_active_instrument = name
            self.update_polygon_renderers(name)
            self.update_status(name)

        select_polygon_from_dropdown(inst, new, on_selected=on_selected)

    def _clear_fit_type(self, name, fit_type):
        """Clear points for a specific fit type"""
        inst = self.instruments[name]
        props = self.FIT_TYPES[fit_type]
        
        idx = inst["selected_poly"]
        if idx is None:
            return
        
        inst["polygons"][idx][props["fit_key"]].clear()
        self._update_fit_glyphs(name, fit_type)
        self.update_status(name)
        
    def _clear_fit_line_renderer(self, inst, polygon_idx, fit_key):
        clear_fit_line_renderer(inst, polygon_idx, fit_key)

    def _shift_fit_line_renderer_indices_after_delete(self, inst, deleted_idx):
        shift_fit_line_renderer_indices_after_delete(inst, deleted_idx)

    def _clear_fit_line_renderers(self, inst, polygon_idx):
        clear_fit_line_renderers_for_polygon(inst, polygon_idx)
        
    def _run_fit_via_registry(self, fit_key, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Shared entry point for all six FIT_TYPES fit methods below.

        Builds a plain (Bokeh-free) FitRequest from the current fit
        snapshot and delegates the actual numeric work to
        fitting.registry.run_fit - the package-owned, independently
        tested implementation. This method is the only thing that still
        lives here: threading, cancellation, and Bokeh source/renderer
        mutation stay in run_fit_by_type/_fit_thread (fitting/ is
        deliberately Bokeh-free, see its modules' docstrings), so it
        keeps the same (name, data, _messages, _progress_cb, _total,
        _roi_mask) -> peaks signature run_fit_by_type already calls.

        self._fit_snapshot (num_modes/dmin_nm/dmax_nm/poly_label) is
        populated by run_fit_by_type on the IO thread before the
        background thread starts - same thread-safety reason _roi_mask
        is passed in as a plain array rather than read from Bokeh state.
        """
        if _messages is None:
            _messages = []
        snap = getattr(self, "_fit_snapshot", {})
        snapshot = FitSnapshot(
            num_modes=snap.get("num_modes", 1),
            roi_mask=_roi_mask,
            dmin_nm=snap.get("dmin_nm"),
            dmax_nm=snap.get("dmax_nm"),
            poly_label=snap.get("poly_label"),
            tau_window_hr=snap.get("tau_window_hr", FitSnapshot.tau_window_hr),
            smoothing_window_hr=snap.get("smoothing_window_hr", FitSnapshot.smoothing_window_hr),
            number_of_divisions=snap.get("number_of_divisions", FitSnapshot.number_of_divisions),
        )
        request = FitRequest(
            instrument_name=name,
            fit_key=fit_key,
            roi=data,
            snapshot=snapshot,
            cancel_token=self.cancel_flag,
            progress_callback=_progress_cb,
            total_work=_total,
        )
        result = run_fit(request)
        _messages.extend(result.messages)
        return list(result.peaks)

    def fit_cross_correlation(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Compute GR via the MCC (cross-correlation) method over the ROI.

        Unlike the other five fit methods, this produces one scalar GR for
        the whole ROI, not (t, d) point markers - so it always returns []
        and smuggles its result back to the IO thread via a specially
        prefixed _messages entry ("MCC_RESULT::<json>"), handled in
        run_fit_by_type's _apply(). See fitting.registry._run_mcc for the
        actual computation (calls science/growth_rate.py's
        compute_cross_correlation_gr using self._fit_snapshot's
        dmin_nm/dmax_nm/poly_label, populated on the IO thread before this
        runs on a background thread - same pattern num_modes already used).
        """
        return self._run_fit_via_registry(
            "mcc", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    
    def run_fit_by_type(self, name, fit_key):
        """Launch the fit in a background daemon thread.

        THREAD SAFETY RULES (Bokeh):
          - Background threads must NEVER read or write Bokeh document objects
            (ColumnDataSource, Widget, Figure, Renderer, etc.).
          - All document mutations must happen via doc.add_next_tick_callback().
          - FitCancellationToken (cancel_flag), backed by threading.Event, is
            safe from any thread.

        We therefore snapshot every piece of data the fit needs from Bokeh
        objects HERE, on the IO thread, before the background thread starts.
        The thread receives only plain Python / NumPy / Pandas values.
        """
        props = self.FIT_TYPES[fit_key]
        self.show_loader(f"Fitting {props['name']}", "Processing…")
        doc = curdoc()

        # ── Snapshot everything needed from Bokeh objects NOW (IO thread) ──
        roi = self.get_roi_dataframe(name)
        if roi is None:
            self.hide_loader()
            return

        fit_method = props.get("fit_method")
        if fit_method is None:
            self.system_div.text = f"❌ No fit method defined for {fit_key}"
            self.hide_loader()
            return

        # Snapshot widget values that fit methods read
        try:
            num_modes_val = int(self.fit_modes_input.value)
            num_modes_val = max(1, min(num_modes_val, 10))
        except ValueError:
            num_modes_val = 1

        selected_poly_idx = self.instruments[name]["selected_poly"]

        # Snapshot the true polygon mask too (same one get_roi_dataframe just
        # used to build `roi`) so fit methods can re-apply it AFTER their own
        # internal interpolation step. interpolate(limit_area="inside") fills
        # any NaN gap sandwiched between two valid values along the diameter
        # axis - it can't distinguish "real sensor gap" from "excluded by
        # this ROI", so a jagged/non-convex polygon boundary can silently let
        # a fit see (and place a peak at) diameters outside what was drawn.
        # See fit_mode for where this actually gets used.
        roi_mask_arr = (
            self.roi_mask(name, selected_poly_idx)
            if selected_poly_idx is not None else None
        )

        # Also snapshot the Fit Dp min/max fields and the selected polygon's
        # label, on the IO thread, for fit_cross_correlation - same
        # thread-safety reason as num_modes_val/roi_mask_arr above.
        try:
            dmin_nm_val = float(self.instruments[name]["fit_dmin_input"].value)
            dmax_nm_val = float(self.instruments[name]["fit_dmax_input"].value)
        except (KeyError, TypeError, ValueError):
            dmin_nm_val = None
            dmax_nm_val = None

        # MCC method-parameter fields: unlike Fit Dp min/max above, these
        # fall back to FitSnapshot's own defaults (matching the published
        # method) on blank/invalid input rather than blocking the fit -
        # they're advanced knobs, not something every MCC run requires
        # touching.
        mcc_inst = self.instruments[name]

        def _parsed_or_default(widget_key, cast, default):
            try:
                return cast(mcc_inst[widget_key].value)
            except (KeyError, TypeError, ValueError):
                return default

        tau_window_val = _parsed_or_default("mcc_tau_window_input", float, FitSnapshot.tau_window_hr)
        smoothing_window_val = _parsed_or_default(
            "mcc_smoothing_window_input", float, FitSnapshot.smoothing_window_hr
        )
        num_divisions_val = _parsed_or_default(
            "mcc_num_divisions_input", int, FitSnapshot.number_of_divisions
        )

        poly_label_val = None
        if selected_poly_idx is not None:
            polys = self.instruments[name].get("polygons", [])
            if selected_poly_idx < len(polys):
                poly_label_val = polys[selected_poly_idx].get("label") or f"Polygon {selected_poly_idx}"

        # Store snapshot on self so fit methods can read it thread-safely
        self._fit_snapshot = {
            "num_modes": num_modes_val,
            "dmin_nm": dmin_nm_val,
            "dmax_nm": dmax_nm_val,
            "poly_label": poly_label_val,
            "tau_window_hr": tau_window_val,
            "smoothing_window_hr": smoothing_window_val,
            "number_of_divisions": num_divisions_val,
        }

        total_cols = roi.shape[1]   # number of diameter bins (for progress %)

        def _post_progress(msg):
            """Thread-safe progress update to loader_div."""
            doc.add_next_tick_callback(lambda m=msg: self._update_loader_progress(m))

        def _fit_thread():
            peaks = []
            error = None
            cancelled = False
            thread_messages = []

            try:
                peaks = fit_method(name, roi,
                                   _messages=thread_messages,
                                   _progress_cb=_post_progress,
                                   _total=total_cols,
                                   _roi_mask=roi_mask_arr)
                _post_progress("Processing complete; applying fit results")

                if self.cancel_flag.is_requested():
                    cancelled = True

            except Exception as exc:
                import traceback
                error = f"❌ Fit error: {exc}<br><small>{traceback.format_exc().splitlines()[-1]}</small>"

            finally:
                def _apply():
                    try:
                        if error:
                            self.system_div.text = error
                            return
                        if cancelled:
                            self.system_div.text = "⚠ Fit cancelled after " + str(len(peaks)) + " points"
                            # Still store any partial results
                        inst = self.instruments[name]

                        # fit_cross_correlation produces one scalar GR for
                        # the whole ROI, not (t, d) points - it can't touch
                        # inst["results_div"]/self.system_div itself (runs on
                        # the background thread), so it smuggles its result
                        # back via this sentinel-prefixed message instead.
                        # Handle it here and skip the generic peaks-handling
                        # below entirely (peaks is always [] for this method).
                        mcc_msg = next(
                            (m for m in thread_messages if m.startswith("MCC_RESULT::")),
                            None,
                        )
                        if mcc_msg is not None:
                            entry = json.loads(mcc_msg[len("MCC_RESULT::"):])
                            inst.setdefault("mcc_results", []).append(entry)
                            self._refresh_mcc_panel(name)
                            dmin_txt = f"{entry['dmin_nm']:.1f}" if entry.get("dmin_nm") is not None else "?"
                            dmax_txt = f"{entry['dmax_nm']:.1f}" if entry.get("dmax_nm") is not None else "?"
                            if entry.get("ok"):
                                gr = entry["growth_rate_nm_per_hr"]
                                inst["results_div"].text = (
                                    f"<b>Cross-Correlation GR (MCC):</b><br>"
                                    f"• Growth rate: {gr:.2f} nm/hr<br>"
                                    f"• Size range: {dmin_txt}-{dmax_txt} nm<br>"
                                    f"• Region: {entry.get('region_label')}<br>"
                                    f"• Instrument: {name}"
                                )
                                self.system_div.text = f"✅ {name}: MCC growth rate {gr:.2f} nm/hr"
                            else:
                                inst["results_div"].text = (
                                    f"<b>Cross-Correlation GR (MCC) — failed:</b><br>"
                                    f"• Reason: {entry.get('reason')}<br>"
                                    f"• Size range: {dmin_txt}-{dmax_txt} nm<br>"
                                    f"• Region: {entry.get('region_label')}<br>"
                                    f"• Instrument: {name}"
                                )
                                self.system_div.text = f"❌ {name}: MCC failed — {entry.get('reason')}"
                            return

                        if selected_poly_idx is not None and peaks:
                            inst["polygons"][selected_poly_idx][props["fit_key"]].extend(peaks)
                            self._update_fit_glyphs(name, fit_key)
                            # Auto-fit the distribution Y axis to the current
                            # data after every fit, instead of requiring the
                            # user to notice and click the small "Fit Y"
                            # button - previously the axis kept whatever
                            # range it already had, which could make a
                            # perfectly good fit curve look tiny/shrunk
                            # against oversized bounds.
                            self._fit_y_axis_to_data(name, "dist")
                            if fit_key == "mode":
                                mode_lines = "<br>".join(
                                    f"@ {ms_to_datetime(p['time'])}: "
                                    f"μ={p['mean']:.2f} nm  σ={p['sigma']:.2f}  A={p['amplitude']:.2e}"
                                    for p in peaks[:5]
                                )
                                inst["results_div"].text = (
                                    f"<b>Mode Fit Results</b> ({len(peaks)} pts)<br>"
                                    + mode_lines
                                )
                            else:
                                # Show per-diameter progress messages collected from the fit loop
                                progress = "<br>".join(thread_messages[-20:]) if thread_messages else ""
                                inst["results_div"].text = (
                                    f"<b>{props['name']} Results</b> — {len(peaks)} points"
                                    + ("<br><i>Partial (cancelled)</i>" if cancelled else "")
                                    + (f"<br><small style='color:#888;'>{progress}</small>" if progress else "")
                                )
                            if not cancelled:
                                self.system_div.text = f"✅ Added {len(peaks)} {props['name']} points"
                        elif not cancelled:
                            skip_summary = next(
                                (m for m in thread_messages if m.startswith("Skip summary: ")),
                                None,
                            )
                            if skip_summary:
                                self.system_div.text = (
                                    f"⚠ {props['name']}: no peaks found in ROI — "
                                    + skip_summary[len("Skip summary: "):]
                                )
                            else:
                                self.system_div.text = f"⚠ {props['name']}: no peaks found in ROI"
                    finally:
                        self.hide_loader()

                doc.add_next_tick_callback(_apply)

        t = threading.Thread(target=_fit_thread, daemon=True)
        t.start()


    
    
    def fit_mode(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Fit lognormal modes to each time step in the ROI.

        See fitting.registry._run_mode / fitting.engines.mode_peaks_for_time
        for the actual computation, including the roi_mask re-application
        (a jagged/non-convex polygon boundary can otherwise let a mode
        land at a diameter outside what was actually drawn) and the
        degenerate-timestep guard ahead of afi.fit_multimode.
        """
        return self._run_fit_via_registry(
            "mode", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    def fit_gaussian_lsq(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Fit one Gaussian LSQ peak per diameter column in the ROI.

        See fitting.registry._run_gaussian_lsq / fitting.engines.gaussian_lsq_peak.
        """
        return self._run_fit_via_registry(
            "maxconc_gaussian", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    def fit_gmm(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Fit one GMM peak per diameter column in the ROI.

        See fitting.registry._run_gmm / fitting.engines.gmm_peak.
        """
        return self._run_fit_via_registry(
            "maxconc_gmm", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    def fit_peak_picker(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Pick one peak per diameter column in the ROI.

        See fitting.registry._run_peak_picker / fitting.engines.peak_picker_peak.
        """
        return self._run_fit_via_registry(
            "maxconc", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    def fit_appearance(self, name, data, _messages=None, _progress_cb=None, _total=None, _roi_mask=None):
        """Fit one appearance-time sigmoid peak per diameter column in the ROI.

        See fitting.registry._run_appearance / fitting.engines.appearance_time_peak.
        """
        return self._run_fit_via_registry(
            "appearance", name, data,
            _messages=_messages, _progress_cb=_progress_cb, _total=_total, _roi_mask=_roi_mask,
        )

    
    def _fit_y_axis_to_data(self, name, target="dist"):
        """Auto-fit the Y axis of the distribution or a var-line axis to visible data.

        target="dist"  → fits fig_dist y range to current distribution data
        target=line_id → fits the extra_y_range for that var line
        """
        inst = self.instruments[name]
        if target == "dist":
            src = inst.get("src_dist")
            if src is None:
                return
            y = np.array(src.data.get("y", []))
            y = y[np.isfinite(y) & (y > 0)]
            if len(y) == 0:
                return
            ymin, ymax = float(np.nanmin(y)) * 0.8, float(np.nanmax(y)) * 1.25
            fig_dist = inst["fig_dist"]
            fig_dist.y_range.start = ymin
            fig_dist.y_range.end   = ymax
        else:
            for cl in inst.get("overlay_var_lines", []):
                if cl.get("line_id") == target:
                    cl["fit_y"]()
                    break

    def update_status(self, name):
        inst = self.instruments[name]
        roi = inst["selected_poly"]
        n_poly = len(inst["polygons"])
        roi_text = f"#{roi}" if roi is not None else "—"
        modes_col = THEME["success"] if inst["toggle_modes"].active else THEME["error"]
        sum_col   = THEME["success"] if inst["toggle_sum"].active else THEME["error"]
        self.status_div.text = f"""
        <div style='font-size:11px; line-height:1.7; color:rgba(232,240,248,0.85);'>
            <b style='color:{THEME["accent2"]};'>{name}</b><br>
            ROI: <b>{roi_text}</b> &nbsp;({n_poly} polygon{'s' if n_poly != 1 else ''})<br>
            Modes: <span style='color:{modes_col};'>{"●" if inst["toggle_modes"].active else "○"}</span>
            &nbsp; Σ: <span style='color:{sum_col};'>{"●" if inst["toggle_sum"].active else "○"}</span>
        </div>
        """

        
        
    def update_mode_dist_fits(self, name, x_ms):
        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        # --- Safety checks ---
        if df is None or inst["selected_poly"] is None:
            inst["mode_multi_src"].data = dict(xs=[], ys=[], color=[])
            inst["mode_sum_src"].data = dict(x=[], y=[])
            return

        # --- Snap to nearest time ---
        target_dt = pd.to_datetime(x_ms, unit="ms")
        idx = df.index.get_indexer([target_dt], method="nearest")[0]
        closest_dt = df.index[idx]

        if pd.isna(closest_dt):
            inst["mode_multi_src"].data = dict(xs=[], ys=[], color=[])
            inst["mode_sum_src"].data = dict(x=[], y=[])
            return

        # --- Prepare ---
        y_data = df.columns.values.astype(float)

        props = self.FIT_TYPES["mode"]
        fit_key = props["fit_key"]  # <- registry driven

        polygon = inst["polygons"][inst["selected_poly"]]

        xs, ys, colors = [], [], []
        sum_curve = None

        palette = [
            "#ff7f0e",
            "#d62728",
            "#2ca02c",
            "#9467bd",
            "#8c564b",
        ]

        color_index = 0

        # --- Loop through stored mode fits ---
        for f in polygon.get(fit_key, []):
            fit_dt = pd.to_datetime(f["time"], unit="ms")

            if fit_dt == closest_dt:
                dist_fit = afi.gaussian(
                    np.log10(y_data * 1e9),
                    f["amplitude"],
                    f["mean"],
                    f["sigma"]
                )

                xs.append(y_data)
                ys.append(dist_fit)
                colors.append(palette[color_index % len(palette)])
                color_index += 1

                if sum_curve is None:
                    sum_curve = dist_fit.copy()
                else:
                    sum_curve += dist_fit

        # --- Update multi-line curves ---
        inst["mode_multi_src"].data = dict(xs=xs, ys=ys, color=colors)

        # --- Update summed curve ---
        if sum_curve is not None:
            inst["mode_sum_src"].data = dict(x=y_data, y=sum_curve)
        else:
            inst["mode_sum_src"].data = dict(x=[], y=[])

        
    def update_dist_glyphs(self, name, x_ms):
        """Update the distribution plot with glyph markers at the selected time"""
        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        if df is None or inst["selected_poly"] is None:
            # Clear all markers using FIT_TYPES
            for props in self.FIT_TYPES.values():
                inst[props["dist_src_suffix"]].data = dict(x=[], y=[], color=[])
            return
        
        # Snap to nearest time
        target_dt = pd.to_datetime(x_ms, unit="ms")
        idx = df.index.get_indexer([target_dt], method="nearest")[0]
        closest_dt = df.index[idx]
        
        if pd.isna(closest_dt):
            return
        
        # Get the distribution data at this time
        dist = df.loc[closest_dt, :]
        y_data = df.columns.values.astype(float)
        
        # Clear all markers first
        for props in self.FIT_TYPES.values():
            inst[props["dist_src_suffix"]].data = dict(x=[], y=[], color=[])
        
        # Get the selected polygon
        poly_idx = inst["selected_poly"]
        if poly_idx is not None and poly_idx < len(inst["polygons"]):
            poly = inst["polygons"][poly_idx]
            
            # Process each fit type dynamically from FIT_TYPES
            for fit_key, props in self.FIT_TYPES.items():
                x_vals = []
                y_vals = []
                colors = []
                
                # Get the fit points for this type using the fit_key from props
                fit_points = poly.get(props["fit_key"], [])
                
                for f in fit_points:
                    fit_time = pd.to_datetime(f["time"], unit="ms")
                    
                    # Snap fitted time to nearest grid point
                    nearest_idx = df.index.get_indexer([fit_time], method="nearest")[0]
                    fit_snapped = df.index[nearest_idx]
                    
                    if fit_snapped == closest_dt:
                        diam = f["diam"]
                        conc_interp = np.interp(diam, y_data, dist.values)
                        x_vals.append(diam)
                        y_vals.append(conc_interp)
                        colors.append(props["dist_color"])
                
                # Update the data source for this fit type
                inst[props["dist_src_suffix"]].data = dict(x=x_vals, y=y_vals, color=colors)



    def update_dists(self, name, x_ms):
        """Update the size-distribution plot for the clicked time step.

        - The raw curve is always drawn (it's just the spectrum at that time).
        - Fit-point markers are cleared here; update_dist_glyphs re-populates
          them only when a polygon is selected.
        """
        inst = self.instruments[name]
        df = live_instrument_state(inst, name=name).data_frame
        if df is None or df.empty:
            return

        target_dt = pd.to_datetime(x_ms, unit="ms")
        idx = df.index.get_indexer([target_dt], method="nearest")[0]
        closest_dt = df.index[idx]

        if pd.isna(closest_dt):
            return

        dist = df.loc[closest_dt, :]
        inst["fig_dist"].title.text = f"Distribution @ {closest_dt.strftime('%Y-%m-%d %H:%M')}"

        inst["src_dist"].data = dict(
            x=df.columns.values.astype(float),
            y=dist.values
        )

        # Always clear fit-point overlays here; update_dist_glyphs will re-add
        # them only if a polygon is active (called next in on_tap_instrument).
        for props in self.FIT_TYPES.values():
            if props["dist_src_suffix"] in inst:
                inst[props["dist_src_suffix"]].data = dict(x=[], y=[], color=[])
        # Also clear mode fit curves
        inst["mode_multi_src"].data = dict(xs=[], ys=[], color=[])
        inst["mode_sum_src"].data = dict(x=[], y=[])




    def update_visuals(self, attr, old, new):
        """Update color maps for all dataset panels."""
        try:
            low = float(self.clim_low.value)
            high = float(self.clim_high.value)
            pal = PALETTES[self.pal_select.value]
            for inst in self.instruments.values():
                inst["mapper"].low = low
                inst["mapper"].high = high
                inst["mapper"].palette = pal
        except ValueError:
            pass



    def update_polygon_renderers(self, name):
        inst = self.instruments[name]

        xs, ys, f_col = [], [], []

        for i, p in enumerate(inst["polygons"]):
            xs.append(p["x"])
            ys.append(p["y"])
            f_col.append(
                THEME["accent"] if i == inst["selected_poly"] else "white"
            )

        inst["poly_bg_src"].data = dict(
            xs=xs,
            ys=ys,
            fill_color=f_col,
            fill_alpha=[0.3] * len(xs),
            line_color=f_col,
            line_alpha=[0.8] * len(xs)
        )

    def finish_poly_draw(self, name):
        """Finish an in-progress PolyDrawTool polygon on double-click."""
        inst = self.instruments[name]
        data = inst["poly_src"].data
        xs_list = data.get("xs", [])
        ys_list = data.get("ys", [])

        if not xs_list or not ys_list:
            return

        xs = list(xs_list[-1])
        ys = list(ys_list[-1])
        if len(xs) < 3 or len(ys) < 3:
            return

        idx = self._add_roi_polygon(name, xs, ys)
        inst["poly_src"].data = dict(xs=[], ys=[])
        if idx is not None:
            self.system_div.text = f"Added ROI {idx}"

    def _add_roi_polygon(self, name, xs, ys, label=None):
        """Create one ROI polygon from x/y vertices and select it."""
        inst = self.instruments[name]

        if len(xs) < 3 or len(ys) < 3:
            return None

        if label is None:
            label = inst["poly_label_input"].value.strip() if "poly_label_input" in inst else ""
        if not label:
            label = f"Polygon {len(inst['polygons'])}"

        poly = {
            "x": list(xs),
            "y": list(ys),
            "label": label,
        }

        for fit_key, props in self.FIT_TYPES.items():
            poly[props["fit_key"]] = []

        inst["polygons"].append(poly)
        inst["selected_poly"] = len(inst["polygons"]) - 1
        self.last_active_instrument = name
        self.update_polygon_renderers(name)
        self.update_status(name)
        self._update_polygon_dropdown(inst)
        inst["fit_line_poly_raw"].value = str(inst["selected_poly"])
        self._update_poly_span(name)
        return inst["selected_poly"]

    def finish_rect_draw(self, name):
        """Commit the BoxEditTool rectangle after the drag gesture ends."""
        inst = self.instruments[name]
        fig = inst.get("fig")
        rect_tool = inst.get("rect_draw_tool")
        if fig is None or rect_tool is None or fig.toolbar.active_drag is not rect_tool:
            return

        rect_data = inst["rect_src"].data
        signature = (
            tuple(rect_data.get("x", [])),
            tuple(rect_data.get("y", [])),
            tuple(rect_data.get("width", [])),
            tuple(rect_data.get("height", [])),
        )
        if not any(signature) or signature == inst.get("_last_rect_roi_signature"):
            return

        idx = self.on_rect_roi_added(name, None, None, rect_data)
        if idx is not None:
            inst["_last_rect_roi_signature"] = signature

    def on_roi_box_selected(self, name, event):
        """Create a rectangular ROI from a plain drag of the box ROI tool.

        Deliberately does NOT gate on fig.toolbar.active_drag: this app never
        sets that property, so it stays at Bokeh's default "auto" forever and
        a `is not roi_tool` check would reject every call unconditionally.
        Mirrors on_poly_added(), which has no such tool-identity guard
        either.
        """
        inst = self.instruments[name]
        fig = inst.get("fig")
        roi_tool = inst.get("roi_box_tool")
        if fig is None or roi_tool is None:
            return

        if not getattr(event, "final", False):
            return

        geometry = getattr(event, "geometry", None) or {}
        if geometry.get("type") != "rect":
            return

        try:
            x0 = float(geometry["x0"])
            x1 = float(geometry["x1"])
            y0 = float(geometry["y0"])
            y1 = float(geometry["y1"])
        except (KeyError, TypeError, ValueError):
            return

        left, right = min(x0, x1), max(x0, x1)
        bottom, top = min(y0, y1), max(y0, y1)
        if right <= left or top <= bottom:
            return

        idx = self._add_roi_polygon(
            name,
            [left, right, right, left],
            [bottom, bottom, top, top],
        )
        if idx is not None:
            self.system_div.text = f"Added rectangular ROI {idx}"
        return idx

    def on_rect_roi_added(self, name, attr, old, new):
        """Convert BoxEditTool rectangles into regular ROI polygons."""
        inst = self.instruments[name]
        xs = new.get("x", [])
        ys = new.get("y", [])
        widths = new.get("width", [])
        heights = new.get("height", [])

        if not xs or not ys or not widths or not heights:
            return

        x = float(xs[-1])
        y = float(ys[-1])
        width = abs(float(widths[-1]))
        height = abs(float(heights[-1]))
        if width <= 0 or height <= 0:
            return

        left = x - width / 2
        right = x + width / 2
        bottom = y - height / 2
        top = y + height / 2

        idx = self._add_roi_polygon(
            name,
            [left, right, right, left],
            [bottom, bottom, top, top],
        )
        if idx is not None:
            inst["rect_src"].data = dict(x=[], y=[], width=[], height=[])
            self.system_div.text = f"Added rectangular ROI {idx}"
        return idx

    def on_poly_added(self, name, attr, old, new):
        """Handle freehand and click-vertex polygon drawing.

        FreehandDrawTool  — appends a complete polygon when pen lifts.
        PolyDrawTool      — fires on EVERY vertex click (incomplete) AND on
                            double-click (complete). We only accept >= 3 pts.
        """
        inst = self.instruments[name]

        new_xs = new.get("xs", [])
        new_ys = new.get("ys", [])
        old_xs = (old or {}).get("xs", [])

        if len(new_xs) == 0:
            return

        # ── New polygon from FreehandDrawTool: count increases with a complete path ──
        if len(new_xs) <= len(old_xs):
            return

        idx = len(new_xs) - 1

        # Ignore intermediate PolyDrawTool states (< 3 points = not closed yet)
        if not new_xs[idx] or len(new_xs[idx]) < 3:
            return
        
        added_idx = self._add_roi_polygon(name, list(new["xs"][idx]), list(new["ys"][idx]))
        inst["poly_src"].data = dict(xs=[], ys=[])
        if added_idx is not None:
            self.system_div.text = f"Added ROI {added_idx}"


    def toggle_axis_linking(self, attr, old, new):
        if not self.instruments:
            return

        names = list(self.instruments.keys())
        master = self.get_master_name()
        master_range = self.instruments[master]["fig"].x_range

        if new:  # LINK (real linking)
            for name in names:
                if name != master:
                    self.instruments[name]["fig"].x_range = master_range
                    self._ensure_heatmap_range_refresh_bound(name)

            self.link_axes.label = "🔗 Linked"
            self.system_div.text = "<b>System:</b> X-axes linked (live)"

        else:  # UNLINK
            for name in names:
                fig = self.instruments[name]["fig"]
                xr = fig.x_range
                fig.x_range = Range1d(start=xr.start, end=xr.end)
                self._ensure_heatmap_range_refresh_bound(name)

            self.link_axes.label = "🔓 Unlinked"
            self.system_div.text = "<b>System:</b> X-axes unlinked"




    def match_time_ranges(self):
        master = self.get_master_name()
        if not master:
            return

        master_range = self.instruments[master]["fig"].x_range

        for name, inst in self.instruments.items():
            if name == master:
                continue

            inst["fig"].x_range.start = master_range.start
            inst["fig"].x_range.end   = master_range.end

        self.system_div.text = f"🔗 Matched time range to '{master}'"


    def _json_safe(self, value):
        """Convert analysis state to strict JSON-safe Python values."""
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(v) for v in value]
        if isinstance(value, np.ndarray):
            return self._json_safe(value.tolist())
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            value = float(value)
            return value if np.isfinite(value) else None
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if isinstance(value, float):
            return value if np.isfinite(value) else None
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        return value

    def _restore_fit_points(self, points):
        """Normalize fit-point records loaded from JSON."""
        restored = []
        if not isinstance(points, list):
            return restored
        for item in points:
            if not isinstance(item, dict):
                continue
            clean = {}
            for key, value in item.items():
                if value is None:
                    clean[key] = value
                elif key in {"time", "diam", "mean", "sigma", "amplitude", "t_min", "t_max", "k", "r2"}:
                    try:
                        clean[key] = float(value)
                    except Exception:
                        clean[key] = value
                else:
                    clean[key] = value
            restored.append(clean)
        return restored

    def _read_csv_for_roi_restore(self, csv_path):
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        df.columns = df.columns.astype(float)
        df = df.sort_index()
        if not df.index.is_unique:
            df = df.groupby(df.index).mean()
        return df

    def _serialize_var_overlays(self, inst):
        overlays = []
        for cl in inst.get("overlay_var_lines", []):
            try:
                overlays.append({
                    "line_id": cl.get("line_id"),
                    "method": cl["method_select"].value,
                    "dmin_nm": cl["dmin_input"].value,
                    "dmax_nm": cl["dmax_input"].value,
                    "color": cl["color_picker"].color,
                    "style": cl["style_select"].value,
                    "thickness": cl["thickness_slider"].value,
                    "visible": cl["toggle"].active,
                    "ymin": cl["ymin_input"].value,
                    "ymax": cl["ymax_input"].value,
                })
            except Exception:
                continue
        return overlays

    def _restore_var_overlays(self, name, overlays, legacy_pm_density=None):
        if not overlays or name not in self.instruments:
            return
        inst = self.instruments[name]
        diameter_labels = self._overlay_var_diameter_labels()
        for overlay in overlays:
            if not isinstance(overlay, dict):
                continue
            self.add_overlay_var_line(name)
            if not inst["overlay_var_lines"]:
                continue
            cl = inst["overlay_var_lines"][-1]
            try:
                method = overlay.get("method", "Select Method")
                cl["method_select"].value = method
                dmin_nm = str(overlay.get("dmin_nm", ""))
                if not dmin_nm.strip() and legacy_pm_density is not None:
                    dmin_spec = diameter_labels.get(method, (None, None))[0]
                    if dmin_spec is not None and dmin_spec[1] == "raw":
                        dmin_nm = legacy_pm_density
                cl["dmin_input"].value = dmin_nm
                cl["dmax_input"].value = str(overlay.get("dmax_nm", ""))
                cl["color_picker"].color = overlay.get("color", cl["color_picker"].color)
                cl["style_select"].value = overlay.get("style", "solid")
                cl["thickness_slider"].value = int(overlay.get("thickness", 2))
                cl["toggle"].active = bool(overlay.get("visible", True))
                cl["ymin_input"].value = str(overlay.get("ymin", "") or "")
                cl["ymax_input"].value = str(overlay.get("ymax", "") or "")
                cl["update"]()
            except Exception:
                continue

    def save_rois(self):
        from tkinter import Tk, filedialog

        root = Tk()
        # Windows quirk: root.withdraw() BEFORE the dialog suppresses it
        # entirely. Keep show-then-withdraw order for compatibility.
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Save ROI file"
        )
        root.withdraw()
        root.destroy()
        if not file_path:
            self.system_div.text = "<b>System:</b> ROI save cancelled"
            return

        session_meta = default_meta()
        session_meta["data_files"] = {}
        payload = {"meta": session_meta, "instruments": {}}

        # -------- SAVE ROI STATE --------
        for name, inst in self.instruments.items():

            polygons_out = []

            for p in inst.get("polygons", []):
                poly_out = {
                    "x": p.get("x", []),
                    "y": p.get("y", []),
                    "label": p.get("label", "")
                }

                for fit_key, props in self.FIT_TYPES.items():
                    storage_key = props["fit_key"]
                    poly_out[storage_key] = self._restore_fit_points(p.get(storage_key, []))
                poly_out["growth_rates"] = p.get("growth_rates", {})

                polygons_out.append(poly_out)

            payload["instruments"][name] = {
                "polygons": polygons_out,
                "selected_poly": inst.get("selected_poly"),
                "var_overlays": self._serialize_var_overlays(inst),
                "mcc_results": list(inst.get("mcc_results", [])),
                "file_format": inst.get("type"),
                "loaded_path": getattr(inst.get("path_input"), "value", ""),
                "loaded_tz": getattr(inst.get("tz_input"), "value", ""),
                "diameter_unit": getattr(inst.get("diam_unit_input"), "value", ""),
                "data_type": getattr(inst.get("data_type_input"), "value", ""),
                "heatmap_view": getattr(inst.get("heatmap_view_select"), "value", ""),
            }

        # Save EACH instrument's DataFrame to its own CSV, not just the first.
        if self.save_df_checkbox.active:
            base = os.path.splitext(file_path)[0]
            for inst_name, inst in self.instruments.items():
                df = live_instrument_state(inst, name=inst_name).data_frame
                if df is not None:
                    try:
                        safe_name = inst_name.replace(" ", "_").replace("/", "-")
                        csv_path = f"{base}_{safe_name}.csv"
                        df.to_csv(csv_path, index=True)
                        payload["meta"]["data_files"][inst_name] = os.path.basename(csv_path)
                    except Exception as e:
                        self.system_div.text = f"<b>Error:</b> Failed to save CSV for {inst_name} ({e})"
                        return
        payload = self._json_safe(payload)

        # -------- WRITE JSON ATOMICALLY --------
        try:
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, allow_nan=False)
                f.write("\n")
            os.replace(tmp_path, file_path)

            self.system_div.text = f"<b>System:</b> ROIs saved to<br>{file_path}"

        except Exception as e:
            try:
                if os.path.exists(file_path + ".tmp"):
                    os.remove(file_path + ".tmp")
            except Exception:
                pass
            self.system_div.text = f"<b>Error:</b> Failed to save ROIs ({e})"

        



    def load_rois(self):
        from tkinter import Tk, filedialog

        root = Tk()
        path = filedialog.askopenfilename(
            title="Load ROI file",
            filetypes=[("JSON files", "*.json")]
        )
        root.withdraw()
        root.destroy()
        if not path:
            self.system_div.text = "<b>System:</b> ROI load cancelled"
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self.system_div.text = (
                "<b>Error:</b> ROI JSON is not valid. "
                f"Line {e.lineno}, column {e.colno}. "
                "The file may be from an interrupted/failed save; please save again with the current version."
            )
            return
        except Exception as e:
            self.system_div.text = f"<b>Error:</b> Failed to load ROIs ({e})"
            return

        try:
            data = normalize_session_payload(data)
        except (TypeError, ValueError) as e:
            self.system_div.text = f"<b>Error:</b> Invalid ROI file format ({e})"
            return

        supported_formats = {"csv", "nais(.nc)"}
        created_panels = []
        skipped_panels = []
        skipped_panel_names = set()
        for inst_name, inst_state in data["instruments"].items():
            file_format = inst_state.get("file_format") if isinstance(inst_state, dict) else None
            if file_format is not None and file_format not in supported_formats:
                skipped_panel_names.add(inst_name)
                skipped_panels.append(f"{inst_name} (unsupported format: {file_format})")
                continue
            if inst_name in self.instruments:
                continue
            if file_format not in supported_formats:
                skipped_panel_names.add(inst_name)
                skipped_panels.append(f"{inst_name} (unsupported format: {file_format or 'missing'})")
                continue
            try:
                self.create_instrument_entry(inst_name, file_format)
                created_panels.append(inst_name)
            except Exception as e:
                skipped_panel_names.add(inst_name)
                skipped_panels.append(f"{inst_name} ({e})")

        if created_panels:
            self.update_master_options()
            self.tabs.tabs = self._generate_tabs()
            self.update_view_mode(None, None, self.view_mode.value)
            if self.show_tab_manager.active:
                self.tab_manager_container.children = [self.build_tab_manager()]

        # -------- OPTIONAL CSV LOAD FIRST --------
        if self.load_df_checkbox.active:
            meta = data.get("meta", {})
            data_files = meta.get("data_files", {})
            if not data_files and meta.get("data_file"):
                # Legacy single-data-file format.
                data_files = {name: meta.get("data_file") for name in data.get("instruments", {})}

            for inst_name, data_file in data_files.items():
                if inst_name in skipped_panel_names or inst_name not in self.instruments or not data_file:
                    continue
                csv_path = os.path.join(os.path.dirname(path), data_file)
                if not os.path.exists(csv_path):
                    self.system_div.text = f"<b>Warning:</b> CSV file not found for {inst_name}; loading ROI only"
                    continue
                try:
                    df = self._read_csv_for_roi_restore(csv_path)
                    self.update_image(inst_name, df)
                    if self.instruments[inst_name]["type"] == "csv":
                        self.instruments[inst_name]["path_input"].value = csv_path
                    self._style_load_button(self.instruments[inst_name]["load_btn"], "loaded")
                except Exception as e:
                    self.system_div.text = f"<b>Error:</b> Failed to load CSV for {inst_name} ({e})"
                    return

        # -------- RESTORE ROI STATE --------
        loaded_count = 0
        restored_panels = 0
        restored_panel_names = []

        for inst_name, inst_state in data["instruments"].items():

            if inst_name in skipped_panel_names or inst_name not in self.instruments:
                continue

            inst = self.instruments[inst_name]
            loaded_path = inst_state.get("loaded_path")
            if isinstance(loaded_path, str) and loaded_path:
                inst["path_input"].value = loaded_path
            loaded_tz = inst_state.get("loaded_tz")
            if isinstance(loaded_tz, str) and loaded_tz and is_valid_timezone(loaded_tz):
                inst["tz_input"].value = loaded_tz
            diameter_unit = inst_state.get("diameter_unit")
            if isinstance(diameter_unit, str) and diameter_unit in DIAMETER_UNIT_OPTIONS:
                inst["diam_unit_input"].value = diameter_unit
            data_type = inst_state.get("data_type")
            if isinstance(data_type, str) and data_type in DATA_TYPE_OPTIONS:
                inst["data_type_input"].value = data_type
            heatmap_view = inst_state.get("heatmap_view")
            if (
                isinstance(heatmap_view, str)
                and heatmap_view
                and inst.get("heatmap_view_select") is not None
                and heatmap_view in inst["heatmap_view_select"].options
            ):
                inst["heatmap_view_select"].value = heatmap_view
            # Pre-density-box-removal saves stored one density for the whole
            # instrument here rather than per PM overlay line (there was no
            # per-line density box yet) - kept only as a fallback passed into
            # _restore_var_overlays for whichever restored PM line's own
            # dmin_nm comes back blank, so old saved sessions don't silently
            # lose their density and fail to plot; new saves never populate
            # this key at all (see _serialize_var_overlays).
            legacy_pm_density = inst_state.get("pm_density")
            if not (isinstance(legacy_pm_density, str) and legacy_pm_density):
                legacy_pm_density = None
            inst["polygons"] = []

            for p in inst_state.get("polygons", []):
                if not isinstance(p, dict) or "x" not in p or "y" not in p:
                    continue

                xs = p.get("x", [])
                ys = p.get("y", [])
                if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) < 3 or len(ys) < 3:
                    continue

                polygon = {
                    "x": [float(v) for v in xs],
                    "y": [float(v) for v in ys],
                    "label": p.get("label", "")
                }

                for fit_key, props in self.FIT_TYPES.items():
                    storage_key = props["fit_key"]
                    polygon[storage_key] = self._restore_fit_points(p.get(storage_key, []))
                polygon["growth_rates"] = p.get("growth_rates", {})

                inst["polygons"].append(polygon)
                loaded_count += 1

            selected = inst_state.get("selected_poly")
            if isinstance(selected, int) and 0 <= selected < len(inst["polygons"]):
                inst["selected_poly"] = selected
            else:
                inst["selected_poly"] = 0 if inst["polygons"] else None

            mcc_results = inst_state.get("mcc_results", [])
            inst["mcc_results"] = mcc_results if isinstance(mcc_results, list) else []
            self._refresh_mcc_panel(inst_name)

            for cl in list(inst.get("overlay_var_lines", [])):
                self._remove_overlay_var_line(inst_name, cl.get("line_id"))

            # -------- REBUILD VISUALS --------
            self._update_polygon_dropdown(inst)
            self.update_polygon_renderers(inst_name)

            for fit_key in self.FIT_TYPES:
                self._update_fit_glyphs(inst_name, fit_key)

            if hasattr(self, "_restore_conc_line"):
                self._restore_conc_line(inst_name)

            self._restore_var_overlays(
                inst_name, inst_state.get("var_overlays", []), legacy_pm_density=legacy_pm_density
            )
            clear_all_fit_line_renderers(inst)
            self._restore_growth_rate_lines(inst_name)

            restored_panels += 1
            restored_panel_names.append(inst_name)

        message = f"<b>System:</b> Loaded {loaded_count} ROI(s) into {restored_panels} dataset panel(s)"
        if restored_panel_names:
            message += f"<br><small>Restored panels: {', '.join(restored_panel_names)}</small>"
        if created_panels:
            message += f"<br><small>Recreated panels: {', '.join(created_panels)}</small>"
        if skipped_panels:
            message += f"<br><small>Skipped panels: {', '.join(skipped_panels)}</small>"
        self.system_div.text = message

    def _generate_tabs(self):
        tabs_list = []


        for name, inst in self.instruments.items():

            # Build main content
            content = self._build_instrument_content(name, inst)

            #Create close button for THIS tab
            close_btn = Button(label="Remove Dataset", button_type="danger", width=80)

            def make_close(n):
                return lambda: self._on_tab_closed(n)

            close_btn.on_click(make_close(name))
            
            header = row(
                Div(text=  " "), #f" X will just hide the tab. To permanently delete it >> "),
                Spacer(),)
                #close_btn)
                

            # Wrap content with close button
            wrapped_content = column(header, content)

            # Create panel
            panel = TabPanel(title=name, child=wrapped_content, tags=[name]) #, closable=True)

            tabs_list.append(panel)

        return tabs_list
        

    # def _build_top_row(self, name, inst):
        # controls = [inst["file_input"]]
        # if inst["type"] == "nais(.nc)":
            # controls.append(self.species_sel)
        # if inst.get("cb_toggle_"):
            # controls.append(inst["cb_toggle_"])
        # return row(*controls, sizing_mode="stretch_width")
        
    def _build_top_row(self, name, inst):
        """Build the top control row for an instrument"""
        # File controls in a row
        file_controls = row(
            inst["browse_btn"],
            inst["path_input"],
            inst["tz_input"],
            inst["diam_unit_input"],
            inst["data_type_input"],
            inst["load_btn"],
            spacing=8,
            sizing_mode="stretch_width"
        )
        
        # Variable selector for NetCDF files
        species_control = None
        if inst["type"] == "nais(.nc)":  # NetCDF format
            species_control = row(
                Div(text="<b>Species:</b>", styles={"color": THEME["text_secondary"], "margin-right": "8px"}),
                self.species_sel,
                spacing=5
            )
        
        # Return both as separate elements to be placed in column
        return file_controls, species_control
    
    def _build_heatmap_controls(self, inst):
        return row(
            Div(text="<b>HEATMAP</b>", styles={"color": THEME["accent"], "margin-top": "6px", "margin-right": "12px"}),
            row(inst["pal_select"], Spacer(width=8), inst["clim_low"], inst["clim_high"], Spacer(width=8)),
            sizing_mode="stretch_width", styles={"margin-left": "20px"}
        )
    
       
        
    def _build_instrument_content(self, name, inst):
        # Get the top row components
        file_controls, species_control = self._build_top_row(name, inst)
        
        # Heatmap controls card
        heatmap_controls = row(
            inst["pal_select"], 
            Spacer(width=10), 
            inst["clim_low"], 
            inst["clim_high"],
            Spacer(width=10),
            inst["cb_toggle_"]
        )
        
        # Fit controls section
        fit_selector_row = row(inst["fit_type_select"], inst["fit_badge"])
        fit_control_row = row(fit_selector_row, inst["btn_fit_"], inst["btn_clear_"])
        fit_line_row = row(inst["fit_line_poly"], inst["fit_line_source"], inst["btn_fit_line_"])
        dp_controls = inst.get("fit_dp_controls", Spacer())
        label_row = row(inst.get("poly_label_input", Spacer()), inst.get("btn_update_label", Spacer()), sizing_mode="stretch_width")
        
        # Distribution tab content
        dist_help = Div(text=f"""
            <div style='font-size:11px; color:{THEME["text_secondary"]};
                         background:{THEME["surface"]}; border-radius:5px;
                         padding:6px 10px; border-left:3px solid {THEME["info"]};
                         margin-bottom:6px; line-height:1.55;'>
                <b>📊 Size Distribution</b> — spectrum at clicked time.<br>
                Coloured markers show fit results from the active ROI.<br>
                <b>Modes / Σ</b> — toggle lognormal mode curves on/off.
            </div>
        """, sizing_mode="stretch_width")

        btn_fit_y_dist = Button(label="⟺ Fit Y", button_type="light", width=70)
        btn_fit_y_dist.on_click(lambda n=name: self._fit_y_axis_to_data(n, "dist"))
        btn_fit_y_dist_ = TooltipManager.add_to_button(btn_fit_y_dist, "fit_y_dist")

        dist_controls = row(
            inst["toggle_modes_"],
            Spacer(width=8),
            inst["toggle_sum_"],
            Spacer(width=16),
            Div(text=f"<span style='font-size:11px; color:{THEME['text_secondary']};'>"
                     f"Modes:</span>"),
            Spacer(width=4),
            self.fit_modes_input,
            Spacer(),
            btn_fit_y_dist_,
            sizing_mode="stretch_width",
            styles={"align-items": "center"},
        )

        dist_tab_content = column(
            dist_help,
            inst["fig_dist"],
            dist_controls,
            sizing_mode="stretch_width"
        )

        strip_help = TooltipManager._create_themed_help_button(
            TooltipManager.create(
                "<b>Diameter Time Strip</b><br>"
                "Shows concentration vs time at one diameter.<br>"
                "Follow cursor updates the diameter from heatmap clicks.<br>"
                "Overlay fit shows fitted points/curves only for the selected ROI."
            )
        )

        strip_controls_row = row(
            inst["strip_diameter_input"],
            Spacer(width=6),
            inst["btn_plot_strip"],
            Spacer(width=12),
            inst["chk_follow_cursor"],
            Spacer(width=8),
            inst["chk_show_fit"],
            Spacer(width=6),
            strip_help,
            sizing_mode="stretch_width",
        )

        strip_tab_content = column(
            inst["fig_strip"],
            strip_controls_row,
            Div(text=f"<span style='font-size:10px; color:{THEME['text_secondary']};'>"
                      f"Fit overlays:</span>", sizing_mode="stretch_width"),
            inst["fit_overlay_legend"],
            inst["fit_checkboxes"],
            sizing_mode="stretch_width"
        )

        # Kept to one line - the tau/smoothing/divisions tooltips (see
        # tooltip_manager.py's mcc_tau_window etc.) already explain what
        # each field does, so repeating that here would just be the same
        # text twice.
        mcc_help = Div(text=f"""
            <div style='font-size:11px; color:{THEME["text_secondary"]};
                         background:{THEME["surface"]}; border-radius:5px;
                         padding:5px 10px; border-left:3px solid #e41a1c;
                         margin-bottom:4px; line-height:1.4;'>
                <b>MCC Cross-Correlation</b> - uses the selected ROI and the
                Fit Dp min/max range from Fitting Tools.
            </div>
        """, sizing_mode="stretch_width")

        mcc_controls_row = row(
            inst["btn_run_mcc_"],
            Spacer(width=10),
            inst["mcc_tau_window_input"],
            inst["mcc_smoothing_window_input"],
            inst["mcc_num_divisions_input"],
            styles={"align-items": "end", "flex-wrap": "wrap"},
        )

        mcc_tab_content = column(
            mcc_help,
            mcc_controls_row,
            inst["fig_mcc_diag"],
            inst["mcc_results_div"],
            sizing_mode="stretch_width"
        )

        # Local tabs
        local_tabs = Tabs(
            tabs=[
                TabPanel(title="📊 Size Distribution", child=dist_tab_content),
                TabPanel(title="📈 Diameter Strip", child=strip_tab_content),
                TabPanel(title="MCC Cross-Correlation", child=mcc_tab_content),
            ],
            sizing_mode="stretch_width"
        )
        
        # Conc lines container
        conc_controls = inst["overlay_var_container"]
        
        # Create close button separately
        close_tab_btn = Button(label="✕ delete Tab permanently", button_type="danger", width=100)
        close_tab_btn.on_click(lambda: self._on_tab_closed(name))
        
        # ── Top bar: file loader + species + close ──
        top_bar = row(
            file_controls,
            species_control if species_control else Div(text="", width=0),
            Spacer(),
            close_tab_btn,
            sizing_mode="stretch_width",
            styles={
                "background": THEME["surface"],
                "padding": "6px 10px",
                "border-radius": "6px",
                "border": f"1px solid {THEME['border']}",
                "margin-bottom": "8px",
                "align-items": "center",
            }
        )

        # ── Heatmap colour controls ──
        heatmap_ctrl_card = row(
            Div(text=f"<span style='font-size:10px; font-weight:700; text-transform:uppercase;"
                     f" letter-spacing:0.8px; color:{THEME['text_secondary']};'>Colour map</span>"),
            Spacer(width=8),
            inst["pal_select"],
            Spacer(width=10),
            Div(text=f"<span style='font-size:11px; color:{THEME['text_secondary']};'>Min</span>"),
            Spacer(width=4), inst["clim_low"],
            Spacer(width=6),
            Div(text=f"<span style='font-size:11px; color:{THEME['text_secondary']};'>Max</span>"),
            Spacer(width=4), inst["clim_high"],
            Spacer(width=6),
            inst["clim_auto_"],
            Spacer(width=10),
            inst["cb_toggle_"],
            Spacer(width=10),
            inst["heatmap_view_select"],
            sizing_mode="stretch_width",
            styles={
                "background": THEME["surface"],
                "padding": "5px 10px",
                "border-radius": "5px",
                "border": f"1px solid {THEME['border']}",
                "margin-bottom": "6px",
                "align-items": "center",
            }
        )

        # ── Fitting tools card with inline help text ──
        fit_help = Div(text=f"""
            <div style='font-size:11px; color:{THEME["text_secondary"]};
                         line-height:1.5; margin-bottom:6px;'>
                <b>Fitting:</b> Select method → draw ROI polygon → click ▶ Run Fit.<br>
                <b>Growth Rate:</b> After fitting, select source+polygon → Calculate GR.
            </div>
        """, sizing_mode="stretch_width")

        fitting_card = self._create_card("🔬  Fitting Tools", [
            fit_help,
            fit_control_row,
            Spacer(height=8),
            Div(text=f"<span style='font-size:10px; font-weight:600; text-transform:uppercase;"
                     f" letter-spacing:0.7px; color:{THEME['text_secondary']};'>"
                     f"Growth Rate</span>",
                sizing_mode="stretch_width"),
            fit_line_row,
            Spacer(height=6),
            dp_controls,
            Spacer(height=8),
            Div(text=f"<span style='font-size:10px; font-weight:600; text-transform:uppercase;"
                     f" letter-spacing:0.7px; color:{THEME['text_secondary']};'>"
                     f"Polygon Label</span>",
                sizing_mode="stretch_width"),
            label_row,
        ])

        # ── Variable lines card ──
        var_lines_card = self._create_card("📈  Variable Overlays (Conc / CS / CoagS / PM)", [
            Div(text=f"<span style='font-size:11px; color:{THEME['text_secondary']};'>"
                     f"Add a concentration variable (CS, CoagS, Total N, PM1/PM2.5/PM10/"
                     f"PM(custom), …) as a second Y-axis overlay on the heatmap. PM reads "
                     f"density from its own Dmin box below (each line can use its own).</span>",
                sizing_mode="stretch_width"),
            Spacer(height=6),
            row(
                inst["btn_add_overlay_var_"],
                Spacer(width=12),
                inst["pm_interpolate_input"],
                Spacer(width=8),
                inst["pm_data_max_div"],
                sizing_mode="stretch_width",
                styles={"align-items": "center"},
            ),
        ])

        # ── Results card ──
        results_card = self._create_card("📊  Analysis Results", [inst["results_div"]])

        # ── Two-column lower section ──
        lower_section = row(
            # Left: plots + var lines
            column(
                local_tabs,
                Spacer(height=10),
                var_lines_card,
                conc_controls,
                sizing_mode="stretch_width",
                styles={"margin-right": "12px"},
            ),
            # Right: fitting + results
            column(
                fitting_card,
                Spacer(height=8),
                results_card,
                width=360,
            ),
            sizing_mode="stretch_width",
        )

        return column(
            top_bar,
            heatmap_ctrl_card,
            inst["fig"],
            inst["pointer_info_div"],   # pointer readout below heatmap
            Spacer(height=6),
            lower_section,
            sizing_mode="stretch_width",
        )
        

        
    def _generate_stacked_view(self):
        """Stacked view: all heatmaps + one shared distribution figure with a legend.

        Instead of N separate distribution plots side-by-side, draws all
        instrument distributions as coloured lines on ONE shared figure. When
        axes are linked, clicking any heatmap updates all lines
        simultaneously.
        """
        from bokeh.palettes import Category10
        inst_items = list(self.instruments.items())
        heatmaps = [inst["fig"] for _, inst in inst_items]

        # Build one shared distribution figure
        shared_dist_fig = None
        if inst_items:
            shared_dist_fig = figure(
                height=260,
                x_axis_type="log",
                title="Size Distribution (all datasets)",
                sizing_mode="stretch_width",
                tools="pan,box_zoom,wheel_zoom,reset,save",
                background_fill_color=THEME["plot_bg"],
                border_fill_color=THEME["panel"],
                outline_line_color=THEME["plot_border"],
            )
            shared_dist_fig.xaxis.axis_label = "Diameter (m)"
            shared_dist_fig.yaxis.axis_label = "dN/dlogDp (cm⁻³)"
            for attr in ['axis_label_text_color','major_label_text_color','axis_line_color']:
                setattr(shared_dist_fig.xaxis, attr, THEME["text_secondary"])
                setattr(shared_dist_fig.yaxis, attr, THEME["text_secondary"])
            shared_dist_fig.xgrid.grid_line_color = THEME["border"]
            shared_dist_fig.ygrid.grid_line_color = THEME["border"]

            colors = Category10[max(3, len(inst_items))]
            for i, (n, inst) in enumerate(inst_items):
                color = colors[i % len(colors)]
                # Add a line renderer that reads from each instrument's src_dist
                shared_dist_fig.line(
                    "x", "y",
                    source=inst["src_dist"],
                    line_width=2,
                    color=color,
                    legend_label=n,
                    alpha=0.85,
                )
            shared_dist_fig.legend.location = "top_right"
            shared_dist_fig.legend.click_policy = "hide"
            shared_dist_fig.legend.label_text_font_size = "11px"

        children = []
        for _, inst in inst_items:
            children.append(inst["fig"])
            children.append(inst["pointer_info_div"])
        if shared_dist_fig:
            children.append(Spacer(height=8))
            children.append(shared_dist_fig)

        return column(*children, sizing_mode="stretch_both")

    def update_view_mode(self, attr, old, new):
        
        if new == "Tabs":
            self.center_container.children = [self.tabs]
        else:
            stacked = self._generate_stacked_view()   # generate fresh view
            self.center_container.children = [stacked]

    def _on_tab_closed(self, name):
        
        
        if name not in self.instruments:
            return

        # Clean up resources
        inst = self.instruments[name]
        inst["overlay_var_lines"].clear()
        inst["fit_line_srcs"].clear()
        inst["fit_line_renderers"].clear()

        del self.instruments[name]
 
        if name in self.cache:
            del self.cache[name]

        # Update views
        self.tabs.tabs = self._generate_tabs()
        self.update_view_mode(None, None, self.view_mode.value)
        
        # If deleted instrument was master, reset to Auto
        if self.master_select.value == name:
            self.master_select.value = "Auto"
        self.update_master_options()

        if self.show_tab_manager.active:
            self.tab_manager_container.children = [self.build_tab_manager()]

        self.system_div.text = f"🗑 Closed tab '{name}'"

    def get_instrument_tabs(self):
        """Get instrument tabs using tags (more robust than title)"""
        if not isinstance(self.tabs, Tabs):
            return []
        
        if hasattr(self, 'settings_tab') and self.settings_tab is not None:
            return [t for t in self.tabs.tabs 
                    if t is not self.settings_tab and t.tags and len(t.tags) > 0]
        return [t for t in self.tabs.tabs if t.tags and len(t.tags) > 0]

    def get_stable_name(self, tab):
        """Safely extract stable name from tab tags"""
        if tab and hasattr(tab, 'tags') and tab.tags and len(tab.tags) > 0:
            return tab.tags[0]
        return None

    def build_tab_manager(self):

        """Build tab management UI - production-safe, handles all edge cases"""

        #  Stacked mode - tab management not applicable
        if not isinstance(self.tabs, Tabs):
            return column(
                Div(text="""
                    <div style="
                        padding: 20px;
                        background: #1e293b;
                        border-radius: 8px;
                        text-align: center;
                        color: #94a3b8;
                        border-left: 3px solid #3b82f6;
                    ">
                        <div style="font-size: 32px; margin-bottom: 10px;">📊</div>
                        <b style="font-size: 16px;">Stacked Mode Active</b><br>
                        <span style="font-size: 12px;">Tab reordering only available in Tabs mode</span>
                    </div>
                """),
                width=300
            )
        

        instrument_tabs = self.get_instrument_tabs()
        if not instrument_tabs: 
            return column(Div(text="Loading..."), width=300)
        

        current_names = []
        for t in instrument_tabs:
            name = self.get_stable_name(t)
            if name and name in self.instruments:  # verify instrument exists
                current_names.append(name)
                
        
        if not current_names:
            return column(Div(text="No valid datasets found"), width=300)
        
        instrument_selector = Select(
            title="Select Dataset",
            options=current_names,
            value=current_names[0],
            width=250,
            css_classes=["modern-select"]
        )
        
        # Status display - ALWAYS uses live selector.options, not frozen list
        status_div = Div(
            text=self._get_tab_status_text(instrument_selector.options, instrument_selector.value),
            styles={"color": "#94a3b8", "font-size": "12px", "margin": "5px 0"}
        )
        
        def update_status(attr, old, new):
            """Update status using live selector options"""
            if new in instrument_selector.options:
                status_div.text = self._get_tab_status_text(instrument_selector.options, new)
        
        instrument_selector.on_change("value", update_status)
        
        # Common move validation
        def validate_move(name, current_tabs):
            """Validate move operation is safe"""
            if not name:
                return False, "No dataset selected"
            
            # Check if instrument exists in dict (defensive)
            if name not in self.instruments:
                return False, f"Dataset '{name}' not found in registry"
            
            # Check if tab exists with this tag
            found = False
            for t in current_tabs:
                stable_name = self.get_stable_name(t)
                if stable_name == name:
                    found = True
                    break
            
            if not found:
                return False, f"Tab for '{name}' no longer exists"
            
            return True, ""
        
        # Move Up
        def move_up():
            name = instrument_selector.value
            current_tabs = self.get_instrument_tabs()
            
            # Validate
            valid, msg = validate_move(name, current_tabs)
            if not valid:
                if hasattr(self, "system_div"):
                    self.system_div.text = f"⚠ {msg}"
                return
            
            # Find using tags with safety checks
            for i, tab in enumerate(current_tabs):
                stable_name = self.get_stable_name(tab)
                if stable_name == name and i > 0:
                    current_tabs[i-1], current_tabs[i] = current_tabs[i], current_tabs[i-1]
                    break
            else:
                return  # Already at top
            
            # Build new tabs list SAFELY (avoid settings tab duplication)
            new_tabs = list(current_tabs)
            if hasattr(self, 'settings_tab') and self.settings_tab is not None:
                # Only add if not already present
                if self.settings_tab not in new_tabs:
                    new_tabs.append(self.settings_tab)
            
            self.tabs.tabs = new_tabs
            
            # Update instruments order with safety (skip any that don't exist)
            ordered_names = []
            for t in current_tabs:
                stable_name = self.get_stable_name(t)
                if stable_name and stable_name in self.instruments:
                    ordered_names.append(stable_name)
            
            # Only update if we have valid names
            if ordered_names:
                self.instruments = {k: self.instruments[k] for k in ordered_names if k in self.instruments}
            
            # Update UI
            instrument_selector.options = ordered_names
            if name in ordered_names:
                instrument_selector.value = name
            elif ordered_names:
                instrument_selector.value = ordered_names[0]
            
            # Safe system message
            if hasattr(self, "system_div"):
                self.system_div.text = f"✅ Moved '{name}' up"
                
            status_div.text = self._get_tab_status_text(
                instrument_selector.options,
                instrument_selector.value
            )
        
        # Move Down
        def move_down():
            name = instrument_selector.value
            current_tabs = self.get_instrument_tabs()
            
            # Validate
            valid, msg = validate_move(name, current_tabs)
            if not valid:
                if hasattr(self, "system_div"):
                    self.system_div.text = f"⚠ {msg}"
                return
            
            # Find using tags with safety checks
            for i, tab in enumerate(current_tabs):
                stable_name = self.get_stable_name(tab)
                if stable_name == name and i < len(current_tabs) - 1:
                    current_tabs[i+1], current_tabs[i] = current_tabs[i], current_tabs[i+1]
                    break
            else:
                return  # Already at bottom
            
            # Build new tabs list SAFELY (avoid settings tab duplication)
            new_tabs = list(current_tabs)
            if hasattr(self, 'settings_tab') and self.settings_tab is not None:
                # Only add if not already present
                if self.settings_tab not in new_tabs:
                    new_tabs.append(self.settings_tab)
            
            self.tabs.tabs = new_tabs
            
            # Update instruments order with safety (skip any that don't exist)
            ordered_names = []
            for t in current_tabs:
                stable_name = self.get_stable_name(t)
                if stable_name and stable_name in self.instruments:
                    ordered_names.append(stable_name)
            
            # Only update if we have valid names
            if ordered_names:
                self.instruments = {k: self.instruments[k] for k in ordered_names if k in self.instruments}
            
            # Update UI
            instrument_selector.options = ordered_names
            if name in ordered_names:
                instrument_selector.value = name
            elif ordered_names:
                instrument_selector.value = ordered_names[0]
            
            if hasattr(self, "system_div"):
                self.system_div.text = f"✅ Moved '{name}' down"
                
            status_div.text = self._get_tab_status_text(
                instrument_selector.options,
                instrument_selector.value
            )

        
        move_up_btn = Button(label="↑ Move Up", width=110, button_type="primary")
        move_up_btn.on_click(move_up)
        
        move_down_btn = Button(label="↓ Move Down", width=110, button_type="primary")
        move_down_btn.on_click(move_down)
        
        # Initial status update
        update_status(None, None, instrument_selector.value)
        
        return column(
            Div(text="<b style='color: #f1f5f9; font-size: 14px;'>📑 Tab Order</b>"),
            instrument_selector,
            status_div,
            row(move_up_btn, move_down_btn, spacing=5),
            Div(text="<hr style='border: 1px solid #334155; margin: 10px 0;'>"),
            width=300
        )

    def _get_tab_status_text(self, options, current):
        """Generate status text from live options"""
        if not options or current not in options:
            return "📌 Select a dataset"
        idx = options.index(current) + 1
        return f"📌 {len(options)} dataset(s) • Position: {idx}/{len(options)}"

    def toggle_tab_manager(self, active):
        """Show/hide tab manager"""
        if active:
            self.tab_manager_container.children = [self.build_tab_manager()]
            self.show_tab_manager.label = "📑 Hide Tab Manager"
        else:
            self.tab_manager_container.children = []
            self.show_tab_manager.label = "📑 Show Tab Manager"
        




    # --- LAYOUT ---
    def setup_layout(self):
        # Build Dataset Sidebar Sections
        if self.sidebar is None:
            # ── Sidebar header ──
            sidebar_header = Div(text=f"""
                <div style='display:flex; align-items:center; padding: 4px 0 16px 0;
                             border-bottom: 1px solid rgba(255,255,255,0.12);
                             margin-bottom: 16px;'>
                    <div style='
                        width:38px; height:38px;
                        background: linear-gradient(135deg, {THEME["accent"]}, {THEME["accent2"]});
                        border-radius: 10px;
                        display:flex; align-items:center; justify-content:center;
                        margin-right: 12px; flex-shrink:0;
                        box-shadow: 0 2px 8px rgba(0,114,178,0.35);
                    '><span style='color:white; font-size:18px;'>🔬</span></div>
                    <div>
                        <div style='color:#e8f0f8; font-size:15px; font-weight:700;
                                     letter-spacing:0.3px;'>Aerosol Studio</div>
                        <div style='color:rgba(255,255,255,0.4); font-size:10px;
                                     letter-spacing:0.5px; margin-top:1px;'>
                             NPF Analysis · v0.2</div>
                    </div>
                </div>
            """, sizing_mode="stretch_width")

            self.sidebar = column(
                sidebar_header,
                self.system_div,
                Spacer(height=10),
                self._create_card("🖥  Display", [
                    self.view_mode,
                    row(self.master_select, Spacer(width=8), self.link_axes),
                    self.sync_btn_,
                ], sidebar=True),
                Spacer(height=6),
                self._create_card("🎨  Heatmap", [
                    self.pal_select,
                    row(self.clim_low, Spacer(width=6), self.clim_high),
                ], sidebar=True),
                Spacer(height=6),
                self._create_card("➕  Add Dataset", [
                    row(self.new_inst_name, Spacer(width=6), self.new_inst_type),
                    self.btn_add_inst_,
                ], sidebar=True),
                Spacer(height=6),
                self.status_div,
                Spacer(height=6),
                self._create_card("💾  Save / Load", [
                    row(self.btn_save_roi, Spacer(width=4), self.save_df_checkbox),
                    row(self.btn_load_roi, Spacer(width=4), self.load_df_checkbox),
                ], sidebar=True),
                Spacer(height=6),
                self._create_card("📑  Tab Manager", [
                    self.show_tab_manager,
                    self.tab_manager_container,
                ], sidebar=True),
                Spacer(height=10),
                self.hotkey_div,
                sizing_mode="stretch_height",
                width=310,
                css_classes=["sidebar"],
                styles={
                    "overflow-y": "auto",
                    "background": f"linear-gradient(180deg, {THEME['sidebar']} 0%, #12202e 100%)",
                    "padding": "20px 16px",
                    "color": THEME['text_light'],
                    "border-right": f"2px solid {THEME['border_strong']}",
                    "box-shadow": "3px 0 12px rgba(0,0,0,0.15)",
                }
            )
            

        self.tabs.tabs = self._generate_tabs()
        if self.view_mode.value == "Tabs":
            self.center_container.children = [self.tabs]
        else:
            self.center_container.children = [self._generate_stacked_view()]


        if self.show_tab_manager.active:
            self.tab_manager_container.children = [self.build_tab_manager()]

            
        if self.layout is None:
            self.layout = row(self.sidebar, self.center_container, sizing_mode="stretch_both")

            # ── Resizable layout CSS + JS injected once at root level ──
            resize_styles = Div(text="""
            <style>
              /* ── Sidebar resize handle ── */
              .sidebar-resizer {
                width: 6px;
                background: #c8d8e8;
                cursor: col-resize;
                flex-shrink: 0;
                transition: background 0.15s;
                z-index: 10;
              }
              .sidebar-resizer:hover, .sidebar-resizer.dragging { background: #0072b2; }

              /* ── Figure resize handle: a visible grip at the bottom of each plot ── */
              .aerosol-fig-wrap {
                position: relative;
                display: flex;
                flex-direction: column;
                margin-bottom: 6px;
              }
              .aerosol-fig-resize-handle {
                height: 8px;
                background: linear-gradient(90deg,
                  transparent 0%, #c8d8e8 30%, #8aafc8 50%, #c8d8e8 70%, transparent 100%);
                cursor: ns-resize;
                border-radius: 0 0 4px 4px;
                flex-shrink: 0;
                transition: background 0.15s;
              }
              .aerosol-fig-resize-handle:hover {
                background: linear-gradient(90deg,
                  transparent 0%, #0072b2 30%, #56b4e9 50%, #0072b2 70%, transparent 100%);
              }
            </style>

            <script>
            (function() {
              // ── 1. Sidebar horizontal drag-to-resize ──
              function initSidebarResizer() {
                const resizer = document.getElementById('sidebar-resizer');
                if (!resizer) { setTimeout(initSidebarResizer, 400); return; }
                const sidebar = resizer.previousElementSibling;
                let startX, startW;
                resizer.addEventListener('mousedown', function(e) {
                  startX = e.clientX;
                  startW = sidebar.offsetWidth;
                  resizer.classList.add('dragging');
                  document.body.style.userSelect = 'none';
                  document.addEventListener('mousemove', onMove);
                  document.addEventListener('mouseup', onUp);
                  e.preventDefault();
                });
                function onMove(e) {
                  const w = Math.max(180, Math.min(620, startW + e.clientX - startX));
                  sidebar.style.width    = w + 'px';
                  sidebar.style.minWidth = w + 'px';
                  sidebar.style.maxWidth = w + 'px';
                }
                function onUp() {
                  resizer.classList.remove('dragging');
                  document.body.style.userSelect = '';
                  document.removeEventListener('mousemove', onMove);
                  document.removeEventListener('mouseup', onUp);
                }
              }
              setTimeout(initSidebarResizer, 600);

              // ── 2. Figure vertical drag-to-resize ──
              // Wrap each Bokeh canvas element in a flex column and add a
              // visible grip handle below it.  Dragging the handle resizes
              // the canvas via inline style height override.
              function initFigureResizers() {
                // Target the SVG canvas inside each Bokeh figure
                const canvases = document.querySelectorAll('.bk-Canvas, .bk-canvas-events');
                if (canvases.length === 0) { setTimeout(initFigureResizers, 600); return; }

                canvases.forEach(function(canvas) {
                  // Only wrap once
                  const parent = canvas.parentElement;
                  if (!parent || parent.classList.contains('aerosol-fig-wrap')) return;

                  const wrap = document.createElement('div');
                  wrap.className = 'aerosol-fig-wrap';
                  parent.insertBefore(wrap, canvas);
                  wrap.appendChild(canvas);

                  const grip = document.createElement('div');
                  grip.className = 'aerosol-fig-resize-handle';
                  grip.title = 'Drag to resize figure';
                  wrap.appendChild(grip);

                  let startY, startH;
                  grip.addEventListener('mousedown', function(e) {
                    startY = e.clientY;
                    startH = canvas.getBoundingClientRect().height;
                    document.body.style.userSelect = 'none';
                    const onMove = function(ev) {
                      const h = Math.max(120, startH + ev.clientY - startY);
                      canvas.style.height = h + 'px';
                      canvas.style.minHeight = h + 'px';
                    };
                    const onUp = function() {
                      document.body.style.userSelect = '';
                      document.removeEventListener('mousemove', onMove);
                      document.removeEventListener('mouseup', onUp);
                    };
                    document.addEventListener('mousemove', onMove);
                    document.addEventListener('mouseup', onUp);
                    e.preventDefault();
                    e.stopPropagation();
                  });
                });
              }
              // Run after Bokeh has rendered
              setTimeout(initFigureResizers, 1200);
              // Also re-run if new figures appear (instruments added)
              const observer = new MutationObserver(function() {
                initFigureResizers();
              });
              observer.observe(document.body, {childList: true, subtree: true});
            })();
            </script>
            """, sizing_mode="fixed", width=0, height=0,
                styles={"display": "none"})

            resizer_div = Div(
                text='<div id="sidebar-resizer" class="sidebar-resizer"></div>',
                width=5, height=0,
                sizing_mode="stretch_height",
            )

            # Top bar with sidebar toggle — always visible regardless of sidebar state
            top_header = row(
                self.quit_btn,
                self.sidebar_toggle_btn,
                Spacer(),
                sizing_mode="stretch_width",
                styles={
                    "background": THEME["surface"],
                    "padding": "4px 10px",
                    "border-bottom": f"1px solid {THEME['border']}",
                    "align-items": "center",
                    "min-height": "34px",
                }
            )
            self._main_row = row(
                self.sidebar,
                resizer_div,
                self.center_container,
                sizing_mode="stretch_both",
            )
            self.layout = column(
                top_header,
                self._main_row,
                sizing_mode="stretch_both",
            )
            # visible=False: this bar's own dark background must not paint
            # over the app when no fit is running. show_loader()/hide_loader()
            # toggle it in lockstep with the loader overlay and Stop Fit
            # button, instead of only the button's own visibility, which left
            # this fixed bottom-56px bar permanently covering page content.
            self.cancel_bar = row(
                self.cancel_btn,
                sizing_mode="stretch_width",
                visible=False,
                styles={
                    "position": "fixed",
                    "left": "0",
                    "right": "0",
                    "bottom": "0",
                    "height": "56px",
                    "z-index": "10000",
                    "display": "flex",
                    "justify-content": "center",
                    "align-items": "center",
                    "background": "rgba(20,35,50,0.95)",
                    "padding": "8px",
                }
            )
            final_layout = column(
                self.cancel_bar,
                self.loader_div,
                resize_styles,
                self.layout,
                sizing_mode="stretch_both",
            )
            self._doc.add_root(final_layout)


# `bokeh serve` on this file directly (as opposed to main.py, which only
# wraps this same call) never instantiates AerosolStudio on its own -
# importing the module just defines the class, so curdoc() gets no root and
# the browser shows a blank page. main.py has this same trigger; it's
# duplicated here so this file is independently servable too, matching the
# launcher scripts' app entry point.
if __name__.startswith("bokeh_app_"):
    AerosolStudio(curdoc())

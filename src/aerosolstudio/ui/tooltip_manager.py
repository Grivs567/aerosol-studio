"""Package-owned tooltip management and content registry."""

from __future__ import annotations

from bokeh.layouts import row
from bokeh.models import HelpButton, Tooltip
from bokeh.models.dom import HTML


class TooltipManager:
    """Centralized tooltip management.

    All methods are static — no application state is needed.
    Tooltip styling is handled by global CSS, not inline styles.
    """

    DESCRIPTION_SUPPORTED = {
        "AutocompleteInput", "ColorPicker", "DatePicker", "DateRangePicker",
        "MultipleDatePicker", "DatetimeRangePicker", "MultipleDatetimePicker",
        "FileInput", "MultiChoice", "MultiSelect", "NumericInput",
        "PasswordInput", "Select", "Spinner", "TextAreaInput", "TextInput",
        "TimePicker",
    }

    @staticmethod
    def create(content: str, position: str = "right", **kwargs) -> Tooltip:
        """Create a Tooltip with HTML content."""
        return Tooltip(content=HTML(content), position=position, **kwargs)

    @staticmethod
    def _create_themed_help_button(tooltip: Tooltip) -> HelpButton:
        return HelpButton(
            tooltip=tooltip,
            width=18,
            height=18,
            width_policy="fixed",
            height_policy="fixed",
            button_type="light",
            styles={
                "border": "none",
                "background": "transparent",
                "box-shadow": "none",
                "padding": "0",
                "cursor": "pointer",
            },
        )

    @staticmethod
    def add_to_widget(widget, tooltip_key: str, position: str = "right"):
        """Add tooltip to widget if supported; otherwise attach a help button.

        Returns the widget (possibly unchanged) or a row containing the widget
        and a help button.
        """
        if tooltip_key not in TOOLTIPS:
            return widget

        tooltip = TooltipManager.create(TOOLTIPS[tooltip_key], position)

        if widget.__class__.__name__ in TooltipManager.DESCRIPTION_SUPPORTED:
            widget.description = tooltip
            return widget

        help_btn = TooltipManager._create_themed_help_button(tooltip)
        return row(widget, help_btn, sizing_mode="stretch_width",
                   styles={"align-items": "center"})

    @staticmethod
    def add_to_button(button, tooltip_key: str, position: str = "right"):
        """Add a help button next to a regular Bokeh button."""
        if tooltip_key not in TOOLTIPS:
            return button
        tooltip = TooltipManager.create(TOOLTIPS[tooltip_key], position)
        help_btn = TooltipManager._create_themed_help_button(tooltip)
        return row(button, help_btn, sizing_mode="stretch_width",
                   styles={"align-items": "center"})

    @staticmethod
    def add_to_layout(element, tooltip_key: str, position: str = "right"):
        """Add a help button to any layout element."""
        if tooltip_key not in TOOLTIPS:
            return element
        tooltip = TooltipManager.create(TOOLTIPS[tooltip_key], position)
        help_btn = TooltipManager._create_themed_help_button(tooltip)
        return row(element, help_btn, sizing_mode="stretch_width",
                   styles={"align-items": "center"})


TOOLTIPS: dict[str, str] = {
    # Dataset Management
    "instrument_name": "Enter a unique name for this dataset panel (e.g., 'CSV_1', 'NetCDF_1', 'Event_A')",
    "instrument_type": "Select the data file format: CSV text table or NetCDF (.nc)",
    "add_instrument": "Add a new dataset panel with the specified name and file format",
    "match_time_ranges": (
        "Sync every other dataset panel's visible time range to match the "
        "\"master\" panel's current view (set which panel is master via "
        "the master-selection control near the panels) - lets you pan/zoom "
        "one heatmap and have the rest follow."
    ),
    "fit_y_dist": (
        "Auto-fit the Y axis to the currently visible distribution data, "
        "instead of leaving it at whatever range it was last zoomed/panned to."
    ),
    "run_mcc": (
        "Run the MCC (maximum cross-correlation) growth-rate method on the "
        "selected ROI - see the panel above for what it does and which "
        "fields control it."
    ),
    "source_timezone": "Timezone the raw timestamps in this file were actually recorded in (CSV never states this; NetCDF sometimes does but not reliably). Pre-filled with your machine's local timezone — check/change it before clicking Load. Applied once at load time; change it and click Load again to re-interpret the file under a different timezone.",
    "diameter_unit": "Unit of the diameter values in this file (nm/um/m). Checked against NetCDF file attributes when present and updated automatically if they disagree; always editable. Applied once at load time, converted to metres internally — change it and click Load again if detected wrong.",
    "data_type": "Whether the raw values in this file are dN/dlogDp (density) or per-bin Number Concentration (N). Converted to dN/dlogDp internally at load time so the rest of the app (fits, ROI masks, overlays) always sees the same representation. Change it and click Load again if wrong.",
    "heatmap_view": "Live display-only toggle for the heatmap: dN/dlogDp (raw), Number Concentration (N), Surface Density (dS/dlogDp), or Volume Density (dV/dlogDp). Re-renders the heatmap image and color limits only — every fit, ROI mask, and growth-rate calculation always uses the original dN/dlogDp data underneath, unaffected by this toggle.",
    "pm_interpolate": (
        "Off (default): PM is computed only from measured diameters - if the "
        "data doesn't reach the PM cutoff (e.g. data maxes out at 600nm but "
        "PM1 wants 1000nm), the result is really PM at the data's own max "
        "diameter, not the full requested cutoff. On: the distribution's "
        "tail is extrapolated past the measured range using a lognormal-mode "
        "fit (Whitby 1978; Hinds 1999) before integrating - a shape "
        "assumption, not a measurement."
    ),

    # View Controls
    "view_mode": "Switch between tabbed view (separate tabs) or stacked view (all together)",
    "link_axes": "Link X-axes across dataset panels for synchronized zooming/panning",
    "sync_ranges": "Match time ranges of all dataset panels to full data extent",

    "master_axis": """
    <b>X-Axis Master Dataset</b><br><br>
    • When axes are linked, this dataset panel defines the shared time window.<br>
    • When using "Match Time Range", all dataset panels match this panel's current visible time range.<br><br>
    If set to <b>Auto</b>, the first dataset panel is used.
    """,

    # Heatmap Controls
    "color_palette": "Select color palette for heatmap visualization",
    "color_min": "Minimum concentration for color mapping (values below use min color)",
    "color_max": "Maximum concentration for color mapping (values above use max color)",
    "colorbar_toggle": "Show or hide the heatmap colorbar for this dataset panel.",
    "color_limits_auto": (
        "When on, Min/Max are recalculated automatically whenever the data, "
        "species, or heatmap view changes. Editing Min/Max switches this to "
        "Locked so your chosen range stays put; click to re-enable Auto."
    ),

    # NetCDF Controls
    "nais_species": "Select which charged species/variable to display from the NetCDF file",

    # ROI Controls
    "save_roi": "Save all ROIs (polygons) and fitted points to JSON file",
    "load_roi": "Load previously saved ROIs and fits from JSON file",

    # Fitting Controls
    "num_modes": "Number of lognormal modes to fit to size distribution",
    "fit_maxconc": "Find maximum concentration times for each diameter bin",
    "fit_appearance": "Find appearance times using sigmoid fitting to rising edge",
    "fit_modes": "Fit lognormal modes to size distributions",
    "clear_max": "Clear all maximum concentration fit points from selected ROI",
    "clear_app": "Clear all appearance time fit points from selected ROI",
    "clear_modes": "Clear all mode fit points from selected ROI",

    "fit_peak_picker": "Detect peak concentration using prominence-based peak finding.",
    "clear_peak_picker": "Clear peak-picker fit points from selected ROI.",

    "fit_gaussian_lsq": "Fit Gaussian (least squares) to each diameter time series.",
    "clear_gaussian_lsq": "Clear Gaussian LSQ fit points from selected ROI.",

    "fit_gmm": "Fit Gaussian Mixture Model (GMM) to each diameter time series.",
    "clear_gmm": "Clear GMM fit points from selected ROI.",

    "fit_mcc": "Compute growth rate via cross-correlation (time-lag) across size bins in the selected ROI.",
    "clear_mcc": "Clear the last Cross-Correlation (MCC) result for this instrument.",

    # Line Fitting
    "fit_line_source": "Which fitted points to use for growth rate calculation",
    "fit_line_polygon": "Which polygon to use for the fit",
    "fit_line_button": "Fit linear growth rate to points inside selected polygon",

    # Diameter Range
    "dmin": "Minimum diameter (nm) to include in fits (empty = no limit)",
    "dmax": "Maximum diameter (nm) to include in fits (empty = no limit)",

    # Polygon controls
    "polygon_label": "Enter a descriptive label for this polygon (e.g., 'New particle formation event', 'Background period')",

    # Load/Save feedback
    "roi_load_success": "ROIs loaded successfully with all polygons and fit points restored",
    "roi_save_success": "ROIs saved to JSON file with complete metadata and fit results",

    # Selection info
    "selected_polygon": "Currently selected polygon. Click on a polygon in the heatmap to select it.",

    # Fit results display
    "results_display": "Shows results from fitting operations: growth rates, mode parameters, etc.",

    # Status display
    "status_display": "Current dataset-panel state: selected polygon, mode visibility, and sum mode status",
    "system_display": "System messages and operation feedback",

    # Concentration Lines
    "add_overlay_var_line": "Add variable concentration line (CS, CoagS, etc.) as overlay",

    # Hotkeys
    "hotkeys": """
        <b>Keyboard Shortcuts:</b><br>
        • <b>x</b> - Delete selected polygon<br>
        • <b>Delete</b> - Delete selected fit points<br>
        • <b>z</b> - Undo last deletion
    """,

    # Distribution Plot
    "distribution": "Size distribution at selected time. Modes appear as dashed lines when fitted.",

    # Toggle Switches
    "toggle_modes": "Show/hide fitted mode curves on distribution plot",
    "toggle_sum": "Show/hide sum of all fitted modes",
    "toggle_colorbar": "Show/hide colorbar",

    # File Input
    "file_input": "Load data file: CSV text table or NetCDF .nc file",

    "gr_source": "Select which fitted points to use for growth rate calculation:<br>• Max Conc - Peak concentration times<br>• Appearance - Particle appearance times<br>• Mode - Mode diameter evolution",
    "gr_polygon": "Select the ROI polygon containing the particle formation event",
    "gr_calculate": "Calculate growth rate by fitting a line to selected points. Results show rate in nm/hr",
    "gr_dmin": "Minimum diameter (nm) to include in growth rate fit. Use to focus on specific size range.",
    "gr_dmax": "Maximum diameter (nm) to include in growth rate fit. Use to focus on specific size range.",
    "mcc_tau_window": (
        "MCC (cross-correlation) only. Range of time lags searched, in "
        "hours - the published method's default is 22. If a run fails with "
        "\"hit the edge of the search window\", the real lag may be longer "
        "than this allows; widen it and re-run."
    ),
    "mcc_smoothing_window": (
        "MCC (cross-correlation) only. Smoothing window applied to each "
        "size channel's concentration time series before cross-correlating, "
        "in hours - the published method's default is 3."
    ),
    "mcc_num_divisions": (
        "MCC (cross-correlation) only. Splits the Fit Dp min/max range into "
        "this many sub-ranges on a log scale and averages their growth "
        "rates, instead of fitting the whole range as one. Default 1 (no "
        "split)."
    ),

    "gr_clear": "Clear/remove fitted growth rate lines",
    "gr_results": "Growth rate calculation results including R² and fit parameters",
    "gr_help": "Growth Rate Calculation Guide:<br>• Draw ROI polygon around event<br>• Fit points using buttons above<br>• Select point type and polygon<br>• Click 'Calculate GR'<br>• Results show in nm/hr",

    # Variable Line (Concentration Overlay)
    "var_dmin": (
        "Meaning depends on the selected method: an integration range's "
        "lower bound for Concentration, the target diameter for "
        "Coagulation Sink / CoagS from CS, particle density (g/cm³, not a "
        "diameter - default 1.5, typical ambient/urban aerosol) for any PM "
        "method, or unused (greyed out) for methods that take neither, "
        "like Condensation Sink."
    ),
    "var_dmax": (
        "Meaning depends on the selected method: an integration range's "
        "upper bound for Concentration, the PM cutoff diameter for "
        "PM (custom), or unused (greyed out) for methods that don't take "
        "a diameter, like Condensation Sink and the fixed PM1/PM2.5/PM10."
    ),
    "var_method": "Select which variable to calculate and overlay (CS, CoagS, Total Conc, etc.)",
    "var_plot": "Compute and plot the selected variable line",
    "var_toggle": "Show or hide this variable line",
    "var_color": "Change the color of this variable line",
    "var_style": "Change line style (solid, dashed, dotted)",
    "var_thickness": "Adjust line thickness",
    "var_ymin": "Manual minimum Y-axis limit for this variable",
    "var_ymax": "Manual maximum Y-axis limit for this variable",
    "var_apply_y": "Apply manual Y-axis range",
}

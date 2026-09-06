"""Central help text registry for future UI extraction."""

HELP_TEXT = {
    "load_data": "Loads the file currently shown in the path field.",
    "save_roi": "Saves polygons, fit points, growth-rate records, and overlay metadata.",
    "load_roi": "Loads a saved analysis session and restores it onto matching data.",
    "freehand_roi": "Draws a freehand region of interest on the heatmap.",
    "box_roi": "Draws a rectangular region of interest on the heatmap.",
    "lasso_select": "Selects fit points for deletion without creating an ROI.",
    "fit_method": "Selects the scientific fitting method used by Run Fit.",
    "run_fit": "Runs the selected fit method for the selected polygon.",
    "fit_line": "Fits a growth-rate line through stored fit points.",
    "pointer_info": "Shows time, diameter, and concentration for the current pointer position.",
}


def help_text(key: str, default: str = "") -> str:
    """Return help text for a known UI key."""

    return HELP_TEXT.get(key, default)

"""Color constants extracted for future UI modularization."""

THEME = {
    # Layout shells
    "sidebar": "#1e2d3d",  # deep slate-blue (dark enough to frame, not cave-dark)
    "bg": "#f0f4f8",  # very light blue-grey canvas
    "panel": "#ffffff",  # pure white panels inside content area
    "surface": "#e8eef4",  # slightly tinted surface for inset areas
    # Text
    "text": "#1a2533",  # near-black for readability on light bg
    "text_secondary": "#4a5e72",  # muted blue-grey for labels
    "text_light": "#e8f0f8",  # light text for dark sidebar
    # Accent (IBM Cerulean - colorblind-safe teal-blue)
    "accent": "#0072b2",  # primary interactive blue
    "accent_hover": "#005a8c",  # darker on hover
    "accent2": "#56b4e9",  # lighter companion
    # Status colours (all pass CB-safe checks)
    "success": "#009e73",  # green (CB-safe)
    "warning": "#e69f00",  # amber (CB-safe)
    "error": "#d55e00",  # orange-red (CB-safe, NOT pure red)
    "info": "#56b4e9",  # sky blue
    # Borders
    "border": "#c8d8e8",  # light grey-blue border
    "border_strong": "#8aafc8",  # stronger border for cards
    # Figure backgrounds (used in Bokeh plot styling)
    "plot_bg": "#f8fbff",  # nearly white with a hint of blue
    "plot_border": "#c8d8e8",
}

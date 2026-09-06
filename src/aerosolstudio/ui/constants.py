"""UI constants extracted without callback wiring."""

from aerosolstudio.themes.colors import THEME
from aerosolstudio.tools.toolbar import HEATMAP_TOOLBAR_ORDER, HIDDEN_COMPATIBILITY_TOOLS

ICON_LABELS = {
    "load": "Load",
    "save": "Save",
    "fit": "Run Fit",
    "fit_line": "Fit Line",
    "delete": "Delete",
    "undo": "Undo",
    "quit": "Quit Server",
}

LAYOUT_SIZES = {
    "sidebar_width": 280,
    "button_width": 120,
    "compact_button_width": 90,
    "spacer_small": 6,
}

FIT_BUTTON_CSS = """
:host {
  --fit-color: #009e73;
}
button.bk-btn {
  background-color: var(--fit-color) !important;
  border-color: var(--fit-color) !important;
}
"""

__all__ = [
    "FIT_BUTTON_CSS",
    "HEATMAP_TOOLBAR_ORDER",
    "HIDDEN_COMPATIBILITY_TOOLS",
    "ICON_LABELS",
    "LAYOUT_SIZES",
    "THEME",
]

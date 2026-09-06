"""Toolbar policy constants.

The monolithic app still constructs Bokeh tools directly. These constants are a
low-risk reference used by tests and future extraction work.
"""

HEATMAP_TOOLBAR_ORDER = (
    "PanTool",
    "WheelZoomTool",
    "BoxZoomTool",
    "FreehandDrawTool",
    "BoxEditTool",
    "LassoSelectTool",
    "ResetTool",
    "SaveTool",
)

HIDDEN_COMPATIBILITY_TOOLS = ("PolyDrawTool",)

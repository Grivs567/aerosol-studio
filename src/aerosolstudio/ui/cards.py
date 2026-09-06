"""Package-owned card and info-box layout builders.

All functions are pure: they take a theme dict and return Bokeh layout objects.
No application state is read or written.
"""

from __future__ import annotations

from typing import Any

from bokeh.layouts import column
from bokeh.models import Div


def create_card(
    theme: dict[str, Any],
    title: str,
    widgets: list,
    sidebar: bool = False,
):
    """Return a styled card column containing *widgets* under a *title* header."""
    title_color  = theme["accent2"] if sidebar else theme["accent"]
    border_color = "rgba(255,255,255,0.12)" if sidebar else theme["border"]
    bg_color     = "rgba(255,255,255,0.05)" if sidebar else theme["panel"]

    header = Div(
        text=f"""
            <div style='
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.9px;
                color: {title_color};
                margin-bottom: 10px;
                text-transform: uppercase;
                border-bottom: 1px solid {border_color};
                padding-bottom: 5px;
            '>{title}</div>
        """,
        sizing_mode="stretch_width",
    )

    content = column(*widgets, sizing_mode="stretch_width")

    return column(
        header,
        content,
        sizing_mode="stretch_width",
        styles={
            "background-color": bg_color,
            "border-radius": "8px",
            "padding": "12px 14px",
            "border": f"1px solid {border_color}",
            "box-shadow": "0 1px 4px rgba(0,0,0,0.07)" if not sidebar else "none",
            "margin-bottom": "8px",
        },
    )


def create_info_box(
    theme: dict[str, Any],
    label: str,
    value: str,
    bg_color: str | None = None,
    sidebar: bool = False,
) -> Div:
    """Return a labelled info-box Div."""
    bg  = bg_color or ("rgba(255,255,255,0.07)" if sidebar else theme["surface"])
    txt = theme["text_light"] if sidebar else theme["text"]
    lbl = "rgba(255,255,255,0.55)" if sidebar else theme["text_secondary"]
    acc = theme["accent2"] if sidebar else theme["accent"]

    return Div(
        text=f"""
            <div style='
                background: {bg};
                border-radius: 5px;
                padding: 8px 10px;
                border-left: 3px solid {acc};
                margin-bottom: 4px;
            '>
                <span style='font-size:10px; color:{lbl}; display:block;
                             text-transform:uppercase; letter-spacing:0.5px;
                             margin-bottom:3px;'>{label}</span>
                <span style='font-size:12px; color:{txt}; font-weight:600;'>{value}</span>
            </div>
        """,
        sizing_mode="stretch_width",
    )


def create_color_badge(color: str) -> Div:
    """Return a small circular colored badge Div."""
    return Div(
        text=f"""
            <div style='
                width: 12px;
                height: 12px;
                background-color: {color};
                border-radius: 50%;
                display: inline-block;
                border: 1px solid white;
                box-shadow: 0 0 4px rgba(0,0,0,0.3);
            '></div>
        """,
        width=20,
        height=20,
        sizing_mode="fixed",
    )

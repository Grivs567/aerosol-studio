"""Package-owned construction for fit control widgets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from bokeh.models import Button, Div, Select

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.fitting.types import FIT_TYPE_METADATA
from aerosolstudio.ui.cards import create_color_badge
from aerosolstudio.ui.tooltip_manager import TooltipManager

FIT_BUTTON_CSS = """
.bk-btn {
    background-color: var(--fit-color) !important;
    border-color: var(--fit-color) !important;
    color: #111111 !important;
    font-weight: 700 !important;
}
"""


@dataclass(frozen=True)
class FitControls:
    """Bokeh widgets and tooltip wrappers for fit controls."""

    fit_type_select: Select
    fit_badge: Div
    btn_fit: Button
    btn_fit_: Any
    btn_clear: Button
    btn_clear_: Any


def build_fit_controls(
    *,
    fit_metadata: Mapping[str, Mapping[str, Any]] = FIT_TYPE_METADATA,
    callback_seam: CallbackSeam | None = None,
    on_fit_type_change: Callable[..., Any] | None = None,
    on_run_fit: Callable[..., Any] | None = None,
    on_clear_fit: Callable[..., Any] | None = None,
) -> FitControls:
    """Build fit controls without binding callbacks directly."""

    fit_type_options = list(fit_metadata.keys())
    default_key = fit_type_options[0]
    initial_props = fit_metadata[default_key]

    fit_type_select = Select(
        title="Fit Method",
        value=default_key,
        options=[(key, fit_metadata[key]["display_name"]) for key in fit_type_options],
        width=140,
    )
    badge = create_color_badge(str(initial_props["color"]))

    btn_fit = Button(label="▶ Run Fit", button_type="default", width=90)
    btn_clear = Button(label="🗑 Clear", button_type="default", width=90)
    btn_fit.stylesheets = [FIT_BUTTON_CSS]
    btn_clear.stylesheets = [FIT_BUTTON_CSS]
    color_style = {"--fit-color": initial_props["color"]}
    btn_fit.styles = color_style
    btn_clear.styles = color_style

    btn_fit_ = TooltipManager.add_to_button(btn_fit, str(initial_props["tooltip_fit"]))
    btn_clear_ = TooltipManager.add_to_button(btn_clear, str(initial_props["tooltip_clear"]))

    if callback_seam is not None:
        if on_fit_type_change is not None:
            callback_seam.on_change(
                fit_type_select,
                "value",
                on_fit_type_change,
                label="fit-type-select-value",
            )
        if on_run_fit is not None:
            callback_seam.on_click(btn_fit, on_run_fit, label="run-fit-click")
        if on_clear_fit is not None:
            callback_seam.on_click(btn_clear, on_clear_fit, label="clear-fit-click")

    return FitControls(
        fit_type_select=fit_type_select,
        fit_badge=badge,
        btn_fit=btn_fit,
        btn_fit_=btn_fit_,
        btn_clear=btn_clear,
        btn_clear_=btn_clear_,
    )

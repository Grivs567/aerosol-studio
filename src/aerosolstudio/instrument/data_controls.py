"""Package-owned construction for data loading controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bokeh.models import Button, TextInput

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.ui.tooltip_manager import TooltipManager


@dataclass(frozen=True)
class DataControls:
    """Bokeh widgets used for per-instrument data loading."""

    path_input: TextInput
    browse_btn: Button
    load_btn: Button


def build_data_controls(
    *,
    callback_seam: CallbackSeam | None = None,
    on_browse: Callable[..., Any] | None = None,
    on_path_change: Callable[..., Any] | None = None,
    on_load: Callable[..., Any] | None = None,
) -> DataControls:
    """Build data loading controls without binding callbacks directly."""

    path_input = TooltipManager.add_to_widget(
        TextInput(placeholder="Enter file path or browse...", width=400),
        "file_path",
    )
    browse_btn = Button(label="📁 Browse", button_type="primary", width=100)
    load_btn = Button(label="Load", button_type="default", width=80)

    if callback_seam is not None:
        if on_browse is not None:
            callback_seam.on_click(browse_btn, on_browse, label="browse-file-click")
        if on_path_change is not None:
            callback_seam.on_change(path_input, "value", on_path_change, label="path-input-value")
        if on_load is not None:
            callback_seam.on_click(load_btn, on_load, label="load-file-click")

    return DataControls(path_input=path_input, browse_btn=browse_btn, load_btn=load_btn)

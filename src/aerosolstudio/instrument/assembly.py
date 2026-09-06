"""Composed package-side instrument assembly for parity harnesses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.fitting.types import FIT_TYPE_METADATA
from aerosolstudio.instrument.data_controls import DataControls, build_data_controls
from aerosolstudio.instrument.fit_controls import FitControls, build_fit_controls
from aerosolstudio.instrument.heatmap_controls import (
    HeatmapControls,
    build_heatmap_controls,
)
from aerosolstudio.instrument.state import InstrumentState

NOT_YET_ASSEMBLED_HEATMAP_RENDERERS: tuple[str, ...] = ()

NOT_YET_ASSEMBLED_HEATMAP_HANDLERS: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssembledInstrument:
    """Composed package-owned instrument slice covered by stages 4d-4f."""

    name: str
    file_type: str
    callback_seam: CallbackSeam
    data_controls: DataControls
    heatmap_controls: HeatmapControls
    fit_controls: FitControls
    legacy_state: dict[str, Any]
    instrument_state: InstrumentState
    not_yet_assembled_renderers: tuple[str, ...]
    not_yet_assembled_handlers: tuple[str, ...]


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def assemble_minimal_instrument(name: str = "Dataset_1", file_type: str = "csv") -> AssembledInstrument:
    """Compose the package builders into a legacy-state-compatible slice.

    This function intentionally covers only data controls, heatmap controls,
    fit controls, and the structural ``InstrumentState`` wrapper.
    """

    seam = CallbackSeam()
    data_controls = build_data_controls(
        callback_seam=seam,
        on_browse=_noop,
        on_path_change=_noop,
        on_load=_noop,
    )
    heatmap_controls = build_heatmap_controls(
        name,
        callback_seam=seam,
        on_x_range_start=_noop,
        on_x_range_end=_noop,
    )
    fit_controls = build_fit_controls(
        callback_seam=seam,
        on_fit_type_change=_noop,
        on_run_fit=_noop,
        on_clear_fit=_noop,
    )

    legacy_state: dict[str, Any] = {
        "fig": heatmap_controls.fig,
        "pointer_info_div": heatmap_controls.pointer_info_div,
        "mapper": heatmap_controls.mapper,
        "colorbar": heatmap_controls.colorbar,
        "cb_toggle": heatmap_controls.cb_toggle,
        "cb_toggle_": heatmap_controls.cb_toggle_,
        "pal_select": heatmap_controls.pal_select,
        "clim_low": heatmap_controls.clim_low,
        "clim_high": heatmap_controls.clim_high,
        "src_img": heatmap_controls.src_img,
        "_heatmap_refresh_pending": False,
        "img_renderer": heatmap_controls.img_renderer,
        "df": None,
        "type": file_type,
        "path_input": data_controls.path_input,
        "browse_btn": data_controls.browse_btn,
        "load_btn": data_controls.load_btn,
        "fit_type_select": fit_controls.fit_type_select,
        "fit_badge": fit_controls.fit_badge,
        "btn_fit": fit_controls.btn_fit,
        "btn_fit_": fit_controls.btn_fit_,
        "btn_clear": fit_controls.btn_clear,
        "btn_clear_": fit_controls.btn_clear_,
        "fit_types": FIT_TYPE_METADATA,
    }
    instrument_state = InstrumentState.from_legacy_dict(legacy_state, name=name)
    return AssembledInstrument(
        name=name,
        file_type=file_type,
        callback_seam=seam,
        data_controls=data_controls,
        heatmap_controls=heatmap_controls,
        fit_controls=fit_controls,
        legacy_state=legacy_state,
        instrument_state=instrument_state,
        not_yet_assembled_renderers=NOT_YET_ASSEMBLED_HEATMAP_RENDERERS,
        not_yet_assembled_handlers=NOT_YET_ASSEMBLED_HEATMAP_HANDLERS,
    )

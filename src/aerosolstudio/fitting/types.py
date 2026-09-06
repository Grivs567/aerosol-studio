"""Bokeh-free fit metadata and pipeline contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, TypeAlias, runtime_checkable

import pandas as pd

PeakRecord: TypeAlias = dict[str, Any]
ProgressCallback: TypeAlias = Callable[[str], None]


@runtime_checkable
class CancellationToken(Protocol):
    """Read-only cancellation interface consumed by fit orchestration."""

    def is_requested(self) -> bool:
        """Return whether cancellation has been requested."""


FIT_TYPE_METADATA = {
    "maxconc": {
        "name": "Peak Picker",
        "display_name": "Peak Picker",
        "color": "#FF4500",
        "button_type": "warning",
        "marker": "circle",
        "size": 6,
        "fill_color": "#FF4500",
        "line_color": "black",
        "dist_marker": "diamond",
        "dist_color": "#FF4500",
        "src_suffix": "maxconc_src",
        "dist_src_suffix": "maxconc_dist_src",
        "fit_key": "fit_peak_picker",
        "tooltip_fit": "fit_peak_picker",
        "tooltip_clear": "clear_peak_picker",
    },
    "appearance": {
        "name": "Appearance",
        "display_name": "Appearance Time",
        "color": "#00FFFF",
        "button_type": "primary",
        "marker": "circle",
        "size": 6,
        "fill_color": "#00FFFF",
        "line_color": "black",
        "dist_marker": "circle",
        "dist_color": "#00FFFF",
        "src_suffix": "app_src",
        "dist_src_suffix": "app_dist_src",
        "fit_key": "fit_app",
        "tooltip_fit": "fit_appearance",
        "tooltip_clear": "clear_app",
    },
    "mode": {
        "name": "Mode",
        "display_name": "Mode Diameter",
        "color": "#FFD700",
        "button_type": "success",
        "marker": "circle",
        "size": 8,
        "fill_color": "#FFD700",
        "line_color": "black",
        "dist_marker": "star",
        "dist_color": "#FFD700",
        "src_suffix": "mode_src",
        "dist_src_suffix": "mode_dist_src",
        "fit_key": "fit_mode",
        "tooltip_fit": "fit_modes",
        "tooltip_clear": "clear_modes",
    },
    "maxconc_gaussian": {
        "name": "Gaussian LSQ",
        "display_name": "Gaussian LSQ",
        "color": "#1f77b4",
        "button_type": "primary",
        "marker": "triangle",
        "size": 7,
        "fill_color": "#1f77b4",
        "line_color": "black",
        "dist_marker": "triangle",
        "dist_color": "#1f77b4",
        "src_suffix": "gauss_src",
        "dist_src_suffix": "gauss_dist_src",
        "fit_key": "fit_gaussian_lsq",
        "tooltip_fit": "fit_gaussian_lsq",
        "tooltip_clear": "clear_gaussian_lsq",
    },
    "maxconc_gmm": {
        "name": "GMM",
        "display_name": "GMM Fit",
        "color": "#8b5cf6",
        "button_type": "default",
        "marker": "square",
        "size": 7,
        "fill_color": "#8b5cf6",
        "line_color": "black",
        "dist_marker": "square",
        "dist_color": "#8b5cf6",
        "src_suffix": "gmm_src",
        "dist_src_suffix": "gmm_dist_src",
        "fit_key": "fit_gmm",
        "tooltip_fit": "fit_gmm",
        "tooltip_clear": "clear_gmm",
    },
    "mcc": {
        "name": "Cross-Correlation",
        "display_name": "Cross-Correlation (MCC)",
        "color": "#e41a1c",
        "button_type": "danger",
        "marker": "diamond",
        "size": 8,
        "fill_color": "#e41a1c",
        "line_color": "black",
        "dist_marker": "diamond",
        "dist_color": "#e41a1c",
        "src_suffix": "mcc_src",
        "dist_src_suffix": "mcc_dist_src",
        "fit_key": "fit_mcc",
        "tooltip_fit": "fit_mcc",
        "tooltip_clear": "clear_mcc",
    },
}

FIT_TYPE_ORDER = tuple(FIT_TYPE_METADATA)
FIT_TYPE_DISPLAY_FIELDS = ("display_name", "button_type", "color")
FIT_TYPE_DISPLAY_METADATA = {
    key: {field: metadata[field] for field in FIT_TYPE_DISPLAY_FIELDS}
    for key, metadata in FIT_TYPE_METADATA.items()
}

FIT_TYPE_METHOD_NAMES = {
    "maxconc": "fit_peak_picker",
    "appearance": "fit_appearance",
    "mode": "fit_mode",
    "maxconc_gaussian": "fit_gaussian_lsq",
    "maxconc_gmm": "fit_gmm",
    "mcc": "fit_cross_correlation",
}


def bind_fit_type_methods(controller: Any) -> dict[str, dict[str, Any]]:
    """Return runtime fit metadata with methods bound to an app/controller."""

    return {
        key: {**metadata, "fit_method": getattr(controller, FIT_TYPE_METHOD_NAMES[key])}
        for key, metadata in FIT_TYPE_METADATA.items()
    }


@dataclass(frozen=True, eq=False)
class FitSnapshot:
    """Plain values captured on the Bokeh IO thread before worker launch.

    ``roi_mask`` is the boolean polygon mask (see ``AerosolStudio.roi_mask``)
    matching ``FitRequest.roi``'s shape - the mode engine re-applies it after
    its own interpolation step so a jagged/non-convex ROI boundary can't let
    a fit see diameters outside what was actually drawn. ``dmin_nm``,
    ``dmax_nm``, ``poly_label``, ``tau_window_hr``, ``smoothing_window_hr``,
    and ``number_of_divisions`` are read by the MCC (cross-correlation)
    engine only; the other engines ignore them. The tau-window,
    smoothing-window, and number-of-divisions defaults match
    compute_cross_correlation_gr's
    own (and, in turn, the published method's) - a caller that never sets
    them gets identical behavior to before these fields existed.
    """

    num_modes: int = 1
    selected_poly_idx: int | None = None
    roi_mask: Any = None
    dmin_nm: float | None = None
    dmax_nm: float | None = None
    poly_label: str | None = None
    tau_window_hr: float = 22.0
    smoothing_window_hr: float = 3.0
    number_of_divisions: int = 1

    def as_legacy_dict(self) -> dict[str, Any]:
        """Return the legacy dictionary shape still read by wrapper methods."""

        return {"num_modes": self.num_modes}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FitSnapshot):
            return NotImplemented
        roi_mask_equal = self.roi_mask is other.roi_mask
        if not roi_mask_equal and self.roi_mask is not None and other.roi_mask is not None:
            import numpy as np

            roi_mask_equal = bool(np.array_equal(self.roi_mask, other.roi_mask))
        return (
            self.num_modes == other.num_modes
            and self.selected_poly_idx == other.selected_poly_idx
            and roi_mask_equal
            and self.dmin_nm == other.dmin_nm
            and self.dmax_nm == other.dmax_nm
            and self.poly_label == other.poly_label
            and self.tau_window_hr == other.tau_window_hr
            and self.smoothing_window_hr == other.smoothing_window_hr
            and self.number_of_divisions == other.number_of_divisions
        )


@dataclass(frozen=True, eq=False)
class FitRequest:
    """Background-safe fit request shape passed into fit wrappers."""

    instrument_name: str
    fit_key: str
    roi: pd.DataFrame
    snapshot: FitSnapshot = field(default_factory=FitSnapshot)
    cancel_token: CancellationToken | None = None
    progress_callback: ProgressCallback | None = None
    total_work: int | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FitRequest):
            return NotImplemented
        return (
            self.instrument_name == other.instrument_name
            and self.fit_key == other.fit_key
            and self.roi is other.roi  # identity: DataFrames don't support scalar ==
            and self.snapshot == other.snapshot
            and self.cancel_token is other.cancel_token
            and self.progress_callback is other.progress_callback
            and self.total_work == other.total_work
        )

    # object.__hash__ (id-based) is inherited when eq=False on a frozen dataclass.

    @property
    def dataframe(self) -> pd.DataFrame:
        """Alias documenting that the ROI payload is the fit dataframe."""

        return self.roi

    def with_progress(self, callback: ProgressCallback | None) -> FitRequest:
        """Return a copy with a progress callback attached."""

        return replace(self, progress_callback=callback)


@dataclass(frozen=True)
class FitResult:
    """Plain fit result payload before Bokeh model mutation."""

    peaks: tuple[PeakRecord, ...] = ()
    messages: tuple[str, ...] = ()
    cancelled: bool = False
    error: str | None = None

    @classmethod
    def from_parts(
        cls,
        peaks: Sequence[Mapping[str, Any]] | None = None,
        messages: Sequence[str] | None = None,
        *,
        cancelled: bool = False,
        error: str | None = None,
    ) -> FitResult:
        """Build a result from the mutable lists used by existing wrappers."""

        return cls(
            peaks=tuple(dict(peak) for peak in (peaks or ())),
            messages=tuple(messages or ()),
            cancelled=cancelled,
            error=error,
        )

    def to_serializable(self) -> dict[str, Any]:
        """Return JSON-compatible container types for diagnostics/tests."""

        return {
            "peaks": [dict(peak) for peak in self.peaks],
            "messages": list(self.messages),
            "cancelled": self.cancelled,
            "error": self.error,
        }

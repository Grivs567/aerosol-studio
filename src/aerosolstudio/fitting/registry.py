"""Bokeh-free fit engine registry and request dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from aerosolstudio.fitting import engines
from aerosolstudio.fitting.types import FIT_TYPE_ORDER, FitRequest, FitResult
from aerosolstudio.science.growth_rate import compute_cross_correlation_gr
from aerosolstudio.utils.time import datetime_index_to_epoch_ms

import json

EngineCallable = Callable[[FitRequest], FitResult]


@dataclass(frozen=True)
class FitEngineSpec:
    """Registry entry for one fit type."""

    fit_key: str
    engine_id: str
    run: EngineCallable


def _cancel_requested(token: Any) -> bool:
    if token is None:
        return False
    if hasattr(token, "is_requested"):
        return bool(token.is_requested())
    if hasattr(token, "is_set"):
        return bool(token.is_set())
    return False


def _time_ms(index: pd.Index) -> np.ndarray:
    if isinstance(index, pd.DatetimeIndex):
        # See datetime_index_to_epoch_ms's docstring: .view("int64") assumes
        # nanosecond storage, which pandas (notably 3.x) no longer guarantees.
        return datetime_index_to_epoch_ms(index)
    return index.to_numpy(dtype=float)


def _dp_log_nm(columns: pd.Index) -> np.ndarray:
    return np.log10(columns.astype(float).to_numpy() * 1e9)


def _progress(request: FitRequest, message: str) -> None:
    if request.progress_callback is not None:
        request.progress_callback(message)


def _cancelled_result(peaks: list[dict[str, Any]], messages: list[str]) -> FitResult:
    # Partial results ARE kept on cancel (matches studio.py's inline cancel
    # checks, which `return peaks` - whatever was collected before the user
    # cancelled - not an empty list).
    messages.append("⚠ Fit cancelled by user")
    return FitResult.from_parts(peaks, messages, cancelled=True)


def _skip_summary_message(skip_reasons: dict[str, int]) -> str:
    summary = "; ".join(f"{count}× {reason}" for reason, count in skip_reasons.items())
    return f"Skip summary: {summary}"


def _run_column_engine(
    request: FitRequest,
    engine: Callable[..., dict[str, Any] | None],
    label: str,
) -> FitResult:
    data = request.roi.sort_index(axis=1)
    tim = _time_ms(data.index)
    dp = _dp_log_nm(data.columns)
    peaks: list[dict[str, Any]] = []
    messages: list[str] = []
    skip_reasons: dict[str, int] = {}
    fallback_count = 0
    n = len(dp)

    for idx, dp_log_nm in enumerate(dp):
        if _cancel_requested(request.cancel_token):
            return _cancelled_result(peaks, messages)
        if idx == 0 or (idx + 1) % max(1, n // 100) == 0 or idx + 1 == n:
            _progress(
                request,
                f"Processing diameter {idx + 1}/{n}; {n - idx - 1} left; "
                f"Dp ≈ {10 ** dp_log_nm:.1f} nm",
            )
        diagnostics: dict[str, Any] = {}
        try:
            peak = engine(
                tim, float(dp_log_nm), data.iloc[:, idx].to_numpy(dtype=float),
                diagnostics=diagnostics,
            )
        except TypeError:
            peak = engine(
                tim, float(dp_log_nm), data.iloc[:, idx].to_numpy(dtype=float),
            )
        if peak is not None:
            peaks.append(peak)
            messages.append(f"{label}: {10 ** dp_log_nm:.3f} nm")
            if diagnostics.get("fallback"):
                fallback_count += 1
        else:
            reason = diagnostics.get("reason", "unknown")
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    if fallback_count:
        skip_reasons["curve_fit did not converge, used peak estimate instead"] = fallback_count
    if skip_reasons:
        for reason, count in skip_reasons.items():
            messages.append(f"Skip summary: {count}× diameter column skipped ({reason})")

    return FitResult.from_parts(peaks, messages)


def _run_peak_picker(request: FitRequest) -> FitResult:
    return _run_column_engine(request, engines.peak_picker_peak, "Peak")


def _run_appearance(request: FitRequest) -> FitResult:
    return _run_column_engine(request, engines.appearance_time_peak, "Appearance")


def _run_gaussian_lsq(request: FitRequest) -> FitResult:
    return _run_column_engine(request, engines.gaussian_lsq_peak, "Gaussian")


def _run_gmm(request: FitRequest) -> FitResult:
    return _run_column_engine(request, engines.gmm_peak, "GMM")


def _run_mode(request: FitRequest) -> FitResult:
    data = request.roi.sort_index(axis=1)
    tim = _time_ms(data.index)
    dp = _dp_log_nm(data.columns)
    num_modes = request.snapshot.num_modes
    roi_mask = request.snapshot.roi_mask
    peaks: list[dict[str, Any]] = []
    messages: list[str] = []
    # Two independent skip counters, matching studio.py's fit_mode:
    # "empty" = the fit ran but afi.fit_multimode found no gaussians;
    # "degenerate" = the time step was excluded BEFORE fitting was even
    # attempted (too few valid points, or a near-zero/empty concentration
    # integral - see mode_peaks_for_time's docstring for why this guard
    # exists).
    empty_timesteps = 0
    degenerate_timesteps = 0
    n = data.shape[0]

    for idx in range(n):
        if _cancel_requested(request.cancel_token):
            return _cancelled_result(peaks, messages)
        if idx == 0 or (idx + 1) % max(1, n // 100) == 0 or idx + 1 == n:
            time_str = pd.to_datetime(tim[idx], unit="ms").strftime("%Y-%m-%d %H:%M:%S")
            _progress(
                request,
                f"Processing time {idx + 1}/{n}; {n - idx - 1} left; {time_str}",
            )
        roi_mask_row = roi_mask[idx, :] if roi_mask is not None else None
        diagnostics: dict[str, Any] = {}
        try:
            row_peaks = engines.mode_peaks_for_time(
                tim[idx],
                dp,
                data.iloc[idx, :].to_numpy(dtype=float),
                num_modes,
                roi_mask_row=roi_mask_row,
                diagnostics=diagnostics,
            )
        except TypeError:
            row_peaks = engines.mode_peaks_for_time(
                tim[idx],
                dp,
                data.iloc[idx, :].to_numpy(dtype=float),
                num_modes,
            )
        reason = diagnostics.get("reason")
        if reason == "degenerate":
            degenerate_timesteps += 1
            continue
        if reason == "empty":
            empty_timesteps += 1
        peaks.extend(row_peaks)
        time_str = pd.to_datetime(tim[idx], unit="ms").strftime("%Y-%m-%d %H:%M:%S")
        messages.append(f"Fitted: {time_str}")

    if empty_timesteps:
        messages.append(
            f"Skip summary: {empty_timesteps}× time step returned no gaussian modes "
            f"from afi.fit_multimode"
        )
    if degenerate_timesteps:
        messages.append(
            f"Skip summary: {degenerate_timesteps}× time step skipped before fitting "
            f"(near-zero/empty concentration in this ROI)"
        )

    return FitResult.from_parts(peaks, messages)


def _run_mcc(request: FitRequest) -> FitResult:
    """Compute GR via the MCC (cross-correlation) method over the ROI.

    Unlike the other five engines, this produces one scalar GR for the
    whole ROI, not (t, d) point markers - so it always returns no peaks
    and smuggles its result back via a specially prefixed message
    ("MCC_RESULT::<json>"), matching studio.py's ``fit_cross_correlation``
    exactly so its ``_apply()`` message-parsing keeps working unchanged.
    """

    snapshot = request.snapshot
    dmin_nm = snapshot.dmin_nm
    dmax_nm = snapshot.dmax_nm
    region_label = snapshot.poly_label or "selected ROI"

    # Recorded on every result (success or failure) so a run is
    # reproducible/comparable later from the results table alone, now that
    # these are user-editable rather than baked-in constants.
    params_used = {
        "tau_window_hr": snapshot.tau_window_hr,
        "smoothing_window_hr": snapshot.smoothing_window_hr,
        "number_of_divisions": snapshot.number_of_divisions,
    }

    if dmin_nm is None or dmax_nm is None:
        message = "MCC_RESULT::" + json.dumps({
            "ok": False,
            "reason": "invalid Fit Dp min/max — check those fields",
            "dmin_nm": dmin_nm,
            "dmax_nm": dmax_nm,
            "region_label": region_label,
            **params_used,
        })
        return FitResult.from_parts([], [message])

    result = compute_cross_correlation_gr(
        request.roi,
        dmin_nm,
        dmax_nm,
        smoothing_window_hr=snapshot.smoothing_window_hr,
        tau_window_hr=snapshot.tau_window_hr,
        number_of_divisions=snapshot.number_of_divisions,
    )

    if result["ok"]:
        message = "MCC_RESULT::" + json.dumps({
            "ok": True,
            "growth_rate_nm_per_hr": result["growth_rate_nm_per_hr"],
            "dmin_nm": dmin_nm,
            "dmax_nm": dmax_nm,
            "region_label": region_label,
            **params_used,
        })
    else:
        message = "MCC_RESULT::" + json.dumps({
            "ok": False,
            "reason": result["reason"],
            "dmin_nm": dmin_nm,
            "dmax_nm": dmax_nm,
            "region_label": region_label,
            **params_used,
        })
    return FitResult.from_parts([], [message])


ENGINE_REGISTRY: dict[str, FitEngineSpec] = {
    "maxconc": FitEngineSpec("maxconc", "peak_picker", _run_peak_picker),
    "appearance": FitEngineSpec("appearance", "appearance_time", _run_appearance),
    "mode": FitEngineSpec("mode", "mode_peaks", _run_mode),
    "maxconc_gaussian": FitEngineSpec("maxconc_gaussian", "gaussian_lsq", _run_gaussian_lsq),
    "maxconc_gmm": FitEngineSpec("maxconc_gmm", "gmm", _run_gmm),
    "mcc": FitEngineSpec("mcc", "mcc", _run_mcc),
}


if tuple(ENGINE_REGISTRY) != FIT_TYPE_ORDER:  # pragma: no cover - import-time invariant
    raise RuntimeError("Fit engine registry keys must match fit metadata order")


def get_engine(fit_key: str) -> FitEngineSpec:
    """Return the engine registration for ``fit_key``."""

    return ENGINE_REGISTRY[fit_key]


def run_fit(request: FitRequest) -> FitResult:
    """Run the registered engine for a plain fit request."""

    return get_engine(request.fit_key).run(request)

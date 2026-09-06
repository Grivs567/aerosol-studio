"""Pure numerical fit kernels.

These helpers do not import Bokeh and do not touch ``AerosolStudio`` state.
Public GUI orchestration remains in ``studio.py`` (background-thread
dispatch, cancellation, Bokeh source/renderer mutation); the fit math
itself is called from there via ``fitting.registry.run_fit``.

Each per-column kernel (``gaussian_lsq_peak``, ``gmm_peak``,
``peak_picker_peak``, ``appearance_time_peak``) accepts an optional
``diagnostics`` dict. When a kernel returns ``None`` (no peak for this
column) it sets ``diagnostics["reason"]`` to a short human-readable
explanation; ``fitting.registry._run_column_engine`` tallies these into
the "Skip summary: ..." message shown when a fit finds no peaks. This
mirrors ``diagnostics.get("fallback")``, which a kernel sets to ``True``
when it still produced a peak but only via a degraded fallback path
(e.g. ``curve_fit`` failing to converge).
"""

from __future__ import annotations

import aerosol.fitting as afi
import aerosol.functions as af
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

from aerosolstudio.science import gaussian, sigmoid


def mode_peaks_for_time(time_ms, dp_log_nm, conc, num_modes, roi_mask_row=None, diagnostics=None):
    """Fit lognormal modes for one time step and return canonical peak records.

    ``roi_mask_row``, if given, is the boolean ROI-polygon mask for this
    timestep (same length as ``dp_log_nm``); it is re-applied AFTER
    interpolation so a jagged/non-convex polygon boundary can't let a mode
    land at a diameter outside what was actually drawn (interpolation
    can't distinguish a real sensor gap from a point excluded by the ROI).

    Time steps with too few valid points, or a near-zero/empty
    concentration integral, are skipped before reaching
    ``afi.fit_multimode`` - passing degenerate input to it can raise
    (division by zero inside ``af.sample_from_dist``, then "Input X
    contains NaN" from the GMM step). ``diagnostics["reason"]`` is set to
    a short explanation when this function returns ``[]`` for that reason
    (as opposed to a clean fit that legitimately found zero gaussians).
    """

    s = pd.Series(index=dp_log_nm, data=conc).interpolate(limit_area="inside")
    if roi_mask_row is not None:
        row_mask = pd.Series(index=dp_log_nm, data=roi_mask_row)
        s = s.where(row_mask)
    s = s.dropna()
    s[s < 0] = 0

    if len(s) < 5:
        if diagnostics is not None:
            diagnostics["reason"] = "degenerate"
        return []

    trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))
    coef_check = trapz(s.values, s.index.values)
    if not np.isfinite(coef_check) or coef_check <= 0:
        if diagnostics is not None:
            diagnostics["reason"] = "degenerate"
        return []

    # aerosol-functions 0.1.16 dropped fit_multimode's ``method`` kwarg;
    # it now always does GMM-init + least-squares (what method="lsqr"
    # selected before), so the call is just the positional data plus
    # n_modes.
    res = afi.fit_multimode(
        s.index.values, s.values, pd.to_datetime(time_ms, unit="ms"),
        n_modes=num_modes,
    )
    peaks = []
    for r in res["gaussians"]:
        peaks.append(
            {
                "time": time_ms,
                "diam": (10 ** max(-3, min(3, r["mean"]))) * 1e-9,
                "mean": r["mean"],
                "sigma": r["sigma"],
                "amplitude": r["amplitude"],
            }
        )
    if not peaks and diagnostics is not None:
        diagnostics["reason"] = "empty"
    return peaks


def gaussian_lsq_peak(tim, dp_log_nm, conc, diagnostics=None):
    """Fit one Gaussian LSQ peak for a diameter time series."""

    ds = pd.Series(index=tim, data=np.asarray(conc, dtype=float))
    s = ds.interpolate(limit_area="inside").dropna()
    s[s < 0] = 0

    if len(s) < 5:
        if diagnostics is not None:
            diagnostics["reason"] = "too few valid points in ROI (<5)"
        return None

    x = s.index.values.astype(float)
    y = s.values.astype(float)

    if np.nanmax(y) <= 0:
        if diagnostics is not None:
            diagnostics["reason"] = "all concentrations ≤ 0"
        return None

    y_smooth = gaussian_filter1d(y, sigma=1.5)
    idx_guess = np.nanargmax(y_smooth)

    try:
        popt, _ = curve_fit(
            gaussian,
            x,
            y,
            p0=[np.nanmax(y), x[idx_guess], (x.max() - x.min()) / 10, np.nanmin(y)],
            maxfev=10000,
        )
        amplitude, peak_time, sigma_fit, _offset = popt
        peak_time = float(peak_time)
        peak_amp = float(amplitude)
    except (RuntimeError, ValueError, np.linalg.LinAlgError):
        idx_guess = np.nanargmax(y_smooth)
        peak_time = float(x[idx_guess])
        peak_amp = float(y_smooth[idx_guess])
        sigma_fit = 0.0
        if diagnostics is not None:
            diagnostics["fallback"] = True

    return {
        "time": peak_time,
        "diam": float((10**dp_log_nm) * 1e-9),
        "mean": peak_time,
        "sigma": float(sigma_fit),
        "amplitude": peak_amp,
        "t_min": x.min(),
        "t_max": x.max(),
    }


def gmm_peak(tim, dp_log_nm, conc, diagnostics=None):
    """Fit one GMM peak for a diameter time series."""

    ds = pd.Series(index=tim, data=np.asarray(conc).flatten())
    s = ds.interpolate(limit_area="inside").dropna()
    s[s < 0] = 0

    x_interp = s.index.values
    y_interp = s.values

    if len(x_interp) < 3 or len(y_interp) < 3:
        if diagnostics is not None:
            diagnostics["reason"] = "too few valid points in ROI (<3)"
        return None

    trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))
    coef = trapz(y_interp, x_interp)
    if not np.isfinite(coef) or coef <= 0:
        if diagnostics is not None:
            diagnostics["reason"] = "concentration integral ≤ 0"
        return None

    try:
        samples = af.sample_from_dist(x_interp, y_interp, 10000)
        res = afi.fit_gmm(samples, 1, coef)
    except (RuntimeError, ValueError, np.linalg.LinAlgError, IndexError) as exc:
        if diagnostics is not None:
            diagnostics["reason"] = f"GMM fit raised {type(exc).__name__}"
        return None
    if not res:
        if diagnostics is not None:
            diagnostics["reason"] = "GMM fit returned no components"
        return None

    return {
        "time": float(res[0]["mean"]),
        "diam": float((10**dp_log_nm) * 1e-9),
        "mean": res[0]["mean"],
        "sigma": res[0]["sigma"],
        "amplitude": res[0]["amplitude"],
    }


def peak_picker_peak(tim, dp_log_nm, conc, diagnostics=None):
    """Pick one peak for a diameter time series."""

    ds = pd.Series(index=tim, data=np.asarray(conc, dtype=float))
    s = ds.interpolate(limit_area="inside").dropna()
    s[s < 0] = 0

    if len(s) < 5:
        if diagnostics is not None:
            diagnostics["reason"] = "too few valid points in ROI (<5)"
        return None

    x = s.index.values
    y = s.values

    if np.nanmax(y) <= 0:
        if diagnostics is not None:
            diagnostics["reason"] = "all concentrations ≤ 0"
        return None

    y_smooth = gaussian_filter1d(y, sigma=1.5)
    prom = 0.05 * np.nanmax(y_smooth)
    peak_idx, _props = find_peaks(y_smooth, prominence=prom)

    if len(peak_idx) > 0:
        idx = peak_idx[np.argmax(y_smooth[peak_idx])]
    else:
        idx = np.nanargmax(y_smooth)

    peak_time = float(x[idx])
    peak_amp = float(y_smooth[idx])

    return {
        "time": peak_time,
        "diam": float((10**dp_log_nm) * 1e-9),
        "mean": peak_time,
        "sigma": 0.0,
        "amplitude": peak_amp,
    }


def appearance_time_peak(tim_ms, dp_log_nm, conc, diagnostics=None):
    """Fit one appearance-time sigmoid peak for a diameter time series."""

    fac = 1000 * 60 * 60
    ds = pd.Series(index=tim_ms, data=np.asarray(conc).flatten())
    s = ds.interpolate(limit_area="inside").dropna()
    s[s < 0] = 0

    if len(s) < 8:
        if diagnostics is not None:
            diagnostics["reason"] = "too few valid points in ROI (<8)"
        return None

    x_ms = s.index.values
    y = s.values

    # Pick the peak on a lightly smoothed copy, mirroring peak_picker_peak's
    # prominence-based selection above - a plain np.argmax(y) picks whatever
    # the single tallest point in the ROI is, which can be a noise spike or
    # an unrelated feature rather than the real event peak. Everything up to
    # that index is then treated as "the rising limb" fed to the sigmoid
    # fit, so a wrongly-chosen peak can leave the fit dominated by the
    # falling edge of a different feature instead of the intended rising
    # edge. Only the *choice* of peak index is smoothed here; the sigmoid
    # fit below still runs on the real, unsmoothed data.
    y_smooth = gaussian_filter1d(y, sigma=1.5)
    prom = 0.05 * np.nanmax(y_smooth)
    smooth_peaks, _props = (
        find_peaks(y_smooth, prominence=prom) if prom > 0 else (np.array([], dtype=int), {})
    )
    if len(smooth_peaks) > 0:
        peak_idx = int(smooth_peaks[np.argmax(y_smooth[smooth_peaks])])
    else:
        peak_idx = int(np.nanargmax(y_smooth))

    if peak_idx < 5 or peak_idx >= len(y) - 2:
        if diagnostics is not None:
            diagnostics["reason"] = "peak too close to ROI edge"
        return None

    x_rise_ms = x_ms[: peak_idx + 1]
    y_rise = y[: peak_idx + 1]

    ymax = np.max(y_rise)
    if ymax <= 0:
        if diagnostics is not None:
            diagnostics["reason"] = "all concentrations ≤ 0"
        return None

    y_norm = y_rise / ymax
    x_rise_hr = x_rise_ms / fac

    if len(x_rise_hr) < 6:
        if diagnostics is not None:
            diagnostics["reason"] = "too few points on rising limb (<6)"
        return None

    try:
        p0 = [np.nanmedian(x_rise_hr), 1.0]
        params, _ = curve_fit(
            sigmoid,
            x_rise_hr,
            y_norm,
            p0=p0,
            bounds=([x_rise_hr.min(), 0.01], [x_rise_hr.max(), 10.0]),
            maxfev=15000,
        )

        x0_fit, k_fit = params
        y_fit = sigmoid(x_rise_hr, *params)
        ss_res = np.sum((y_norm - y_fit) ** 2)
        ss_tot = np.sum((y_norm - np.mean(y_norm)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        if r2 < 0.6:
            if diagnostics is not None:
                diagnostics["reason"] = "sigmoid fit too weak (R²<0.6)"
            return None

        return {
            "time": x0_fit * fac,
            "diam": (10**dp_log_nm) * 1e-9,
            "R2": r2,
            "k": k_fit,
            "t_min": x_rise_ms.min(),
            "t_max": x_rise_ms.max(),
        }
    except Exception as exc:
        if diagnostics is not None:
            diagnostics["reason"] = f"sigmoid fit raised {type(exc).__name__}"
        return None

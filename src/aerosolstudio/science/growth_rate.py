"""Growth-rate (GR) calculation helpers that are pure and Bokeh-free.

Currently wraps the maximum cross-correlation (MCC) method from:

    Lampilahti, J. et al. (2025), "A cross-correlation-based method for
    determining size-resolved particle growth rates", Aerosol Research,
    3, 637-647, https://doi.org/10.5194/ar-3-637-2025.

The underlying implementation lives in the aerosol-functions dependency
(``aerosol.functions.cross_corr_gr``) - this module does not reimplement
the method's math, only makes it safe and clear to call from the app:

  - Unit handling: ``cross_corr_gr`` compares dmin/dmax directly against
    ``df.columns`` with no conversion. This app's dataframes carry
    diameter columns in METRES; this module accepts dmin/dmax in
    nanometres (the app's UI convention) and converts internally, so a
    caller can never accidentally pass the wrong scale.
  - Failure handling: ``cross_corr_gr`` signals every failure mode as a
    bare negative integer (-999, -888, -777, -666, -555), not an
    exception or a descriptive dict. This module translates each one
    into a specific, human-readable reason.
  - NaN-threshold footgun: ``cross_corr_gr``'s own default is
    ``nan_threshold=0.0`` ("maximum fraction of NaNs allowed" per size
    channel). Since ``fraction_missing >= 0.0`` is true for ANY fraction
    including zero, that literal default makes the function return -999
    on every call, even with perfectly clean data (confirmed
    empirically; still true as of aerosol-functions 0.1.16). This module
    defaults it to 1.0 (effectively disabled) instead of silently
    inheriting a default that breaks the function outright; callers who
    want real NaN-quality gating can still pass a stricter value
    explicitly.

Compatibility note: aerosol-functions 0.1.16 renamed ``cross_corr_gr``'s
``tau_window`` kwarg to ``tau_limit`` and collapsed its separate
``row_threshold``/``col_threshold`` kwargs into a single ``nan_threshold``.
This wrapper keeps its own app-facing names (``tau_window_hr``,
``nan_threshold``) stable and maps them across at the call site, so the
rest of the app (GUI fields, FitSnapshot, batch export) is unaffected by
the dependency's rename. 0.1.16 also added opt-in ``median_filter_window``
(spike removal) and ``gamma`` (cross-correlation normalisation exponent)
knobs, exposed here as pass-throughs.

The wrapper is intentionally conservative: it keeps unit conversion, failure
messages, and default quality thresholds explicit at the application boundary.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import aerosol.functions as af

# cross_corr_gr()'s negative-integer failure sentinels, decoded from its
# source (aerosol/functions.py, aerosol-functions package). Keep in sync if
# the dependency changes; the scientific-baseline test would catch drift in
# the *success* path, but these come from reading the source directly.
_SENTINEL_MESSAGES: dict[int, str] = {
    -999: (
        "bad data: diameter range outside the ROI's data, too many missing "
        "values, timestamps not strictly increasing, fewer than 23 time "
        "steps in the ROI, or fewer size channels in range than "
        "number_of_divisions"
    ),
    -888: "no discernible time lag between the two size channels (tau_max = 0)",
    -777: (
        "negative time lag - the larger size channel's concentration rose "
        "before the smaller one's; not a valid growth signal in this range"
    ),
    -666: (
        "best-fit lag hit the edge of the tau search window - the real lag "
        "may be longer than tau_window_hr allows; try widening it"
    ),
    -555: "cross-correlation growth-rate calculation failed for an unrecognized reason",
}


def compute_cross_correlation_gr(
    df: pd.DataFrame,
    dmin_nm: float,
    dmax_nm: float,
    *,
    smoothing_window_hr: float = 3.0,
    tau_window_hr: float = 22.0,
    number_of_divisions: int = 1,
    nan_threshold: float = 1.0,
    median_filter_window_hr: float | None = None,
    gamma: float = 0.25,
    verbose: bool = False,
) -> dict[str, Any]:
    """Compute particle growth rate via the maximum cross-correlation method.

    Parameters
    ----------
    df:
        Number size distribution: a DatetimeIndex-indexed DataFrame whose
        columns are particle diameters in METRES (this app's standard
        dataframe convention - e.g. what get_roi_dataframe() returns).
    dmin_nm, dmax_nm:
        Diameter range for the GR calculation, in NANOMETRES (this app's
        UI convention - e.g. what gr_dmin_input/gr_dmax_input hold).
    smoothing_window_hr:
        Rolling-mean window applied to each size channel's concentration
        time series, in hours. Mapped to ``cross_corr_gr``'s
        ``smoothing_window``.
    tau_window_hr:
        Range of time lags searched, in hours. Mapped to
        ``cross_corr_gr``'s ``tau_limit`` (renamed from ``tau_window`` in
        aerosol-functions 0.1.16). If a result comes back with reason
        "hit the edge of the tau search window", widen this.
    number_of_divisions:
        Split [dmin_nm, dmax_nm] into this many sub-ranges on a log
        scale and average their GRs (see the paper's Sect. 2.1, point 5).
    nan_threshold:
        Maximum allowed fraction of missing values in any one size
        channel before the ROI is rejected as bad data. Default 1.0
        (effectively disabled) - see the NaN-threshold footgun note in
        this module's docstring before lowering this. Mapped to
        ``cross_corr_gr``'s ``nan_threshold`` (0.1.16 replaced the
        earlier separate ``row_threshold``/``col_threshold``).
    median_filter_window_hr:
        Optional rolling-median window, in hours, applied before
        smoothing for spike removal (aerosol-functions 0.1.16+).
        ``None`` (default) disables it.
    gamma:
        Cross-correlation normalisation exponent passed straight to
        ``cross_corr_gr`` (aerosol-functions 0.1.16+); the upstream
        default is 0.25.
    verbose:
        If True, also return the raw lag/correlation arrays.

    Returns
    -------
    On success: {"ok": True, "growth_rate_nm_per_hr": float, "method": str,
    "dmin_nm": float, "dmax_nm": float, "data_reso_hr": float, ...}

    On failure: {"ok": False, "reason": str, "sentinel": int | None} - never
    raises for expected failure modes (bad range, insufficient data, no
    lag found, etc.); only genuinely unexpected errors (e.g. malformed df)
    propagate as exceptions.
    """
    if df is None or df.empty:
        return {"ok": False, "reason": "no data in ROI", "sentinel": None}
    if not isinstance(df.index, pd.DatetimeIndex):
        return {"ok": False, "reason": "ROI data index is not a DatetimeIndex", "sentinel": None}
    if len(df.index) < 2:
        return {"ok": False, "reason": "fewer than 2 time steps in ROI", "sentinel": None}
    if dmin_nm >= dmax_nm:
        return {"ok": False, "reason": "dmin_nm must be less than dmax_nm", "sentinel": None}

    diffs = df.index.to_series().diff().dropna().dt.total_seconds()
    if diffs.empty or diffs.median() <= 0:
        return {
            "ok": False,
            "reason": "cannot determine a positive time resolution from the ROI's timestamps",
            "sentinel": None,
        }
    data_reso_hr = float(diffs.median()) / 3600.0

    dmin_m = dmin_nm * 1e-9
    dmax_m = dmax_nm * 1e-9

    result = af.cross_corr_gr(
        df,
        dmin_m,
        dmax_m,
        median_filter_window=median_filter_window_hr,
        smoothing_window=smoothing_window_hr,
        tau_limit=tau_window_hr,
        number_of_divisions=number_of_divisions,
        nan_threshold=nan_threshold,
        data_reso=data_reso_hr,
        gamma=gamma,
        verbose=verbose,
    )

    # Failure paths in cross_corr_gr return a bare negative int; success
    # paths return a dict with a "gr" key. Normalize both to one shape.
    if isinstance(result, dict):
        gr = result.get("gr")
    else:
        gr = result

    if gr in _SENTINEL_MESSAGES:
        return {"ok": False, "reason": _SENTINEL_MESSAGES[gr], "sentinel": gr}

    if not isinstance(gr, (int, float)):
        return {
            "ok": False,
            "reason": f"unexpected return type from cross_corr_gr: {type(gr).__name__}",
            "sentinel": None,
        }

    out: dict[str, Any] = {
        "ok": True,
        "growth_rate_nm_per_hr": float(gr),
        "method": "MCC (cross-correlation)",
        "dmin_nm": dmin_nm,
        "dmax_nm": dmax_nm,
        "data_reso_hr": data_reso_hr,
    }
    if verbose and isinstance(result, dict):
        out["lag_s"] = result.get("lag")
        out["corr"] = result.get("corr")
    return out

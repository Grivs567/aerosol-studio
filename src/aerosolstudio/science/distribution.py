"""Particle-size-distribution unit conversions: dN/dlogDp <-> N, surface,
volume, and PM (mass) concentration.

Pure, Bokeh-free, and deliberately separate from ``units.py`` (which only
does bare scalar unit conversions like nm<->m) - everything here is
domain-specific aerosol-science math, not a generic unit converter.

Conventions used throughout this module (matching the rest of the app):
  - Diameter (``diameters_m``) is always in METRES - the app's internal
    canonical unit (see ``roi_mask``/``_points_in_polygon`` docstrings).
  - dN/dlogDp values are in cm^-3 (the convention already used by
    ``science/overlay_var.py``'s ``af.calc_conc`` output and everywhere
    else concentration numbers are shown in the UI).
  - Heatmap surface/volume density views use the dedicated
    ``aerosol-functions`` transforms and therefore return dS/dlogDp in
    m^2/cm^3 and dV/dlogDp in m^3/cm^3 for metre-based diameter columns.
  - PM (mass concentration) is returned in ug/m^3.

Bin-width caveat (read before trusting exact numbers at the very ends of
a size distribution): only bin CENTERS are known from a loaded file (one
diameter value per column), never bin edges. This module infers each
bin's width in log10(Dp) space from the geometric midpoints between
adjacent centers - standard practice for log-spaced size-distribution
bins, and exact for interior bins. The two edge bins (smallest and
largest diameter) have no neighbor on one side, so their outer edge is
extrapolated by mirroring the adjacent bin's width. This is a real,
unavoidable approximation given the data available (never encoded in the
file), and only affects the single smallest/largest bin - it does not
compound or affect interior bins.
"""

from __future__ import annotations

import aerosol.functions as af
import numpy as np
import pandas as pd

__all__ = [
    "bin_log10_widths",
    "dndlogdp_to_number",
    "number_to_dndlogdp",
    "dndlogdp_to_surface_area",
    "dndlogdp_to_volume",
    "volume_to_pm",
    "extend_distribution_to_diameter",
    "PM_CUTOFFS_NM",
]

# Standard regulatory/literature PM cutoffs, in nanometres.
PM_CUTOFFS_NM = {
    "PM1": 1000.0,
    "PM2.5": 2500.0,
    "PM10": 10000.0,
}


def bin_log10_widths(diameters_m: np.ndarray) -> np.ndarray:
    """Return each bin's width in log10(Dp) space, one value per diameter.

    ``diameters_m`` must be sorted ascending (bin centers, metres). Interior
    bins use the geometric-midpoint edges between neighbors (exact under
    the standard assumption of log-uniform bin spacing); the first and
    last bins mirror their single neighbor's width - see module docstring.
    """

    dp = np.asarray(diameters_m, dtype=float)
    if dp.ndim != 1:
        raise ValueError("diameters_m must be 1-D")
    n = dp.size
    if n == 0:
        return np.zeros(0)
    if n == 1:
        # No neighbor at all to infer a width from - undefined, so this
        # single "bin" can't meaningfully be converted. Callers should
        # treat this as a degenerate case (e.g. skip conversion).
        return np.full(1, np.nan)
    if np.any(dp <= 0) or np.any(np.diff(dp) <= 0):
        raise ValueError("diameters_m must be strictly increasing and positive")

    log_dp = np.log10(dp)
    # Edges at the geometric midpoint (arithmetic midpoint in log-space)
    # between adjacent centers.
    interior_edges = (log_dp[:-1] + log_dp[1:]) / 2.0
    first_half_width = interior_edges[0] - log_dp[0]
    last_half_width = log_dp[-1] - interior_edges[-1]
    edges = np.concatenate(
        (
            [log_dp[0] - first_half_width],
            interior_edges,
            [log_dp[-1] + last_half_width],
        )
    )
    return edges[1:] - edges[:-1]


def _apply_per_column(df: pd.DataFrame, transform) -> pd.DataFrame:
    diameters_m = df.columns.to_numpy(dtype=float)
    widths = bin_log10_widths(diameters_m)
    out = transform(df.to_numpy(dtype=float), diameters_m, widths)
    return pd.DataFrame(out, index=df.index, columns=df.columns)


def dndlogdp_to_number(df: pd.DataFrame) -> pd.DataFrame:
    """Convert dN/dlogDp (cm^-3) to per-bin number concentration N (cm^-3).

    ``df`` columns are diameter in metres (bin centers); values are
    dN/dlogDp. N_i = (dN/dlogDp)_i * dlogDp_i.
    """

    return _apply_per_column(df, lambda vals, dp, w: vals * w)


def number_to_dndlogdp(df: pd.DataFrame) -> pd.DataFrame:
    """Inverse of ``dndlogdp_to_number``: per-bin N (cm^-3) back to
    dN/dlogDp (cm^-3)."""

    return _apply_per_column(df, lambda vals, dp, w: vals / w)


def dndlogdp_to_surface_area(df: pd.DataFrame) -> pd.DataFrame:
    """Convert dN/dlogDp to dS/dlogDp using ``aerosol-functions``.

    Columns are particle diameters in metres; returned values are m^2/cm^3,
    matching ``aerosol.functions.surf_dist``.
    """

    return af.surf_dist(df)


def dndlogdp_to_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Convert dN/dlogDp to dV/dlogDp using ``aerosol-functions``.

    Columns are particle diameters in metres; returned values are m^3/cm^3,
    matching ``aerosol.functions.vol_dist``.
    """

    return af.vol_dist(df)


def extend_distribution_to_diameter(
    df: pd.DataFrame, target_dmax_m: float, tail_points: int = 4
) -> pd.DataFrame:
    """Extend a dN/dlogDp distribution's diameter grid out to
    ``target_dmax_m`` by assuming its upper tail follows a single lognormal
    mode - the standard model for atmospheric aerosol size distributions
    (Whitby, K.T. (1978). "The physical characteristics of sulfur aerosols."
    Atmospheric Environment, 12(1-3), 135-159; Hinds, W.C. (1999). Aerosol
    Technology: Properties, Behavior, and Measurement of Airborne Particles,
    2nd ed., Wiley, Ch. 4). For a lognormal mode, ln(dN/dlogDp) is an exact
    quadratic function of log10(Dp) - so this fits a degree-2 polynomial
    (ordinary least squares, not an iterative optimizer, so it's cheap
    enough to run per-row/per-timestamp) to the last ``tail_points``
    measured bins in that space, then evaluates it on synthetic bins added
    beyond the measured range at the same log-spacing as the existing grid.

    Existing bins/columns are returned completely untouched; only new
    columns are appended. If ``target_dmax_m`` is already within (or below)
    the measured range, ``df`` is returned unchanged - no synthetic bins are
    needed.

    This is a shape *assumption*, not a measurement: a tail that isn't
    actually lognormal (e.g. an unresolved second mode just past the
    measured range) will extrapolate incorrectly, and a fitted parabola
    that curves upward at large Dp (a sign the fit is unreliable, since a
    lognormal tail past its mode is strictly decreasing) is clamped to be
    non-increasing from the last real value rather than trusted outright.
    It exists only for the optional "interpolate PSD" toggle (see
    science/pm.py's PM overlay methods) - unchecked, PM is computed only
    from what was actually measured, same as before this function existed.
    """

    diameters_m = df.columns.to_numpy(dtype=float)
    if diameters_m.size < 2:
        # Can't infer a grid spacing or fit a tail from 0-1 columns.
        return df

    current_max = diameters_m.max()
    if target_dmax_m <= current_max:
        return df

    log_step = float(np.median(np.diff(np.log10(diameters_m))))
    if not np.isfinite(log_step) or log_step <= 0:
        return df

    n_new = int(np.ceil((np.log10(target_dmax_m) - np.log10(current_max)) / log_step))
    if n_new <= 0:
        return df
    new_log_dp = np.log10(current_max) + log_step * np.arange(1, n_new + 1)
    new_dp_m = 10.0 ** new_log_dp

    tail_points = min(tail_points, diameters_m.size)
    tail_log_dp = np.log10(diameters_m[-tail_points:])
    values = df.to_numpy(dtype=float)
    tail_values = values[:, -tail_points:]

    new_values = np.full((values.shape[0], n_new), np.nan)
    for i in range(values.shape[0]):
        row = tail_values[i]
        mask = np.isfinite(row) & (row > 0)
        if mask.sum() < 3:
            # A quadratic (lognormal) fit needs at least 3 points - leave
            # this row's extension as NaN rather than guess from fewer.
            continue
        coeffs = np.polyfit(tail_log_dp[mask], np.log(row[mask]), deg=2)
        predicted = np.exp(np.polyval(coeffs, new_log_dp))
        anchor = row[mask][-1]
        new_values[i] = np.minimum.accumulate(np.concatenate(([anchor], predicted)))[1:]

    extended = pd.DataFrame(new_values, index=df.index, columns=new_dp_m)
    return pd.concat([df, extended], axis=1)


def volume_to_pm(df: pd.DataFrame, dmax_nm: float, density_g_cm3: float) -> pd.Series:
    """Integrate dV/dlogDp up to ``dmax_nm`` and convert to PM (ug/m^3).

    Unit identity used here: 1 (um^3/cm^3) of material at 1 g/cm^3 density
    is exactly 1 ug/m^3 - so ``PM[ug/m^3] = density[g/cm^3] * V[um^3/cm^3]``
    with no extra scale factor. (1 um^3 = 1e-18 m^3, 1 cm^3 = 1e-6 m^3, so
    um^3/cm^3 -> volume fraction is 1e-12; density in g/cm^3 -> kg/m^3 is
    1e3; kg/m^3 -> ug/m^3 is 1e9; 1e-12 x 1e3 x 1e9 = 1.)
    """

    diameters_m = df.columns.to_numpy(dtype=float)
    dmax_m = dmax_nm * 1e-9
    widths = bin_log10_widths(diameters_m)
    included = diameters_m <= dmax_m

    dp_um = diameters_m * 1e6
    dv_dlogdp = (np.pi / 6.0) * (dp_um[np.newaxis, :] ** 3) * df.to_numpy(dtype=float)
    volume_conc = np.nansum(
        np.where(included[np.newaxis, :], dv_dlogdp * widths[np.newaxis, :], 0.0),
        axis=1,
    )
    pm = density_g_cm3 * volume_conc
    return pd.Series(pm, index=df.index)

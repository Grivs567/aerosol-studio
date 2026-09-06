"""PM (mass concentration) overlay-method registry.

Deliberately isolated from ``app/studio.py`` and structured the same way as
``science/overlay_var.py`` (which wraps ``aerosol.functions`` calls behind
a plain ``name -> callable(df, dmin, dmax)`` dict): the app should never need
to know *how* PM is computed, only that ``build_pm_methods(...)`` hands back
callables with that same signature.

Right now the actual math lives in ``science/distribution.py``
(``volume_to_pm``), which is pure Python/numpy and has no dependency on the
external ``aerosol-functions`` package. If/when PM calculation is added to
that package (mirroring how ``concentration.py`` calls ``af.calc_conc`` /
``af.calc_cs`` / ``af.calc_coags`` today), only the single ``_compute_pm``
call below needs to change - nothing in ``app/studio.py`` or ``overlay.py``
has to move, since both only ever see the registry's callables, never this
module's internals.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from aerosolstudio.science.distribution import (
    PM_CUTOFFS_NM,
    extend_distribution_to_diameter,
    volume_to_pm,
)

__all__ = ["build_pm_methods", "DEFAULT_PM_DENSITY_G_CM3", "PM_DIAMETER_LABELS"]

DEFAULT_PM_DENSITY_G_CM3 = 1.5

# UI metadata, mirroring overlay_var_diameter_labels in science/overlay_var.py
# - see that module's docstring for the (label, unit, default) spec shape.
# Density rides the existing dmin box (unit "raw" - a plain g/cm^3 number,
# not a diameter, so it must NOT get the usual nm-to-metres conversion)
# instead of a separate always-visible widget, and pre-fills with
# DEFAULT_PM_DENSITY_G_CM3 the moment a PM method is selected (if the box is
# currently blank) so a fresh line always has something sane to compute
# with; dmax is the cutoff diameter for "PM (custom)" only (no sensible
# default - the user must pick one) - the fixed PM1/PM2.5/PM10 entries
# ignore it and use their standard regulatory cutoffs instead.
PM_DIAMETER_LABELS = {
    "PM1": (("Density (g/cm³)", "raw", str(DEFAULT_PM_DENSITY_G_CM3)), None),
    "PM2.5": (("Density (g/cm³)", "raw", str(DEFAULT_PM_DENSITY_G_CM3)), None),
    "PM10": (("Density (g/cm³)", "raw", str(DEFAULT_PM_DENSITY_G_CM3)), None),
    "PM (custom)": (
        ("Density (g/cm³)", "raw", str(DEFAULT_PM_DENSITY_G_CM3)),
        ("PM cutoff (nm)", "nm", None),
    ),
}


def _compute_pm(
    df: pd.DataFrame, dmax_nm: float, density_g_cm3: float, interpolate: bool
) -> pd.Series:
    """Single seam for the actual PM computation - swap this call to a
    future ``af.calc_pm(...)`` (or similar) without touching any caller.

    When ``interpolate`` is on and ``dmax_nm`` reaches past the data's
    measured diameters, the distribution's tail is first extended via a
    lognormal-mode extrapolation (see
    ``distribution.extend_distribution_to_diameter``) before integrating -
    an explicit, visible opt-in. Off (the default), PM is computed only
    from what was actually measured, truncating silently at the data's own
    max diameter exactly as before this option existed."""

    if interpolate:
        df = extend_distribution_to_diameter(df, target_dmax_m=dmax_nm * 1e-9)
    return volume_to_pm(df, dmax_nm=dmax_nm, density_g_cm3=density_g_cm3)


def _coerce_density(raw_density: float) -> float:
    """``raw_density`` is the overlay line's own dmin value, already parsed
    as a plain float by OverlayVarLine._read_dmin_dmax_m (PM_DIAMETER_LABELS
    marks it unit "raw", so no nm-to-metres conversion has been applied) -
    only non-positive values need a fallback here; unparseable input never
    reaches this far (_read_dmin_dmax_m returns None on a ValueError, which
    makes OverlayVarLine.update() bail out before calling any method)."""
    if raw_density <= 0:
        return DEFAULT_PM_DENSITY_G_CM3
    return raw_density


def _coerce_interpolate(interpolate_getter: Callable[[], object] | None) -> bool:
    if interpolate_getter is None:
        return False
    try:
        return bool(interpolate_getter())
    except Exception:
        return False


def build_pm_methods(
    interpolate_getter: Callable[[], object] | None = None,
) -> dict[str, Callable]:
    """Return PM1/PM2.5/PM10/PM(custom) methods with the same
    ``(df, dmin, dmax) -> pd.Series`` signature used by
    ``science/overlay_var.py``'s ``overlay_var_methods`` registry, so they can be
    merged straight into that dict and used interchangeably by
    ``OverlayVarLine``/``add_overlay_var_line``/``_download_overlay_var_line``.

    Density comes from ``dmin`` (the overlay line's own dmin box, relabeled
    "Density (g/cm³)" per PM_DIAMETER_LABELS - unit "raw", so it arrives
    here as a plain, unconverted g/cm^3 number) - not a separate widget, so
    each overlay line can use its own density and there's nothing extra to
    wire up per instrument.

    ``interpolate_getter`` is still a zero-arg callable read fresh on every
    invocation (e.g. ``lambda: inst["pm_interpolate_toggle"].active``) since
    it stays a per-instrument setting, not a per-line one; defaults to None
    (interpolation off) so existing callers that don't pass it are unaffected.

    The generic ``dmax`` parameter (metres, from the overlay's own dmax
    input box) is used only by "PM (custom)"; the fixed PM1/PM2.5/PM10
    entries ignore it and use their standard regulatory cutoffs instead.
    """

    def _fixed(cutoff_nm):
        def _method(df, dmin, dmax, _cutoff=cutoff_nm):
            density = _coerce_density(dmin)
            interpolate = _coerce_interpolate(interpolate_getter)
            return _compute_pm(df, dmax_nm=_cutoff, density_g_cm3=density, interpolate=interpolate)

        return _method

    def _custom(df, dmin, dmax):
        density = _coerce_density(dmin)
        interpolate = _coerce_interpolate(interpolate_getter)
        cutoff_nm = dmax * 1e9  # dmax is still a diameter - existing *1e-9 convention
        return _compute_pm(df, dmax_nm=cutoff_nm, density_g_cm3=density, interpolate=interpolate)

    return {
        "PM1": _fixed(PM_CUTOFFS_NM["PM1"]),
        "PM2.5": _fixed(PM_CUTOFFS_NM["PM2.5"]),
        "PM10": _fixed(PM_CUTOFFS_NM["PM10"]),
        "PM (custom)": _custom,
    }

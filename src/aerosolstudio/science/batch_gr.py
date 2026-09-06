"""Batch growth-rate collection across many loaded instruments/days.

Pure, Bokeh-free orchestration: given the app's already-loaded instrument
state, produce one flat table of GR results suitable for CSV export -
mirroring the shape of a typical multi-day GR summary (e.g. the
supp_GR_results.csv workflow this was modeled on).

IMPORTANT design constraint: this collects results, it never computes them.
Both GR families below are only ever gathered from where the user
already ran them, with full context (which instrument, which region, which
diameter range) visible right there in the interactive app:

  - Point-fit methods (Gaussian/Appearance/Mode/GMM/Peak Picker): run
    per-polygon via "Fit Line" in an instrument's own tab, next to its
    heatmap; stored in ``polygon["growth_rates"][fit_key]``.
  - MCC (cross-correlation): run via the "Cross-Corr GR" button in an
    instrument's own tab (same Growth Rate panel as Fit Line), scoped to
    either the whole loaded dataset or the user's selected ROI, using the
    same Dp min/max fields Fit Line uses; stored in
    ``inst["mcc_results"]`` (a list - the user may run it more than once
    with different regions/ranges).

An earlier version of this module ran MCC itself, blind, over hardcoded
default size windows across every loaded instrument with no way to tell
which data or region a result came from. That produced numbers with no
way to sanity-check them against the actual heatmap. This module now
only ever reports what was computed in full context; a "skipped" row
with a specific reason is always safer than a number nobody can verify.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


def _point_fit_rows(instrument_name: str, polygons: Iterable[dict]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for poly_idx, poly in enumerate(polygons):
        label = poly.get("label") or f"Polygon {poly_idx}"
        growth_rates = poly.get("growth_rates") or {}
        for fit_key, gr in growth_rates.items():
            rows.append(
                {
                    "instrument": instrument_name,
                    "polygon": label,
                    "method": gr.get("source_name", fit_key),
                    "region": label,
                    "dmin_nm": gr.get("dp_min_nm"),
                    "dmax_nm": gr.get("dp_max_nm"),
                    "growth_rate_nm_per_hr": gr.get("growth_rate_nm_per_hr"),
                    "r2": gr.get("r2"),
                    "n_points": gr.get("n_points"),
                    "status": "ok",
                    "reason": "",
                }
            )
        if not growth_rates:
            rows.append(
                {
                    "instrument": instrument_name,
                    "polygon": label,
                    "method": None,
                    "region": label,
                    "dmin_nm": None,
                    "dmax_nm": None,
                    "growth_rate_nm_per_hr": None,
                    "r2": None,
                    "n_points": None,
                    "status": "skipped",
                    "reason": "no point-fit GR computed yet for this polygon "
                    "(run Fit Line in the instrument tab first)",
                }
            )
    return rows


def _mcc_rows(instrument_name: str, mcc_results: Iterable[dict] | None) -> list[dict[str, Any]]:
    mcc_results = list(mcc_results or [])
    if not mcc_results:
        return [
            {
                "instrument": instrument_name,
                "polygon": None,
                "method": "MCC (cross-correlation)",
                "region": None,
                "dmin_nm": None,
                "dmax_nm": None,
                "growth_rate_nm_per_hr": None,
                "r2": None,
                "n_points": None,
                "status": "skipped",
                "reason": "no MCC GR computed yet for this instrument "
                "(run Cross-Corr GR in the instrument tab first)",
            }
        ]

    rows: list[dict[str, Any]] = []
    for entry in mcc_results:
        base = {
            "instrument": instrument_name,
            "polygon": None,
            "method": "MCC (cross-correlation)",
            "region": entry.get("region_label"),
            "dmin_nm": entry.get("dmin_nm"),
            "dmax_nm": entry.get("dmax_nm"),
            "r2": None,  # MCC reports a correlation, not an R^2; not conflated here
            "n_points": None,
        }
        if entry.get("ok"):
            base.update(
                growth_rate_nm_per_hr=entry.get("growth_rate_nm_per_hr"),
                status="ok",
                reason="",
            )
        else:
            base.update(
                growth_rate_nm_per_hr=None,
                status="failed",
                reason=entry.get("reason", "unknown failure"),
            )
        rows.append(base)
    return rows


def collect_batch_gr_results(
    instruments: dict[str, dict[str, Any]],
    *,
    include_point_fits: bool = True,
    include_mcc: bool = True,
) -> list[dict[str, Any]]:
    """Build a flat GR results table across every loaded instrument.

    Collects only - never computes. Every row traces back to something the
    user explicitly ran in an instrument's own tab, with the region and
    diameter range it used.

    Parameters
    ----------
    instruments:
        Mapping of instrument name -> instrument dict, in the same shape
        as the app's ``self.instruments`` (reads "polygons" for point-fit
        results, "mcc_results" for MCC results - both optional/absent is
        fine and reported as a "skipped" row with a reason).
    include_point_fits, include_mcc:
        Toggle each GR family independently.

    Returns
    -------
    A list of row dicts, one per (instrument, polygon, method) or
    (instrument, MCC run) - ready to hand to pandas.DataFrame for CSV
    export. Every row has a "status" of "ok", "skipped", or "failed", and
    a "reason" that is never empty for non-"ok" rows - there is no silent
    gap in this table.
    """
    rows: list[dict[str, Any]] = []

    for name, inst in instruments.items():
        if include_point_fits:
            rows.extend(_point_fit_rows(name, inst.get("polygons") or []))
        if include_mcc:
            rows.extend(_mcc_rows(name, inst.get("mcc_results")))

    return rows


def batch_gr_results_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Convenience: results table -> a DataFrame with a stable column order."""
    columns = [
        "instrument",
        "polygon",
        "method",
        "region",
        "dmin_nm",
        "dmax_nm",
        "growth_rate_nm_per_hr",
        "r2",
        "n_points",
        "status",
        "reason",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns]

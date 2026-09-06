"""Diameter-unit and concentration-representation declarations for file loading.

Raw instrument files rarely declare their units unambiguously: CSV headers
never carry a units string at all, and NetCDF attributes are inconsistent
across instruments and processing pipelines. Historically this app assumed
every loaded diameter column was already in metres and every value was
already dN/dlogDp, with zero validation - a silent assumption in the same
spirit as the old hardcoded +5:30 timezone shift (see ``utils/tz.py``).

This module intentionally does NOT try to guess silently. It mirrors the
Source Timezone pattern: the user declares diameter unit and data type at
load time (defaulting to nm / dN/dlogDp per instrument), the app uses
NetCDF attributes as a best-effort cross-check when present, and the
declared/detected value is always visible and editable before the next
Load click. Pure, Bokeh-free, and deliberately separate from
``science/distribution.py`` (which does the actual PSD math) - this module
only resolves *which* unit/representation is in play.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "DEFAULT_DIAMETER_UNIT",
    "DIAMETER_UNIT_OPTIONS",
    "DEFAULT_DATA_TYPE",
    "DATA_TYPE_OPTIONS",
    "diameter_unit_to_metres_factor",
    "detect_diameter_unit_from_attrs",
    "suggest_diameter_unit",
    "validate_diameter_magnitude",
]

DIAMETER_UNIT_OPTIONS = ["nm", "um", "m"]
DEFAULT_DIAMETER_UNIT = "nm"

DATA_TYPE_OPTIONS = ["dN/dlogDp", "Number Concentration (N)"]
DEFAULT_DATA_TYPE = "dN/dlogDp"

_DIAMETER_UNIT_FACTORS_TO_M = {
    "nm": 1e-9,
    "um": 1e-6,
    "m": 1.0,
}

# Broad but physically-motivated plausible range for RAW diameter values
# (i.e. before unit conversion to metres) under each declared unit. Real
# aerosol size distributions run roughly 1 nm to a few tens of microns, so
# these bounds are deliberately generous - they exist to catch a wrong unit
# choice (typically off by a factor of 1e3 or 1e9), not to second-guess a
# real instrument's range.
_DIAMETER_MAGNITUDE_PLAUSIBLE_RANGE = {
    "nm": (0.3, 20000.0),
    "um": (0.0003, 20.0),
    "m": (3e-10, 2e-5),
}

_ATTR_UNIT_ALIASES = {
    "nm": "nm", "nanometer": "nm", "nanometers": "nm",
    "nanometre": "nm", "nanometres": "nm",
    "um": "um", "µm": "um", "micrometer": "um", "micrometers": "um",
    "micrometre": "um", "micrometres": "um", "micron": "um", "microns": "um",
    "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
}


def diameter_unit_to_metres_factor(unit_name: str):
    """Return the multiplicative factor to convert a diameter value in
    ``unit_name`` to metres, or None if ``unit_name`` isn't recognized."""

    key = (unit_name or "").strip().lower().replace("µ", "u")
    return _DIAMETER_UNIT_FACTORS_TO_M.get(key)


def detect_diameter_unit_from_attrs(attrs) -> str | None:
    """Best-effort sniff of a diameter unit from NetCDF variable attributes.

    Returns one of ``DIAMETER_UNIT_OPTIONS``, or None if nothing recognizable
    is present. Callers should keep the user's currently-declared value in
    that case rather than guessing - detection only ever *narrows* toward a
    value already backed by the file, never invents one.
    """

    if not attrs:
        return None
    raw = None
    for key in ("units", "unit", "Units", "Unit"):
        if key in attrs and attrs[key]:
            raw = attrs[key]
            break
    if not raw:
        return None
    text = str(raw).strip().lower().replace("µ", "u")
    return _ATTR_UNIT_ALIASES.get(text)


def suggest_diameter_unit(raw_values) -> str | None:
    """Best-effort guess of which ``DIAMETER_UNIT_OPTIONS`` entry the raw
    (pre-conversion) diameter values look like, based on typical magnitude.

    Returns None if there isn't enough finite/positive data to judge, or if
    no declared unit's plausible range fits.
    """

    values = np.asarray(raw_values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return None
    typical = float(np.median(values))
    for unit in DIAMETER_UNIT_OPTIONS:
        lo, hi = _DIAMETER_MAGNITUDE_PLAUSIBLE_RANGE[unit]
        if lo <= typical <= hi:
            return unit
    return None


def validate_diameter_magnitude(raw_values, declared_unit: str) -> str | None:
    """Sanity-check that raw (pre-conversion) diameter values are physically
    plausible for ``declared_unit``.

    Returns None if plausible (or if there's nothing usable to check).
    Otherwise returns a human-readable message describing the mismatch,
    naming a likely correct unit when one is identifiable. A wrong unit
    here silently corrupts every downstream diameter-dependent calculation
    (heatmap/strip axes, PM, growth-rate fitting) with no other error, so
    callers should surface/raise this rather than proceeding.
    """

    values = np.asarray(raw_values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return None

    bounds = _DIAMETER_MAGNITUDE_PLAUSIBLE_RANGE.get(declared_unit)
    if bounds is None:
        return None  # unrecognized unit name is handled elsewhere

    lo, hi = bounds
    typical = float(np.median(values))
    if lo <= typical <= hi:
        return None

    range_text = f"{values.min():.6g} - {values.max():.6g}"
    suggestion = suggest_diameter_unit(values)
    if suggestion and suggestion != declared_unit:
        return (
            f"Diameter values ({range_text}) look implausible for unit "
            f"'{declared_unit}' (typical value {typical:.6g}). They look more "
            f"like '{suggestion}'. Change Diameter Unit to '{suggestion}' and "
            f"reload, or confirm '{declared_unit}' is really correct."
        )
    return (
        f"Diameter values ({range_text}) look implausible for unit "
        f"'{declared_unit}' (typical value {typical:.6g}). Check the "
        f"Diameter Unit setting before loading."
    )

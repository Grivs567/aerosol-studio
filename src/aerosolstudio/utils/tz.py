"""Timezone helpers for interpreting raw instrument timestamps.

Every loaded file (CSV or NetCDF) has a timestamp column/index whose values
are *naive* wall-clock readings — there is no reliable way to know, from the
file alone, what timezone those clock readings were taken in (CSV files
never carry this metadata at all; NetCDF attributes sometimes do, but not
consistently). The app therefore asks the user to declare it explicitly at
load time (see the "Source Timezone" input next to each instrument's Load
button in ``studio.py``), defaulting to the machine's own local timezone as
a starting guess the user can override before clicking Load.

This module is deliberately dependency-light and pure (no Bokeh, no
studio.py imports) so it can be unit-tested and reused on its own — see the
"keep processing code in its own module" convention already used by
``aerosolstudio/science/overlay_var.py``.
"""

from __future__ import annotations

import zoneinfo

import pandas as pd

__all__ = [
    "DEFAULT_TIMEZONE",
    "detect_local_timezone",
    "list_timezones",
    "is_valid_timezone",
    "localize_naive_index_to_utc",
]

DEFAULT_TIMEZONE = "UTC"


def detect_local_timezone() -> str:
    """Best-effort guess at the machine's own IANA timezone name.

    Used only to *pre-fill* the source-timezone input as a convenience —
    the user always sees this value before loading and can change it, so a
    wrong guess here never silently corrupts data (it just starts the user
    off with a possibly-wrong default they're asked to confirm).

    Falls back to ``"UTC"`` if the local zone can't be determined (e.g. the
    optional ``tzlocal`` package is missing, or detection fails for any
    reason) rather than raising — this is a convenience default, not a
    correctness-critical path.
    """

    try:
        import tzlocal

        name = tzlocal.get_localzone_name()
        if name and is_valid_timezone(name):
            return name
    except Exception:
        pass
    return DEFAULT_TIMEZONE


def list_timezones() -> list[str]:
    """Return every known IANA timezone name, sorted, for the picker's
    autocomplete list."""

    return sorted(zoneinfo.available_timezones())


def is_valid_timezone(name: str) -> bool:
    """Return True if ``name`` is a real IANA timezone name.

    On Windows this requires the ``tzdata`` package to be installed (Windows
    has no system IANA tz database); ``tzdata`` is a pinned dependency of
    this package specifically so this never fails purely because of the
    platform.
    """

    if not name:
        return False
    try:
        zoneinfo.ZoneInfo(name)
        return True
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def localize_naive_index_to_utc(
    index_like: object, tz_name: str
) -> tuple[pd.DatetimeIndex, int]:
    """Reinterpret naive timestamps as wall-clock time in ``tz_name`` and
    convert to naive-but-UTC timestamps.

    The rest of the app (ROI polygons, fits, epoch-ms conversions) works
    entirely in naive timestamps that are implicitly assumed to already be
    UTC — see ``datetime_index_to_epoch_ms``, which raises if handed a
    tz-aware index. So the contract here is: take naive local-clock values,
    localize them to the declared source timezone, convert to UTC, then
    strip tz-awareness back off, leaving plain naive timestamps whose
    numeric value is now correctly UTC-referenced. This replaces the old
    hardcoded ``+5:30`` (IST) shift that used to be applied unconditionally
    to every NetCDF load regardless of where the data actually came from.

    DST transitions can make a wall-clock reading ambiguous (falls twice,
    at a "clocks back" transition) or nonexistent (skipped entirely, at a
    "clocks forward" transition). Ambiguous readings are dropped (``NaT``)
    rather than guessed at; nonexistent readings are shifted forward to the
    next valid instant. Returns the cleaned index plus a count of any rows
    dropped as ambiguous, so the caller can surface that to the user instead
    of silently losing rows.
    """

    idx = pd.DatetimeIndex(index_like)
    if idx.tz is not None:
        idx = idx.tz_localize(None)

    localized = idx.tz_localize(tz_name, ambiguous="NaT", nonexistent="shift_forward")
    dropped = int(localized.isna().sum())

    utc_naive = localized.tz_convert("UTC").tz_localize(None)
    return utc_naive, dropped

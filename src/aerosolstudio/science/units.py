"""Pure unit conversion helpers."""

from __future__ import annotations

import numpy as np


def nm_to_m(value):
    """Convert nanometres to metres."""

    return np.asarray(value, dtype=float) * 1e-9


def meters_to_nm(value):
    """Convert metres to nanometres."""

    return np.asarray(value, dtype=float) * 1e9


def seconds_to_hours(value):
    """Convert seconds to hours."""

    return np.asarray(value, dtype=float) / 3600.0

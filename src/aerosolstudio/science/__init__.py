"""Pure scientific utility helpers."""

from aerosolstudio.science.numeric import (
    auto_range_log,
    discrete_to_continuous,
    finite_positive,
    gaussian,
    normalize_writable_array,
    safe_log10,
    safe_median_filter,
    safe_power10,
    sigmoid,
)
from aerosolstudio.science.units import meters_to_nm, nm_to_m, seconds_to_hours

__all__ = [
    "auto_range_log",
    "discrete_to_continuous",
    "finite_positive",
    "gaussian",
    "meters_to_nm",
    "nm_to_m",
    "normalize_writable_array",
    "safe_log10",
    "safe_median_filter",
    "safe_power10",
    "seconds_to_hours",
    "sigmoid",
]

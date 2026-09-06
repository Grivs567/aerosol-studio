"""Time formatting helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ms_to_datetime(ms: float | int) -> pd.Timestamp:
    """Convert milliseconds since epoch to a pandas timestamp."""

    return pd.to_datetime(int(ms), unit="ms")


def time_value_to_ms(value: object) -> float:
    """Normalize pandas/numpy/numeric datetime values to epoch milliseconds."""

    if isinstance(value, pd.Timestamp):
        return float(value.value // 1_000_000)
    if isinstance(value, np.datetime64):
        return float(pd.Timestamp(value).value // 1_000_000)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(pd.to_datetime(value).value // 1_000_000)


def datetime_index_to_epoch_ms(index_like: object) -> np.ndarray:
    """Convert a datetime-like index/array to epoch milliseconds (int64).

    ``DatetimeIndex.view("int64")`` (used throughout the codebase before this
    helper existed) reinterprets the raw underlying buffer with no unit
    conversion, so it silently assumes nanosecond storage. That assumption
    broke under pandas >= 2.0, where ``pd.read_csv(parse_dates=...)``,
    ``pd.to_datetime``, and ``pd.date_range`` can all produce non-nanosecond
    (commonly microsecond, as of pandas 3.x) datetime64 dtypes: the raw
    ``.view("int64")`` values then come out 1000x (or 1e6x) off, since the
    call sites still divide by 1_000_000 assuming ns input. This helper goes
    through an explicit ``astype("datetime64[ms]")`` conversion instead,
    which is resolution-safe regardless of the source unit (ns/us/ms/s).
    """

    idx = pd.DatetimeIndex(index_like)
    return idx.astype("datetime64[ms]").astype(np.int64)

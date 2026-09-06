"""Pure numerical guardrails for scientific helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np


def normalize_writable_array(values: Iterable[float], *, dtype: type = float) -> np.ndarray:
    """Return a writable numpy array copy."""

    return np.array(values, dtype=dtype, copy=True)


def finite_positive(values: Iterable[float]) -> np.ndarray:
    """Return finite values greater than zero."""

    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr) & (arr > 0)]


def discrete_to_continuous(palette: Sequence[str], n: int = 256) -> list[str]:
    """Convert discrete color palette to continuous by interpolation.

    Note: plt.cm.colors does not exist; use matplotlib.colors.rgb2hex directly.
    """
    from matplotlib.colors import LinearSegmentedColormap, rgb2hex

    cmap = LinearSegmentedColormap.from_list("interp_map", palette, N=n)
    return [rgb2hex(cmap(i / (n - 1))) for i in range(n)]


def auto_range_log(values: Iterable[float], pad_frac: float = 0.1) -> tuple[float, float]:
    """Compute a safe positive range for log-axis display."""

    valid = finite_positive(values)
    if len(valid) == 0:
        return 1.0, 100.0
    ymin = float(np.nanmin(valid))
    ymax = float(np.nanmax(valid))
    return ymin * (1 - pad_frac), ymax * (1 + pad_frac)


def safe_log10(values: Iterable[float]) -> np.ndarray:
    """Return log10 values, using NaN outside the positive finite domain."""

    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    mask = np.isfinite(arr) & (arr > 0)
    out[mask] = np.log10(arr[mask])
    return out


def safe_power10(values: Iterable[float] | float, *, min_exp: float = -300, max_exp: float = 300):
    """Compute ``10 ** x`` with exponent clipping to avoid overflow."""

    arr = np.asarray(values, dtype=float)
    clipped = np.clip(arr, min_exp, max_exp)
    result = np.power(10.0, clipped)
    if np.ndim(values) == 0:
        return float(result)
    return result


def safe_median_filter(values: Iterable[float], kernel_size: int = 5) -> np.ndarray:
    """Median-filter one-dimensional data with a kernel safe for tiny arrays."""

    arr = np.asarray(values, dtype=float).reshape(-1)
    if len(arr) == 0:
        return arr.copy()
    kernel = min(int(kernel_size), len(arr))
    if kernel < 1:
        kernel = 1
    if kernel % 2 == 0:
        kernel -= 1
    if kernel <= 1:
        return arr.copy()
    radius = kernel // 2
    padded = np.pad(arr, (radius, radius), mode="edge")
    return np.asarray([np.nanmedian(padded[i : i + kernel]) for i in range(len(arr))], dtype=float)


def gaussian(x, amplitude: float, mu: float, sigma: float, offset: float):
    """Gaussian curve with a positive sigma guard."""

    sigma = max(float(abs(sigma)), np.finfo(float).eps)
    x_arr = np.asarray(x, dtype=float)
    return amplitude * np.exp(-((x_arr - mu) ** 2) / (2 * sigma**2)) + offset


def sigmoid(x, x0: float, k: float):
    """Numerically stable logistic sigmoid."""

    z = np.clip(-float(k) * (np.asarray(x, dtype=float) - float(x0)), -700, 700)
    return 1.0 / (1.0 + np.exp(z))

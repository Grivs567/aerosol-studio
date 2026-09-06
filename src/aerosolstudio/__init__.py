"""Aerosol Studio package skeleton.

The canonical executable app is the package Bokeh entry point.
"""

# --- numpy>=2.0 compatibility shim -----------------------------------------
# numpy 2.0 removed the deprecated `np.trapz` alias in favor of
# `np.trapezoid`. The installed third-party `aerosol-functions` 0.1.13
# package (aerosol/fitting.py, aerosol/functions.py, aerosol/aerosol_analyzer.py)
# still calls `np.trapz` directly and raises AttributeError on numpy>=2.0.
# Patch it back in here, at the top of this package's __init__, so it is in
# place before any aerosol.* module (or our own code) can call it. Remove
# once upstream aerosol-functions is fixed/pinned.
import numpy as _np

if not hasattr(_np, "trapz"):
    _np.trapz = _np.trapezoid
# -----------------------------------------------------------------------------

from aerosolstudio.config.branding import APP_NAME, __version__
from aerosolstudio.utils.paths import canonical_app_path

__all__ = ["APP_NAME", "__version__", "canonical_app_path"]

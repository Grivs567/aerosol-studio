"""Console entry points for Aerosol Studio.

This launcher serves the package-owned Bokeh entry point.
"""

from __future__ import annotations

import subprocess
import sys

from aerosolstudio.utils.paths import canonical_app_path


def run_app() -> int:
    """Launch Aerosol Studio with ``bokeh serve --show``."""

    app_path = canonical_app_path()
    if not app_path.exists():
        raise FileNotFoundError(f"Canonical Aerosol Studio app not found: {app_path}")
    cmd = [sys.executable, "-m", "bokeh", "serve", "--show", str(app_path)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(run_app())

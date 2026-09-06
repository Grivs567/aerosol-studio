"""Path helpers for launchers and package resources."""

from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    """Return the installed ``aerosolstudio`` package directory."""

    return Path(__file__).resolve().parents[1]


def repository_root() -> Path:
    """Return the source checkout root when running from this repository."""

    return Path(__file__).resolve().parents[3]


def canonical_app_path() -> Path:
    """Return the canonical package Bokeh app path.

    ``AEROSOL_STUDIO_APP`` lets frozen installers or downstream packages point
    at a copied canonical app without changing the package code.
    """

    override = os.environ.get("AEROSOL_STUDIO_APP")
    if override:
        return Path(override).expanduser().resolve()
    return package_root() / "main.py"


def data_dir() -> Path:
    """Return the repository data directory."""

    return repository_root() / "data"


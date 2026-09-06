"""Bokeh package entry point for the package-owned Aerosol Studio app."""

from __future__ import annotations

from bokeh.document import Document
from bokeh.io import curdoc

from aerosolstudio.app.studio import AerosolStudio


def build_document(doc: Document) -> AerosolStudio:
    """Build the Bokeh document with the package-owned studio controller."""

    return AerosolStudio(doc)


if __name__.startswith("bokeh_app_"):
    build_document(curdoc())

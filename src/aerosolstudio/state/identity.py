"""Stable identity helpers for passive records.

The canonical app still uses indices and existing dictionaries at runtime.
These helpers provide deterministic IDs for future session and renderer
metadata without changing live orchestration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from aerosolstudio.io.json_utils import json_safe


def stable_id(prefix: str, payload: Any) -> str:
    """Return a deterministic short ID for JSON-safe payload content."""

    encoded = json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def polygon_id(polygon: dict[str, Any]) -> str:
    """Return a passive stable ID for polygon geometry and label."""

    return stable_id(
        "poly",
        {
            "x": polygon.get("x", []),
            "y": polygon.get("y", []),
            "label": polygon.get("label", ""),
        },
    )


def fit_group_id(instrument_name: str, polygon_identifier: str, fit_key: str) -> str:
    """Return a passive stable ID for a polygon fit-point group."""

    return stable_id(
        "fitgrp",
        {"instrument": instrument_name, "polygon_id": polygon_identifier, "fit_key": fit_key},
    )


def renderer_metadata_id(metadata: RendererMetadata) -> str:
    """Return a passive stable ID for renderer metadata."""

    payload = metadata.to_payload()
    payload["renderer_id"] = None
    return stable_id("renderer", payload)


@dataclass(frozen=True)
class RendererMetadata:
    """Passive renderer tag metadata; not a Bokeh renderer wrapper."""

    category: str
    owner_instrument: str
    polygon_id: str | None = None
    fit_key: str | None = None
    renderer_id: str | None = None

    def to_payload(self) -> dict[str, str | None]:
        return {
            "category": self.category,
            "owner_instrument": self.owner_instrument,
            "polygon_id": self.polygon_id,
            "fit_key": self.fit_key,
            "renderer_id": self.renderer_id,
        }


def tag_renderer_metadata(
    category: str,
    owner_instrument: str,
    *,
    polygon_identifier: str | None = None,
    fit_key: str | None = None,
) -> RendererMetadata:
    """Build passive renderer metadata with a deterministic renderer ID."""

    base = RendererMetadata(
        category=category,
        owner_instrument=owner_instrument,
        polygon_id=polygon_identifier,
        fit_key=fit_key,
    )
    return RendererMetadata(
        category=base.category,
        owner_instrument=base.owner_instrument,
        polygon_id=base.polygon_id,
        fit_key=base.fit_key,
        renderer_id=renderer_metadata_id(base),
    )

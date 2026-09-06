"""Versioned session schema helpers."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from aerosolstudio.config.branding import __version__
from aerosolstudio.config.constants import (
    SESSION_SCHEMA_NAME,
    SESSION_SCHEMA_VERSION,
    SESSION_SOFTWARE_NAME,
)
from aerosolstudio.io.json_utils import json_safe

JsonDict = dict[str, Any]


def default_meta() -> JsonDict:
    """Return metadata for a new session payload."""

    return {
        "schema": SESSION_SCHEMA_NAME,
        "schema_version": SESSION_SCHEMA_VERSION,
        "software": SESSION_SOFTWARE_NAME,
        "app_version": __version__,
    }


def _json_safe(value: Any) -> Any:
    """Convert common scientific values into JSON-compatible primitives."""

    return json_safe(value)


def migrate_session_payload(payload: JsonDict) -> JsonDict:
    """Migrate a loaded session payload to the current schema wrapper.

    Existing canonical saves already use a top-level ``meta`` and
    ``instruments`` structure. Older or hand-made payloads that only contain an
    instrument mapping are wrapped without discarding any keys.
    """

    if not isinstance(payload, dict):
        raise TypeError("Session payload must be a dictionary.")

    data = deepcopy(payload)
    if "instruments" not in data:
        data = {"instruments": data}

    meta = default_meta()
    existing_meta = data.get("meta")
    if isinstance(existing_meta, dict):
        meta.update(existing_meta)
    meta.setdefault("schema", SESSION_SCHEMA_NAME)
    meta.setdefault("software", SESSION_SOFTWARE_NAME)
    source_schema_version = "1.0"
    if isinstance(existing_meta, dict):
        source_schema_version = str(
            existing_meta.get("schema_version") or existing_meta.get("version") or "1.0"
        )
    meta["schema_version"] = source_schema_version
    if meta["schema_version"] != SESSION_SCHEMA_VERSION:
        meta["migrated_from_schema_version"] = meta["schema_version"]
        meta["schema_version"] = SESSION_SCHEMA_VERSION

    data["meta"] = meta
    data.setdefault("instruments", {})
    return _json_safe(data)


def validate_session_payload(payload: JsonDict) -> list[str]:
    """Return validation errors for a session payload."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Session payload must be a dictionary."]

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        errors.append("Session payload is missing a metadata dictionary.")
    else:
        if meta.get("schema") != SESSION_SCHEMA_NAME:
            errors.append("Session metadata has an unknown schema name.")
        if not meta.get("schema_version"):
            errors.append("Session metadata is missing schema_version.")

    instruments = payload.get("instruments")
    if not isinstance(instruments, dict):
        errors.append("Session payload is missing an instruments dictionary.")
        return errors

    for instrument_name, instrument in instruments.items():
        if not isinstance(instrument, dict):
            errors.append(f"Instrument {instrument_name!r} must be a dictionary.")
            continue
        polygons = instrument.get("polygons", [])
        if polygons is not None and not isinstance(polygons, list):
            errors.append(f"Instrument {instrument_name!r} polygons must be a list.")
            continue
        for index, polygon in enumerate(polygons or []):
            if not isinstance(polygon, dict):
                errors.append(f"Polygon {index} in {instrument_name!r} must be a dictionary.")
                continue
            if "x" in polygon and not isinstance(polygon["x"], list):
                errors.append(f"Polygon {index} in {instrument_name!r} has non-list x coordinates.")
            if "y" in polygon and not isinstance(polygon["y"], list):
                errors.append(f"Polygon {index} in {instrument_name!r} has non-list y coordinates.")

    return errors


def normalize_session_payload(payload: JsonDict) -> JsonDict:
    """Migrate and validate a payload, raising ``ValueError`` on problems."""

    migrated = migrate_session_payload(payload)
    errors = validate_session_payload(migrated)
    if errors:
        raise ValueError("; ".join(errors))
    return migrated


def dumps_session(payload: JsonDict) -> str:
    """Serialize a session payload with deterministic key ordering."""

    normalized = normalize_session_payload(payload)
    return json.dumps(normalized, indent=2, sort_keys=True, allow_nan=False)


def loads_session(text: str) -> JsonDict:
    """Load, migrate, and validate a session JSON string."""

    return normalize_session_payload(json.loads(text))


def save_session(path: str | Path, payload: JsonDict) -> None:
    """Write a deterministic session JSON file."""

    Path(path).write_text(dumps_session(payload) + "\n", encoding="utf-8")


def load_session(path: str | Path) -> JsonDict:
    """Read, migrate, and validate a session JSON file."""

    return loads_session(Path(path).read_text(encoding="utf-8"))

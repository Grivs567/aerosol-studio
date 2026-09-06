"""Passive cleanup-planning helpers for instrument lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aerosolstudio.state.keys import (
    DISTRIBUTION_RUNTIME_KEY,
    DOCUMENT_CALLBACKS_KEY,
    FIT_RUNTIME_KEY,
    HEATMAP_RUNTIME_KEY,
    OVERLAY_KEY,
    OVERLAY_RUNTIME_KEY,
    POLYGON_RUNTIME_KEY,
    RENDERER_CALLBACKS_KEY,
    TOOL_CALLBACKS_KEY,
    WIDGET_CALLBACKS_KEY,
)


@dataclass(frozen=True)
class CleanupSnapshot:
    """Passive cleanup plan containing references only."""

    renderers: tuple[Any, ...]
    callbacks: tuple[Any, ...]
    overlays: tuple[Any, ...]
    tools: tuple[Any, ...]


def _existing_refs(*refs: Any) -> tuple[Any, ...]:
    return tuple(ref for ref in refs if ref is not None)


def collect_renderer_cleanup_targets(inst: dict[str, Any]) -> tuple[Any, ...]:
    """Collect renderer/runtime references without mutating them."""

    return _existing_refs(
        inst.get(HEATMAP_RUNTIME_KEY),
        inst.get(POLYGON_RUNTIME_KEY),
        inst.get(FIT_RUNTIME_KEY),
        inst.get(DISTRIBUTION_RUNTIME_KEY),
    )


def collect_callback_cleanup_targets(inst: dict[str, Any]) -> tuple[Any, ...]:
    """Collect callback registry references without deregistering them."""

    return _existing_refs(
        inst.get(WIDGET_CALLBACKS_KEY),
        inst.get(RENDERER_CALLBACKS_KEY),
        inst.get(TOOL_CALLBACKS_KEY),
        inst.get(DOCUMENT_CALLBACKS_KEY),
    )


def collect_overlay_cleanup_targets(inst: dict[str, Any]) -> tuple[Any, ...]:
    """Collect overlay references without removing overlays."""

    return _existing_refs(inst.get(OVERLAY_RUNTIME_KEY), inst.get(OVERLAY_KEY))


def collect_tool_cleanup_targets(inst: dict[str, Any]) -> tuple[Any, ...]:
    """Collect tool lifecycle references without unregistering tools."""

    return _existing_refs(inst.get(TOOL_CALLBACKS_KEY))


def build_cleanup_snapshot(inst: dict[str, Any]) -> CleanupSnapshot:
    """Build a passive cleanup snapshot for diagnostics."""

    return CleanupSnapshot(
        renderers=collect_renderer_cleanup_targets(inst),
        callbacks=collect_callback_cleanup_targets(inst),
        overlays=collect_overlay_cleanup_targets(inst),
        tools=collect_tool_cleanup_targets(inst),
    )

"""Passive lifecycle ownership containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RendererLifecycleGroup:
    """Renderer/runtime references owned by an instrument."""

    heatmap: Any = None
    polygon: Any = None
    fit: Any = None
    distribution: Any = None


@dataclass(frozen=True)
class CallbackLifecycleGroup:
    """Callback registry references owned by an instrument."""

    widget: Any = None
    renderer: Any = None
    tool: Any = None
    document: Any = None


@dataclass(frozen=True)
class OverlayLifecycleGroup:
    """Overlay references owned by an instrument."""

    runtime: Any = None
    overlays: Any = None


@dataclass(frozen=True)
class ToolLifecycleGroup:
    """Tool callback and figure-event references owned by an instrument."""

    callbacks: Any = None


@dataclass(frozen=True)
class InstrumentLifecycleRuntime:
    """Passive lifecycle ownership map for one instrument."""

    name: str
    renderers: RendererLifecycleGroup
    callbacks: CallbackLifecycleGroup
    overlays: OverlayLifecycleGroup
    tools: ToolLifecycleGroup

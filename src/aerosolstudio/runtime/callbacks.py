"""Passive callback runtime containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CallbackReference:
    """A passive reference to an already-registered callback."""

    owner: Any
    event: str
    callback: Any
    label: str = ""
    lifecycle: str = ""


@dataclass(frozen=True)
class WidgetCallbackRuntime:
    """Widget callback references grouped by lifecycle."""

    callbacks: tuple[CallbackReference, ...] = ()


@dataclass(frozen=True)
class RendererCallbackRuntime:
    """Renderer/model callback references grouped by lifecycle."""

    callbacks: tuple[CallbackReference, ...] = ()


@dataclass(frozen=True)
class DocumentCallbackRuntime:
    """Document-level callback references grouped by lifecycle."""

    callbacks: tuple[CallbackReference, ...] = ()


@dataclass(frozen=True)
class ToolCallbackRuntime:
    """Tool and figure-event callback references grouped by lifecycle."""

    callbacks: tuple[CallbackReference, ...] = ()

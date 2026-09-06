"""Pure helpers for passive callback registries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aerosolstudio.runtime.callbacks import (
    CallbackReference,
    DocumentCallbackRuntime,
    RendererCallbackRuntime,
    ToolCallbackRuntime,
    WidgetCallbackRuntime,
)


def _reference(
    owner: Any,
    event: str,
    callback: Any,
    *,
    label: str = "",
    lifecycle: str = "",
) -> CallbackReference:
    return CallbackReference(
        owner=owner,
        event=event,
        callback=callback,
        label=label,
        lifecycle=lifecycle,
    )


def register_widget_callback(
    callbacks: Sequence[CallbackReference],
    owner: Any,
    event: str,
    callback: Any,
    *,
    label: str = "",
    lifecycle: str = "",
) -> tuple[CallbackReference, ...]:
    """Return a new passive widget-callback registry tuple."""

    return (*callbacks, _reference(owner, event, callback, label=label, lifecycle=lifecycle))


def register_renderer_callback(
    callbacks: Sequence[CallbackReference],
    owner: Any,
    event: str,
    callback: Any,
    *,
    label: str = "",
    lifecycle: str = "",
) -> tuple[CallbackReference, ...]:
    """Return a new passive renderer/model-callback registry tuple."""

    return (*callbacks, _reference(owner, event, callback, label=label, lifecycle=lifecycle))


def register_tool_callback(
    callbacks: Sequence[CallbackReference],
    owner: Any,
    event: str,
    callback: Any,
    *,
    label: str = "",
    lifecycle: str = "",
) -> tuple[CallbackReference, ...]:
    """Return a new passive tool-callback registry tuple."""

    return (*callbacks, _reference(owner, event, callback, label=label, lifecycle=lifecycle))


def group_callbacks(
    *,
    widget: Iterable[CallbackReference] = (),
    renderer: Iterable[CallbackReference] = (),
    tool: Iterable[CallbackReference] = (),
    document: Iterable[CallbackReference] = (),
) -> Mapping[str, Any]:
    """Group passive callback references into runtime containers."""

    return {
        "widget": WidgetCallbackRuntime(tuple(widget)),
        "renderer": RendererCallbackRuntime(tuple(renderer)),
        "tool": ToolCallbackRuntime(tuple(tool)),
        "document": DocumentCallbackRuntime(tuple(document)),
    }


def snapshot_callback_registry(runtime: Any) -> tuple[dict[str, str], ...]:
    """Return a serializable diagnostic snapshot without invoking callbacks."""

    callbacks = getattr(runtime, "callbacks", runtime)
    return tuple(
        {
            "owner_type": type(ref.owner).__name__,
            "event": ref.event,
            "callback_name": getattr(ref.callback, "__name__", type(ref.callback).__name__),
            "label": ref.label,
            "lifecycle": ref.lifecycle,
        }
        for ref in callbacks
    )

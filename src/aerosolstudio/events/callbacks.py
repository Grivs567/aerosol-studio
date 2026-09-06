"""Deferred callback seam.

Construction code declares widget/model callbacks against this seam instead of
calling ``widget.on_change`` (etc.) directly inline. Registrations are recorded
as plain data -- inspectable for parity checks -- and bound to the real Bokeh
objects later via :meth:`CallbackSeam.bind`.

This module imports neither Bokeh nor the application controller. ``bind()`` duck-types the
target's ``on_change`` / ``on_event`` / ``on_click`` methods, so the seam is
fully unit testable with fakes and stays importable without the monolith. This
replaces the inline registrations in ``create_instrument_entry`` (figure range
callbacks, mode toggles, fit-type UI callback) with a port the factory can use
without closing over the monolith ``self``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CHANGE = "change"
EVENT = "event"
CLICK = "click"


@dataclass(frozen=True)
class CallbackRegistration:
    """One recorded, not-yet-bound callback registration.

    ``kind`` is one of ``"change"``, ``"event"`` or ``"click"``. ``trigger`` is
    the changed attribute name for ``change``, the Bokeh event for ``event``,
    and ``None`` for ``click``.
    """

    kind: str
    target: Any
    handler: Callable[..., Any]
    trigger: Any = None
    label: str = ""


class CallbackSeam:
    """Collect callback registrations, then bind them to real objects once."""

    def __init__(self) -> None:
        self._registrations: list[CallbackRegistration] = []
        self._bound = False

    def on_change(self, target: Any, attr: str, handler: Callable[..., Any], *, label: str = "") -> None:
        """Record a ``target.on_change(attr, handler)`` registration."""
        self._record(CHANGE, target, handler, attr, label)

    def on_event(self, target: Any, event: Any, handler: Callable[..., Any], *, label: str = "") -> None:
        """Record a ``target.on_event(event, handler)`` registration."""
        self._record(EVENT, target, handler, event, label)

    def on_click(self, target: Any, handler: Callable[..., Any], *, label: str = "") -> None:
        """Record a ``target.on_click(handler)`` registration."""
        self._record(CLICK, target, handler, None, label)

    def _record(self, kind: str, target: Any, handler: Callable[..., Any], trigger: Any, label: str) -> None:
        if self._bound:
            raise RuntimeError("CallbackSeam already bound; cannot record new callbacks")
        self._registrations.append(CallbackRegistration(kind, target, handler, trigger, label))

    @property
    def registrations(self) -> tuple[CallbackRegistration, ...]:
        """Return an immutable snapshot of recorded registrations."""
        return tuple(self._registrations)

    @property
    def bound(self) -> bool:
        """Whether :meth:`bind` has already run."""
        return self._bound

    def __len__(self) -> int:
        return len(self._registrations)

    def bind(self) -> int:
        """Attach every recorded registration to its target; idempotent guard.

        Returns the number of callbacks bound. Raises if called twice.
        """
        if self._bound:
            raise RuntimeError("CallbackSeam already bound")
        for registration in self._registrations:
            if registration.kind == CHANGE:
                registration.target.on_change(registration.trigger, registration.handler)
            elif registration.kind == EVENT:
                registration.target.on_event(registration.trigger, registration.handler)
            elif registration.kind == CLICK:
                registration.target.on_click(registration.handler)
            else:  # pragma: no cover - kind is set internally only
                raise ValueError(f"Unknown callback kind: {registration.kind!r}")
        self._bound = True
        return len(self._registrations)

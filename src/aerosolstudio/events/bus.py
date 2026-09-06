"""Minimal synchronous in-process event bus.

Handlers subscribe by exact event type and are invoked in registration order
when a matching event is emitted. The bus is Bokeh-free and has no app or
instrument dependencies, so it is unit testable and importable without the
monolith.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, TypeVar

E = TypeVar("E")


class EventBus:
    """Dispatch events to type-keyed handlers in registration order."""

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Register ``handler`` for ``event_type``; duplicate handlers are ignored."""
        handlers = self._subscribers[event_type]
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """Remove ``handler`` from ``event_type``; a no-op if it is not registered."""
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def emit(self, event: Any) -> int:
        """Invoke every handler registered for ``type(event)``.

        Returns the number of handlers invoked. Handlers run in registration
        order against a snapshot, so a handler may safely (un)subscribe during
        dispatch without affecting the current emission.
        """
        handlers = list(self._subscribers.get(type(event), ()))
        for handler in handlers:
            handler(event)
        return len(handlers)

    def subscriber_count(self, event_type: type) -> int:
        """Return the number of handlers registered for ``event_type``."""
        return len(self._subscribers.get(event_type, ()))

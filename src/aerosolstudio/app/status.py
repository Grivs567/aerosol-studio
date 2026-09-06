"""App-owned status output service.

Owns the single status ``Div`` (the monolith's ``system_div``) and turns
:class:`~aerosolstudio.events.types.StatusMessage` notifications into text
updates. Instrument-side code never touches the Div directly: it emits a
``StatusMessage`` on the event bus or calls an injected :class:`StatusSink`.

The service duck-types ``status_div.text``, so it is testable with a fake and
does not require Bokeh at import time.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aerosolstudio.events.bus import EventBus
from aerosolstudio.events.types import StatusMessage


@runtime_checkable
class StatusSink(Protocol):
    """Interface instrument-side code may receive to report status."""

    def notify(self, message: StatusMessage) -> None: ...


class AppStatusService:
    """Render :class:`StatusMessage` notifications into the status ``Div``."""

    def __init__(self, status_div: Any) -> None:
        self._div = status_div
        self._last: StatusMessage | None = None

    def notify(self, message: StatusMessage) -> None:
        """Write ``message`` to the status Div and remember it as the last one."""
        self._div.text = message.html
        self._last = message

    @property
    def last_message(self) -> StatusMessage | None:
        """The most recently rendered message, or ``None`` before any."""
        return self._last

    def subscribe_to(self, bus: EventBus) -> None:
        """Subscribe this service to ``StatusMessage`` events on ``bus``."""
        bus.subscribe(StatusMessage, self.notify)

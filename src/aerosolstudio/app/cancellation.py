"""App-owned fit cancellation token.

Replaces the monolith's bare ``cancel_flag = threading.Event()``. The app
controller owns one :class:`FitCancellationToken` and injects it into fit
orchestration; fit code only reads :meth:`is_requested` and never reaches into
app internals. The read-only cancellation protocol lives in
``aerosolstudio.fitting.types`` so fitting code can depend on it without
importing the ``app`` package.
"""

from __future__ import annotations

import threading


class FitCancellationToken:
    """Thread-safe cancellation flag owned by the app controller."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        """Signal that the running fit should stop after the current step."""
        self._event.set()

    def reset(self) -> None:
        """Clear the cancellation signal before starting a new fit."""
        self._event.clear()

    def is_requested(self) -> bool:
        """Whether cancellation has been requested and not yet reset."""
        return self._event.is_set()

"""Cross-concern event types for the in-process event bus.

These are plain, Bokeh-free dataclasses. New event types are added here as the
emitters that produce them are ported into package modules. The first stage of
the package migration introduces only the status channel; later steps add the
data/ROI/fit/link events described in the target design.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StatusLevel(str, Enum):  # noqa: UP042
    """Severity of a status message destined for the app status area."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class StatusMessage:
    """A status notification for the app status area (monolith ``system_div``).

    ``html`` is the pre-rendered message body. ``level`` lets the status owner
    decide styling without the emitter touching any widget.
    """

    html: str
    level: StatusLevel = StatusLevel.INFO

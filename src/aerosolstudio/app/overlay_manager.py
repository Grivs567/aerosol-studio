"""Package-owned overlay-line lifecycle management.

Extracted from ``app/studio.py``, which still owns the surrounding app
wiring: choosing which callbacks an overlay line's buttons trigger, adding/
removing controls from the instrument dict, export, save/restore, colors,
and status messages. This module owns only the pieces mechanical enough not
to need any of that - starting with ID allocation here; add/remove, export,
and save/restore logic are intended to move here in later passes, followed
by the overlay UI container/button creation itself (see the per-instrument
extraction pattern already established by ``instrument/heatmap_controls.py``
and ``instrument/strip_controls.py`` for what that end state should look
like - this module is the same treatment for the overlay section).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["next_overlay_var_id"]


def next_overlay_var_id(existing_lines: Sequence[Mapping[str, object]], prefix: str = "var") -> str:
    """Return the next unused ``"{prefix}_{N}"`` id for a new overlay line.

    ``existing_lines`` takes the same list-of-dicts shape already used by
    ``inst["overlay_var_lines"]`` (each entry has a ``"line_id"`` key, from
    ``OverlayVarLine.as_state()``) rather than a bare set of ids, so callers
    can pass that list straight through with no pre-extraction.

    ``prefix`` defaults to ``"var"``, matching what this same allocation
    loop already used inline in ``studio.py`` before this extraction (this
    module changes where the logic lives, not what it does). Line ids are
    never read back out of saved ROI files on restore - a restored line
    always gets a freshly allocated id here, same as a brand new one - so
    changing the prefix, if that's ever wanted, has no backward-
    compatibility effect on old saved sessions either way.
    """

    used_ids = {line.get("line_id") for line in existing_lines}
    n = 0
    while f"{prefix}_{n}" in used_ids:
        n += 1
    return f"{prefix}_{n}"

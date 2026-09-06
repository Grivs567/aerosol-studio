"""Package-owned application controller.

This module is the migration target for runtime behavior currently implemented
in the application controller. It owns an increasing share of GUI construction,
callback registration, and lifecycle management as the migration proceeds.

Current ownership:
  - LoaderOverlay (fit progress overlay + cancel button)
  - SidebarToggle (sidebar visibility button + layout mutation)

Not yet owned (still in monolith):
  - AerosolStudio.__init__ / create_widgets / setup_layout
  - Instrument creation, callbacks, tabs, session save/load
"""

from __future__ import annotations

from typing import Any

from aerosolstudio.app.cancellation import FitCancellationToken
from aerosolstudio.app.loader import LoaderOverlay
from aerosolstudio.app.sidebar import SidebarToggle


class AerosolStudioApp:
    """Runtime controller for Aerosol Studio.

    Instantiate this class to obtain package-owned runtime components.
    During migration, the main controller creates one instance and delegates
    the owned behaviors to it instead of implementing them inline.
    """

    def __init__(self, theme: dict[str, Any]) -> None:
        self._theme = theme
        self.cancel_flag = FitCancellationToken()
        self.loader: LoaderOverlay | None = None
        self.sidebar_toggle: SidebarToggle | None = None

    def create_loader(self, on_cancel) -> LoaderOverlay:
        """Create and return the fit-progress overlay owned by this app.

        The caller is responsible for placing ``loader.div`` and
        ``loader.cancel_btn`` in the Bokeh document layout.

        Args:
            on_cancel: Callback bound to the cancel button's on_click handler.

        Returns:
            The constructed LoaderOverlay instance.
        """
        self.loader = LoaderOverlay(self._theme, self.cancel_flag, on_cancel)
        return self.loader

    def create_sidebar_toggle(self, on_toggle) -> SidebarToggle:
        """Create and return the package-owned sidebar visibility control."""
        self.sidebar_toggle = SidebarToggle(on_toggle)
        return self.sidebar_toggle

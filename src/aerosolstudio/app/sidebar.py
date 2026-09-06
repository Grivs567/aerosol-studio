"""Package-owned sidebar visibility control."""

from __future__ import annotations

from typing import Any

from bokeh.models import Button, Div


class SidebarToggle:
    """Own the sidebar toggle button and its layout mutation behavior."""

    def __init__(self, on_toggle) -> None:
        self.visible = True
        self.button = Button(label="Hide Panel", button_type="light", width=110)
        self.button.on_click(on_toggle)

    @staticmethod
    def _is_resizer(child: Any) -> bool:
        return hasattr(child, "text") and "sidebar-resizer" in getattr(child, "text", "")

    def toggle(self, main_row: Any, sidebar: Any) -> None:
        """Remove or restore the sidebar and its resize handle."""
        if main_row is None:
            return

        content = [
            child
            for child in list(main_row.children)
            if child is not sidebar and not self._is_resizer(child)
        ]
        if self.visible:
            main_row.children = content
            self.button.label = "Show Panel"
            self.visible = False
            return

        resizer = Div(
            text='<div id="sidebar-resizer" class="sidebar-resizer"></div>',
            width=5,
            height=0,
            sizing_mode="stretch_height",
        )
        main_row.children = [sidebar, resizer, *content]
        self.button.label = "Hide Panel"
        self.visible = True

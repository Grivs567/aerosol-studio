"""Loader overlay component.

Owns the fit-progress overlay Div and cancel Button.
Has no dependency on instrument state.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bokeh.models import Button, Div

from aerosolstudio.app.cancellation import FitCancellationToken


class LoaderOverlay:
    """Self-contained fit-progress overlay.

    Creates and owns the loader Div and cancel Button.
    The caller is responsible for placing ``self.div`` and ``self.cancel_btn``
    in the Bokeh document layout.

    Args:
        theme: The application theme dict (keys: accent, border, text, text_secondary).
        cancel_flag: The shared FitCancellationToken that fit threads poll via
            is_requested().
        on_cancel: Callback wired to the cancel button's on_click handler.
    """

    _PROGRESS_START = "<!-- loader-progress-start -->"
    _PROGRESS_END = "<!-- loader-progress-end -->"

    def __init__(
        self,
        theme: dict[str, Any],
        cancel_flag: FitCancellationToken,
        on_cancel: Callable,
    ) -> None:
        self._theme = theme
        self.cancel_flag = cancel_flag

        self.cancel_btn = Button(
            label="Stop Fit",
            button_type="danger",
            width=180,
            height=40,
            visible=False,
            styles={"font-size": "14px", "font-weight": "700"},
        )
        self.cancel_btn.on_click(on_cancel)

        self.div = Div(
            text="",
            sizing_mode="stretch_both",
            styles={
                "position": "fixed",
                "top": "0",
                "left": "0",
                "z-index": "9999",
                "pointer-events": "none",
            },
        )

    def show(self, message: str = "Processing...", submessage: str = "Please wait") -> None:
        """Display the overlay and reset the cancellation flag."""
        t = self._theme
        self.cancel_flag.reset()
        self.div.text = f"""
        <div id="loader-overlay" style="
            position:fixed; top:0; left:0; width:100%; height:calc(100% - 56px);
            background:rgba(30,45,61,0.72);
            z-index:9999; display:flex;
            justify-content:center; align-items:center; flex-direction:column;
            backdrop-filter:blur(5px);
        ">
            <div style="
                background:#ffffff;
                padding:28px 36px;
                border-radius:12px;
                box-shadow:0 8px 32px rgba(0,114,178,0.18), 0 2px 8px rgba(0,0,0,0.12);
                text-align:center;
                border-top:4px solid {t['accent']};
                min-width:260px;
            ">
                <div style="
                    width:44px; height:44px;
                    border:4px solid {t['border']};
                    border-top:4px solid {t['accent']};
                    border-radius:50%;
                    margin:0 auto 18px;
                    animation:spin 0.85s linear infinite;
                "></div>
                <div style="color:{t['text']}; font-size:15px;
                             font-weight:600; margin-bottom:6px;">{message}</div>
                <div style="color:{t['text_secondary']}; font-size:12px;
                             margin-bottom:18px;">{submessage}</div>
                {self._PROGRESS_START}
                <div style="color:{t['text_secondary']}; font-size:11px;"></div>
                {self._PROGRESS_END}
            </div>
        </div>
        <style>
            @keyframes spin {{ 0%{{transform:rotate(0deg);}} 100%{{transform:rotate(360deg);}} }}
        </style>
        """
        self.cancel_btn.visible = True
        self.cancel_btn.label = "Stop Fit"

    def update_progress(self, message: str) -> None:
        """Replace the live progress line without rebuilding the full overlay."""
        start = self._PROGRESS_START
        end = self._PROGRESS_END
        if start not in self.div.text or end not in self.div.text:
            return
        t = self._theme
        before, remainder = self.div.text.split(start, 1)
        _old, after = remainder.split(end, 1)
        progress = (
            f'<div style="color:{t["text_secondary"]}; font-size:11px;">'
            f"{message}</div>"
        )
        self.div.text = before + start + progress + end + after

    def hide(self) -> None:
        """Clear the overlay and hide the cancel button."""
        self.div.text = ""
        self.cancel_btn.visible = False
        self.cancel_btn.label = "Stop Fit"

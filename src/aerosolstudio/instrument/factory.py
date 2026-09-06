"""Structural instrument factory boundary.

This is the first Stage 4 slice: it does not build Bokeh panels and does not
wire into the monolith. It proves the future factory can consume fit display
metadata from ``fitting.types`` and callback registrations through the callback
seam without importing monolith runtime or fit engines.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aerosolstudio.events.callbacks import CallbackSeam
from aerosolstudio.fitting.types import FIT_TYPE_DISPLAY_METADATA, FIT_TYPE_METADATA
from aerosolstudio.instrument.state import STATE_KEY_GROUPS, InstrumentState


@dataclass(frozen=True)
class FitOptionSpec:
    """Bokeh-free fit option data needed by the future fit method selector."""

    key: str
    display_name: str
    button_type: str
    color: str


@dataclass(frozen=True)
class InstrumentSpec:
    """Structural output from the package-owned factory boundary."""

    name: str
    file_type: str
    known_state_keys: frozenset[str]
    state_groups: tuple[StateGroupSpec, ...]
    callback_specs: tuple[FactoryCallbackSpec, ...]
    fit_options: tuple[FitOptionSpec, ...]
    default_fit_key: str
    default_badge_color: str
    callback_labels: tuple[str, ...]


@dataclass(frozen=True)
class StateGroupSpec:
    """Named group of legacy-compatible state keys owned by the factory."""

    name: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class FactoryCallbackSpec:
    """Bokeh-free description of one inline construction callback."""

    label: str
    kind: str
    target_key: str
    trigger: str | None = None


FACTORY_CALLBACK_SPECS: tuple[FactoryCallbackSpec, ...] = (
    FactoryCallbackSpec("palette-select-value", "change", "pal_select", "value"),
    FactoryCallbackSpec("color-limit-low-value", "change", "clim_low", "value"),
    FactoryCallbackSpec("color-limit-high-value", "change", "clim_high", "value"),
    FactoryCallbackSpec("browse-file-click", "click", "browse_btn"),
    FactoryCallbackSpec("path-input-value", "change", "path_input", "value"),
    FactoryCallbackSpec("load-file-click", "click", "load_btn"),
    FactoryCallbackSpec("colorbar-toggle-active", "change", "cb_toggle", "active"),
    FactoryCallbackSpec("mode-toggle-active", "change", "toggle_modes", "active"),
    FactoryCallbackSpec("sum-toggle-active", "change", "toggle_sum", "active"),
    FactoryCallbackSpec("poly-source-data", "change", "poly_src", "data"),
    FactoryCallbackSpec("heatmap-tap", "event", "fig", "tap"),
    FactoryCallbackSpec("finish-poly-doubletap", "event", "fig", "DoubleTap"),
    FactoryCallbackSpec("finish-rect-panend", "event", "fig", "PanEnd"),
    FactoryCallbackSpec("roi-box-selection", "event", "fig", "SelectionGeometry"),
    FactoryCallbackSpec("heatmap-range-start", "change", "fig.x_range", "start"),
    FactoryCallbackSpec("heatmap-range-end", "change", "fig.x_range", "end"),
    FactoryCallbackSpec("fit-type-select-value", "change", "fit_type_select", "value"),
    FactoryCallbackSpec("run-fit-click", "click", "btn_fit"),
    FactoryCallbackSpec("clear-fit-click", "click", "btn_clear"),
    FactoryCallbackSpec("growth-polygon-select-value", "change", "fit_line_poly_raw", "value"),
    FactoryCallbackSpec("fit-line-click", "click", "btn_fit_line"),
    FactoryCallbackSpec("growth-clear-click", "click", "reset_btn"),
    FactoryCallbackSpec("heatmap-reset", "event", "fig", "Reset"),
    FactoryCallbackSpec("add-overlay-click", "click", "btn_add_overlay_var"),
    FactoryCallbackSpec("polygon-label-click", "click", "btn_update_label"),
    FactoryCallbackSpec("plot-strip-click", "click", "btn_plot_strip"),
    FactoryCallbackSpec("fit-checkboxes-active", "change", "fit_checkboxes", "active"),
)


class InstrumentFactory:
    """Create structural instrument specs before Bokeh model construction moves."""

    def __init__(
        self,
        *,
        fit_display_metadata: Mapping[str, Mapping[str, str]] = FIT_TYPE_DISPLAY_METADATA,
        full_fit_metadata: Mapping[str, Mapping[str, Any]] = FIT_TYPE_METADATA,
        callback_seam: CallbackSeam | None = None,
    ) -> None:
        self._fit_display_metadata = fit_display_metadata
        self._full_fit_metadata = full_fit_metadata
        self._callback_seam = callback_seam

    def fit_options(self) -> tuple[FitOptionSpec, ...]:
        """Return selector-ready fit options from ``fitting.types`` metadata."""

        return tuple(
            FitOptionSpec(
                key=key,
                display_name=metadata["display_name"],
                button_type=metadata["button_type"],
                color=metadata["color"],
            )
            for key, metadata in self._fit_display_metadata.items()
        )

    def build_spec(self, name: str, file_type: str) -> InstrumentSpec:
        """Build a Bokeh-free structural spec for one instrument."""

        options = self.fit_options()
        default_key = options[0].key if options else ""
        labels = tuple(registration.label for registration in self._callback_seam.registrations) if self._callback_seam else ()
        return InstrumentSpec(
            name=name,
            file_type=file_type,
            known_state_keys=self.expected_state_keys(),
            state_groups=self.state_group_specs(),
            callback_specs=self.callback_specs(),
            fit_options=options,
            default_fit_key=default_key,
            default_badge_color=self._fit_display_metadata[default_key]["color"] if default_key else "",
            callback_labels=labels,
        )

    def state_group_specs(self) -> tuple[StateGroupSpec, ...]:
        """Return structural groups corresponding to ``create_instrument_entry`` state."""

        return tuple(StateGroupSpec(name=name, keys=tuple(keys)) for name, keys in STATE_KEY_GROUPS.items())

    def callback_specs(self) -> tuple[FactoryCallbackSpec, ...]:
        """Return Bokeh-free callback specs for inline construction callbacks."""

        return FACTORY_CALLBACK_SPECS

    def expected_state_keys(self) -> frozenset[str]:
        """Return static plus dynamic source keys needed by legacy-compatible state."""

        keys = set(InstrumentState.all_known_keys())
        for metadata in self._full_fit_metadata.values():
            for field in ("src_suffix", "dist_src_suffix"):
                value = metadata.get(field)
                if isinstance(value, str):
                    keys.add(value)
        return frozenset(keys)

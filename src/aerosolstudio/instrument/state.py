"""Structural per-instrument state container.

This module is additive: the monolith still owns runtime behavior and still
uses its legacy ``inst`` dictionaries. ``InstrumentState`` is the package-owned
shape that can hold that state without importing the monolith or Bokeh app
controllers.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

STATE_KEY_GROUPS: dict[str, tuple[str, ...]] = {
    "heatmap_view": (
        "fig",
        "pointer_info_div",
        "mapper",
        "colorbar",
        "cb_toggle",
        "cb_toggle_",
        "pal_select",
        "clim_low",
        "clim_high",
        "heatmap_view_select",
        "src_img",
        "_heatmap_refresh_pending",
        "img_renderer",
    ),
    "data_loading": (
        "df",
        "type",
        "path_input",
        "browse_btn",
        "tz_input",
        "diam_unit_input",
        "data_type_input",
        "load_btn",
    ),
    "distribution": (
        "src_dist",
        "fig_dist",
        "mode_multi_src",
        "mode_sum_src",
        "mode_sum_line",
        "mode_fit_renderer",
        "toggle_modes",
        "toggle_sum",
        "toggle_modes_",
        "toggle_sum_",
    ),
    "roi": (
        "poly_src",
        "poly_bg_src",
        "rect_src",
        "rect_draw_tool",
        "roi_box_tool",
        "_last_rect_roi_signature",
        "polygons",
        "selected_poly",
        "mask_src",
    ),
    "fit_controls_state": (
        "fit_type_select",
        "fit_badge",
        "btn_fit",
        "btn_fit_",
        "btn_clear",
        "btn_clear_",
        "fit_renderers",
        "fit_types",
        "results_div",
        "undo_stack",
    ),
    "overlay": (
        "overlay_var_lines",
        "overlay_var_container",
        "btn_add_overlay_var",
        "btn_add_overlay_var_",
    ),
    "growth_rate_lines": (
        "fit_line_source",
        "fit_line_source_raw",
        "fit_line_poly",
        "fit_line_srcs",
        "fit_line_renderers",
        "fit_dp_controls",
        "fit_dmin_input",
        "fit_dmax_input",
        "btn_fit_line_",
        "btn_fit_line",
        "reset_btn",
        "fit_line_poly_raw",
        "mcc_results",
    ),
    "polygon_label_widgets": (
        "btn_update_label",
        "poly_label_input",
    ),
    "strip_plot": (
        "fig_strip",
        "src_strip_raw",
        "src_strip_fit",
        "src_strip_point",
        "strip_diameter_input",
        "btn_plot_strip",
        "chk_show_fit",
        "chk_follow_cursor",
        "fit_checkboxes",
        "fit_overlay_legend",
        "src_strip_fits",
        "src_strip_points",
        "poly_span",
        "fit_checkbox_keys",
        "strip_time_marker",
    ),
}


def _dynamic_fit_source_keys(inst: Mapping[str, Any]) -> tuple[str, ...]:
    fit_types = inst.get("fit_types", {}) or {}
    keys: list[str] = []
    for props in fit_types.values():
        if isinstance(props, Mapping):
            for field in ("src_suffix", "dist_src_suffix"):
                value = props.get(field)
                if isinstance(value, str):
                    keys.append(value)
    return tuple(keys)


@dataclass
class InstrumentState:
    """Structural owner for one instrument's state.

    Step 3a keeps this as a faithful container only. Behavior-heavy methods
    raise with citations to the current monolith owner until those behaviors are
    ported in later migration steps.
    """

    name: str
    file_type: str
    _state: MutableMapping[str, Any] = field(default_factory=dict)
    _root_panel: Any = None
    _destroyed: bool = False

    @classmethod
    def from_legacy_dict(
        cls,
        inst: Mapping[str, Any],
        *,
        name: str = "",
        root_panel: Any = None,
    ) -> InstrumentState:
        """Wrap a legacy monolith inst dict without mutating it.

        The copy is shallow: Bokeh models, sources, lists, and dicts retain
        identity so parity tests can prove no runtime object was dropped.
        """

        return cls(
            name=name,
            file_type=str(inst.get("type", "")),
            _state=dict(inst),
            _root_panel=root_panel,
        )

    @classmethod
    def bind_live(
        cls,
        inst: MutableMapping[str, Any],
        *,
        name: str = "",
        root_panel: Any = None,
    ) -> InstrumentState:
        """Bind an InstrumentState to a live monolith inst dict by reference.

        Unlike ``from_legacy_dict()``, this path intentionally keeps the exact
        mapping object so writes remain visible to existing monolith readers
        during incremental runtime wiring.
        """

        return cls(
            name=name,
            file_type=str(inst.get("type", "")),
            _state=inst,
            _root_panel=root_panel,
        )

    @property
    def data_frame(self) -> Any:
        return self._state.get("df")

    @property
    def root_panel(self) -> Any:
        return self._root_panel

    @property
    def heatmap_figure(self) -> Any:
        return self._state.get("fig")

    @property
    def distribution_figure(self) -> Any:
        return self._state.get("fig_dist")

    @property
    def strip_figure(self) -> Any:
        return self._state.get("fig_strip")

    @property
    def selected_polygon_index(self) -> int | None:
        selected = self._state.get("selected_poly")
        return selected if isinstance(selected, int) or selected is None else None

    @property
    def legacy_state(self) -> Mapping[str, Any]:
        """Read-only view by convention of the held legacy state mapping."""

        return self._state

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    @staticmethod
    def all_known_keys() -> frozenset[str]:
        """Return every static legacy inst key covered by the design groups."""

        return frozenset(key for keys in STATE_KEY_GROUPS.values() for key in keys)

    def grouped_keys(self) -> dict[str, tuple[str, ...]]:
        """Return held keys classified by the design's state table groups."""

        groups = {name: tuple(key for key in keys if key in self._state) for name, keys in STATE_KEY_GROUPS.items()}
        dynamic_keys = tuple(key for key in _dynamic_fit_source_keys(self._state) if key in self._state)
        groups["fit_and_distribution_sources"] = dynamic_keys
        known = {key for keys in groups.values() for key in keys}
        groups["extra"] = tuple(key for key in self._state if key not in known)
        return groups

    def missing_design_keys(self) -> dict[str, tuple[str, ...]]:
        """Return design-table keys absent from this state."""

        return {
            group: tuple(key for key in keys if key not in self._state)
            for group, keys in STATE_KEY_GROUPS.items()
            if any(key not in self._state for key in keys)
        }

    def set_loaded_data(self, df: Any, *, path: str | None = None) -> None:
        self._state["df"] = df
        if path is not None:
            self._state["loaded_path"] = path

    def update_heatmap(self, df: Any) -> None:
        # Current owner: update_image at studio.py:2011-2074.
        raise NotImplementedError("Heatmap update behavior remains in studio.py:2011-2074")

    def set_color_limits(self, low: float, high: float, palette: str) -> None:
        # Current owner: heatmap control callbacks at heatmap_controls.py:210-236.
        raise NotImplementedError("Color-limit behavior remains in heatmap_controls.py:210-236")

    def add_polygon(self, polygon: dict[str, Any], *, select: bool = True) -> int:
        polygons = self._state.setdefault("polygons", [])
        polygons.append(polygon)
        index = len(polygons) - 1
        if select:
            self._state["selected_poly"] = index
        return index

    def delete_selected_polygon(self) -> None:
        # Current owner: on_keypress delete block at studio.py:2810-2932.
        raise NotImplementedError("ROI delete behavior remains in studio.py:2810-2932")

    def undo_last_delete(self) -> bool:
        # Current owner: on_keypress undo block at studio.py:2880-2920.
        raise NotImplementedError("ROI undo behavior remains in studio.py:2880-2920")

    def select_polygon(self, index: int | None) -> None:
        self._state["selected_poly"] = index

    def rename_selected_polygon(self, label: str) -> None:
        selected = self.selected_polygon_index
        polygons = self._state.get("polygons") or []
        if selected is None or selected < 0 or selected >= len(polygons):
            return
        polygons[selected]["label"] = label

    def clear_growth_line(self, fit_key: str | None = None) -> None:
        # Current owner: clear_fit_line at studio.py:1372-1406.
        raise NotImplementedError("Growth-line clearing remains in studio.py:1372-1406")

    def restore_growth_lines(self) -> None:
        # Current owner: _restore_growth_rate_lines at studio.py:1873-1909.
        raise NotImplementedError("Growth-line restoration remains in studio.py:1873-1909")

    def add_overlay(self) -> str:
        # Current owner: add_overlay_var_line at studio.py:2321-2365.
        raise NotImplementedError("Overlay creation remains in studio.py:2321-2365")

    def remove_overlay(self, line_id: str) -> None:
        # Current owner: _remove_overlay_var_line at studio.py:2419-2438.
        raise NotImplementedError("Overlay removal remains in studio.py:2419-2438")

    def serialize_overlays(self) -> list[dict[str, Any]]:
        # Current owner: _serialize_var_overlays at studio.py:3879-3899.
        raise NotImplementedError("Overlay serialization remains in studio.py:3879-3899")

    def restore_overlays(self, payload: list[dict[str, Any]]) -> None:
        # Current owner: _restore_var_overlays at studio.py:3899-3924.
        raise NotImplementedError("Overlay restoration remains in studio.py:3899-3924")

    def update_distribution_at(self, x_ms: float) -> None:
        # Current owner: update_dists at studio.py:3515-3556.
        raise NotImplementedError("Distribution update remains in studio.py:3515-3556")

    def update_distribution_fit_markers(self, x_ms: float) -> None:
        # Current owner: update_dist_glyphs at studio.py:3456-3515.
        raise NotImplementedError("Distribution fit-marker update remains in studio.py:3456-3515")

    def update_strip_plot(self) -> None:
        # Current owner: update_strip_plot at studio.py:2494-2627.
        raise NotImplementedError("Strip plot update remains in studio.py:2494-2627")

    def serialize_session(self) -> dict[str, Any]:
        # Current owner: save_rois at studio.py:3924-4018.
        raise NotImplementedError("Session serialization remains in studio.py:3924-4018")

    def restore_session(self, payload: dict[str, Any]) -> None:
        # Current owner: load_rois at studio.py:4018-4201.
        raise NotImplementedError("Session restoration remains in studio.py:4018-4201")

    def destroy(self) -> None:
        self._destroyed = True


def live_instrument_state(
    inst: MutableMapping[str, Any],
    *,
    name: str = "",
    root_panel: Any = None,
) -> InstrumentState:
    """Return a live-bound InstrumentState for a monolith inst dict.

    This is the runtime accessor used during incremental wiring. It preserves
    the original dict object so migrated readers and legacy readers observe the
    same values while ownership moves in small slices.
    """

    state = inst.get("_state")
    if isinstance(state, InstrumentState) and state.legacy_state is inst:
        return state

    state = InstrumentState.bind_live(inst, name=name, root_panel=root_panel)
    inst["_state"] = state
    return state

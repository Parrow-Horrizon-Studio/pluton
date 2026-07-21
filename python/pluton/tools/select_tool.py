"""The Select tool (Spacebar).

Hover pre-highlights the entity under the cursor. Click replaces the selection;
Shift-click toggles; clicking empty space clears. Box-select (drag a rectangle)
is added in M4b Task 8. Esc clears the selection.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.annotations.picking import pick_annotation
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.units import Units
from pluton.viewport.picking import pick_selectable

_HOVER_EDGE_COLOR = (0.45, 0.70, 1.00)
_HOVER_FILL_COLOR = (0.40, 0.70, 1.00, 0.18)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_BOX_WINDOW_COLOR = (0.25, 0.50, 0.95)   # left->right, enclose-only
_BOX_CROSSING_COLOR = (0.15, 0.65, 0.30)  # right->left, touch
_DRAG_THRESHOLD_PX = 4.0
_HOVER_BBOX_COLOR = (0.60, 0.78, 1.00)   # Task 15: lighter blue for hover silhouette bbox


class SelectTool(Tool):
    @property
    def name(self) -> str:
        return "Select"

    @property
    def shortcut(self) -> str:
        return "Space"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._selection = None
        self._model = None
        self._units_provider = None  # M7d — callable () -> pluton.units.Units (or None)
        self._request_rebuild = None  # M4e — callable () -> None
        self._hovered: tuple[str, int] | None = None
        self._hovered_instance = None  # M4e — Instance | None (for Task 15 silhouette)
        self._hovered_annotation: int | None = None  # M7d — annotation id under the cursor
        self._press_px: tuple[float, float] | None = None
        self._is_box = False
        self._box_rect: tuple[float, float, float, float] | None = None
        self._box_window = True  # True = L->R window, False = R->L crossing
        self._suppress_next_release = False  # M4e — set after double-click to eat the trailing release

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._selection = ctx.selection
        self._model = ctx.model
        self._units_provider = ctx.units_provider
        self._request_rebuild = ctx.request_context_rebuild
        self._hovered = None
        self._hovered_instance = None
        self._hovered_annotation = None
        self._press_px = None
        self._is_box = False
        self._box_rect = None
        self._suppress_next_release = False

    def _world_transform(self):
        return self._model.active_world_transform if self._model is not None else None

    def _units(self) -> Units:
        # M7d: every other units provider in this codebase (wall/opening/roof
        # options bars, the annotation painter) always yields a real Units
        # object -- None is not a value format_length expects.
        return self._units_provider() if self._units_provider is not None else Units()

    def _pick_annotation(self, cx: float, cy: float, w: int, h: int) -> int | None:
        """M7d: annotation hit-test scoped to the active context, mirroring how
        pick_selectable/pick_instance already scope to it."""
        if self._model is None or self._camera is None:
            return None
        return pick_annotation(
            (cx, cy),
            self._model.active_context.annotations,
            self._model.active_world_transform,
            self._camera,
            w,
            h,
            self._units(),
        )

    def deactivate(self) -> None:
        self._hovered = None
        self._reset_press()

    def _viewport_size(self) -> tuple[int, int]:
        if self._size_provider is None:
            return (1, 1)
        return self._size_provider()

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_px is not None:
            cx, cy = self._cursor(event)
            px, py = self._press_px
            if self._is_box or abs(cx - px) >= _DRAG_THRESHOLD_PX or abs(cy - py) >= _DRAG_THRESHOLD_PX:
                self._is_box = True
                self._box_rect = (px, py, cx, cy)
                self._box_window = (cx - px) >= 0.0
            return
        self._hovered = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene,
            world_transform=self._world_transform(),
        )
        # M7d: also track the hovered annotation (drawn on top, so hover-picked first)
        cx, cy = self._cursor(event)
        w, h = self._viewport_size()
        self._hovered_annotation = self._pick_annotation(cx, cy, w, h)
        # M4e: also track hovered instance for Task 15 silhouette rendering
        if self._model is not None and self._camera is not None:
            cx, cy = self._cursor(event)
            w, h = self._viewport_size()
            origin, direction = self._camera.ray_from_screen(cx, cy, w, h)
            self._hovered_instance = self._model.pick_instance(origin, direction)
        else:
            self._hovered_instance = None

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._press_px = self._cursor(event)
        self._is_box = False
        self._box_rect = None

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        # M4e: suppress the trailing release after a double-click enter
        if self._suppress_next_release:
            self._suppress_next_release = False
            self._reset_press()
            return
        if self._selection is None:
            self._reset_press()
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._is_box and self._box_rect is not None:
            from pluton.viewport.picking import entities_in_box
            mode = "window" if self._box_window else "crossing"
            edges, faces = entities_in_box(
                self._box_rect, mode, self._viewport_size(), self._camera, self._scene,
                world_transform=self._world_transform(),
            )
            if shift:
                self._selection.add(edges=edges, faces=faces)
            else:
                self._selection.replace(edges=edges, faces=faces)
        else:
            cx, cy = self._cursor(event)
            w, h = self._viewport_size()
            # M7d: annotations draw on top, so they win the click before the
            # instance/geometry pick below ever runs.
            ann_id = self._pick_annotation(cx, cy, w, h)
            if ann_id is not None:
                if shift:
                    self._selection.toggle_annotation(ann_id)
                else:
                    self._selection.replace(annotations=[ann_id])
                self._reset_press()
                return
            # M4e: try instance pick first (only if we have a model + camera)
            if self._model is not None and self._camera is not None:
                origin, direction = self._camera.ray_from_screen(cx, cy, w, h)
                inst = self._model.pick_instance(origin, direction)
                if inst is not None:
                    if shift:
                        self._selection.toggle_instance(inst.id)
                    else:
                        self._selection.replace(instances=[inst.id])
                    self._reset_press()
                    return
            # Fall through to entity pick
            hit = pick_selectable(
                self._cursor(event), self._viewport_size(), self._camera, self._scene,
                world_transform=self._world_transform(),
            )
            if hit is None:
                if not shift:
                    # M4e: inside a group, empty-click exits one level; at root clear selection
                    if self._model is not None and self._model.active_path:
                        self._exit_one()
                    else:
                        self._selection.clear()
            elif hit[0] == "edge":
                self._selection.toggle_edge(hit[1]) if shift else self._selection.replace(edges=[hit[1]])
            else:
                self._selection.toggle_face(hit[1]) if shift else self._selection.replace(faces=[hit[1]])
        self._reset_press()

    def _reset_press(self) -> None:
        self._press_px = None
        self._is_box = False
        self._box_rect = None
        self._box_window = True

    def on_mouse_double_click(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Double-click an instance to enter it (group/component open for editing)."""
        if self._model is None or self._camera is None:
            return
        cx, cy = self._cursor(event)
        w, h = self._viewport_size()
        origin, direction = self._camera.ray_from_screen(cx, cy, w, h)
        inst = self._model.pick_instance(origin, direction)
        if inst is not None:
            self._model.enter(inst)
            self._enter_or_exit_cleanup()
            self._suppress_next_release = True

    def _enter_or_exit_cleanup(self) -> None:
        """Clear selection and trigger a context rebuild after enter/exit."""
        if self._selection is not None:
            self._selection.clear()
        if self._request_rebuild is not None:
            self._request_rebuild()

    def _exit_one(self) -> None:
        """Exit one level of group nesting and rebuild the tool context."""
        if self._model is not None:
            self._model.exit_one()
            self._enter_or_exit_cleanup()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            # M4e: Esc inside a group exits one level; at root it clears selection
            if self._model is not None and self._model.active_path:
                self._exit_one()
            elif self._selection is not None:
                self._selection.clear()

    def overlay(self) -> ToolOverlay:
        box_rect = self._box_rect if self._is_box else None
        box_color = _BOX_WINDOW_COLOR if self._box_window else _BOX_CROSSING_COLOR
        segs = np.zeros((0, 3), dtype=np.float32)
        fills: list[np.ndarray] = []
        if not self._is_box and self._hovered is not None and self._scene is not None:
            kind, ent_id = self._hovered
            if kind == "edge":
                try:
                    e = self._scene.edge(ent_id)
                    p1 = np.asarray(self._scene.vertex(e.v1_id).position, dtype=np.float32)
                    p2 = np.asarray(self._scene.vertex(e.v2_id).position, dtype=np.float32)
                    segs = np.array([p1, p2], dtype=np.float32)
                except KeyError:
                    pass
            else:  # face
                try:
                    from pluton.geometry.transforms import apply_mat, is_identity_transform
                    wt = self._world_transform()
                    use_wt = wt is not None and not is_identity_transform(wt)
                    wt_arr = np.asarray(wt, dtype=np.float64) if use_wt else None

                    def _to_world_sel(local_pos: np.ndarray) -> np.ndarray:
                        if not use_wt:
                            return local_pos
                        return apply_mat(local_pos.reshape(1, 3), wt_arr)[0]

                    loop = self._scene.face_loop(ent_id)
                    fills = [np.array(
                        [_to_world_sel(np.asarray(self._scene.vertex(v).position, dtype=np.float32)) for v in loop],
                        dtype=np.float32,
                    )]
                except KeyError:
                    pass

        # Task 15: hover silhouette — draw the hovered instance's bbox as a
        # lighter-blue world polyline so it renders via the existing overlay path.
        world_polylines: list = []
        if (
            not self._is_box
            and self._hovered_instance is not None
            and self._model is not None
        ):
            aabb = self._hovered_instance.definition.local_aabb()
            if aabb is not None:
                from pluton.viewport.scene_renderer import aabb_world_edges
                lo, hi = aabb
                active_world = self._model.active_world_transform
                world_t = active_world @ self._hovered_instance.transform
                bbox_segs = aabb_world_edges(lo, hi, world_t)
                world_polylines.append((bbox_segs, _HOVER_BBOX_COLOR, 1.5))

        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_HOVER_EDGE_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=_HOVER_FILL_COLOR,
            box_rect=box_rect,
            box_rect_color=box_color,
            world_polylines=world_polylines,
            hovered_annotation_id=self._hovered_annotation if not self._is_box else None,
        )

    @property
    def has_active_gesture(self) -> bool:
        if self._is_box:
            return True
        return self._selection is not None and not self._selection.is_empty()

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        return None

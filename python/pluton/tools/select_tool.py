"""The Select tool (Spacebar).

Hover pre-highlights the entity under the cursor. Click replaces the selection;
Shift-click toggles; clicking empty space clears. Box-select (drag a rectangle)
is added in M4b Task 8. Esc clears the selection.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_HOVER_EDGE_COLOR = (0.45, 0.70, 1.00)
_HOVER_FILL_COLOR = (0.40, 0.70, 1.00, 0.18)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


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
        self._hovered: tuple[str, int] | None = None
        self._press_px: tuple[float, float] | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._selection = ctx.selection
        self._hovered = None
        self._press_px = None

    def deactivate(self) -> None:
        self._hovered = None
        self._press_px = None

    def _viewport_size(self) -> tuple[int, int]:
        if self._size_provider is None:
            return (1, 1)
        return self._size_provider()

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton:
            return  # press/drag handled in press/release (box-select: Task 8)
        self._hovered = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene
        )

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._press_px = self._cursor(event)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._selection is None:
            self._press_px = None
            return
        hit = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene
        )
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if hit is None:
            if not shift:
                self._selection.clear()
        elif hit[0] == "edge":
            if shift:
                self._selection.toggle_edge(hit[1])
            else:
                self._selection.replace(edges=[hit[1]])
        else:  # face
            if shift:
                self._selection.toggle_face(hit[1])
            else:
                self._selection.replace(faces=[hit[1]])
        self._press_px = None

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._selection is not None:
            self._selection.clear()

    def overlay(self) -> ToolOverlay:
        segs = np.zeros((0, 3), dtype=np.float32)
        fills: list[np.ndarray] = []
        if self._hovered is not None and self._scene is not None:
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
                    loop = self._scene.face_loop(ent_id)
                    fills = [np.array(
                        [self._scene.vertex(v).position for v in loop], dtype=np.float32
                    )]
                except KeyError:
                    pass
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_HOVER_EDGE_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=_HOVER_FILL_COLOR,
        )

    @property
    def has_active_gesture(self) -> bool:
        # True when there's a selection to clear (so Esc reaches on_key_press
        # rather than deactivating the tool).
        return self._selection is not None and not self._selection.is_empty()

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        return None

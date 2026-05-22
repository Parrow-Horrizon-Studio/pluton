"""The Rectangle drawing tool.

Two-corner gesture: first click sets the first corner, second click commits
an axis-aligned rectangle on the ground plane (Z=0). ESC cancels mid-drag.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


class _State(Enum):
    IDLE = 0
    DRAGGING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MARKER_COLOR_BY_KIND = {
    1: (0.7, 0.7, 0.7),     # GRID
    2: None,                # AXIS_LOCK (Rectangle doesn't axis-lock; never set)
    3: (0.2, 0.85, 0.95),   # MIDPOINT
    4: (0.25, 0.78, 0.26),  # ENDPOINT
}


class RectangleTool(Tool):
    @property
    def name(self) -> str:
        return "Rectangle"

    @property
    def shortcut(self) -> str:
        return "R"

    def __init__(self) -> None:
        self._scene = None
        self._state = _State.IDLE
        self._first_corner: np.ndarray | None = None
        self._preview_corner: np.ndarray | None = None
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = _MARKER_COLOR_BY_KIND.get(int(snap.kind), _NEUTRAL_COLOR)
        if self._state == _State.DRAGGING:
            self._preview_corner = snap.world_position.copy()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return

        if self._state == _State.IDLE:
            self._first_corner = snap.world_position.copy()
            self._preview_corner = snap.world_position.copy()
            self._state = _State.DRAGGING
            return

        # DRAGGING — commit or drop
        assert self._first_corner is not None
        second = snap.world_position
        if np.array_equal(second, self._first_corner):
            self._reset_gesture()
            return

        x0, y0 = float(self._first_corner[0]), float(self._first_corner[1])
        x1, y1 = float(second[0]), float(second[1])
        s = self._scene  # type: ignore[assignment]
        v0 = s.add_vertex(np.array([x0, y0, 0.0], dtype=np.float32))
        v1 = s.add_vertex(np.array([x1, y0, 0.0], dtype=np.float32))
        v2 = s.add_vertex(np.array([x1, y1, 0.0], dtype=np.float32))
        v3 = s.add_vertex(np.array([x0, y1, 0.0], dtype=np.float32))
        s.add_edge(v0, v1)
        s.add_edge(v1, v2)
        s.add_edge(v2, v3)
        s.add_edge(v3, v0)
        s.add_face_from_loop((v0, v1, v2, v3))
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        if self._state == _State.DRAGGING and self._first_corner is not None and self._preview_corner is not None:
            x0, y0 = float(self._first_corner[0]), float(self._first_corner[1])
            x1, y1 = float(self._preview_corner[0]), float(self._preview_corner[1])
            segments = np.array(
                [
                    [x0, y0, 0.0], [x1, y0, 0.0],
                    [x1, y0, 0.0], [x1, y1, 0.0],
                    [x1, y1, 0.0], [x0, y1, 0.0],
                    [x0, y1, 0.0], [x0, y0, 0.0],
                ],
                dtype=np.float32,
            )
        else:
            segments = np.zeros((0, 3), dtype=np.float32)

        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
        )

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None  # Rectangle tool doesn't drive axis-lock

    # ---- internal -------------------------------------------------------
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._first_corner = None
        self._preview_corner = None
        self._snap_marker_pos = None

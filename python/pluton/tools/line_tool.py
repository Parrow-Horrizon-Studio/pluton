"""The Line drawing tool.

Click → click → click polyline. Snapping back onto the first vertex of the
gesture closes the loop and creates a face (provided ≥ 3 vertices exist).
Snapping onto some other existing vertex extends the polyline to it.
Otherwise, a new vertex is created at the snapped position.

ESC clears the visible gesture state; it does not un-add committed vertices.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


class _State(Enum):
    IDLE = 0
    DRAWING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_AXIS_COLORS = {
    0: (0.95, 0.30, 0.30),  # X — red
    1: (0.30, 0.85, 0.30),  # Y — green
    2: (0.30, 0.40, 0.95),  # Z — blue
}
_MARKER_COLOR_BY_KIND = {
    1: (0.7, 0.7, 0.7),     # GRID
    3: (0.2, 0.85, 0.95),   # MIDPOINT
    4: (0.25, 0.78, 0.26),  # ENDPOINT
    # AXIS_LOCK (2) intentionally absent — falls back to _NEUTRAL_COLOR
    # because the rubber-band itself shows the axis color, so the marker
    # doesn't need to duplicate that signal.
}


class LineTool(Tool):
    @property
    def name(self) -> str:
        return "Line"

    @property
    def shortcut(self) -> str:
        return "L"

    def __init__(self) -> None:
        self._scene = None
        self._state = _State.IDLE
        self._gesture_vertex_ids: list[int] = []
        self._preview_tip: np.ndarray | None = None
        self._rubber_band_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_kind: int = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = _MARKER_COLOR_BY_KIND.get(int(snap.kind), _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._state == _State.DRAWING:
            self._preview_tip = snap.world_position.copy()
            if snap.kind == SnapKind.AXIS_LOCK and snap.axis is not None:
                self._rubber_band_color = _AXIS_COLORS.get(snap.axis, _NEUTRAL_COLOR)
            else:
                self._rubber_band_color = _NEUTRAL_COLOR

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return

        s = self._scene  # type: ignore[assignment]
        if self._state == _State.IDLE:
            # First click — seed the gesture.
            if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
                vid = snap.vertex_id
            else:
                vid = s.add_vertex(snap.world_position)
            self._gesture_vertex_ids = [vid]
            self._state = _State.DRAWING
            self._preview_tip = snap.world_position.copy()
            return

        # DRAWING — branch 1, 2, or 3
        tip_vid = self._gesture_vertex_ids[-1]
        first_vid = self._gesture_vertex_ids[0]

        if (
            snap.kind == SnapKind.ENDPOINT
            and snap.vertex_id == first_vid
            and len(self._gesture_vertex_ids) >= 3
        ):
            # Branch 1 — loop closure
            s.add_edge(tip_vid, first_vid)
            s.add_face_from_loop(tuple(self._gesture_vertex_ids))
            self._reset_gesture()
            return

        if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
            # Branch 2 — extend polyline to an existing vertex
            if snap.vertex_id == tip_vid:
                return  # degenerate: dropped
            s.add_edge(tip_vid, snap.vertex_id)
            self._gesture_vertex_ids.append(snap.vertex_id)
            return

        # Branch 3 — new vertex
        new_vid = s.add_vertex(snap.world_position)
        if new_vid == tip_vid:
            return  # degenerate: dropped
        s.add_edge(tip_vid, new_vid)
        self._gesture_vertex_ids.append(new_vid)

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        s = self._scene  # type: ignore[assignment]
        if (
            self._state == _State.DRAWING
            and s is not None
            and self._preview_tip is not None
            and self._gesture_vertex_ids
        ):
            anchor = s.vertex(self._gesture_vertex_ids[-1]).position
            segments = np.array(
                [
                    [float(anchor[0]), float(anchor[1]), float(anchor[2])],
                    [
                        float(self._preview_tip[0]),
                        float(self._preview_tip[1]),
                        float(self._preview_tip[2]),
                    ],
                ],
                dtype=np.float32,
            )
        else:
            segments = np.zeros((0, 3), dtype=np.float32)

        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=self._rubber_band_color,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAWING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        s = self._scene  # type: ignore[assignment]
        if self._state != _State.DRAWING or s is None or not self._gesture_vertex_ids:
            return None
        return s.vertex(self._gesture_vertex_ids[-1]).position.copy()

    # ---- internal -------------------------------------------------------
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._gesture_vertex_ids = []
        self._preview_tip = None
        self._rubber_band_color = _NEUTRAL_COLOR
        self._snap_marker_pos = None
        self._snap_marker_kind = 0

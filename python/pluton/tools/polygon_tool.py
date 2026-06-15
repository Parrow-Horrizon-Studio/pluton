"""The Polygon drawing tool.

Two-click gesture identical to Circle, but commits a regular inscribed N-gon.
The side count (default 6, remembered for the session) is nudged with Up/Down
during the gesture. ESC cancels.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.geometry import polygon
from pluton.tools.shape_support import (
    build_closed_face,
    polyline_segments,
    resolve_drawing_plane,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MIN_RADIUS = 1e-4
_MIN_SIDES = 3
_MAX_SIDES = 64


class _State(Enum):
    IDLE = 0
    DRAWING = 1


class PolygonTool(Tool):
    @property
    def name(self) -> str:
        return "Polygon"

    @property
    def shortcut(self) -> str:
        return "G"

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._state = _State.IDLE
        self._plane = None
        self._center: np.ndarray | None = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._sides = 6  # remembered across gestures (instance lives for the session)
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_kind = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
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
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._state == _State.DRAWING and self._plane is not None:
            uv = self._plane.project(snap.world_position)
            self._radius = float(np.linalg.norm(uv))
            self._start_angle = float(np.arctan2(uv[1], uv[0]))

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return
        s = self._scene  # type: ignore[assignment]

        if self._state == _State.IDLE:
            self._plane = resolve_drawing_plane(snap, s)
            self._center = snap.world_position.copy()
            self._state = _State.DRAWING
            return

        if self._plane is None:
            self._reset_gesture()
            return
        uv = self._plane.project(snap.world_position)
        radius = float(np.linalg.norm(uv))
        if radius < _MIN_RADIUS:
            return
        start_angle = float(np.arctan2(uv[1], uv[0]))
        ring_uv = polygon(radius, self._sides, start_angle)
        world = self._plane.to_world(ring_uv).astype(np.float32)
        composite = build_closed_face(s, world, name="Draw Polygon")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._reset_gesture()
        elif key == Qt.Key.Key_Up:
            self._sides = min(_MAX_SIDES, self._sides + 1)
        elif key == Qt.Key.Key_Down:
            self._sides = max(_MIN_SIDES, self._sides - 1)

    def overlay(self) -> ToolOverlay:
        if (
            self._state == _State.DRAWING
            and self._plane is not None
            and self._radius >= _MIN_RADIUS
        ):
            ring_uv = polygon(self._radius, self._sides, self._start_angle)
            world = self._plane.to_world(ring_uv).astype(np.float32)
            segments = polyline_segments(world, closed=True)
        else:
            segments = np.zeros((0, 3), dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAWING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        if self._state == _State.DRAWING and self._center is not None:
            return self._center.copy()
        return None

    @property
    def status_text(self) -> str | None:
        if self._state == _State.DRAWING:
            return f"Radius: {self._radius:.3f}   Sides: {self._sides}"
        return None

    def _reset_gesture(self) -> None:
        # NOTE: _sides is intentionally NOT reset — it persists across gestures.
        self._state = _State.IDLE
        self._plane = None
        self._center = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
        self._snap_marker_color = _NEUTRAL_COLOR

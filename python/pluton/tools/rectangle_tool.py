"""The Rectangle drawing tool.

Two-corner gesture: first click sets the first corner, second click commits
an axis-aligned rectangle on the ground plane (Z=0). ESC cancels mid-drag.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND


class _State(Enum):
    IDLE = 0
    DRAGGING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


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
        self._snap_marker_kind: int = 0
        self._composite: CompositeCommand | None = None
        self._command_stack = None  # populated in activate()

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

        # Normalize to a canonical CCW-from-above winding (min -> max on each
        # axis) so the face normal always points +Z (up), regardless of which
        # diagonal the user dragged the second corner toward. Without this, a
        # down-right / up-left drag yields a -Z normal and push/pull would
        # extrude the rectangle downward instead of up.
        xlo, xhi = min(x0, x1), max(x0, x1)
        ylo, yhi = min(y0, y1), max(y0, y1)

        composite = CompositeCommand(name="Draw Rectangle")
        s = self._scene  # type: ignore[assignment]
        v_cmds = [
            AddVertexCommand(np.array([xlo, ylo, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([xhi, ylo, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([xhi, yhi, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([xlo, yhi, 0.0], dtype=np.float32)),
        ]
        for c in v_cmds:
            c.do(s)
            composite.children.append(c)
        vids = [c._vertex_id for c in v_cmds]  # type: ignore[attr-defined]
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            e_cmd = AddEdgeCommand(vids[a], vids[b])
            e_cmd.do(s)
            composite.children.append(e_cmd)
        f_cmd = AddFaceCommand(tuple(vids))
        f_cmd.do(s)
        composite.children.append(f_cmd)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() != Qt.Key.Key_Escape:
            return
        if self._composite is not None:
            # We haven't built a composite mid-drag in Rectangle (it commits
            # atomically on second click), so there is nothing to roll back.
            self._composite = None
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
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAGGING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None  # Rectangle tool doesn't drive axis-lock

    # ---- internal -------------------------------------------------------
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._first_corner = None
        self._preview_corner = None
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
        self._composite = None

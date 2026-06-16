"""The Move tool (M) — point-to-point translation of the selection.

Press snaps a grab point and captures the selection's vertices + their
original positions. Drag computes delta = destination - grab (axis-lock is
provided by the SnapEngine, which the viewport calls with anchor_or_none =
the grab point). Release commits one TransformVerticesCommand. The mesh is
never mutated until release, so Esc/deactivate simply resets.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.geometry.transforms import translate
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.transform_support import selection_vertices

_NEUTRAL = (0.85, 0.85, 0.85)
_GHOST = (0.30, 0.65, 1.0)


class MoveTool(Tool):
    @property
    def name(self) -> str:
        return "Move"

    @property
    def shortcut(self) -> str:
        return "M"

    def __init__(self) -> None:
        self._scene = None
        self._stack = None
        self._selection = None
        self._dragging = False
        self._grab: np.ndarray | None = None
        self._delta = np.zeros(3, dtype=np.float32)
        self._vertex_ids: list[int] = []
        self._orig: dict[int, np.ndarray] = {}

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._stack = ctx.command_stack
        self._selection = ctx.selection
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._selection is None or self._selection.is_empty():
            return
        if snap.kind == SnapKind.NONE:
            return
        self._vertex_ids = selection_vertices(self._scene, self._selection)
        if not self._vertex_ids:
            return
        self._orig = {v: self._scene.vertex(v).position.copy() for v in self._vertex_ids}
        self._grab = np.asarray(snap.world_position, np.float32).copy()
        self._delta = np.zeros(3, dtype=np.float32)
        self._dragging = True

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if not self._dragging or self._grab is None or snap.kind == SnapKind.NONE:
            return
        self._delta = (np.asarray(snap.world_position, np.float32) - self._grab).astype(np.float32)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        from pluton.viewport.snap_engine import SnapKind
        if snap is not None and getattr(snap, "world_position", None) is not None \
                and snap.kind != SnapKind.NONE and self._grab is not None:
            dest = np.asarray(snap.world_position, np.float32)
            self._delta = (dest - self._grab).astype(np.float32)
        ids = self._vertex_ids
        if ids:
            pts = np.array([self._orig[v] for v in ids], np.float32)
            new = translate(pts, self._delta)
            moves = {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}
            cmd = TransformVerticesCommand(moves)
            if not cmd.is_empty() and self._stack is not None:
                self._stack.execute(cmd, self._scene)
        self._reset()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        polylines: list = []
        segs = np.zeros((0, 3), dtype=np.float32)
        marker = None
        if self._dragging and self._grab is not None and self._scene is not None:
            ghost = self._ghost_segments()
            if ghost.shape[0] >= 2:
                polylines.append((ghost, _GHOST, 2.0))
            segs = np.array([self._grab, self._grab + self._delta], dtype=np.float32)
            marker = (self._grab + self._delta).astype(np.float32)
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=marker,
            snap_marker_color=_GHOST,
            world_polylines=polylines,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._dragging

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return self._grab.copy() if (self._dragging and self._grab is not None) else None

    @property
    def status_text(self) -> str | None:
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._dragging:
            d = self._delta
            return f"Move Δ ({d[0]:.2f}, {d[1]:.2f}, {d[2]:.2f})"
        return "Move: pick a grab point"

    # ---- internal ----
    def _ghost_segments(self) -> np.ndarray:
        """Selection edges + face loops as world segments, translated by delta."""
        s = self._scene
        sel = self._selection
        pts: list[list[float]] = []

        def seg(p0, p1):
            q0 = np.asarray(p0, np.float32) + self._delta
            q1 = np.asarray(p1, np.float32) + self._delta
            pts.append([float(q0[0]), float(q0[1]), float(q0[2])])
            pts.append([float(q1[0]), float(q1[1]), float(q1[2])])

        for e_id in sel.edges:
            try:
                e = s.edge(e_id)
            except KeyError:
                continue
            seg(s.vertex(e.v1_id).position, s.vertex(e.v2_id).position)
        for f_id in sel.faces:
            try:
                loop = s.face_loop(f_id)
            except KeyError:
                continue
            n = len(loop)
            for i in range(n):
                seg(s.vertex(loop[i]).position, s.vertex(loop[(i + 1) % n]).position)
        return np.array(pts, dtype=np.float32) if pts else np.zeros((0, 3), np.float32)

    def _reset(self) -> None:
        self._dragging = False
        self._grab = None
        self._delta = np.zeros(3, dtype=np.float32)
        self._vertex_ids = []
        self._orig = {}

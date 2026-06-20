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

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
    SplitEdgeCommand,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import world_to_local_point
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND


class _State(Enum):
    IDLE = 0
    DRAWING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_AXIS_COLORS = {
    0: (0.95, 0.30, 0.30),  # X — red
    1: (0.30, 0.85, 0.30),  # Y — green
    2: (0.30, 0.40, 0.95),  # Z — blue
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
        self._model = None
        self._state = _State.IDLE
        self._gesture_vertex_ids: list[int] = []
        self._preview_tip: np.ndarray | None = None
        self._rubber_band_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_kind: int = 0
        self._composite: CompositeCommand | None = None
        self._command_stack = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._reset_gesture()

    def _world_transform(self):  # noqa: ANN202
        return self._model.active_world_transform if self._model is not None else None

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
            self._composite = CompositeCommand(name="Draw Line")
            vid, cmd = self._vertex_for_snap(snap, s)
            if cmd is not None:
                self._composite.children.append(cmd)
            self._gesture_vertex_ids = [vid]
            self._state = _State.DRAWING
            self._preview_tip = snap.world_position.copy()
            return

        assert self._composite is not None
        tip_vid = self._gesture_vertex_ids[-1]
        first_vid = self._gesture_vertex_ids[0]

        # Branch 1 — loop closure (snap back onto the first vertex with ≥3 points).
        if (
            snap.kind == SnapKind.ENDPOINT
            and snap.vertex_id == first_vid
            and len(self._gesture_vertex_ids) >= 3
        ):
            e_cmd = AddEdgeCommand(tip_vid, first_vid)
            e_cmd.do(s)
            self._composite.children.append(e_cmd)
            f_cmd = AddFaceCommand(tuple(self._gesture_vertex_ids))
            f_cmd.do(s)
            self._composite.children.append(f_cmd)
            if self._command_stack is not None:
                self._command_stack.push_executed(self._composite, self._scene)
            self._reset_gesture()
            return

        # Branches 2/3 — extend to a resolved vertex (reuse / split / new).
        vid, cmd = self._vertex_for_snap(snap, s)
        if vid == tip_vid:
            if cmd is not None:
                cmd.undo(s)  # degenerate: clicked the current tip
            return
        if cmd is not None:
            self._composite.children.append(cmd)
        e_cmd = AddEdgeCommand(tip_vid, vid)
        e_cmd.do(s)
        self._composite.children.append(e_cmd)
        self._gesture_vertex_ids.append(vid)

    def apply_typed_value(self, text, units) -> bool:
        from pluton.units import parse_length
        if (
            self._state != _State.DRAWING
            or self._preview_tip is None
            or not self._gesture_vertex_ids
        ):
            return False
        length = parse_length(text, units)
        if length is None or length <= 0:
            return False
        s = self._scene
        # anchor_local is in the active context's local space.
        # _preview_tip is always world. Convert anchor local→world to get the
        # direction purely in world space, then convert the world target local.
        anchor_local = np.asarray(s.vertex(self._gesture_vertex_ids[-1]).position, np.float32)
        wt = self._world_transform()
        from pluton.geometry.transforms import apply_mat, is_identity_transform
        if is_identity_transform(wt):
            anchor_world = anchor_local
        else:
            anchor_world = apply_mat(
                anchor_local.astype(np.float64).reshape(1, 3),
                np.asarray(wt, dtype=np.float64)
            )[0].astype(np.float32)
        direction = np.asarray(self._preview_tip, np.float32) - anchor_world
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return False
        target_world = (anchor_world + (direction / norm) * length).astype(np.float32)
        target_local = world_to_local_point(target_world, wt)
        from pluton.commands.scene_commands import AddEdgeCommand, AddVertexCommand
        assert self._composite is not None
        v_cmd = AddVertexCommand(target_local)
        v_cmd.do(s)
        self._composite.children.append(v_cmd)
        new_vid = v_cmd._vertex_id  # type: ignore[attr-defined]
        e_cmd = AddEdgeCommand(self._gesture_vertex_ids[-1], new_vid)
        e_cmd.do(s)
        self._composite.children.append(e_cmd)
        self._gesture_vertex_ids.append(new_vid)
        self._preview_tip = target_world.copy()
        return True

    def on_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        s = self._scene  # type: ignore[assignment]

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Finish the open polyline: register it as one undoable unit and end
            # the gesture (ready to start a new line). Matches SketchUp/CAD Enter.
            if self._state == _State.DRAWING and self._composite is not None:
                if len(self._gesture_vertex_ids) >= 2 and self._composite.children:
                    if self._command_stack is not None:
                        self._command_stack.push_executed(self._composite, self._scene)
                else:
                    # Only the start point was placed — nothing to commit; discard.
                    self._composite.undo(s)
                self._composite = None
            self._reset_gesture()
            return

        if key != Qt.Key.Key_Escape:
            return
        # ESC mid-gesture: roll back the in-progress composite.
        if self._composite is not None:
            self._composite.undo(s)
            self._composite = None
        self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        s = self._scene  # type: ignore[assignment]
        if (
            self._state == _State.DRAWING
            and s is not None
            and self._preview_tip is not None
            and self._gesture_vertex_ids
        ):
            anchor_local = s.vertex(self._gesture_vertex_ids[-1]).position
            wt = self._world_transform()
            from pluton.geometry.transforms import apply_mat, is_identity_transform
            if is_identity_transform(wt):
                anchor_world = anchor_local
            else:
                anchor_world = apply_mat(
                    np.asarray(anchor_local, dtype=np.float64).reshape(1, 3),
                    np.asarray(wt, dtype=np.float64)
                )[0]
            segments = np.array(
                [
                    [float(anchor_world[0]), float(anchor_world[1]), float(anchor_world[2])],
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
    def _vertex_for_snap(self, snap, scene):  # noqa: ANN001
        """Resolve a snap to a vertex id. Splits the host edge for interior
        snaps. Returns (vertex_id, command_or_None); caller appends the command."""
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
            return snap.vertex_id, None
        if snap.edge_id is not None and snap.edge_t is not None and snap.kind in (
            SnapKind.MIDPOINT, SnapKind.ON_EDGE, SnapKind.INTERSECTION
        ):
            split = SplitEdgeCommand(snap.edge_id, snap.edge_t)
            split.do(scene)
            if split.new_vertex_id is not None:
                return split.new_vertex_id, split
            # Split was a no-op (degenerate/coincident edge_t). Reuse the host
            # edge's nearest endpoint rather than dropping a free vertex on the
            # edge interior (which would be a T-junction).
            edge = scene.edge(snap.edge_id)
            pos = np.asarray(snap.world_position, dtype=np.float32)
            v1p = scene.vertex(edge.v1_id).position
            v2p = scene.vertex(edge.v2_id).position
            nearest = (
                edge.v1_id
                if float(np.linalg.norm(pos - v1p)) <= float(np.linalg.norm(pos - v2p))
                else edge.v2_id
            )
            return nearest, None
        local = world_to_local_point(snap.world_position, self._world_transform())
        cmd = AddVertexCommand(local)
        cmd.do(scene)
        return cmd._vertex_id, cmd  # type: ignore[attr-defined]

    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._gesture_vertex_ids = []
        self._preview_tip = None
        self._rubber_band_color = _NEUTRAL_COLOR
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
        self._composite = None

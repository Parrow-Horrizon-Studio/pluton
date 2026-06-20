"""The Eraser tool (E).

Hover/drag over EDGES to delete them. Erasing an edge cascades to its incident
faces (a face can't survive losing a boundary edge), so removal is composed as:
remove incident face(s) first, then the edge. A press-drag-release stroke
accumulates into one undoable CompositeCommand.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import RemoveEdgeCommand, RemoveFaceCommand
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_ERASE_EDGE_COLOR = (1.00, 0.40, 0.40)
_ERASE_FILL_COLOR = (1.00, 0.35, 0.35, 0.20)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class EraserTool(Tool):
    @property
    def name(self) -> str:
        return "Eraser"

    @property
    def shortcut(self) -> str:
        return "E"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._command_stack = None
        self._model = None
        self._hovered_edge: int | None = None
        self._stroke: CompositeCommand | None = None
        self._erased: set[int] = set()

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._hovered_edge = None
        self._stroke = None
        self._erased = set()

    def _world_transform(self):  # noqa: ANN202
        return self._model.active_world_transform if self._model is not None else None

    def deactivate(self) -> None:
        # Roll back any in-progress (un-committed) erase stroke so a mid-drag
        # tool switch never leaves un-undoable scene mutations.
        if self._stroke is not None and self._stroke.children and self._scene is not None:
            self._stroke.undo(self._scene)
        self._hovered_edge = None
        self._stroke = None
        self._erased = set()

    def _viewport_size(self) -> tuple[int, int]:
        return self._size_provider() if self._size_provider is not None else (1, 1)

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def _pick_edge(self, event: QMouseEvent) -> int | None:
        hit = pick_selectable(self._cursor(event), self._viewport_size(), self._camera, self._scene, world_transform=self._world_transform())
        return hit[1] if hit is not None and hit[0] == "edge" else None

    def _erase_edge(self, e_id: int) -> None:
        """Append (and execute) the cascade for one edge into the active stroke."""
        if self._stroke is None or e_id in self._erased:
            return
        try:
            self._scene.edge(e_id)
        except KeyError:
            return
        for f_id in self._scene.edge_faces(e_id):
            if f_id is None:
                continue
            cmd = RemoveFaceCommand(f_id)
            cmd.do(self._scene)
            self._stroke.children.append(cmd)
        edge_cmd = RemoveEdgeCommand(e_id)
        edge_cmd.do(self._scene)
        self._stroke.children.append(edge_cmd)
        self._erased.add(e_id)

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton and self._stroke is not None:
            e_id = self._pick_edge(event)
            if e_id is not None:
                self._erase_edge(e_id)
            return
        self._hovered_edge = self._pick_edge(event)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._stroke = CompositeCommand(name="Erase")
        self._erased = set()
        e_id = self._pick_edge(event)
        if e_id is not None:
            self._erase_edge(e_id)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._stroke is not None and self._stroke.children and self._command_stack is not None:
            self._command_stack.push_executed(self._stroke, self._scene)
        self._stroke = None
        self._erased = set()
        self._hovered_edge = None

    def overlay(self) -> ToolOverlay:
        segs = np.zeros((0, 3), dtype=np.float32)
        fills: list[np.ndarray] = []
        if self._hovered_edge is not None and self._scene is not None:
            try:
                from pluton.geometry.transforms import apply_mat, is_identity_transform
                wt = self._world_transform()
                use_wt = not is_identity_transform(wt)
                wt_arr = np.asarray(wt, dtype=np.float64) if use_wt else None

                def _to_world(local_pos: np.ndarray) -> np.ndarray:
                    if not use_wt:
                        return local_pos
                    return apply_mat(local_pos.reshape(1, 3), wt_arr)[0]

                e = self._scene.edge(self._hovered_edge)
                p1 = _to_world(np.asarray(self._scene.vertex(e.v1_id).position, dtype=np.float32))
                p2 = _to_world(np.asarray(self._scene.vertex(e.v2_id).position, dtype=np.float32))
                segs = np.array([p1, p2], dtype=np.float32)
                for f_id in self._scene.edge_faces(self._hovered_edge):
                    if f_id is None:
                        continue
                    loop = self._scene.face_loop(f_id)
                    fills.append(np.array(
                        [_to_world(np.asarray(self._scene.vertex(v).position, dtype=np.float32)) for v in loop],
                        dtype=np.float32,
                    ))
            except KeyError:
                pass
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_ERASE_EDGE_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=_ERASE_FILL_COLOR,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._stroke is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

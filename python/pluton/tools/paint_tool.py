"""The Paint tool (B).

Click a face to apply the active material; Alt-click to sample (eyedropper)
the clicked face's material as the new active material. Painting the Default
material removes paint. Each paint is one undoable PaintFaceCommand.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.material_commands import PaintFaceCommand
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_HOVER_ALPHA = 0.45
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class PaintTool(Tool):
    @property
    def name(self) -> str:
        return "Paint"

    @property
    def shortcut(self) -> str:
        return "B"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._command_stack = None
        self._model = None
        self._active_material_provider = None
        self._set_active_material = None
        self._hovered_face: int | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._active_material_provider = ctx.active_material_provider
        self._set_active_material = ctx.set_active_material
        self._hovered_face = None

    def deactivate(self) -> None:
        self._hovered_face = None

    def _world_transform(self):  # noqa: ANN202
        return self._model.active_world_transform if self._model is not None else None

    def _viewport_size(self) -> tuple[int, int]:
        return self._size_provider() if self._size_provider is not None else (1, 1)

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def _pick_face(self, event: QMouseEvent) -> int | None:
        hit = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene,
            world_transform=self._world_transform(),
        )
        return hit[1] if hit is not None and hit[0] == "face" else None

    def _active_material(self):  # noqa: ANN202
        if self._active_material_provider is None:
            return None
        return self._active_material_provider()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._hovered_face = self._pick_face(event)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        f_id = self._pick_face(event)
        if f_id is None or self._scene is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Eyedropper: sample the face's material. Not a mutation.
            if self._set_active_material is not None:
                self._set_active_material(self._scene.face_material(f_id))
            return
        mat = self._active_material()
        if mat is None or mat.id == self._scene.face_material(f_id):
            return  # no-op guard avoids empty undo entries
        if self._command_stack is not None:
            cmd = PaintFaceCommand(f_id, mat.id)
            cmd.do(self._scene)
            self._command_stack.push_executed(cmd, self._scene)

    def overlay(self) -> ToolOverlay:
        fills: list[np.ndarray] = []
        mat = self._active_material()
        tint = mat.color if mat is not None else _NEUTRAL_COLOR
        if self._hovered_face is not None and self._scene is not None:
            try:
                from pluton.geometry.transforms import apply_mat, is_identity_transform
                wt = self._world_transform()
                use_wt = not is_identity_transform(wt)
                wt_arr = np.asarray(wt, dtype=np.float64) if use_wt else None

                def _to_world(local_pos: np.ndarray) -> np.ndarray:
                    if not use_wt:
                        return local_pos
                    return apply_mat(local_pos.reshape(1, 3), wt_arr)[0]

                loop = self._scene.face_loop(self._hovered_face)
                fills.append(np.array(
                    [_to_world(np.asarray(self._scene.vertex(v).position, dtype=np.float32))
                     for v in loop],
                    dtype=np.float32,
                ))
            except KeyError:
                pass
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=(tint[0], tint[1], tint[2], _HOVER_ALPHA),
        )

    @property
    def has_active_gesture(self) -> bool:
        return False

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    def status_text(self) -> str | None:
        mat = self._active_material()
        name = mat.name if mat is not None else "Default"
        return f"Paint: {name} · Alt-click to sample"

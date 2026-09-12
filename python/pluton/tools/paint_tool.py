"""The Paint tool (B).

Click a face to apply the active material to the side you clicked; drag to
paint every face the cursor crosses as one undo step. Alt-click samples
(eyedropper) the clicked side's material as the new active material.
Painting the Default material removes paint.

Side resolution follows model.pick_face_local (M7.4 #92): the face normal is
transformed by the inverse-transpose of the world transform's linear block,
not the linear block itself, so a non-uniformly scaled group still picks the
correct side.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.material_commands import PaintFaceCommand
from pluton.geometry.transforms import is_identity_transform, mat_invert
from pluton.scene.scene import Side
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_HOVER_ALPHA = 0.45
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


def side_for_ray(world_normal, ray_direction) -> Side:
    """Which side of a face a ray hits.

    A ray travelling against the normal strikes the front. `world_normal` must
    already be in world space, transformed by the inverse-transpose of the
    world matrix's linear block (see model.pick_face_local, fixed in M7.4 #92):
    the plain linear block gives the wrong side under a non-uniform scale.
    """
    return Side.FRONT if float(np.dot(world_normal, ray_direction)) < 0.0 else Side.BACK


class PaintTool(Tool):
    @property
    def name(self) -> str:
        return "Paint"

    @property
    def shortcut(self) -> str:
        return "B"

    @property
    def id(self) -> str:
        return "paint"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._command_stack = None
        self._model = None
        self._active_material_provider = None
        self._set_active_material = None
        self._hovered_face: int | None = None
        self._stroke_commands: list = []
        self._stroke_painted: set[tuple[int, Side]] = set()
        self._stroke_active: bool = False
        self._stroke_material_id: int | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._active_material_provider = ctx.active_material_provider
        self._set_active_material = ctx.set_active_material
        self._hovered_face = None
        self._stroke_commands = []
        self._stroke_painted = set()
        self._stroke_active = False
        self._stroke_material_id = None

    def deactivate(self) -> None:
        # Roll back any in-progress (un-committed) paint stroke so switching
        # tools mid-drag never leaves un-undoable scene mutations, mirroring
        # EraserTool.deactivate.
        if self._stroke_active and self._stroke_commands and self._scene is not None:
            for cmd in reversed(self._stroke_commands):
                cmd.undo(self._scene)
        self._hovered_face = None
        self._stroke_commands = []
        self._stroke_painted = set()
        self._stroke_active = False
        self._stroke_material_id = None

    def _world_transform(self):
        return self._model.active_world_transform if self._model is not None else None

    def _viewport_size(self) -> tuple[int, int]:
        return self._size_provider() if self._size_provider is not None else (1, 1)

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def _pick_face(self, event: QMouseEvent) -> int | None:
        hit = pick_selectable(
            self._cursor(event),
            self._viewport_size(),
            self._camera,
            self._scene,
            world_transform=self._world_transform(),
        )
        return hit[1] if hit is not None and hit[0] == "face" else None

    def _resolve_side(self, event: QMouseEvent, f_id: int) -> Side:
        """Which side of face `f_id` the cursor ray strikes, in world space.

        Mirrors model.pick_face_local (M7.4 #92): the local face normal is
        carried into world space by the inverse-transpose of the world
        transform's linear block, not the linear block itself, so a
        non-uniformly scaled group still resolves the correct side.
        """
        cx, cy = self._cursor(event)
        w, h = self._viewport_size()
        _origin, direction = self._camera.ray_from_screen(cx, cy, w, h)
        normal = np.asarray(self._scene.face_normal(f_id), dtype=np.float64)
        wt = self._world_transform()
        if not is_identity_transform(wt):
            w_inv = mat_invert(np.asarray(wt, dtype=np.float64))
            normal = w_inv[:3, :3].T @ normal
            length = float(np.linalg.norm(normal))
            if length > 1e-12:
                normal = normal / length
        return side_for_ray(normal, np.asarray(direction, dtype=np.float64))

    def _active_material(self):
        if self._active_material_provider is None:
            return None
        return self._active_material_provider()

    def _begin_stroke(self, material_id: int) -> None:
        self._stroke_commands = []
        self._stroke_painted = set()
        self._stroke_active = True
        self._stroke_material_id = material_id

    def _paint_during_stroke(self, f_id: int, side: Side, material_id: int) -> None:
        if (f_id, side) in self._stroke_painted:
            return
        if self._scene.face_material(f_id, side) == material_id:
            self._stroke_painted.add((f_id, side))
            return
        cmd = PaintFaceCommand(f_id, material_id, side)
        cmd.do(self._scene)  # eager, so the paint appears live
        self._stroke_commands.append(cmd)
        self._stroke_painted.add((f_id, side))

    def _end_stroke(self) -> None:
        if self._stroke_commands and self._command_stack is not None:
            composite = CompositeCommand(name="Paint", children=self._stroke_commands)
            self._command_stack.push_executed(composite, self._scene)
        self._stroke_commands = []
        self._stroke_painted = set()
        self._stroke_active = False
        self._stroke_material_id = None

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        f_id = self._pick_face(event)
        self._hovered_face = f_id
        if (
            self._stroke_active
            and f_id is not None
            and self._stroke_material_id is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            side = self._resolve_side(event, f_id)
            self._paint_during_stroke(f_id, side, self._stroke_material_id)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        f_id = self._pick_face(event)
        if f_id is None or self._scene is None:
            return
        side = self._resolve_side(event, f_id)
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Eyedropper: sample the clicked side's material. Not a mutation.
            if self._set_active_material is not None:
                self._set_active_material(self._scene.face_material(f_id, side))
            return
        mat = self._active_material()
        if mat is None:
            return
        self._begin_stroke(mat.id)
        self._paint_during_stroke(f_id, side, mat.id)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:
        self._end_stroke()

    def overlay(self) -> ToolOverlay:
        fills: list[np.ndarray] = []
        mat = self._active_material()
        tint = mat.base_color if mat is not None else _NEUTRAL_COLOR
        if self._hovered_face is not None and self._scene is not None:
            try:
                from pluton.geometry.transforms import apply_mat

                wt = self._world_transform()
                use_wt = not is_identity_transform(wt)
                wt_arr = np.asarray(wt, dtype=np.float64) if use_wt else None

                def _to_world(local_pos: np.ndarray) -> np.ndarray:
                    if not use_wt:
                        return local_pos
                    return apply_mat(local_pos.reshape(1, 3), wt_arr)[0]

                loop = self._scene.face_loop(self._hovered_face)
                fills.append(
                    np.array(
                        [
                            _to_world(np.asarray(self._scene.vertex(v).position, dtype=np.float32))
                            for v in loop
                        ],
                        dtype=np.float32,
                    )
                )
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
        # Mirrors EraserTool.has_active_gesture: True only for a live stroke,
        # not for a mere hover -- so a right-click mid-drag is suppressed as
        # a cancel (ViewportWidget.contextMenuEvent) instead of popping the
        # context menu, and Esc/tool-switch semantics stay consistent with
        # the sibling drag tools.
        return self._stroke_active

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        mat = self._active_material()
        name = mat.name if mat is not None else "Default"
        return f"Paint: {name} · Alt-click to sample"

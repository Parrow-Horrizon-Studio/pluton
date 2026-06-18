"""The Scale tool (S) - bounding-box gizmo.

On activate the selection's AABB + grips are computed. Press picks the nearest
grip (screen space); its opposite is the anchor (Ctrl -> AABB centre). Drag
computes per-axis factors (corner = uniform along the diagonal; edge/face =
per-axis; Shift = uniform across driven axes). Zero-extent driven axes stay 1.
Release commits one TransformVerticesCommand. Preview is overlay-only.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.geometry.transforms import scale as scale_pts
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.transform_support import (
    GripSpec,
    grip_specs,
    selection_aabb,
    selection_vertices,
)

_GRIP_PX = 9.0
_GRIP_COLOR = (0.20, 0.75, 0.35)
_ACTIVE_COLOR = (1.0, 0.85, 0.10)
_BOX_COLOR = (0.20, 0.55, 0.95)
_EPS = 1e-3


class ScaleTool(Tool):
    @property
    def name(self) -> str:
        return "Scale"

    @property
    def shortcut(self) -> str:
        return "S"

    def __init__(self) -> None:
        self._scene = None
        self._stack = None
        self._selection = None
        self._camera = None
        self._size_provider = None
        self._units_provider = None
        self._lo = None
        self._hi = None
        self._grips: list[GripSpec] = []
        self._vertex_ids: list[int] = []
        self._orig: dict[int, np.ndarray] = {}
        self._active: GripSpec | None = None
        self._anchor = np.zeros(3, np.float32)
        self._factor_vec = np.ones(3, np.float32)

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._stack = ctx.command_stack
        self._selection = ctx.selection
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._units_provider = ctx.units_provider
        self._rebuild_box()

    def deactivate(self) -> None:
        self._reset_drag()
        self._lo = self._hi = None
        self._grips = []

    def _rebuild_box(self) -> None:
        self._reset_drag()
        self._vertex_ids = (
            selection_vertices(self._scene, self._selection)
            if self._selection is not None and not self._selection.is_empty()
            else []
        )
        box = selection_aabb(self._scene, self._vertex_ids)
        if box is None:
            self._lo = self._hi = None
            self._grips = []
            return
        self._lo, self._hi = box
        self._grips = grip_specs(self._lo, self._hi)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or not self._grips:
            return
        grip = self._pick_grip(event)
        if grip is None:
            return
        self._orig = {v: self._scene.vertex(v).position.copy() for v in self._vertex_ids}
        self._active = grip
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._anchor = (
            ((self._lo + self._hi) * 0.5).astype(np.float32) if ctrl else grip.opposite.copy()
        )
        self._factor_vec = np.ones(3, np.float32)

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._active is None:
            return
        cursor = self._cursor_world(event)
        if cursor is None:
            return
        uniform = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        extent = (self._hi - self._lo).astype(np.float32)
        self._factor_vec = self._factor_vec_for(self._active, self._anchor, cursor, extent, uniform)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or self._active is None:
            return
        cursor = self._cursor_world(event)
        if cursor is not None:
            uniform = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            extent = (self._hi - self._lo).astype(np.float32)
            self._factor_vec = self._factor_vec_for(
                self._active, self._anchor, cursor, extent, uniform
            )
        ids = self._vertex_ids
        if ids:
            pts = np.array([self._orig[v] for v in ids], np.float32)
            new = scale_pts(pts, self._anchor, self._factor_vec)
            moves = {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}
            cmd = TransformVerticesCommand(moves)
            if not cmd.is_empty() and self._stack is not None:
                self._stack.execute(cmd, self._scene)
        self._reset_drag()
        self._rebuild_box()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_drag()

    def apply_typed_value(self, text, units) -> bool:
        if self._active is None:
            return False
        try:
            factor = float(text.strip())
        except (ValueError, AttributeError):
            return False
        if factor <= 0:
            return False
        out = np.ones(3, np.float32)
        extent = (self._hi - self._lo).astype(np.float32)
        for ax in self._active.axes:
            if abs(float(extent[ax])) > 1e-9:
                out[ax] = factor
        ids = self._vertex_ids
        pts = np.array([self._orig[v] for v in ids], np.float32)
        new = scale_pts(pts, self._anchor, out)
        moves = {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}
        from pluton.commands.scene_commands import TransformVerticesCommand
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset_drag()
        self._rebuild_box()
        return True

    def overlay(self) -> ToolOverlay:
        polylines: list = []
        markers: list = []
        if self._lo is not None and self._hi is not None:
            preview_lo, preview_hi = self._lo, self._hi
            if self._active is not None:
                corners = scale_pts(
                    np.array([self._lo, self._hi], np.float32), self._anchor, self._factor_vec
                )
                preview_lo = np.minimum(corners[0], corners[1]).astype(np.float32)
                preview_hi = np.maximum(corners[0], corners[1]).astype(np.float32)
            polylines.append((self._box_segments(preview_lo, preview_hi), _BOX_COLOR, 1.5))
            for g in self._grips:
                is_active = (
                    self._active is not None and np.allclose(g.position, self._active.position)
                )
                color = _ACTIVE_COLOR if is_active else _GRIP_COLOR
                markers.append((g.position.copy(), _GRIP_PX, color))
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), np.float32),
            rubber_band_color=(1, 1, 1),
            snap_marker_position=None,
            snap_marker_color=(1, 1, 1),
            world_polylines=polylines,
            screen_markers=markers,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._active is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._active is not None:
            f = self._factor_vec
            return f"Scale ({f[0]:.2f}, {f[1]:.2f}, {f[2]:.2f})"
        return "Scale: drag a handle"

    # ---- factor math (pure; unit-tested) ----
    def _factors(self, grip, anchor, cursor, extent, uniform):  # noqa: ANN001
        """Test-facing alias; delegates to _factor_vec_for."""
        return self._factor_vec_for(grip, anchor, cursor, extent, uniform)

    def _factor_vec_for(
        self, grip: GripSpec, anchor, cursor, extent, uniform: bool
    ) -> np.ndarray:
        anchor = np.asarray(anchor, np.float32)
        cursor = np.asarray(cursor, np.float32)
        extent = np.asarray(extent, np.float32)
        out = np.ones(3, np.float32)
        driven = [ax for ax in grip.axes if abs(float(extent[ax])) > 1e-9]
        if len(grip.axes) == 3 and len(driven) >= 2:
            diag = grip.position - anchor
            dlen = float(np.linalg.norm(diag))
            if dlen > 1e-9:
                proj = float(np.dot(cursor - anchor, diag)) / dlen
                fac = max(proj / dlen, _EPS)
                for ax in driven:
                    out[ax] = fac
            return out
        for ax in driven:
            denom = float(grip.position[ax] - anchor[ax])
            if abs(denom) < 1e-9:
                continue
            out[ax] = max((float(cursor[ax]) - float(anchor[ax])) / denom, _EPS)
        if uniform and driven:
            f = float(np.max([out[ax] for ax in driven]))
            for ax in driven:
                out[ax] = f
        return out

    # ---- screen picking (camera-dependent; stubbed in unit tests) ----
    def _pick_grip(self, event) -> GripSpec | None:  # noqa: ANN001
        if self._camera is None or self._size_provider is None:
            return None
        w, h = self._size_provider()
        pos = event.position()
        best, best_d = None, _GRIP_PX * 1.6
        for g in self._grips:
            proj = self._camera.world_to_screen(g.position, w, h)
            if proj is None:
                continue
            sx, sy, _d = proj
            dist = ((sx - pos.x()) ** 2 + (sy - pos.y()) ** 2) ** 0.5
            if dist < best_d:
                best, best_d = g, dist
        return best

    def _cursor_world(self, event):  # noqa: ANN001
        """Cursor ray intersect the ground-parallel plane through the grip.

        Falls back to None if no camera. (M4d refines with axis-aware dragging.)
        """
        if self._camera is None or self._size_provider is None:
            return None
        w, h = self._size_provider()
        pos = event.position()
        origin, direction = self._camera.ray_from_screen(pos.x(), pos.y(), w, h)
        n = np.array([0, 0, 1], np.float32)
        p0 = self._active.position if self._active is not None else self._anchor
        denom = float(np.dot(direction, n))
        if abs(denom) < 1e-9:
            return None
        t = float(np.dot(p0 - origin, n)) / denom
        if t <= 0:
            return None
        return (origin + t * direction).astype(np.float32)

    def _box_segments(self, lo, hi) -> np.ndarray:
        lo = np.asarray(lo, np.float32)
        hi = np.asarray(hi, np.float32)
        c = [
            [lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]],
            [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
            [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]],
            [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]],
        ]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        segs = np.empty((2 * len(edges), 3), np.float32)
        for i, (u, v) in enumerate(edges):
            segs[2 * i] = c[u]
            segs[2 * i + 1] = c[v]
        return segs

    def _reset_drag(self) -> None:
        self._active = None
        self._anchor = np.zeros(3, np.float32)
        self._factor_vec = np.ones(3, np.float32)
        self._orig = {}

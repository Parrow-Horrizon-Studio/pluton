"""The Push/Pull tool — SketchUp-style face extrusion.

Three-state machine:
    IDLE     — no face under cursor; no overlay.
    HOVERING — cursor over a live face; that face highlighted (light blue).
    DRAGGING — face armed by click; cursor moves drive depth via line-line CPA;
               ghost prism rendered.

Click in HOVERING arms the face. Click in DRAGGING commits (or cancels if
depth < 1e-3). ESC in DRAGGING cancels. ESC in HOVERING / IDLE is handled
by MainWindow's two-stage ESC (it deactivates the tool).
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


# Visual constants (RGBA).
_HOVER_FILL_COLOR = (0.40, 0.70, 1.00, 0.20)   # light blue
_ARMED_FILL_COLOR = (0.20, 0.50, 0.95, 0.40)   # darker blue
_GHOST_FILL_COLOR = (0.40, 0.70, 1.00, 0.15)   # light blue, fainter

_MIN_COMMIT_DEPTH = 1e-3  # world units; below this is treated as cancel
_DEGENERATE_VIEW_EPSILON = 1e-4  # |1 - (d·n)²| below this freezes depth


class _State(Enum):
    IDLE = 0
    HOVERING = 1
    DRAGGING = 2


class PushPullTool(Tool):
    """SketchUp-style face extrusion tool."""

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._camera = None
        self._widget_size_provider = None

        self._state: _State = _State.IDLE

        # HOVERING data
        self._hovered_face_id: int | None = None

        # DRAGGING data (set when entering DRAGGING; cleared on exit)
        self._armed_face_id: int | None = None
        self._armed_face_loop: list[int] = []
        self._armed_face_normal: np.ndarray | None = None
        self._armed_face_center: np.ndarray | None = None
        self._current_depth: float = 0.0

    # ---- Tool ABC ------------------------------------------------------

    @property
    def name(self) -> str:
        return "Push/Pull"

    @property
    def shortcut(self) -> str:
        return "P"

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAGGING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None  # Push/Pull doesn't drive axis-lock.

    @property
    def status_text(self) -> str | None:
        if self._state == _State.DRAGGING:
            return f"depth: {self._current_depth:.3f}"
        return None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._camera = ctx.camera
        self._widget_size_provider = ctx.widget_size_provider
        self._reset_to_idle()

    def deactivate(self) -> None:
        self._reset_to_idle()

    # ---- Event handlers -----------------------------------------------

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.DRAGGING:
            self._update_depth_from_event(event)
            return
        # IDLE / HOVERING — per-frame ray-pick.
        hit = self._pick_face_under_cursor(event)
        if hit is None:
            self._state = _State.IDLE
            self._hovered_face_id = None
        else:
            self._state = _State.HOVERING
            self._hovered_face_id = hit.face_id

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.IDLE:
            return  # clicking empty space is a no-op
        if self._state == _State.HOVERING:
            self._arm_face(self._hovered_face_id)
            return
        # DRAGGING — Task 10 wires commit; Task 11 wires near-zero cancel.
        return

    def on_key_press(self, event: QKeyEvent) -> None:
        # Task 11 wires ESC cancel for DRAGGING.
        return

    def overlay(self) -> ToolOverlay:
        polygons: list[np.ndarray] = []
        if self._state == _State.HOVERING and self._hovered_face_id is not None:
            polygons = [self._loop_world_coords(self._hovered_face_id)]
        # DRAGGING overlay is added in Task 9; face_fill_color will switch to
        # _ARMED_FILL_COLOR / _GHOST_FILL_COLOR depending on state at that point.
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=(0.85, 0.85, 0.85),
            snap_marker_position=None,
            snap_marker_color=(0.85, 0.85, 0.85),
            snap_marker_kind=0,
            face_fill_polygons=polygons,
            face_fill_color=_HOVER_FILL_COLOR,
        )

    # ---- Helpers -------------------------------------------------------

    def _pick_face_under_cursor(self, event: QMouseEvent):
        """Return RayMeshHit | None for the cursor position in `event`."""
        if self._camera is None or self._widget_size_provider is None or self._scene is None:
            return None
        pos = event.position()
        width, height = self._widget_size_provider()
        origin, direction = self._camera.ray_from_screen(
            float(pos.x()), float(pos.y()), int(width), int(height)
        )
        return self._scene.ray_pick_face(origin, direction)

    def _loop_world_coords(self, face_id: int) -> np.ndarray:
        """Return the face's boundary loop as an (N, 3) float32 ndarray."""
        assert self._scene is not None, "_loop_world_coords requires an active scene"
        loop_ids = self._scene.face_loop(face_id)
        coords = np.zeros((len(loop_ids), 3), dtype=np.float32)
        for i, vid in enumerate(loop_ids):
            v = self._scene.vertex(vid)
            coords[i] = v.position
        return coords

    def _arm_face(self, face_id: int) -> None:
        """Cache the source face's data and enter DRAGGING."""
        assert self._scene is not None
        self._armed_face_id = face_id
        self._armed_face_loop = self._scene.face_loop(face_id)
        self._armed_face_normal = self._scene.face_normal(face_id)
        self._armed_face_center = self._scene.face_center(face_id)
        self._current_depth = 0.0
        self._state = _State.DRAGGING

    def _update_depth_from_event(self, event: QMouseEvent) -> None:
        """Update self._current_depth via line-line CPA between the camera ray
        and the line (face_center, +normal). Holds the previous depth if the
        view is ~parallel to the normal (degenerate case)."""
        if self._camera is None or self._widget_size_provider is None:
            return
        assert self._armed_face_normal is not None
        assert self._armed_face_center is not None

        pos = event.position()
        width, height = self._widget_size_provider()
        origin, direction = self._camera.ray_from_screen(
            float(pos.x()), float(pos.y()), int(width), int(height)
        )
        d_norm = float(np.linalg.norm(direction))
        if d_norm < 1e-9:
            return
        d_hat = direction / d_norm
        n_hat = self._armed_face_normal  # already unit
        c = self._armed_face_center

        b = float(np.dot(d_hat, n_hat))
        denom = 1.0 - b * b
        if abs(denom) < _DEGENERATE_VIEW_EPSILON:
            return  # depth frozen
        w = origin.astype(np.float32) - c
        e = float(np.dot(n_hat, w))
        d_param = float(np.dot(d_hat, w))
        t = (e - b * d_param) / denom
        self._current_depth = max(0.0, t)

    def _reset_to_idle(self) -> None:
        self._state = _State.IDLE
        self._hovered_face_id = None
        self._armed_face_id = None
        self._armed_face_loop = []
        self._armed_face_normal = None
        self._armed_face_center = None
        self._current_depth = 0.0

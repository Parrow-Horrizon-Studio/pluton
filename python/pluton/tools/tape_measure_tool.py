"""The Tape Measure tool (T) — point-to-point distance readout, and (M7.6b
Task 7) construction-guide creation.

Two distinct gestures now share the same clicks:

- A plain click (press, then release with no meaningful drag) still just
  advances the classic two-point measurement (`_a` / `_b`), exactly as
  before Task 7.
- A click-drag-release starting on an edge creates a `Guide` parallel to
  that edge, offset by the drag's perpendicular component (spec 2.4); a
  click-drag starting on a vertex, ended either by release or by typing an
  exact distance (`apply_typed_value`), creates a `GuidePoint` at that
  distance along the dragged direction.

Holding `Ctrl` at the press suppresses guide creation for that gesture and
restores the pre-Task-7 measure-only behaviour, matching SketchUp's own
Tape Measure modifier.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.annotation_commands import CreateAnnotationCommand
from pluton.geometry.transforms import is_identity_transform, mat_invert
from pluton.model.annotation import Guide, GuidePoint
from pluton.tools.annotation_support import world_to_active_local
from pluton.tools.shape_support import resolve_drawing_plane
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_LINE_COLOR = (0.95, 0.85, 0.20)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_GUIDE_PREVIEW_COLOR = (0.45, 0.45, 0.52)

# Ctrl returns the tool to its pre-Task-7 measure-only behaviour -- no Guide
# or GuidePoint is created, no matter how the gesture is dragged.
_GUIDE_SUPPRESS_MODIFIER = Qt.KeyboardModifier.ControlModifier

# World-unit thresholds below which a release/typed-value reads as "no real
# drag happened" -- a plain click -- rather than a commit. Matches
# OffsetTool's _MIN_COMMIT_DISTANCE.
_MIN_DRAG_DISTANCE = 1e-3
_EPS = 1e-9


class TapeMeasureTool(Tool):
    @property
    def name(self) -> str:
        return "Tape Measure"

    @property
    def shortcut(self) -> str:
        return "T"

    @property
    def id(self) -> str:
        return "tape_measure"

    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._units_provider = None
        self._a: np.ndarray | None = None
        self._b: np.ndarray | None = None
        self._cursor: np.ndarray | None = None
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_kind: int = 0

        # Guide/GuidePoint drag state, independent of the _a/_b measurement
        # above -- every left click opens one of these, whether or not it
        # ends up creating anything.
        self._drag_active = False
        self._drag_suppressed = False
        self._drag_press_snap = None
        self._drag_press_point: np.ndarray | None = None
        self._drag_current_point: np.ndarray | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._model = ctx.model
        self._command_stack = ctx.command_stack
        self._units_provider = ctx.units_provider
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def _world_transform(self):
        return self._model.active_world_transform if self._model is not None else None

    def _world_vec_to_local(self, world_vec: np.ndarray) -> np.ndarray:
        """A WORLD direction vector (no translation) -> the active context's
        local frame, via the inverse of the world transform's linear block --
        the same conversion `draw_plan._vec_to_world` runs in reverse."""
        wt = self._world_transform()
        world_vec = np.asarray(world_vec, dtype=np.float64)
        if is_identity_transform(wt):
            return world_vec
        inv3 = mat_invert(np.asarray(wt, dtype=np.float64))[:3, :3]
        return inv3 @ world_vec

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._cursor = np.asarray(snap.world_position, np.float32).copy()
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._drag_active:
            self._drag_current_point = np.asarray(snap.world_position, dtype=np.float64).copy()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        from pluton.viewport.snap_engine import SnapKind

        if event.button() != Qt.MouseButton.LeftButton or snap.kind == SnapKind.NONE:
            return
        p = np.asarray(snap.world_position, np.float32).copy()

        # Every left click on real geometry opens a potential guide-creating
        # drag, independent of the _a/_b measurement bookkeeping below.
        # Re-armed on EVERY press (not just the first), so a drag started
        # from the second or third click resolves against THAT click's
        # point, not a stale one from earlier in the measurement.
        self._drag_active = True
        self._drag_suppressed = bool(event.modifiers() & _GUIDE_SUPPRESS_MODIFIER)
        self._drag_press_snap = snap
        self._drag_press_point = np.asarray(snap.world_position, dtype=np.float64).copy()
        self._drag_current_point = self._drag_press_point.copy()

        if self._a is None:
            self._a = p
        elif self._b is None:
            self._b = p
        else:  # third click starts a fresh measurement
            self._a, self._b = p, None

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:
        from pluton.viewport.snap_engine import SnapKind

        if event.button() != Qt.MouseButton.LeftButton or not self._drag_active:
            return
        if snap is not None and snap.kind != SnapKind.NONE:
            self._drag_current_point = np.asarray(snap.world_position, dtype=np.float64).copy()

        press_snap = self._drag_press_snap
        suppressed = self._drag_suppressed
        press_point = self._drag_press_point
        current_point = self._drag_current_point
        self._drag_active = False
        self._drag_suppressed = False
        self._drag_press_snap = None
        self._drag_press_point = None
        self._drag_current_point = None

        if suppressed or press_snap is None or self._model is None or self._command_stack is None:
            return

        created = False
        if press_snap.edge_id is not None:
            created = self._commit_edge_guide(press_snap, press_point, current_point)
        elif press_snap.vertex_id is not None:
            created = self._commit_vertex_point(press_point, current_point)
        if created:
            self._reset()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def apply_typed_value(self, text, units) -> bool:
        from pluton.units import parse_length

        if (
            not self._drag_active
            or self._drag_suppressed
            or self._drag_press_snap is None
            or self._drag_press_snap.vertex_id is None
            or self._model is None
            or self._command_stack is None
        ):
            return False

        direction = np.asarray(self._drag_current_point, dtype=np.float64) - np.asarray(
            self._drag_press_point, dtype=np.float64
        )
        norm = float(np.linalg.norm(direction))
        if norm < _EPS:
            return False

        distance = parse_length(text, units)
        if distance is None or distance <= 0:
            return False

        target_world = (
            np.asarray(self._drag_press_point, dtype=np.float64) + (direction / norm) * distance
        )
        self._create_guide_point(target_world)
        self._reset()
        return True

    def overlay(self) -> ToolOverlay:
        polylines = []
        end = self._b if self._b is not None else self._cursor
        if self._a is not None and end is not None:
            seg = np.array([self._a, end], np.float32)
            polylines.append((seg, _LINE_COLOR, 2.0))

        preview = self._drag_preview_segment()
        if preview is not None:
            polylines.append((preview, _GUIDE_PREVIEW_COLOR, 1.0))

        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), np.float32),
            rubber_band_color=(1, 1, 1),
            snap_marker_position=(
                self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None
            ),
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
            world_polylines=polylines,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._a is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        if self._drag_active and self._drag_press_point is not None:
            return self._drag_press_point.astype(np.float32).copy()
        return self._a.copy() if self._a is not None else None

    @property
    def status_text(self):
        end = self._b if self._b is not None else self._cursor
        if self._a is None or end is None:
            return "Tape Measure: pick the first point"
        delta = np.asarray(end, np.float32) - self._a
        dist = float(np.linalg.norm(delta))
        if self._units_provider is not None:
            from pluton.units import format_length

            d = format_length(dist, self._units_provider())
            dx = format_length(abs(float(delta[0])), self._units_provider())
            dy = format_length(abs(float(delta[1])), self._units_provider())
            dz = format_length(abs(float(delta[2])), self._units_provider())
            return f"Distance {d}   Δ({dx}, {dy}, {dz})"
        return f"Distance {dist:.3f}"

    # ---- guide / guide-point creation -----------------------------------

    def _edge_direction_local(self, edge_id) -> np.ndarray | None:
        """Unit direction of `edge_id`'s two endpoints, straight from the
        scene's own (local) vertex positions -- treated as world exactly the
        way `ViewportWidget._edge_direction` and every drag tool's plane
        resolution already treats undeformed local geometry, so this stays
        consistent with the rest of the codebase rather than introducing a
        one-off stricter frame conversion Task 7 alone would carry."""
        if edge_id is None or self._scene is None:
            return None
        try:
            edge = self._scene.edge(edge_id)
            p1 = np.asarray(self._scene.vertex(edge.v1_id).position, dtype=np.float64)
            p2 = np.asarray(self._scene.vertex(edge.v2_id).position, dtype=np.float64)
        except (KeyError, AttributeError):
            return None
        d = p2 - p1
        n = float(np.linalg.norm(d))
        return None if n < _EPS else d / n

    def _resolve_offset_direction(self, press_snap) -> tuple[np.ndarray, np.ndarray] | None:
        """(perpendicular unit vector, edge unit direction), or None.

        Spec 2.4: perpendicular to the clicked edge, within the plane of the
        face that edge bounds. `resolve_drawing_plane` already implements
        exactly the face-or-fallback rule this needs -- keyed off
        `snap.face_id`, which is populated for every snap regardless of the
        winning kind (M7.6b Task 1) -- so a two-face edge resolves to
        whichever face was under the cursor at click time, and a free edge
        (no face) falls back to the gesture's drawing plane. The perpendicular
        itself is the cross product of that plane's normal with the edge
        direction, which is perpendicular to the edge and orthogonal to the
        normal by construction -- i.e. guaranteed to lie IN the plane -- and
        None only when that cross product degenerates (the edge direction is
        parallel to the plane's normal, e.g. a free vertical edge falling
        back to the horizontal ground plane: there is no direction
        perpendicular to a vertical edge that also lies in a horizontal
        plane, since the edge does not lie in that plane at all).
        """
        edge_dir = self._edge_direction_local(press_snap.edge_id)
        if edge_dir is None:
            return None
        plane = resolve_drawing_plane(press_snap, self._scene)
        perp = np.cross(plane.normal, edge_dir)
        norm = float(np.linalg.norm(perp))
        if norm < _EPS:
            return None
        return perp / norm, edge_dir

    def _commit_edge_guide(self, press_snap, press_point, current_point) -> bool:
        resolved = self._resolve_offset_direction(press_snap)
        if resolved is None:
            return False
        perp_unit, edge_dir = resolved
        raw_delta = np.asarray(current_point, dtype=np.float64) - np.asarray(
            press_point, dtype=np.float64
        )
        scalar = float(np.dot(raw_delta, perp_unit))
        if abs(scalar) < _MIN_DRAG_DISTANCE:
            return False
        origin_world = np.asarray(press_point, dtype=np.float64) + perp_unit * scalar

        origin_local = world_to_active_local(self._model, origin_world)
        direction_local = self._world_vec_to_local(edge_dir)
        guide = Guide(
            self._model.new_annotation_id(),
            tuple(float(v) for v in origin_local),
            tuple(float(v) for v in direction_local),
        )
        self._command_stack.execute(
            CreateAnnotationCommand(guide, self._model.active_context), self._model
        )
        return True

    def _commit_vertex_point(self, press_point, current_point) -> bool:
        dist = float(
            np.linalg.norm(
                np.asarray(current_point, dtype=np.float64)
                - np.asarray(press_point, dtype=np.float64)
            )
        )
        if dist < _MIN_DRAG_DISTANCE:
            return False
        self._create_guide_point(current_point)
        return True

    def _create_guide_point(self, position_world) -> None:
        local = world_to_active_local(self._model, position_world)
        point = GuidePoint(self._model.new_annotation_id(), tuple(float(v) for v in local))
        self._command_stack.execute(
            CreateAnnotationCommand(point, self._model.active_context), self._model
        )

    def _drag_preview_segment(self) -> np.ndarray | None:
        """A world-space 2-point line for the in-progress drag, or None.

        Best-effort only: overlay() is called every frame including mid-drag
        with a not-yet-resolvable direction (e.g. a free vertical edge, see
        `_resolve_offset_direction`), so any failure here just omits the
        preview rather than raising.
        """
        if (
            not self._drag_active
            or self._drag_suppressed
            or self._drag_press_snap is None
            or self._drag_press_point is None
            or self._drag_current_point is None
        ):
            return None
        press_snap = self._drag_press_snap
        press = self._drag_press_point
        current = self._drag_current_point

        if press_snap.edge_id is not None:
            resolved = self._resolve_offset_direction(press_snap)
            if resolved is None:
                return None
            perp_unit, _edge_dir = resolved
            raw_delta = np.asarray(current, dtype=np.float64) - np.asarray(press, dtype=np.float64)
            scalar = float(np.dot(raw_delta, perp_unit))
            end = press + perp_unit * scalar
        elif press_snap.vertex_id is not None:
            end = current
        else:
            return None
        return np.array([press, end], dtype=np.float32)

    def _reset(self) -> None:
        self._a = None
        self._b = None
        self._cursor = None
        self._snap_marker_pos = None
        self._snap_marker_color = _NEUTRAL_COLOR
        self._snap_marker_kind = 0
        self._drag_active = False
        self._drag_suppressed = False
        self._drag_press_snap = None
        self._drag_press_point = None
        self._drag_current_point = None

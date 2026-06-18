"""The Tape Measure tool (T) — point-to-point distance readout (measure-only)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_LINE_COLOR = (0.95, 0.85, 0.20)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class TapeMeasureTool(Tool):
    @property
    def name(self) -> str:
        return "Tape Measure"

    @property
    def shortcut(self) -> str:
        return "T"

    def __init__(self) -> None:
        self._scene = None
        self._units_provider = None
        self._a: np.ndarray | None = None
        self._b: np.ndarray | None = None
        self._cursor: np.ndarray | None = None
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_kind: int = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._units_provider = ctx.units_provider
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._cursor = np.asarray(snap.world_position, np.float32).copy()
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if event.button() != Qt.MouseButton.LeftButton or snap.kind == SnapKind.NONE:
            return
        p = np.asarray(snap.world_position, np.float32).copy()
        if self._a is None:
            self._a = p
        elif self._b is None:
            self._b = p
        else:  # third click starts a fresh measurement
            self._a, self._b = p, None

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        polylines = []
        end = self._b if self._b is not None else self._cursor
        if self._a is not None and end is not None:
            seg = np.array([self._a, end], np.float32)
            polylines.append((seg, _LINE_COLOR, 2.0))
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

    def _reset(self) -> None:
        self._a = None
        self._b = None
        self._cursor = None
        self._snap_marker_pos = None
        self._snap_marker_color = _NEUTRAL_COLOR
        self._snap_marker_kind = 0

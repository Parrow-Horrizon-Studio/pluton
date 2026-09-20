"""Acquisition and inference locking: the stateful half of the snap path.

`SnapEngine` is stateless by design. Hover-dwell acquisition needs a clock and
locking needs memory across frames, so both live here, behind an injected
`now_ms` so dwell is a value in tests and never a wall-clock timer.

`ViewportWidget._snap_for_event` is the single choke point every tool already
flows through, so wiring this in there leaves all twenty tools untouched: they
keep receiving exactly one `SnapResult`.

`AcquiredKind` and `Acquired` are defined in `snap_types.py`, not here, and
re-exported below: Task 4's candidate generators in `snap_candidates.py` need
`AcquiredKind` and must never import this (stateful) module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from pluton.viewport.snap_types import Acquired, AcquiredKind, SnapKind, SnapResult

__all__ = [
    "DWELL_MS",
    "MOVE_TOLERANCE_PX",
    "Acquired",
    "AcquiredKind",
    "InferenceState",
    "Lock",
]

DWELL_MS = 250.0
"""Milliseconds the cursor must rest on a candidate before it is acquired."""

MOVE_TOLERANCE_PX = 8.0
"""Cursor travel that restarts the dwell. Matches SnapEngine.PIXEL_TOLERANCE."""

_AXIS_DIRS = {
    0: np.array([1.0, 0.0, 0.0], dtype=np.float64),
    1: np.array([0.0, 1.0, 0.0], dtype=np.float64),
    2: np.array([0.0, 0.0, 1.0], dtype=np.float64),
}
_AXIS_NAMES = {0: "Red", 1: "Green", 2: "Blue"}

_ACQUIRABLE_VERTEX = (SnapKind.ENDPOINT,)
_ACQUIRABLE_EDGE = (SnapKind.MIDPOINT, SnapKind.ON_EDGE)


@dataclass(frozen=True, slots=True)
class Lock:
    """A pinned inference line. Wins outright, bypassing precedence."""

    origin: np.ndarray
    direction: np.ndarray
    axis: int | None
    label: str
    # "axis" | "edge" | "shift": which control armed this lock. A lock's origin
    # decides who is allowed to release it, so toggling one control never gets
    # mistaken for releasing a lock a different control armed.
    source: str


class InferenceState:
    def __init__(self, now_ms=None) -> None:
        self._now = now_ms if now_ms is not None else _default_now_ms
        self._acquired: Acquired | None = None
        self._lock: Lock | None = None
        self._pending_key: tuple[int, int] | None = None  # (kind marker, entity id)
        self._pending_since: float = 0.0
        self._pending_px: tuple[float, float] = (0.0, 0.0)
        self._pending_snap = None

    @property
    def acquired(self) -> Acquired | None:
        return self._acquired

    @property
    def lock(self) -> Lock | None:
        return self._lock

    def observe(self, snap, cursor_px, edge_direction=None) -> None:
        """Feed one frame's snap and cursor position into the dwell timer."""
        key = _acquirable_key(snap)
        if key is None:
            self._pending_key = None
            self._pending_snap = None
            return

        moved = (
            self._pending_key != key
            or float(
                np.hypot(cursor_px[0] - self._pending_px[0], cursor_px[1] - self._pending_px[1])
            )
            > MOVE_TOLERANCE_PX
        )
        if moved:
            self._pending_key = key
            self._pending_since = float(self._now())
            self._pending_px = (float(cursor_px[0]), float(cursor_px[1]))
            self._pending_snap = snap
            return

        self._pending_snap = snap
        if float(self._now()) - self._pending_since >= DWELL_MS:
            self._acquired = _acquire(snap, edge_direction)

    def clear_acquisition(self) -> None:
        self._acquired = None
        self._pending_key = None
        self._pending_snap = None

    def toggle_axis_lock(self, axis: int) -> None:
        if self._lock is not None and self._lock.source == "axis" and self._lock.axis == axis:
            self._lock = None
            return
        origin = self._acquired.position if self._acquired is not None else np.zeros(3)
        self._lock = Lock(
            origin=np.asarray(origin, dtype=np.float64).reshape(3),
            direction=_AXIS_DIRS[axis].copy(),
            axis=axis,
            label=f"on {_AXIS_NAMES[axis]} Axis",
            source="axis",
        )

    def toggle_edge_lock(self) -> None:
        """Lock to the acquired edge's direction. A no-op with no acquired edge."""
        if self._lock is not None and self._lock.source == "edge":
            self._lock = None
            return
        if self._acquired is None or self._acquired.direction is None:
            return
        self._lock = Lock(
            origin=self._acquired.position.astype(np.float64),
            direction=self._acquired.direction.astype(np.float64),
            axis=None,
            label="Parallel to Edge",
            source="edge",
        )

    def set_shift_lock(self, held: bool, snap) -> None:
        """Hold the inference currently showing. Releasing Shift clears it.

        Only a lock this same method armed (`source == "shift"`) is released
        here: MainWindow.eventFilter is installed application-wide, so any
        Shift release anywhere -- a panel, a dialog, an unrelated Shift-click --
        must not discard a lock some other control (an arrow key) armed.
        """
        if not held:
            if self._lock is not None and self._lock.source == "shift":
                self._lock = None
            return
        if self._lock is not None or snap is None:
            return
        direction = _direction_of(snap)
        if direction is None:
            return
        self._lock = Lock(
            origin=np.asarray(snap.world_position, dtype=np.float64).reshape(3),
            direction=direction,
            axis=snap.axis,
            label=snap.label,
            source="shift",
        )

    def release_lock(self) -> None:
        self._lock = None

    def end_gesture(self) -> None:
        self._lock = None
        self.clear_acquisition()

    def apply_lock(self, snap, camera, viewport_size, cursor_px):
        """Override `snap` with the locked line's nearest point to the cursor ray.

        Returns `snap` unchanged when no lock is active, so the no-lock path
        stays byte-identical to the pre-M7.6b behaviour.
        """
        if self._lock is None or camera is None or snap is None:
            return snap
        from pluton.geometry.ray import closest_points_two_lines

        width, height = int(viewport_size[0]), int(viewport_size[1])
        ray_origin, ray_dir = camera.ray_from_screen(
            float(cursor_px[0]), float(cursor_px[1]), width, height
        )
        _, _, _c_ray, c_line = closest_points_two_lines(
            ray_origin, ray_dir, self._lock.origin, self._lock.direction
        )
        return SnapResult(
            kind=SnapKind.AXIS_LOCK,
            world_position=np.asarray(c_line, dtype=np.float32),
            axis=self._lock.axis,
            vertex_id=None,
            label=self._lock.label,
            edge_id=None,
            face_id=snap.face_id,
            edge_t=None,
        )


def _default_now_ms() -> float:
    return time.monotonic() * 1000.0


def _acquirable_key(snap):
    if snap is None:
        return None
    if snap.kind in _ACQUIRABLE_VERTEX and snap.vertex_id is not None:
        return (int(AcquiredKind.VERTEX), int(snap.vertex_id))
    if snap.kind in _ACQUIRABLE_EDGE and snap.edge_id is not None:
        return (int(AcquiredKind.EDGE), int(snap.edge_id))
    return None


def _acquire(snap, edge_direction=None) -> Acquired:
    if snap.kind in _ACQUIRABLE_VERTEX:
        return Acquired(
            kind=AcquiredKind.VERTEX,
            position=np.asarray(snap.world_position, dtype=np.float64).reshape(3),
            direction=None,
            entity_id=int(snap.vertex_id),
        )
    direction = None
    if edge_direction is not None:
        d = np.asarray(edge_direction, dtype=np.float64).reshape(3)
        n = float(np.linalg.norm(d))
        direction = d / n if n >= 1e-12 else None
    return Acquired(
        kind=AcquiredKind.EDGE,
        position=np.asarray(snap.world_position, dtype=np.float64).reshape(3),
        direction=direction,
        entity_id=int(snap.edge_id),
    )


def _direction_of(snap):
    """The world direction a snap result implies, or None if it implies none."""
    if snap.axis is not None:
        return _AXIS_DIRS[snap.axis].copy()
    return None

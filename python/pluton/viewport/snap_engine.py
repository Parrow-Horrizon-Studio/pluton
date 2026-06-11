"""Snap & inference engine for M2 drawing tools.

Evaluates four snap kinds (Grid, Axis-lock, Midpoint, Endpoint) and picks
the highest-precedence one within tolerance. Precedence is encoded in the
numeric value of `SnapKind` — higher wins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from pluton.scene import Scene
from pluton.viewport.camera import Camera


class SnapKind(IntEnum):
    """Snap kinds, ordered by precedence (higher wins on a tie)."""

    NONE = 0
    GRID = 1
    AXIS_LOCK = 2
    MIDPOINT = 3
    ENDPOINT = 4
    ON_FACE = 5
    ON_EDGE = 6
    INTERSECTION = 7


@dataclass(frozen=True, slots=True)
class SnapResult:
    """The chosen snap for one cursor position."""

    kind: SnapKind
    world_position: np.ndarray
    axis: int | None  # 0=X (red), 1=Y (green), 2=Z (blue); only AXIS_LOCK
    vertex_id: int | None  # only ENDPOINT
    label: str
    edge_id: int | None = None  # MIDPOINT / ON_EDGE / INTERSECTION
    face_id: int | None = None  # ON_FACE
    edge_t: float | None = None  # parameter along edge_id (drives split_edge)


_AXIS_NAMES = {0: "Red", 1: "Green", 2: "Blue"}

# Snap-marker colors, keyed by kind. Shared by tools (overlay color); the
# renderer is shape-only. AXIS_LOCK has no marker color (the rubber-band shows
# the axis color instead).
MARKER_COLOR_BY_KIND = {
    SnapKind.GRID: (0.70, 0.70, 0.70),
    SnapKind.MIDPOINT: (0.13, 0.77, 0.84),       # cyan
    SnapKind.ENDPOINT: (0.15, 0.75, 0.26),       # green
    SnapKind.ON_EDGE: (0.89, 0.23, 0.18),        # red
    SnapKind.ON_FACE: (0.18, 0.42, 0.88),        # blue
    SnapKind.INTERSECTION: (0.82, 0.23, 0.82),   # magenta
}

# Precedence, highest first. Decoupled from the enum's integer values.
_PRECEDENCE = [
    SnapKind.ENDPOINT,
    SnapKind.INTERSECTION,
    SnapKind.MIDPOINT,
    SnapKind.ON_EDGE,
    SnapKind.ON_FACE,
    SnapKind.AXIS_LOCK,
    SnapKind.GRID,
]
_PRECEDENCE_RANK = {k: i for i, k in enumerate(_PRECEDENCE)}  # lower = higher precedence


@dataclass
class _Candidate:
    """One in-tolerance snap candidate, before precedence selection."""

    kind: SnapKind
    world_position: np.ndarray
    screen_dist: float
    depth: float
    label: str
    vertex_id: int | None = None
    edge_id: int | None = None
    face_id: int | None = None
    axis: int | None = None
    edge_t: float | None = None


class SnapEngine:
    """SketchUp-style snap & inference engine."""

    PIXEL_TOLERANCE = 8.0  # screen-space, endpoint & midpoint
    AXIS_DEG_TOLERANCE = 5.0  # angular tolerance for axis-lock
    GRID_SIZE_WORLD = 1.0  # 1 m grid spacing matches M1

    def snap(
        self,
        cursor_world_on_ground: np.ndarray | None,
        cursor_screen: tuple[float, float],
        camera: Camera,
        scene: Scene,
        anchor: np.ndarray | None = None,
    ) -> SnapResult:
        """Return the chosen snap for the given cursor."""
        if cursor_world_on_ground is None:
            return SnapResult(
                kind=SnapKind.NONE,
                world_position=np.zeros(3, dtype=np.float32),
                axis=None,
                vertex_id=None,
                label="—",
            )

        if scene is None:
            return SnapResult(
                kind=SnapKind.NONE,
                world_position=np.zeros(3, dtype=np.float32),
                axis=None,
                vertex_id=None,
                label="—",
            )

        # Pixel→world tolerance is approximated as a fixed constant for M2.
        # Rationale: at the default camera distance (~12 m from target) and
        # FOV (45°), 8 px ≈ 0.05–0.2 m depending on cursor depth. The simple
        # constant 0.2 m fits PIXEL_TOLERANCE=8 at depth ~10 m, which is
        # comfortably the M2 use case. M4 can refine this once we have hits
        # on faces at varying depths.
        world_tolerance = 0.2

        # --- Endpoint: highest precedence ----------------------------------
        endpoint_vid = scene.find_vertex_near(cursor_world_on_ground, world_tolerance)
        if endpoint_vid is not None:
            return SnapResult(
                kind=SnapKind.ENDPOINT,
                world_position=scene.vertex(endpoint_vid).position.copy(),
                axis=None,
                vertex_id=endpoint_vid,
                label="Endpoint",
            )

        # --- Midpoint -------------------------------------------------------
        best_midpoint = None
        best_md2 = world_tolerance * world_tolerance
        for e in scene.edges_iter():
            p1 = scene.vertex(e.v1_id).position
            p2 = scene.vertex(e.v2_id).position
            mid = (p1 + p2) * 0.5
            d = mid - cursor_world_on_ground
            d2 = float(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            if d2 <= best_md2:
                best_md2 = d2
                best_midpoint = mid.astype(np.float32)
        if best_midpoint is not None:
            return SnapResult(
                kind=SnapKind.MIDPOINT,
                world_position=best_midpoint,
                axis=None,
                vertex_id=None,
                label="Midpoint",
            )

        # --- Axis-lock (only when drawing — anchor is set) -----------------
        if anchor is not None:
            delta = cursor_world_on_ground - anchor
            length_xy = math.hypot(float(delta[0]), float(delta[1]))
            if length_xy > 1e-6:
                # Angles in radians: 0 = +X axis, π/2 = +Y axis.
                angle = math.atan2(float(delta[1]), float(delta[0]))
                tol_rad = math.radians(self.AXIS_DEG_TOLERANCE)
                # Distance to nearest axis direction (0, ±π for X; ±π/2 for Y).
                # Z axis (vertical) is only relevant when drawing off-ground —
                # in M2 we're always on Z=0 so Z-lock never fires.
                deltas = {
                    0: min(abs(angle), abs(abs(angle) - math.pi)),  # X axis
                    1: abs(abs(angle) - math.pi / 2.0),  # Y axis
                }
                best_axis = min(deltas, key=deltas.get)
                if deltas[best_axis] <= tol_rad:
                    # Project the cursor onto the locked axis line through anchor.
                    if best_axis == 0:
                        projected = np.array(
                            [cursor_world_on_ground[0], anchor[1], 0.0], dtype=np.float32
                        )
                    else:
                        projected = np.array(
                            [anchor[0], cursor_world_on_ground[1], 0.0], dtype=np.float32
                        )
                    return SnapResult(
                        kind=SnapKind.AXIS_LOCK,
                        world_position=projected,
                        axis=best_axis,
                        vertex_id=None,
                        label=f"on {_AXIS_NAMES[best_axis]} Axis",
                    )

        # --- Grid (always available on the ground plane) -------------------
        gx = round(float(cursor_world_on_ground[0]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
        gy = round(float(cursor_world_on_ground[1]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
        return SnapResult(
            kind=SnapKind.GRID,
            world_position=np.array([gx, gy, 0.0], dtype=np.float32),
            axis=None,
            vertex_id=None,
            label="Grid",
        )


def _closest_points_two_lines(p1, d1, p2, d2):
    """Closest points between two infinite lines L1=p1+s*d1, L2=p2+t*d2.

    Returns (s, t, c1, c2). For parallel lines s=0 (and t follows). All inputs
    are float32 (3,) numpy arrays; d1/d2 need not be unit length.
    """
    r = p1 - p2
    a = float(np.dot(d1, d1))
    e = float(np.dot(d2, d2))
    f = float(np.dot(d2, r))
    b = float(np.dot(d1, d2))
    c = float(np.dot(d1, r))
    denom = a * e - b * b
    s = 0.0 if abs(denom) < 1e-12 else (b * f - c * e) / denom
    t = (b * s + f) / e if e > 1e-12 else 0.0
    c1 = p1 + s * d1
    c2 = p2 + t * d2
    return s, t, c1.astype(np.float32), c2.astype(np.float32)


def _closest_point_on_segment_to_ray(ray_origin, ray_dir, a, b):
    """Closest point ON segment [a, b] to the (infinite) ray line. Returns
    (point, t) with t clamped to [0, 1]."""
    d2 = b - a
    _, t, _, _ = _closest_points_two_lines(ray_origin, ray_dir, a, d2)
    t = max(0.0, min(1.0, t))
    return (a + t * d2).astype(np.float32), float(t)

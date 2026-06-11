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

    PIXEL_TOLERANCE = 8.0  # screen-space proximity for point/edge inferences
    AXIS_DEG_TOLERANCE = 5.0
    GRID_SIZE_WORLD = 1.0

    def snap(self, cursor_screen, viewport_size, camera, scene, anchor=None) -> SnapResult:
        """Return the chosen 3D snap for the given cursor.

        cursor_screen: (px, py) pixel coords. viewport_size: (width, height).
        The cursor ray and ground hit are derived internally from the camera.
        """
        if cursor_screen is None or camera is None or scene is None:
            return self._none()
        px, py = float(cursor_screen[0]), float(cursor_screen[1])
        width = int(viewport_size[0])
        height = int(viewport_size[1])
        ray_origin, ray_dir = camera.ray_from_screen(px, py, width, height)
        ground_hit = camera.ray_intersect_ground(px, py, width, height)

        cands: list[_Candidate] = []
        cands += self._endpoint_candidates(px, py, width, height, camera, scene)
        cands += self._edge_point_candidates(
            px, py, width, height, camera, scene, ray_origin, ray_dir
        )
        # On-Edge / On-Face plug in here (Task 9); Axis / Intersection (Task 10).

        within = [c for c in cands if c.screen_dist <= self.PIXEL_TOLERANCE]
        if within:
            return self._to_result(self._select(within))

        if ground_hit is not None:
            gx = round(float(ground_hit[0]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            gy = round(float(ground_hit[1]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            return SnapResult(
                kind=SnapKind.GRID,
                world_position=np.array([gx, gy, 0.0], dtype=np.float32),
                axis=None, vertex_id=None, label="Grid",
            )
        return self._none()

    # --- selection --------------------------------------------------------

    def _select(self, candidates: list[_Candidate]) -> _Candidate:
        return min(candidates, key=lambda c: (_PRECEDENCE_RANK[c.kind], c.depth))

    def _to_result(self, c: _Candidate) -> SnapResult:
        return SnapResult(
            kind=c.kind,
            world_position=np.asarray(c.world_position, dtype=np.float32),
            axis=c.axis,
            vertex_id=c.vertex_id,
            label=c.label,
            edge_id=c.edge_id,
            face_id=c.face_id,
            edge_t=c.edge_t,
        )

    def _none(self) -> SnapResult:
        return SnapResult(
            kind=SnapKind.NONE,
            world_position=np.zeros(3, dtype=np.float32),
            axis=None, vertex_id=None, label="—",
        )

    # --- candidate generators --------------------------------------------

    def _endpoint_candidates(self, px, py, width, height, camera, scene):
        out: list[_Candidate] = []
        for v in scene.vertices_iter():
            proj = camera.world_to_screen(v.position, width, height)
            if proj is None:
                continue
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= self.PIXEL_TOLERANCE:
                out.append(_Candidate(
                    kind=SnapKind.ENDPOINT, world_position=v.position.copy(),
                    screen_dist=d, depth=depth, label="Endpoint", vertex_id=v.id,
                ))
        return out

    def _edge_point_candidates(self, px, py, width, height, camera, scene, ray_origin, ray_dir):
        """Midpoint candidates (On-Edge is added in Task 9 into this method)."""
        out: list[_Candidate] = []
        for e in scene.edges_iter():
            p1 = scene.vertex(e.v1_id).position
            p2 = scene.vertex(e.v2_id).position
            mid = (p1 + p2) * 0.5
            proj = camera.world_to_screen(mid, width, height)
            if proj is not None:
                sx, sy, depth = proj
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.MIDPOINT, world_position=mid.astype(np.float32),
                        screen_dist=d, depth=depth, label="Midpoint",
                        edge_id=e.id, edge_t=0.5,
                    ))
        return out


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

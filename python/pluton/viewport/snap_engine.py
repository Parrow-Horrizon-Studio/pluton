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

from pluton.geometry.transforms import apply_mat, is_identity_transform, mat_invert
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

_INTERSECTION_EPS = 1e-3  # world-space closest-approach below this = a real crossing
_AXIS_DIRS = {
    0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
    2: np.array([0.0, 0.0, 1.0], dtype=np.float32),
}

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

    def snap(self, cursor_screen, viewport_size, camera, scene, anchor=None, world_transform=None) -> SnapResult:
        """Return the chosen 3D snap for the given cursor.

        cursor_screen: (px, py) pixel coords. viewport_size: (width, height).
        The cursor ray and ground hit are derived internally from the camera.

        world_transform: optional (4,4) matrix mapping local (scene) coords to world.
        None or identity → behaviour is identical to the no-arg call (regression-safe).
        When non-identity, vertex/edge positions are transformed to world before screen
        projection, and the camera ray is transformed to local space for face picking.
        """
        if cursor_screen is None or camera is None or scene is None:
            return self._none()
        px, py = float(cursor_screen[0]), float(cursor_screen[1])
        width = int(viewport_size[0])
        height = int(viewport_size[1])
        ray_origin, ray_dir = camera.ray_from_screen(px, py, width, height)
        ground_hit = camera.ray_intersect_ground(px, py, width, height)

        # world_transform support: local→world for screen projections; world→local for ray.
        use_wt = not is_identity_transform(world_transform)
        if use_wt:
            wt = np.asarray(world_transform, dtype=np.float64)
            inv = mat_invert(wt)

            def _to_world(local_pos):
                return apply_mat(local_pos, wt)[0]

            # Camera ray in local space (for face picking).
            ray_origin_local = apply_mat(ray_origin, inv)[0]
            ray_dir_local = (inv[:3, :3] @ np.asarray(ray_dir, dtype=np.float64)).astype(np.float32)
        else:
            def _to_world(local_pos):  # type: ignore[misc]
                return local_pos

            ray_origin_local = ray_origin
            ray_dir_local = ray_dir

        cands: list[_Candidate] = []
        cands += self._endpoint_candidates(px, py, width, height, camera, scene, _to_world)
        cands += self._edge_point_candidates(
            px, py, width, height, camera, scene, ray_origin, ray_dir, _to_world,
            ray_origin_local, ray_dir_local,
        )
        face_cand = self._face_candidate(ray_origin_local, ray_dir_local, scene)
        if face_cand is not None:
            if use_wt:
                # Surface the snap result in world space.
                face_cand.world_position = apply_mat(face_cand.world_position, wt)[0]
            cands.append(face_cand)
        if anchor is not None:
            a = np.asarray(anchor, dtype=np.float32)
            cands += self._axis_candidates(px, py, width, height, camera, a, ray_origin, ray_dir)
            cands += self._intersection_candidates(px, py, width, height, camera, scene, a)

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

    def _endpoint_candidates(self, px, py, width, height, camera, scene, _to_world=None):
        if _to_world is None:
            def _to_world(p):  # type: ignore[misc]
                return p
        out: list[_Candidate] = []
        for v in scene.vertices_iter():
            world_pos = _to_world(v.position)
            proj = camera.world_to_screen(world_pos, width, height)
            if proj is None:
                continue
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= self.PIXEL_TOLERANCE:
                out.append(_Candidate(
                    kind=SnapKind.ENDPOINT, world_position=np.asarray(world_pos, dtype=np.float32),
                    screen_dist=d, depth=depth, label="Endpoint", vertex_id=v.id,
                ))
        return out

    def _edge_point_candidates(
        self, px, py, width, height, camera, scene, ray_origin, ray_dir,
        _to_world=None, ray_origin_local=None, ray_dir_local=None,
    ):
        """Midpoint AND On-Edge candidates for each live edge.

        The Midpoint block projects the geometric midpoint of each edge.
        The On-Edge block uses `ray_origin`/`ray_dir` (the cursor ray) to find
        the closest point on the 3D segment to the ray, producing an ON_EDGE
        candidate whenever that projected point is within pixel tolerance.

        _to_world: optional callable that maps a local position to world space.
        ray_origin_local / ray_dir_local: the camera ray in local space (for
        finding the closest point on local-space segments).
        """
        if _to_world is None:
            def _to_world(p):  # type: ignore[misc]
                return p
        if ray_origin_local is None:
            ray_origin_local = ray_origin
        if ray_dir_local is None:
            ray_dir_local = ray_dir

        out: list[_Candidate] = []
        for e in scene.edges_iter():
            p1 = scene.vertex(e.v1_id).position
            p2 = scene.vertex(e.v2_id).position
            # Work in local space for segment math; project world positions to screen.
            mid_local = (p1 + p2) * 0.5
            mid_world = _to_world(mid_local)
            proj = camera.world_to_screen(mid_world, width, height)
            if proj is not None:
                sx, sy, depth = proj
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.MIDPOINT,
                        world_position=np.asarray(mid_world, dtype=np.float32),
                        screen_dist=d, depth=depth, label="Midpoint",
                        edge_id=e.id, edge_t=0.5,
                    ))
            # On-Edge: closest point on the local 3D segment to the local cursor ray.
            on_pt_local, t = _closest_point_on_segment_to_ray(ray_origin_local, ray_dir_local, p1, p2)
            on_pt_world = _to_world(on_pt_local)
            proj_e = camera.world_to_screen(on_pt_world, width, height)
            if proj_e is not None:
                sx, sy, depth = proj_e
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.ON_EDGE,
                        world_position=np.asarray(on_pt_world, dtype=np.float32),
                        screen_dist=d, depth=depth, label="On Edge",
                        edge_id=e.id, edge_t=t,
                    ))
        return out

    def _axis_candidates(self, px, py, width, height, camera, anchor, ray_origin, ray_dir):
        out: list[_Candidate] = []
        for axis_idx, axis_dir in _AXIS_DIRS.items():
            # Point on the infinite axis line (through anchor) nearest the cursor ray.
            _, _, _c_ray, c_axis = _closest_points_two_lines(ray_origin, ray_dir, anchor, axis_dir)
            proj = camera.world_to_screen(c_axis, width, height)
            if proj is None:
                continue
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= self.PIXEL_TOLERANCE:
                out.append(_Candidate(
                    kind=SnapKind.AXIS_LOCK, world_position=c_axis,
                    screen_dist=d, depth=depth,
                    label=f"on {_AXIS_NAMES[axis_idx]} Axis", axis=axis_idx,
                ))
        return out

    def _intersection_candidates(self, px, py, width, height, camera, scene, anchor):
        out: list[_Candidate] = []
        for axis_idx, axis_dir in _AXIS_DIRS.items():
            for e in scene.edges_iter():
                a = scene.vertex(e.v1_id).position
                b = scene.vertex(e.v2_id).position
                seg_dir = b - a
                _, t, c_axis, c_edge = _closest_points_two_lines(anchor, axis_dir, a, seg_dir)
                if t < 0.0 or t > 1.0:
                    continue  # crossing lies outside the edge segment
                if float(np.linalg.norm(c_axis - c_edge)) > _INTERSECTION_EPS:
                    continue  # skew — no genuine 3D crossing
                proj = camera.world_to_screen(c_edge, width, height)
                if proj is None:
                    continue
                sx, sy, depth = proj
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.INTERSECTION, world_position=c_edge,
                        screen_dist=d, depth=depth, label="Intersection",
                        edge_id=e.id, edge_t=float(t),
                    ))
        return out

    def _face_candidate(self, ray_origin, ray_dir, scene):
        """On-Face via the C++ ray-mesh pick. Screen distance is 0 (under cursor)."""
        hit = scene.ray_pick_face(ray_origin, ray_dir)
        if hit is None:
            return None
        point = np.array([hit.point[0], hit.point[1], hit.point[2]], dtype=np.float32)
        return _Candidate(
            kind=SnapKind.ON_FACE, world_position=point,
            screen_dist=0.0, depth=float(hit.t), label="On Face",
            face_id=int(hit.face_id),
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

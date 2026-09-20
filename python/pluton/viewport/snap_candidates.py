"""Pure snap candidate generators.

Each function turns geometry plus a cursor ray into zero or more `Candidate`s.
No engine state, no acquisition, no locking: those live in `snap_engine.py` and
`inference.py` respectively. Split out of `snap_engine.py` in M7.6b so the file
that gained six new generators did not also own the selection policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pluton.geometry.ray import (
    closest_point_on_segment_to_ray as _closest_point_on_segment_to_ray,
)
from pluton.geometry.ray import (
    closest_points_two_lines as _closest_points_two_lines,
)

if TYPE_CHECKING:
    # snap_engine imports this module, so a runtime top-level import of SnapKind
    # here would deadlock on the circular import. Each function below imports it
    # locally instead; this guarded import only serves the `Candidate.kind` annotation.
    from pluton.viewport.snap_engine import SnapKind

_AXIS_NAMES = {0: "Red", 1: "Green", 2: "Blue"}

_INTERSECTION_EPS = 1e-3  # world-space closest-approach below this = a real crossing
_AXIS_DIRS = {
    0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
    2: np.array([0.0, 0.0, 1.0], dtype=np.float32),
}


@dataclass
class Candidate:
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


def endpoint_candidates(px, py, width, height, camera, scene, to_world, pixel_tolerance):
    from pluton.viewport.snap_engine import SnapKind

    out: list[Candidate] = []
    for v in scene.vertices_iter():
        world_pos = to_world(v.position)
        proj = camera.world_to_screen(world_pos, width, height)
        if proj is None:
            continue
        sx, sy, depth = proj
        d = math.hypot(sx - px, sy - py)
        if d <= pixel_tolerance:
            out.append(
                Candidate(
                    kind=SnapKind.ENDPOINT,
                    world_position=np.asarray(world_pos, dtype=np.float32),
                    screen_dist=d,
                    depth=depth,
                    label="Endpoint",
                    vertex_id=v.id,
                )
            )
    return out


def edge_point_candidates(
    px,
    py,
    width,
    height,
    camera,
    scene,
    ray_origin,
    ray_dir,
    to_world,
    ray_origin_local=None,
    ray_dir_local=None,
    *,
    pixel_tolerance,
):
    """Midpoint AND On-Edge candidates for each live edge.

    The Midpoint block projects the geometric midpoint of each edge.
    The On-Edge block uses `ray_origin`/`ray_dir` (the cursor ray) to find
    the closest point on the 3D segment to the ray, producing an ON_EDGE
    candidate whenever that projected point is within pixel tolerance.

    to_world: callable that maps a local position to world space.
    ray_origin_local / ray_dir_local: the camera ray in local space (for
    finding the closest point on local-space segments).
    """
    from pluton.viewport.snap_engine import SnapKind

    if ray_origin_local is None:
        ray_origin_local = ray_origin
    if ray_dir_local is None:
        ray_dir_local = ray_dir

    out: list[Candidate] = []
    for e in scene.edges_iter():
        p1 = scene.vertex(e.v1_id).position
        p2 = scene.vertex(e.v2_id).position
        # Work in local space for segment math; project world positions to screen.
        mid_local = (p1 + p2) * 0.5
        mid_world = to_world(mid_local)
        proj = camera.world_to_screen(mid_world, width, height)
        if proj is not None:
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= pixel_tolerance:
                out.append(
                    Candidate(
                        kind=SnapKind.MIDPOINT,
                        world_position=np.asarray(mid_world, dtype=np.float32),
                        screen_dist=d,
                        depth=depth,
                        label="Midpoint",
                        edge_id=e.id,
                        edge_t=0.5,
                    )
                )
        # On-Edge: closest point on the local 3D segment to the local cursor ray.
        on_pt_local, t = _closest_point_on_segment_to_ray(ray_origin_local, ray_dir_local, p1, p2)
        on_pt_world = to_world(on_pt_local)
        proj_e = camera.world_to_screen(on_pt_world, width, height)
        if proj_e is not None:
            sx, sy, depth = proj_e
            d = math.hypot(sx - px, sy - py)
            if d <= pixel_tolerance:
                out.append(
                    Candidate(
                        kind=SnapKind.ON_EDGE,
                        world_position=np.asarray(on_pt_world, dtype=np.float32),
                        screen_dist=d,
                        depth=depth,
                        label="On Edge",
                        edge_id=e.id,
                        edge_t=t,
                    )
                )
    return out


def axis_candidates(px, py, width, height, camera, anchor, ray_origin, ray_dir, pixel_tolerance):
    from pluton.viewport.snap_engine import SnapKind

    out: list[Candidate] = []
    for axis_idx, axis_dir in _AXIS_DIRS.items():
        # Point on the infinite axis line (through anchor) nearest the cursor ray.
        _, _, _c_ray, c_axis = _closest_points_two_lines(ray_origin, ray_dir, anchor, axis_dir)
        proj = camera.world_to_screen(c_axis, width, height)
        if proj is None:
            continue
        sx, sy, depth = proj
        d = math.hypot(sx - px, sy - py)
        if d <= pixel_tolerance:
            out.append(
                Candidate(
                    kind=SnapKind.AXIS_LOCK,
                    world_position=c_axis,
                    screen_dist=d,
                    depth=depth,
                    label=f"on {_AXIS_NAMES[axis_idx]} Axis",
                    axis=axis_idx,
                )
            )
    return out


def intersection_candidates(px, py, width, height, camera, scene, anchor, pixel_tolerance):
    from pluton.viewport.snap_engine import SnapKind

    out: list[Candidate] = []
    for _axis_idx, axis_dir in _AXIS_DIRS.items():
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
            if d <= pixel_tolerance:
                out.append(
                    Candidate(
                        kind=SnapKind.INTERSECTION,
                        world_position=c_edge,
                        screen_dist=d,
                        depth=depth,
                        label="Intersection",
                        edge_id=e.id,
                        edge_t=float(t),
                    )
                )
    return out


def face_candidate(ray_origin, ray_dir, scene):
    """On-Face via the C++ ray-mesh pick. Screen distance is 0 (under cursor)."""
    from pluton.viewport.snap_engine import SnapKind

    hit = scene.ray_pick_face(ray_origin, ray_dir)
    if hit is None:
        return None
    point = np.array([hit.point[0], hit.point[1], hit.point[2]], dtype=np.float32)
    return Candidate(
        kind=SnapKind.ON_FACE,
        world_position=point,
        screen_dist=0.0,
        depth=float(hit.t),
        label="On Face",
        face_id=int(hit.face_id),
    )

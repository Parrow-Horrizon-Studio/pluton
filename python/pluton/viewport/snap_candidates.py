"""Pure snap candidate generators.

Each function turns geometry plus a cursor ray into zero or more `Candidate`s.
No engine state, no acquisition, no locking: those live in `snap_engine.py` and
`inference.py` respectively. Split out of `snap_engine.py` in M7.6b so the file
that gained six new generators did not also own the selection policy.

`Candidate` and `SnapKind` come from `snap_types.py`, not `snap_engine.py`: this
module and `snap_engine` share that vocabulary without importing each other.
"""

from __future__ import annotations

import math

import numpy as np

from pluton.geometry.ray import (
    closest_point_on_segment_to_ray as _closest_point_on_segment_to_ray,
)
from pluton.geometry.ray import (
    closest_points_two_lines as _closest_points_two_lines,
)
from pluton.viewport.snap_types import AcquiredKind, Candidate, SnapKind

_AXIS_NAMES = {0: "Red", 1: "Green", 2: "Blue"}

_INTERSECTION_EPS = 1e-3  # world-space closest-approach below this = a real crossing
_AXIS_DIRS = {
    0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
    2: np.array([0.0, 0.0, 1.0], dtype=np.float32),
}


def endpoint_candidates(px, py, width, height, camera, scene, to_world, pixel_tolerance):
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


_PLANE_PARALLEL_EPS = 1e-4
"""abs(dot(n, d)) above 1 - this means cross(n, d) is too short to normalise."""


def _line_candidate(
    px, py, width, height, camera, origin, direction, kind, label, pixel_tolerance, axis=None
):
    """One candidate on the infinite line through `origin` along `direction`.

    The same shape axis_candidates already uses: the point on the line nearest
    the cursor ray, projected and tested against the pixel tolerance.
    """
    ray_origin, ray_dir = camera.ray_from_screen(px, py, width, height)
    _, _, _c_ray, c_line = _closest_points_two_lines(ray_origin, ray_dir, origin, direction)
    proj = camera.world_to_screen(c_line, width, height)
    if proj is None:
        return None
    sx, sy, depth = proj
    d = math.hypot(sx - px, sy - py)
    if d > pixel_tolerance:
        return None
    return Candidate(
        kind=kind,
        world_position=np.asarray(c_line, dtype=np.float32),
        screen_dist=d,
        depth=depth,
        label=label,
        axis=axis,
    )


def directional_candidates(
    px, py, width, height, camera, anchor, acquired, plane_normal, pixel_tolerance
):
    """PARALLEL and PERPENDICULAR against an acquired EDGE, from the anchor.

    Parallel is well defined in 3D: the line through the anchor along the edge.
    Perpendicular is not, so it resolves inside the drawing plane. When the edge
    runs along the plane normal the cross product degenerates and NO candidate is
    offered, rather than a guessed direction.
    """
    out = []
    if acquired is None or acquired.kind != AcquiredKind.EDGE or acquired.direction is None:
        return out
    if anchor is None:
        return out

    origin = np.asarray(anchor, dtype=np.float64).reshape(3)
    d = np.asarray(acquired.direction, dtype=np.float64).reshape(3)

    cand = _line_candidate(
        px,
        py,
        width,
        height,
        camera,
        origin,
        d,
        SnapKind.PARALLEL,
        "Parallel to Edge",
        pixel_tolerance,
    )
    if cand is not None:
        out.append(cand)

    if plane_normal is not None:
        n = np.asarray(plane_normal, dtype=np.float64).reshape(3)
        ln = float(np.linalg.norm(n))
        if ln > 0.0:
            n = n / ln
            if abs(float(np.dot(n, d))) <= 1.0 - _PLANE_PARALLEL_EPS:
                perp = np.cross(n, d)
                perp = perp / float(np.linalg.norm(perp))
                cand = _line_candidate(
                    px,
                    py,
                    width,
                    height,
                    camera,
                    origin,
                    perp,
                    SnapKind.PERPENDICULAR,
                    "Perpendicular to Edge",
                    pixel_tolerance,
                )
                if cand is not None:
                    out.append(cand)
    return out


def from_point_candidates(px, py, width, height, camera, acquired, pixel_tolerance):
    """The three axis lines radiating from an acquired VERTEX.

    Anchored at the acquired point, not at the gesture anchor: the whole purpose
    is aligning to geometry the line never touches.
    """
    out = []
    if acquired is None or acquired.kind != AcquiredKind.VERTEX:
        return out
    origin = np.asarray(acquired.position, dtype=np.float64).reshape(3)
    for axis_idx, axis_dir in _AXIS_DIRS.items():
        cand = _line_candidate(
            px,
            py,
            width,
            height,
            camera,
            origin,
            np.asarray(axis_dir, dtype=np.float64),
            SnapKind.FROM_POINT,
            f"From Point on {_AXIS_NAMES[axis_idx]} Axis",
            pixel_tolerance,
            axis=axis_idx,
        )
        if cand is not None:
            out.append(cand)
    return out


def face_candidate(ray_origin, ray_dir, scene):
    """On-Face via the C++ ray-mesh pick. Screen distance is 0 (under cursor)."""
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

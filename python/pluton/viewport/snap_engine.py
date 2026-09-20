"""Snap & inference engine for M2 drawing tools.

Evaluates four snap kinds (Grid, Axis-lock, Midpoint, Endpoint) and picks
the highest-precedence one within tolerance. Precedence is encoded in the
numeric value of `SnapKind` — higher wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from pluton.geometry.ray import (
    closest_point_on_segment_to_ray as _closest_point_on_segment_to_ray,
)
from pluton.geometry.ray import (
    closest_points_two_lines as _closest_points_two_lines,
)
from pluton.geometry.transforms import apply_mat, is_identity_transform, mat_invert
from pluton.viewport.snap_candidates import Candidate as _Candidate
from pluton.viewport.snap_candidates import (
    axis_candidates as _axis_candidates,
)
from pluton.viewport.snap_candidates import (
    edge_point_candidates as _edge_point_candidates,
)
from pluton.viewport.snap_candidates import (
    endpoint_candidates as _endpoint_candidates,
)
from pluton.viewport.snap_candidates import (
    face_candidate as _face_candidate,
)
from pluton.viewport.snap_candidates import (
    intersection_candidates as _intersection_candidates,
)

# `_closest_point_on_segment_to_ray` and `_closest_points_two_lines` are no longer
# called from this module directly (their call sites moved to snap_candidates.py
# with the generators that used them); they are kept importable from here (and
# listed below so lint does not treat them as unused) because existing code,
# including tests/test_snap_engine.py, imports them from this module by name.
__all__ = [
    "_closest_point_on_segment_to_ray",
    "_closest_points_two_lines",
]


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


# Snap-marker colors, keyed by kind. Shared by tools (overlay color); the
# renderer is shape-only. AXIS_LOCK has no marker color (the rubber-band shows
# the axis color instead).
MARKER_COLOR_BY_KIND = {
    SnapKind.GRID: (0.70, 0.70, 0.70),
    SnapKind.MIDPOINT: (0.13, 0.77, 0.84),  # cyan
    SnapKind.ENDPOINT: (0.15, 0.75, 0.26),  # green
    SnapKind.ON_EDGE: (0.89, 0.23, 0.18),  # red
    SnapKind.ON_FACE: (0.18, 0.42, 0.88),  # blue
    SnapKind.INTERSECTION: (0.82, 0.23, 0.82),  # magenta
}

# Precedence, highest first. Decoupled from the enum's integer values.
#
# ON_FACE sits second from last, above only the GRID fallback. Its candidate is
# ALWAYS in tolerance whenever the cursor ray hits a face, because the candidate's
# position is the ray-face intersection and therefore reprojects onto the cursor.
# Ranking it high meant it swallowed every directional inference while drawing on
# a face, which is the ordinary case. The face itself is not lost: `snap()` copies
# `face_id` onto whichever candidate wins.
_PRECEDENCE = [
    SnapKind.ENDPOINT,
    SnapKind.INTERSECTION,
    SnapKind.MIDPOINT,
    SnapKind.ON_EDGE,
    SnapKind.AXIS_LOCK,
    SnapKind.ON_FACE,
    SnapKind.GRID,
]
_PRECEDENCE_RANK = {k: i for i, k in enumerate(_PRECEDENCE)}  # lower = higher precedence


class SnapEngine:
    """SketchUp-style snap & inference engine."""

    PIXEL_TOLERANCE = 8.0  # screen-space proximity for point/edge inferences
    AXIS_DEG_TOLERANCE = 5.0
    GRID_SIZE_WORLD = 1.0

    def snap(
        self, cursor_screen, viewport_size, camera, scene, anchor=None, world_transform=None
    ) -> SnapResult:
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
        cands += _endpoint_candidates(
            px, py, width, height, camera, scene, _to_world, self.PIXEL_TOLERANCE
        )
        cands += _edge_point_candidates(
            px,
            py,
            width,
            height,
            camera,
            scene,
            ray_origin,
            ray_dir,
            _to_world,
            ray_origin_local,
            ray_dir_local,
            pixel_tolerance=self.PIXEL_TOLERANCE,
        )
        face_cand = _face_candidate(ray_origin_local, ray_dir_local, scene)
        if face_cand is not None:
            if use_wt:
                # Surface the snap result in world space.
                face_cand.world_position = apply_mat(face_cand.world_position, wt)[0]
            cands.append(face_cand)
        if anchor is not None:
            a = np.asarray(anchor, dtype=np.float32)
            cands += _axis_candidates(
                px, py, width, height, camera, a, ray_origin, ray_dir, self.PIXEL_TOLERANCE
            )
            cands += _intersection_candidates(
                px, py, width, height, camera, scene, a, self.PIXEL_TOLERANCE
            )

        within = [c for c in cands if c.screen_dist <= self.PIXEL_TOLERANCE]
        if within:
            chosen = self._select(within)
            # The face under the cursor rides every result, not only an ON_FACE
            # win. Tools resolve their drawing plane from it, and a snap to a
            # face's own corner or midpoint is still a snap ON that face: keying
            # the plane off the winning KIND put those gestures on a horizontal
            # plane instead of the wall they were drawn against.
            if chosen.face_id is None and face_cand is not None:
                chosen.face_id = face_cand.face_id
            return self._to_result(chosen)

        if ground_hit is not None:
            gx = round(float(ground_hit[0]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            gy = round(float(ground_hit[1]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            return SnapResult(
                kind=SnapKind.GRID,
                world_position=np.array([gx, gy, 0.0], dtype=np.float32),
                axis=None,
                vertex_id=None,
                label="Grid",
            )
        return self._none()

    # --- selection --------------------------------------------------------

    def _select(self, candidates: list[_Candidate]) -> _Candidate:
        """Highest precedence, then nearest the cursor, then nearest the camera.

        `screen_dist` is the middle key because of #31: with precedence and depth
        alone, two candidates of the SAME kind are separated only by depth, so a
        vertex sitting exactly under the cursor could lose to one several pixels
        away that happened to be nearer the camera.
        """
        return min(candidates, key=lambda c: (_PRECEDENCE_RANK[c.kind], c.screen_dist, c.depth))

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
            axis=None,
            vertex_id=None,
            label="—",
        )

"""Loop-to-loop lofting, shared by Push/Pull, Offset and Follow Me.

All three tools perform the same operation with different destinations:
Push/Pull displaces the source loop along the face normal, Offset displaces
it along angle bisectors in plane, and Follow Me transforms a profile to
each station along a path. Only the destination positions differ, so the
stitching lives here.

Qt-free on purpose: this is the arithmetic most likely to be wrong, and it
must be testable without a QApplication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
    DissolveEdgeCommand,
)


@dataclass(frozen=True, slots=True)
class LoftResult:
    """Commands already executed against the scene, plus the ids they created.

    `dst_vertex_ids` is parallel to the `src_loop_vids` passed in. Returning
    it is what lets callers stop reading AddVertexCommand._vertex_id.
    """

    commands: list
    dst_vertex_ids: list


def loft_between_loops(
    scene,
    src_loop_vids: Sequence[int],
    dst_positions: Sequence[np.ndarray],
    *,
    cap_start: bool,
    cap_end: bool,
) -> LoftResult:
    """Stitch a ring of quads between `src_loop_vids` and new vertices at
    `dst_positions`, executing each command as it is built.

    Commands are executed here, not by the caller: every caller pushes the
    finished CompositeCommand with push_executed, so the scene must already
    reflect the change.

    `cap_start` closes the source end with the source loop REVERSED, so its
    normal points opposite the sweep. `cap_end` closes the destination end
    in source winding. Two flags rather than one because the callers need
    three different answers: Push/Pull always caps the far end and caps the
    near end only for a standalone source, Follow Me caps both ends of an
    open path, and a closed path caps neither.
    """
    n = len(src_loop_vids)
    assert n == len(dst_positions), "loop and destination lengths must match"

    commands: list = []

    dst_vert_cmds: list[AddVertexCommand] = []
    for pos in dst_positions:
        c = AddVertexCommand(np.asarray(pos, dtype=np.float32))
        c.do(scene)
        dst_vert_cmds.append(c)
        commands.append(c)
    # AddVertexCommand has no public accessor for the id it allocated (kept
    # private per this milestone's resolution: scene_commands.py is touched
    # by other tasks and widening its API is out of scope). This matches the
    # shipped Push/Pull code's own reach-in.
    dst_vids = [c._vertex_id for c in dst_vert_cmds]  # type: ignore[attr-defined]

    for src_vid, dst_vid in zip(src_loop_vids, dst_vids, strict=True):
        c = AddEdgeCommand(src_vid, dst_vid)
        c.do(scene)
        commands.append(c)

    for i in range(n):
        c = AddEdgeCommand(dst_vids[i], dst_vids[(i + 1) % n])
        c.do(scene)
        commands.append(c)

    for i in range(n):
        a = src_loop_vids[i]
        b = src_loop_vids[(i + 1) % n]
        c = AddFaceCommand((a, b, dst_vids[(i + 1) % n], dst_vids[i]))
        c.do(scene)
        commands.append(c)

    if cap_end:
        c = AddFaceCommand(tuple(dst_vids))
        c.do(scene)
        commands.append(c)

    if cap_start:
        c = AddFaceCommand(tuple(reversed(list(src_loop_vids))))
        c.do(scene)
        commands.append(c)

    return LoftResult(commands=commands, dst_vertex_ids=dst_vids)


def seam_merge(scene, candidate_edges: Sequence[int]) -> list:
    """Dissolve candidate edges whose two incident faces are coplanar.

    Single pass over the candidates only. Callers capture them BEFORE
    removing a source face, because removal invalidates the boundary.
    """
    out: list = []
    for e in candidate_edges:
        if not scene.edge_is_live(e):
            continue
        f_a, f_b = scene.edge_faces(e)
        if f_a is None or f_b is None:
            continue
        if scene.faces_are_coplanar(f_a, f_b):
            cmd = DissolveEdgeCommand(e)
            cmd.do(scene)
            out.append(cmd)
    return out


_EPS = 1e-9

# Relative back-off applied when a requested distance is clamped (Finding 1,
# Task 6 review): the analytic/binary-search limit is the distance AT WHICH
# an edge reaches exactly zero length or the loop starts to self-intersect,
# not a safe distance short of it. Pulling back by a fixed fraction of that
# limit -- rather than a fixed absolute amount -- keeps the back-off
# proportional to the polygon's own scale: a millimetre-scale polygon and a
# kilometre-scale one both end up with an offset edge shorter by the same
# *fraction* of the limit, so neither a tiny polygon gets over-corrected nor
# a huge one gets a back-off too small to matter at its own scale. 1e-4 is
# comfortably above float64 rounding noise (~1e-16 relative) yet visually
# imperceptible on any drag.
_COLLAPSE_BACKOFF = 1e-4


def offset_polygon(
    points: np.ndarray, normal: np.ndarray, distance: float
) -> tuple[np.ndarray, float]:
    """Offset a planar polygon along each edge's inward normal by `distance`.

    Positive `distance` offsets inward (may collapse the loop); negative
    offsets outward (never collapses). Each vertex moves along the bisector
    of its two adjacent edge normals, scaled so every offset edge stays
    parallel to its original -- the classic "miter" polygon offset.

    Returns `(offset_points, clamped_distance)`. `clamped_distance` equals
    the requested `distance` unless offsetting further would collapse the
    polygon (an analytic per-edge limit) or make it self-intersect (concave
    loops, caught by a bounded binary search), in which case it is the
    largest distance, short of that limit by a small relative margin, that
    still yields a non-degenerate polygon: every edge has strictly positive
    length and no two vertices coincide. The margin exists because the limit
    itself is defined by exact collapse/self-intersection, and a distance
    exactly at it is unusable (some callers weld coincident vertices).

    The general concave straight-skeleton collapse problem is not solved
    here -- only a two-stage approximation: an exact analytic limit for the
    common case, backstopped by a 12-iteration binary search against a
    simple-polygon check for loops where that limit is optimistic.
    """
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    normal_u = _unit(np.asarray(normal, dtype=np.float64))

    edge_dirs = [_unit(pts[(i + 1) % n] - pts[i]) for i in range(n)]
    edge_lengths = [float(np.linalg.norm(pts[(i + 1) % n] - pts[i])) for i in range(n)]

    # Winding depends on how the source face was built, not on an assumed
    # CCW convention, so derive which normal sign makes the loop CCW from
    # the signed area itself rather than trusting the caller's `normal`.
    cross_sum = np.zeros(3)
    for i in range(n):
        cross_sum += np.cross(pts[i], pts[(i + 1) % n])
    n_eff = normal_u if np.dot(cross_sum, normal_u) >= 0 else -normal_u

    edge_normals = [_unit(np.cross(n_eff, d)) for d in edge_dirs]

    # Per-vertex bisector displacement: K = (n_prev + n_next) / (1 + n_prev.n_next).
    # This is 1 / sin(theta / 2) in disguise (theta the interior angle at the
    # vertex) -- it diverges as theta -> 0 (a needle-thin vertex), so the
    # denominator is floored away from zero to keep the scale finite.
    bisectors = []
    for i in range(n):
        n_prev = edge_normals[i - 1]
        n_next = edge_normals[i]
        denom = max(1.0 + float(np.dot(n_prev, n_next)), _EPS)
        bisectors.append((n_prev + n_next) / denom)

    def offset_at(d: float) -> np.ndarray:
        return np.array([pts[i] + d * bisectors[i] for i in range(n)])

    if distance <= 0.0:
        return offset_at(distance), distance

    # Stage 1: analytic per-edge collapse limit. Each offset edge's length
    # is affine in d (both its endpoints move at a fixed rate), so the
    # distance at which it hits zero solves exactly.
    analytic_limit = float("inf")
    for i in range(n):
        rate = float(np.dot(bisectors[(i + 1) % n] - bisectors[i], edge_dirs[i]))
        if rate < -_EPS:
            analytic_limit = min(analytic_limit, -edge_lengths[i] / rate)

    clamped = min(distance, analytic_limit)
    was_clamped = clamped < distance

    # Stage 2: the analytic limit only guards against an edge collapsing
    # onto itself. A concave loop's reflex corners can self-intersect with a
    # *different* edge first, which the per-edge check cannot see, so
    # validate and binary search downward if needed, bounded at 12 steps.
    e1, e2 = _plane_basis(n_eff)
    if not _is_simple_offset(offset_at(clamped), e1, e2):
        was_clamped = True
        lo, hi = 0.0, clamped
        for _ in range(12):
            mid = 0.5 * (lo + hi)
            if _is_simple_offset(offset_at(mid), e1, e2):
                lo = mid
            else:
                hi = mid
        clamped = lo

    if was_clamped:
        # `clamped` above is the distance AT WHICH degeneracy first occurs
        # (an exact analytic root, or a binary-search value pinned
        # arbitrarily close to the self-intersection boundary) -- not a
        # safe distance short of it. Pull back by a fraction of `clamped`
        # itself so every offset edge keeps strictly positive length. See
        # `_COLLAPSE_BACKOFF` for why this is relative, not absolute.
        clamped *= 1.0 - _COLLAPSE_BACKOFF

    return offset_at(clamped), clamped


def _unit(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm < _EPS:
        return v
    return v / norm


def _plane_basis(n_eff: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0.0, 0.0]) if abs(n_eff[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = _unit(np.cross(helper, n_eff))
    e2 = np.cross(n_eff, e1)
    return e1, e2


def _is_simple_offset(pts: np.ndarray, e1: np.ndarray, e2: np.ndarray) -> bool:
    """No two non-adjacent edges of the closed, projected polygon cross.

    Plain four-orientation sign-of-cross-product test, with no collinearity
    tolerance: two segments are judged to cross only when their endpoints
    fall on strictly opposite sides of each other (`sign() != sign()`).
    Exact collinearity -- both signs landing on 0 -- is therefore never a
    crossing, which is what lets the rectangle's own stage-1 analytic
    collapse (two opposite edges retracing the same line segment) pass this
    check without tripping the binary search.

    This is an internal implementation choice, not an external contract:
    there is nothing outside this module that defines "simple" for an
    offset polygon, so this check exists only to drive the binary search
    towards a distance that this same check accepts. `tests/test_offset_polygon.py`
    verifies the *result* with its own, independently-derived parametric
    segment-intersection algorithm rather than reusing this one, so a bug
    shared between the two would still surface as a test failure.
    """
    n = len(pts)
    proj = np.stack([pts @ e1, pts @ e2], axis=-1)
    for i in range(n):
        a1, a2 = proj[i], proj[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            b1, b2 = proj[j], proj[(j + 1) % n]
            if _segments_cross(a1, a2, b1, b2):
                return False
    return True


def _segments_cross(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray, p4: np.ndarray) -> bool:
    def side(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.floating:
        # Scalar 2D cross product computed directly: np.cross on length-2
        # vectors is deprecated in NumPy 2.0.
        ab = b - a
        ac = c - a
        return np.sign(ab[0] * ac[1] - ab[1] * ac[0])

    d1, d2 = side(p3, p4, p1), side(p3, p4, p2)
    d3, d4 = side(p1, p2, p3), side(p1, p2, p4)
    return bool(d1 != d2 and d3 != d4)

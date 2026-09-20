"""Bridges between snaps/world geometry and the command layer for drawing tools.

- resolve_drawing_plane: pick the construction plane from the first click's snap.
- build_closed_face / build_open_polyline: turn a ring/polyline of world points
  into one CompositeCommand over AddVertex/AddEdge(/AddFace), reusing existing
  vertices that coincide with a generated point (so undo stays correct).
  build_open_polyline also hands back the resolved vertex-id chain alongside
  the composite, since some of those ids may be pre-existing vertices the
  composite's own children don't reveal.
- polyline_segments: world points -> (2N, 3) GL_LINES pairs for overlay preview.
- chain_cuts_face: the single face a drawn chain divides, if any (M7.6a).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import AddEdgeCommand, AddFaceCommand, AddVertexCommand
from pluton.geometry import DrawingPlane
from pluton.viewport.picking import world_to_local_point

# "Strictly inside" rejects a point this close to a polygon edge, so a chain
# drawn along the boundary cannot read as inside on one platform and outside
# on another (float round-trip through the ray-crossing test).
_EDGE_EPS = 1e-9

# Reuse an existing vertex when a generated point lands within this distance of
# it (world units / meters; ~10 µm at meter scale). Loose enough to absorb
# float round-trip error from a snapped point; tight enough not to merge
# genuinely-distinct CAD vertices — but intentionally-close vertices below this
# threshold WILL be merged (acceptable at architectural/product scale; revisit
# if sub-mm precision is ever required).
_COINCIDENT_EPS = 1e-5


def resolve_drawing_plane(snap, scene) -> DrawingPlane:
    """ON_FACE snap → that face's plane; otherwise a ground-parallel plane
    through the snapped point's height."""
    from pluton.viewport.snap_engine import SnapKind

    origin = np.asarray(snap.world_position, dtype=np.float64).reshape(3)
    if snap.kind == SnapKind.ON_FACE and snap.face_id is not None:
        try:
            return DrawingPlane.from_face(scene, snap.face_id, origin)
        except (ValueError, KeyError):
            return DrawingPlane.horizontal(origin)
    return DrawingPlane.horizontal(origin)


def _resolve_vertex(scene, composite: CompositeCommand, point: np.ndarray) -> int:
    """Reuse an existing coincident vertex, else add one (recorded in composite)."""
    # Cast to float32 so the coincidence query uses the same precision the scene
    # stores vertices in.
    p = np.asarray(point, dtype=np.float32).reshape(3)
    existing = scene.find_vertex_near(p, _COINCIDENT_EPS)
    if existing is not None:
        return existing
    cmd = AddVertexCommand(p)
    cmd.do(scene)
    composite.children.append(cmd)
    return cmd.vertex_id


def _resolve_ring(scene, composite, world_points):
    """Resolve each point to a vertex id, dropping consecutive duplicates."""
    vids: list[int] = []
    for p in np.asarray(world_points, dtype=np.float32):
        vid = _resolve_vertex(scene, composite, p)
        if not vids or vids[-1] != vid:
            vids.append(vid)
    return vids


def build_closed_face(scene, world_points, name: str = "Draw Shape", world_transform=None):
    """Closed ring of world points → vertices + boundary edges + one face.
    Returns the CompositeCommand (already executed), or None if degenerate
    (fewer than 3 distinct vertices).

    world_transform: when non-identity, each point is converted from world space
    to the local frame before writing (so geometry lands at the correct position
    when drawing inside a moved group/component)."""
    from pluton.geometry.transforms import is_identity_transform

    if not is_identity_transform(world_transform):
        world_points = [world_to_local_point(p, world_transform) for p in world_points]
    composite = CompositeCommand(name=name)
    vids = _resolve_ring(scene, composite, world_points)
    if len(vids) >= 2 and vids[0] == vids[-1]:
        vids.pop()
    if len(vids) < 3:
        composite.undo(scene)
        return None
    n = len(vids)
    seen_edges: set[tuple[int, int]] = set()
    for i in range(n):
        a, b = vids[i], vids[(i + 1) % n]
        key = (a, b) if a < b else (b, a)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        e = AddEdgeCommand(a, b)
        e.do(scene)
        composite.children.append(e)
    # Face is the LAST child: undo reverses children, so the face is removed
    # before its edges (which are removed before their vertices) — the only
    # order remove_face/remove_edge accept.
    f = AddFaceCommand(tuple(vids))
    f.do(scene)
    composite.children.append(f)
    return composite


def build_open_polyline(scene, world_points, name: str = "Draw Curve", world_transform=None):
    """Open polyline of world points → vertices + connecting edges (no face).
    Returns (CompositeCommand, vertex_ids) with the composite already
    executed, or None if degenerate (fewer than 2 distinct vertices).

    vertex_ids is the resolved, order-preserving, consecutive-duplicate-free
    chain of vertex ids the polyline actually touched, in Scene's own
    coordinate frame -- some of these may be pre-existing vertices the
    polyline snapped onto rather than ones this call created, so a caller
    that needs to know which vertices were touched (M7.6a's face-split
    detection is the first one) cannot reconstruct it from the composite's
    children alone and gets it handed back here instead.

    world_transform: when non-identity, each point is converted from world space
    to the local frame before writing (so geometry lands at the correct position
    when drawing inside a moved group/component)."""
    from pluton.geometry.transforms import is_identity_transform

    if not is_identity_transform(world_transform):
        world_points = [world_to_local_point(p, world_transform) for p in world_points]
    composite = CompositeCommand(name=name)
    vids = _resolve_ring(scene, composite, world_points)
    if len(vids) < 2:
        composite.undo(scene)
        return None
    seen_edges: set[tuple[int, int]] = set()
    for i in range(len(vids) - 1):
        a, b = vids[i], vids[i + 1]
        key = (a, b) if a < b else (b, a)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        e = AddEdgeCommand(a, b)
        e.do(scene)
        composite.children.append(e)
    return composite, vids


def polyline_segments(points: np.ndarray, closed: bool) -> np.ndarray:
    """World points → (2N, 3) float32 GL_LINES endpoint pairs for overlay."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    n = len(pts)
    if n < 2:
        return np.zeros((0, 3), dtype=np.float32)
    if closed:
        seg = np.empty((2 * n, 3), dtype=np.float32)
        seg[0::2] = pts
        seg[1::2] = np.roll(pts, -1, axis=0)
    else:
        seg = np.empty((2 * (n - 1), 3), dtype=np.float32)
        seg[0::2] = pts[:-1]
        seg[1::2] = pts[1:]
    return seg


def _dominant_axis_pair(normal: np.ndarray) -> tuple[int, int]:
    """(u, v) column indices used to flatten 3D points to 2D.

    Mirrors Scene._project_loop_to_2d_for_earcut's dominant-axis rule exactly
    (same axis choice, same order, same sign-based swap) rather than a
    simpler "drop the dominant coordinate, keep the rest in index order"
    scheme -- the two disagree for a Y-dominant normal (earcut orders that
    pair (z, x), not (x, z)) and whenever the dominant component is
    negative. Reusing the exact rule means a face's own boundary loop and
    this module's test points always land in the same 2D frame.
    """
    nx, ny, nz = float(normal[0]), float(normal[1]), float(normal[2])
    ax, ay, az = abs(nx), abs(ny), abs(nz)
    if az >= ax and az >= ay:
        return (0, 1) if nz >= 0.0 else (1, 0)
    if ax >= ay:
        return (1, 2) if nx >= 0.0 else (2, 1)
    return (2, 0) if ny >= 0.0 else (0, 2)


def _dist_point_to_segment(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-18:
        return float(np.hypot(px - x1, py - y1))
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return float(np.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))


def _strictly_inside_polygon(poly_2d: np.ndarray, pt: np.ndarray) -> bool:
    """Even-odd ray-crossing containment, with a hard reject within
    `_EDGE_EPS` of any edge segment (see the module-level comment)."""
    n = len(poly_2d)
    x, y = float(pt[0]), float(pt[1])
    inside = False
    for i in range(n):
        x1, y1 = float(poly_2d[i, 0]), float(poly_2d[i, 1])
        x2, y2 = float(poly_2d[(i + 1) % n, 0]), float(poly_2d[(i + 1) % n, 1])
        if _dist_point_to_segment(x, y, x1, y1, x2, y2) <= _EDGE_EPS:
            return False
        if (y1 > y) != (y2 > y):
            x_at_y = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_at_y:
                inside = not inside
    return inside


def _orientation(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Signed area of (o, a, b); sign gives turn direction, 0.0 means collinear."""
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _segments_properly_cross(p1, p2, p3, p4) -> bool:
    """True iff segment p1-p2 and segment p3-p4 cross at a point interior to
    both -- a genuine transversal crossing.

    A shared endpoint, a touch along one segment's interior, or a collinear
    overlap all force at least one of the four orientation products below to
    be zero or same-signed, so none of those register here -- deliberately:
    a chain's own ends legitimately touch the boundary loop where they
    attach to it. Only an actual crossing through a loop edge counts, which
    is the case a sampled interior vertex and sampled segment midpoints can
    both miss on a concave loop (see chain_cuts_face's own test suite for
    the reproduction that motivated this).
    """
    d1 = _orientation(p3, p4, p1)
    d2 = _orientation(p3, p4, p2)
    d3 = _orientation(p1, p2, p3)
    d4 = _orientation(p1, p2, p4)
    return d1 * d2 < 0.0 and d3 * d4 < 0.0


def _segment_crosses_loop_boundary(
    poly_2d: np.ndarray, seg_a: np.ndarray, seg_b: np.ndarray
) -> bool:
    """True if the 2D segment (seg_a, seg_b) properly crosses any of the
    polygon's own boundary edges."""
    n = len(poly_2d)
    for i in range(n):
        edge_a = poly_2d[i]
        edge_b = poly_2d[(i + 1) % n]
        if _segments_properly_cross(seg_a, seg_b, edge_a, edge_b):
            return True
    return False


def _face_is_cut_by_chain(scene, face, chain: list[int], chain_pos: np.ndarray) -> bool:
    """Rule 2 (candidacy) + rule 3 (geometric containment) for one face."""
    loop = face.loop_vertex_ids
    loop_set = set(loop)
    if chain[0] not in loop_set or chain[-1] not in loop_set:
        return False
    interior_set = set(chain[1:-1])
    if interior_set & loop_set:
        return False

    try:
        normal = scene.face_normal(face.id)
    except (KeyError, ValueError):
        return False

    u, v = _dominant_axis_pair(normal)
    loop_pos = np.array([scene.vertex(vid).position for vid in loop], dtype=np.float64)
    poly_2d = loop_pos[:, (u, v)]
    plane_point = loop_pos[0]
    dist_tol = scene._DIST_TOL

    for pos in chain_pos[1:-1]:
        if abs(float(np.dot(pos - plane_point, normal))) > dist_tol:
            return False
        if not _strictly_inside_polygon(poly_2d, pos[[u, v]]):
            return False

    for i in range(len(chain_pos) - 1):
        seg_a, seg_b = chain_pos[i][[u, v]], chain_pos[i + 1][[u, v]]
        mid = (chain_pos[i] + chain_pos[i + 1]) / 2.0
        if not _strictly_inside_polygon(poly_2d, mid[[u, v]]):
            return False
        # The interior-vertex and midpoint samples above are point samples;
        # a concave loop can dip outside the polygon strictly BETWEEN two
        # sampled points and back in without either sample seeing it. This
        # is the check that actually carries the guarantee.
        if _segment_crosses_loop_boundary(poly_2d, seg_a, seg_b):
            return False

    return True


def chain_cuts_face(scene, chain: Sequence[int]) -> int | None:
    """The single face this drawn chain divides, or None.

    Reads the drawing tool's own gesture state rather than searching the mesh:
    an edge drawn across a face carries no face pointer, so there is nothing
    to find it by, and the tool already knows the path it drew. The cost is
    that a path assembled across separate gestures does not split, which is a
    recorded carve-out of M7.6a.

    O(faces), once per gesture end. Scene has no vertex-to-faces accessor and
    this is not a per-frame path.

    Containment is not just point sampling: every interior chain vertex and
    every segment midpoint must land strictly inside the candidate's polygon,
    AND every chain segment must not properly cross any of the polygon's own
    boundary edges. The segment-crossing check exists because point samples
    alone can both land inside a concave polygon while the straight segment
    between them still dips outside and back through a notch (an ordinary
    L-shaped floor plan is enough to hit this) -- an interior-vertex/midpoint
    sample cannot see that, but a real segment-vs-edge crossing test can.
    """
    chain = list(chain)
    if len(chain) < 2 or chain[0] == chain[-1] or len(set(chain)) != len(chain):
        return None

    chain_pos = np.array([scene.vertex(vid).position for vid in chain], dtype=np.float64)
    survivors = [
        face.id
        for face in scene.faces_iter()
        if _face_is_cut_by_chain(scene, face, chain, chain_pos)
    ]
    return survivors[0] if len(survivors) == 1 else None

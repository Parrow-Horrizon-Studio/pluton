"""Bridges between snaps/world geometry and the command layer for drawing tools.

- resolve_drawing_plane: pick the construction plane from the first click's snap.
- build_closed_face / build_open_polyline: turn a ring/polyline of world points
  into one CompositeCommand over AddVertex/AddEdge(/AddFace), reusing existing
  vertices that coincide with a generated point (so undo stays correct).
- polyline_segments: world points -> (2N, 3) GL_LINES pairs for overlay preview.
"""

from __future__ import annotations

import numpy as np

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import AddEdgeCommand, AddFaceCommand, AddVertexCommand
from pluton.geometry import DrawingPlane

# Reuse an existing vertex when a generated point lands within this distance of
# it (world units / meters; ~10 µm at meter scale). Loose enough to absorb
# float round-trip error from a snapped point; tight enough not to merge
# genuinely-distinct CAD vertices — but intentionally-close vertices below this
# threshold WILL be merged (acceptable at architectural/product scale; revisit
# if sub-mm precision is ever required).
_COINCIDENT_EPS = 1e-5


def resolve_drawing_plane(snap, scene) -> DrawingPlane:  # noqa: ANN001
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


def _resolve_vertex(scene, composite: CompositeCommand, point: np.ndarray) -> int:  # noqa: ANN001
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
    return cmd._vertex_id  # type: ignore[attr-defined]


def _resolve_ring(scene, composite, world_points):  # noqa: ANN001
    """Resolve each point to a vertex id, dropping consecutive duplicates."""
    vids: list[int] = []
    for p in np.asarray(world_points, dtype=np.float32):
        vid = _resolve_vertex(scene, composite, p)
        if not vids or vids[-1] != vid:
            vids.append(vid)
    return vids


def build_closed_face(scene, world_points, name: str = "Draw Shape"):  # noqa: ANN001
    """Closed ring of world points → vertices + boundary edges + one face.
    Returns the CompositeCommand (already executed), or None if degenerate
    (fewer than 3 distinct vertices)."""
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


def build_open_polyline(scene, world_points, name: str = "Draw Curve"):  # noqa: ANN001
    """Open polyline of world points → vertices + connecting edges (no face).
    Returns the CompositeCommand (already executed), or None if degenerate
    (fewer than 2 distinct vertices)."""
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
    return composite


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

"""The editable polygonal scene — thin Python wrapper over the C++ HalfEdgeMesh.

Pure-Python topology is gone. Every public method delegates into the C++
HalfEdgeMesh held in self._mesh, with mapbox-earcut still owning face
triangulation on the Python side.

Idempotent mutators (`add_vertex`; `add_edge` and `add_face_from_loop`
arrive in this same milestone) so tools never have to check existence
before inserting. A single `dirty` flag tracks "has the renderer
seen the current state yet"; the renderer calls `mark_clean()` after
re-uploading buffers.
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Iterable, Sequence
from enum import Enum
from typing import TYPE_CHECKING

import mapbox_earcut
import numpy as np

from pluton._core import HalfEdgeMesh, ray_intersect_mesh

if TYPE_CHECKING:
    from pluton._core import RayMeshHit
from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex

SplitResult = namedtuple("SplitResult", "vertex edge_a edge_b face_a face_b")

# Material id 0 == MaterialLibrary.DEFAULT_ID: the "unpainted / standard look"
# sentinel. Kept as a literal to avoid a scene -> model import.
_DEFAULT_MATERIAL_ID = 0


class Side(Enum):
    """Which side of a face a material applies to.

    FRONT is the side the face normal points out of. Lives here rather than
    beside Material because `model` imports `scene`, not the reverse.
    """

    FRONT = 0
    BACK = 1


def _project_loop_to_2d_for_earcut(positions_3d: np.ndarray) -> np.ndarray:
    """Project an (N, 3) loop onto its dominant axis-aligned plane.

    Returns an (N, 2) float32 array suitable for mapbox_earcut. The projection
    plane is the one perpendicular to the largest component of the polygon's
    normal (Newell's method over the whole loop, so a reflex first corner
    cannot flip the estimate the way a single edge cross product can). Without
    this, vertical faces collapse to collinear points in XY and earcut returns
    zero triangles.

    The SIGN of that dominant component decides the ORDER of the axis pair, and
    it matters as much as the choice of plane. Earcut emits triangles wound the
    same way as the 2D ring it is handed, and those indices are fed straight to
    the renderer; if the projection mirrors the loop, every triangle of that
    face comes back wound backwards relative to the face's own normal. Only a
    right-handed pair (u, v) — one where u x v points along the normal —
    preserves the loop's orientation:

        +Z -> (x, y)    -Z -> (y, x)
        +X -> (y, z)    -X -> (z, y)
        +Y -> (z, x)    -Y -> (x, z)

    Picking the pair from abs(n) instead mirrors three of those six cases, which
    is what made three of a box's six faces render with their back material
    (fixed in v0.7.1; invisible before M7.5a gave the two sides distinct looks).
    """
    if positions_3d.shape[0] < 3:
        return positions_3d[:, :2].astype(np.float32)
    # Newell's method: sum over every loop edge, robust to concave corners.
    p = positions_3d.astype(np.float64)
    q = np.roll(p, -1, axis=0)
    n = np.array(
        [
            float(np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2]))),
            float(np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0]))),
            float(np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1]))),
        ]
    )
    nx, ny, nz = float(n[0]), float(n[1]), float(n[2])
    ax, ay, az = abs(nx), abs(ny), abs(nz)
    if az >= ax and az >= ay:
        u, v = (0, 1) if nz >= 0.0 else (1, 0)  # +Z -> (x, y) / -Z -> (y, x)
    elif ax >= ay:
        u, v = (1, 2) if nx >= 0.0 else (2, 1)  # +X -> (y, z) / -X -> (z, y)
    else:
        u, v = (2, 0) if ny >= 0.0 else (0, 2)  # +Y -> (z, x) / -Y -> (x, z)
    return np.stack([positions_3d[:, u], positions_3d[:, v]], axis=1).astype(np.float32)


class Scene:
    """Editable polygonal scene with stable integer IDs (C++ HalfEdgeMesh backed)."""

    # Recommended tolerances for faces_are_coplanar (cos(0.5 deg) angle tolerance,
    # 1e-4 world-unit distance tolerance). Kept at the class top since they're
    # part of Scene's public contract, not an implementation detail local to
    # one method.
    _ANGLE_TOL_COS = 0.9999619  # cos(0.5°)
    _DIST_TOL = 1e-4

    def __init__(self) -> None:
        self._mesh = HalfEdgeMesh()
        self._face_materials_front: dict[int, int] = {}
        self._face_materials_back: dict[int, int] = {}
        self._render_dirty = False

    # --- Mutators ---------------------------------------------------------

    def add_vertex(self, position: np.ndarray) -> int:
        """Insert a vertex at `position` (float32 (3,)) and return its ID.

        Idempotent on exact equality (delegated to C++ HalfEdgeMesh).
        """
        if position.dtype != np.float32 or position.shape != (3,):
            position = np.asarray(position, dtype=np.float32).reshape(3)
        return self._mesh.add_vertex(float(position[0]), float(position[1]), float(position[2]))

    def vertex_slab_size(self) -> int:
        """Number of vertex slots ever allocated — live plus tombstoned.

        `add_vertex` only ever appends a slot when it actually creates a vertex
        (a dedup returns an existing id, and `remove_vertex` tombstones rather
        than freeing), so comparing this across an `add_vertex` call is an
        exact O(1) test for "did that call create, or deduplicate?".
        """
        return self._mesh.vertex_slab_size()

    def add_edge(self, v1_id: int, v2_id: int) -> int:
        """Insert an undirected edge between two existing vertices."""
        if v1_id == v2_id:
            raise ValueError(f"self-loop edge requested at vertex {v1_id}")
        if not self._mesh.vertex_is_live(v1_id):
            raise KeyError(f"add_edge: unknown v1_id={v1_id}")
        if not self._mesh.vertex_is_live(v2_id):
            raise KeyError(f"add_edge: unknown v2_id={v2_id}")
        return self._mesh.add_halfedge_pair(v1_id, v2_id)

    def add_face_from_loop(self, ordered_vertex_ids: Sequence[int]) -> int:
        """Insert a face bounded by the given closed vertex loop.

        Triangulates the loop via mapbox-earcut, then passes both the loop and
        the triangulation into the C++ HalfEdgeMesh.  Any loop edges that do
        not yet exist are auto-inserted before the face is created.
        """
        loop = tuple(ordered_vertex_ids)
        if len(loop) < 3:
            raise ValueError(f"face needs at least 3 vertices, got {len(loop)}")
        for vid in loop:
            if not self._mesh.vertex_is_live(vid):
                raise KeyError(f"add_face_from_loop: unknown vertex_id={vid}")

        # Build an (N, 3) array of the loop's 3D positions for projection.
        xyz = np.empty((len(loop), 3), dtype=np.float32)
        for i, vid in enumerate(loop):
            pos = self._mesh.vertex_position(vid)
            xyz[i] = (pos[0], pos[1], pos[2])
        # Project onto the dominant axis-aligned plane so vertical faces don't
        # collapse to collinear points (which would yield zero triangles).
        projected = _project_loop_to_2d_for_earcut(xyz)
        ring_ends = np.array([len(loop)], dtype=np.uint32)
        local_indices = mapbox_earcut.triangulate_float32(projected, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        triangles = [int(loop[i]) for tri in local_indices for i in tri]

        # Auto-insert any loop edges that don't already exist (M2 callers do
        # not pre-insert edges before calling add_face_from_loop, but the C++
        # HalfEdgeMesh requires all boundary edges to be present).
        n = len(loop)
        for i in range(n):
            v_from = loop[i]
            v_to = loop[(i + 1) % n]
            self._mesh.add_halfedge_pair(v_from, v_to)

        return self._mesh.add_face_from_loop(list(loop), triangles)

    def remove_vertex(self, v_id: int) -> None:
        """Remove a vertex. Raises KeyError if not live, ValueError if still referenced."""
        try:
            self._mesh.remove_vertex(v_id)
        except IndexError as e:
            raise KeyError(str(e)) from None
        except ValueError:
            raise

    def remove_edge(self, e_id: int) -> None:
        try:
            self._mesh.remove_edge(e_id)
        except IndexError as e:
            raise KeyError(str(e)) from None
        except ValueError:
            raise

    def remove_face(self, f_id: int) -> None:
        try:
            self._mesh.remove_face(f_id)
        except IndexError as e:
            raise KeyError(str(e)) from None

    def restore_vertex(self, v_id: int, position: np.ndarray) -> None:
        """Restore a previously-removed vertex with its original ID. Used by undo."""
        position = np.asarray(position, dtype=np.float32).reshape(3)
        self._mesh.restore_vertex(v_id, float(position[0]), float(position[1]), float(position[2]))

    def restore_edge(self, e_id: int, v1_id: int, v2_id: int) -> None:
        """Restore a previously-removed edge with its original ID. Used by undo."""
        self._mesh.restore_edge(e_id, v1_id, v2_id)

    def restore_face(self, f_id: int, ordered_vertex_ids: Sequence[int]) -> None:
        """Restore a previously-removed face with its original ID. Used by undo."""
        loop = tuple(ordered_vertex_ids)
        xyz = np.empty((len(loop), 3), dtype=np.float32)
        for i, vid in enumerate(loop):
            pos = self._mesh.vertex_position(vid)
            xyz[i] = (pos[0], pos[1], pos[2])
        projected = _project_loop_to_2d_for_earcut(xyz)
        ring_ends = np.array([len(loop)], dtype=np.uint32)
        local_indices = mapbox_earcut.triangulate_float32(projected, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        triangles = [int(loop[i]) for tri in local_indices for i in tri]
        self._mesh.restore_face(f_id, list(loop), triangles)

    def set_vertex_position(self, v_id: int, position: np.ndarray) -> None:
        """Move an existing live vertex to `position` (float32 (3,)) in place.

        Recomputes cached normals on incident faces (delegated to C++).
        Raises KeyError if the vertex is not live.
        """
        position = np.asarray(position, dtype=np.float32).reshape(3)
        try:
            self._mesh.set_vertex_position(
                v_id, float(position[0]), float(position[1]), float(position[2])
            )
        except IndexError as e:
            raise KeyError(str(e)) from None

    def clear(self) -> None:
        """Reset the scene to empty. Renderer will re-upload empty buffers."""
        self._mesh.clear()
        self._face_materials_front.clear()
        self._face_materials_back.clear()
        self._render_dirty = True

    # --- Lifecycle (renderer sync) ----------------------------------------

    def mark_clean(self) -> None:
        self._mesh.mark_clean()
        self._render_dirty = False

    # --- M3b picking + face geometry helpers ---------------------------------

    def ray_pick_face(
        self,
        origin: np.ndarray,
        direction: np.ndarray,
    ) -> RayMeshHit | None:
        """Return the closest live face hit, or None.

        Thin wrapper around the C++ pluton._core.ray_intersect_mesh. Caller
        passes a 3-vector origin + 3-vector direction (need not be unit length).
        The returned RayMeshHit exposes .face_id, .t, .point.
        """
        origin_list = [float(origin[0]), float(origin[1]), float(origin[2])]
        direction_list = [float(direction[0]), float(direction[1]), float(direction[2])]
        return ray_intersect_mesh(self._mesh, origin_list, direction_list)

    def face_loop(self, f_id: int) -> list[int]:
        """Ordered boundary vertex IDs of the given live face."""
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_loop: face {f_id} is not live")
        return list(self._mesh.face_loop_vertices(f_id))

    def face_normal(self, f_id: int) -> np.ndarray:
        """Geometric normal of the planar face, computed from the first three
        boundary vertices via cross product, then normalized.

        Assumes the face is planar (M2 / M3a only produce planar faces).
        # TODO M4+: handle non-planar faces (Newell's method, or fan-from-centroid).
        """
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_normal: face {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        if len(loop) < 3:
            raise ValueError(f"face_normal: face {f_id} has fewer than 3 vertices")
        p0 = np.asarray(self._mesh.vertex_position(loop[0]), dtype=np.float32)
        p1 = np.asarray(self._mesh.vertex_position(loop[1]), dtype=np.float32)
        p2 = np.asarray(self._mesh.vertex_position(loop[2]), dtype=np.float32)
        n = np.cross(p1 - p0, p2 - p0).astype(np.float32)
        length = float(np.linalg.norm(n))
        if length < 1e-9:
            raise ValueError(f"face_normal: face {f_id} is degenerate (first 3 vertices collinear)")
        return (n / length).astype(np.float32)

    def face_center(self, f_id: int) -> np.ndarray:
        """Centroid (mean) of the face's boundary vertex positions."""
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_center: face {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        acc = np.zeros(3, dtype=np.float32)
        for vid in loop:
            pos = self._mesh.vertex_position(vid)
            acc += np.asarray(pos, dtype=np.float32)
        return (acc / float(len(loop))).astype(np.float32)

    # ---- M3c additions ----

    def dissolve_edge(self, edge_id: int) -> int | None:
        """Dissolve an edge between two adjacent faces.

        Returns the new (surviving) face id on success, or None if the edge
        is boundary / dead / would create a degenerate result.
        """
        result = self._mesh.dissolve_edge(edge_id)
        if result == self._mesh.INVALID_ID:
            return None
        return int(result)

    def faces_are_coplanar(self, f1_id: int, f2_id: int) -> bool:
        """True iff the two faces' normals and planes agree within tolerance.

        Applies Scene's recommended tolerances (_ANGLE_TOL_COS, _DIST_TOL) to
        HalfEdgeMesh.faces_are_coplanar, which takes tolerances as required
        arguments with no built-in defaults of its own.
        """
        return bool(
            self._mesh.faces_are_coplanar(
                f1_id,
                f2_id,
                self._ANGLE_TOL_COS,
                self._DIST_TOL,
            )
        )

    def face_edges(self, f_id: int) -> list[int]:
        """Edge IDs around the face's boundary loop, in order.

        For each consecutive vertex pair (v_i, v_{i+1}) in the boundary loop,
        looks up the edge id via the kernel's idempotent add_halfedge_pair,
        which returns the EXISTING edge id for an already-present live pair
        (no mutation). add_halfedge_pair returns the edge id directly — do
        NOT divide by 2.
        """
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"Face {f_id} is not live")
        loop = list(self._mesh.face_loop_vertices(f_id))
        edges: list[int] = []
        n = len(loop)
        for i in range(n):
            v_a, v_b = loop[i], loop[(i + 1) % n]
            edge_id = self._mesh.add_halfedge_pair(v_a, v_b)  # returns the edge id
            edges.append(int(edge_id))
        return edges

    def edge_faces(self, e_id: int) -> tuple[int | None, int | None]:
        """The pair of face ids on each side of the edge. None if no face on that side."""
        if not self._mesh.edge_is_live(e_id):
            raise KeyError(f"Edge {e_id} is not live")
        he_a = 2 * e_id
        he_b = 2 * e_id + 1
        f_a = self._mesh.halfedge_face(he_a)
        f_b = self._mesh.halfedge_face(he_b)
        invalid_id = self._mesh.INVALID_ID
        return (
            None if f_a == invalid_id else int(f_a),
            None if f_b == invalid_id else int(f_b),
        )

    def edge_is_boundary(self, e_id: int) -> bool:
        """True iff the edge has fewer than two incident faces."""
        f_a, f_b = self.edge_faces(e_id)
        return f_a is None or f_b is None

    def edge_between(self, v1_id: int, v2_id: int) -> int | None:
        """The live edge joining `v1_id` and `v2_id`, or None.

        Non-mutating, unlike add_halfedge_pair, which this replaces at the
        two call sites that were using it as a lookup (#26).
        """
        return self._mesh.edge_between(v1_id, v2_id)

    def edge_is_live(self, e_id: int) -> bool:
        """True while `e_id` refers to a live edge slot."""
        return self._mesh.edge_is_live(e_id)

    # ---- M3d additions ----

    def point_on_edge(self, e_id: int, t: float) -> np.ndarray:
        """World point at parameter t along edge e (t measured v1→v2 of edge())."""
        e = self.edge(e_id)
        pa = self.vertex(e.v1_id).position
        pb = self.vertex(e.v2_id).position
        return (pa + float(t) * (pb - pa)).astype(np.float32)

    def closest_point_on_edge(self, e_id: int, world_point: np.ndarray) -> tuple[np.ndarray, float]:
        """Closest point on edge segment to `world_point`, plus its clamped t∈[0,1]."""
        e = self.edge(e_id)
        pa = self.vertex(e.v1_id).position
        pb = self.vertex(e.v2_id).position
        ab = pb - pa
        denom = float(np.dot(ab, ab))
        if denom < 1e-18:
            return pa.astype(np.float32), 0.0
        t = float(np.dot(np.asarray(world_point, dtype=np.float32) - pa, ab) / denom)
        t = max(0.0, min(1.0, t))
        return (pa + t * ab).astype(np.float32), t

    def split_edge(self, e_id: int, t: float) -> SplitResult | None:
        """Split edge e at parameter t. Returns a SplitResult (face_* None for a
        boundary edge's empty side), or None if the split is invalid."""
        res = self._mesh.split_edge(int(e_id), float(t))
        if res is None:
            return None
        invalid = self._mesh.INVALID_ID
        return SplitResult(
            vertex=int(res.vertex),
            edge_a=int(res.edge_a),
            edge_b=int(res.edge_b),
            face_a=None if res.face_a == invalid else int(res.face_a),
            face_b=None if res.face_b == invalid else int(res.face_b),
        )

    # --- Queries ----------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._mesh.is_dirty() or self._render_dirty

    def vertex(self, v_id: int) -> Vertex:
        if not self._mesh.vertex_is_live(v_id):
            raise KeyError(f"vertex_id {v_id} is not live")
        pos = self._mesh.vertex_position(v_id)
        return Vertex(id=v_id, position=np.array(pos, dtype=np.float32))

    def edge(self, e_id: int) -> Edge:
        if not self._mesh.edge_is_live(e_id):
            raise KeyError(f"edge_id {e_id} is not live")
        verts = self._mesh.edge_vertices(e_id)
        return Edge(id=e_id, v1_id=verts[0], v2_id=verts[1])

    def face(self, f_id: int) -> Face:
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_id {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        tris = self._mesh.face_triangles(f_id)
        triangles = np.array(tris, dtype=np.int32).reshape(-1, 3)
        return Face(
            id=f_id,
            loop_vertex_ids=tuple(loop),
            plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            triangles=triangles,
        )

    def vertices_iter(self) -> Iterable[Vertex]:
        v = self._mesh.next_live_vertex(0)
        while v != HalfEdgeMesh.INVALID_ID:
            yield self.vertex(v)
            v = self._mesh.next_live_vertex(v + 1)

    def edges_iter(self) -> Iterable[Edge]:
        e = self._mesh.next_live_edge(0)
        while e != HalfEdgeMesh.INVALID_ID:
            yield self.edge(e)
            e = self._mesh.next_live_edge(e + 1)

    def faces_iter(self) -> Iterable[Face]:
        f = self._mesh.next_live_face(0)
        while f != HalfEdgeMesh.INVALID_ID:
            yield self.face(f)
            f = self._mesh.next_live_face(f + 1)

    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None:
        """Return the ID of the live vertex closest to `world_xyz` within `tolerance`."""
        best_id: int | None = None
        best_d2 = tolerance * tolerance
        v = self._mesh.next_live_vertex(0)
        while v != HalfEdgeMesh.INVALID_ID:
            pos = self._mesh.vertex_position(v)
            d0 = pos[0] - float(world_xyz[0])
            d1 = pos[1] - float(world_xyz[1])
            d2 = pos[2] - float(world_xyz[2])
            d_sq = d0 * d0 + d1 * d1 + d2 * d2
            if d_sq <= best_d2:
                best_d2 = d_sq
                best_id = v
            v = self._mesh.next_live_vertex(v + 1)
        return best_id

    # --- Per-face material sidecar ----------------------------------------

    def _materials_for(self, side: Side) -> dict[int, int]:
        return self._face_materials_front if side is Side.FRONT else self._face_materials_back

    def set_face_material(self, f_id: int, material_id: int, side: Side = Side.FRONT) -> None:
        """Paint one side of a face. material_id 0 (Default) clears that side."""
        if material_id == _DEFAULT_MATERIAL_ID:
            self.clear_face_material(f_id, side)
            return
        self._materials_for(side)[f_id] = material_id
        self._render_dirty = True

    def clear_face_material(self, f_id: int, side: Side = Side.FRONT) -> None:
        """Remove any material from one side of a face."""
        if self._materials_for(side).pop(f_id, None) is not None:
            self._render_dirty = True

    def face_material(self, f_id: int, side: Side = Side.FRONT) -> int:
        """Material id painted on one side, or 0 (Default) if unpainted."""
        return self._materials_for(side).get(f_id, _DEFAULT_MATERIAL_ID)

    def faces_with_material(self, material_id: int) -> list[tuple[int, Side]]:
        """Every painted (face, side) referencing `material_id`.

        Only painted faces are stored, since painting Default clears the entry,
        so this scans the two sidecars rather than walking the mesh.
        """
        found = [(f, Side.FRONT) for f, m in self._face_materials_front.items() if m == material_id]
        found += [(f, Side.BACK) for f, m in self._face_materials_back.items() if m == material_id]
        return found

    def face_triangle_materials(self, side: Side = Side.FRONT) -> np.ndarray:
        """Per-triangle material id, aligned 1:1 with face_triangle_buffer().

        Walks live faces in next_live_face ascending order (the exact order the
        C++ face_triangle_buffer uses) and repeats each face's material id by
        its triangle count.
        """
        materials = self._materials_for(side)
        mats: list[int] = []
        f = self._mesh.next_live_face(0)
        while f != HalfEdgeMesh.INVALID_ID:
            n_tris = len(self._mesh.face_triangles(f)) // 3
            mats.extend([materials.get(f, _DEFAULT_MATERIAL_ID)] * n_tris)
            f = self._mesh.next_live_face(f + 1)
        return np.asarray(mats, dtype=np.int64)

    # --- Render-buffer projection -----------------------------------------

    def edge_line_buffer(self) -> np.ndarray:
        buf = self._mesh.edge_line_buffer()
        if not buf:
            return np.zeros((0, 3), dtype=np.float32)
        return np.asarray(buf, dtype=np.float32).reshape(-1, 3)

    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]:
        positions, normals = self._mesh.face_triangle_buffer()
        if not positions:
            empty = np.zeros((0, 3), dtype=np.float32)
            return empty, empty
        pos = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
        nrm = np.asarray(normals, dtype=np.float32).reshape(-1, 3)
        return pos, nrm

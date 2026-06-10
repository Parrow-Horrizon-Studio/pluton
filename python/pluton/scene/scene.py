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

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import mapbox_earcut
import numpy as np

from pluton._core import HalfEdgeMesh, ray_intersect_mesh

if TYPE_CHECKING:
    from pluton._core import RayMeshHit
from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex


def _project_loop_to_2d_for_earcut(positions_3d: np.ndarray) -> np.ndarray:
    """Project an (N, 3) loop onto its dominant axis-aligned plane.

    Returns an (N, 2) float32 array suitable for mapbox_earcut. The projection
    plane is the one perpendicular to the largest component of the polygon's
    geometric normal (cross product of the first two boundary edges):
      - normal mostly +Z → XY projection
      - normal mostly +X → YZ projection
      - normal mostly +Y → XZ projection
    Without this, vertical faces collapse to collinear points in XY and earcut
    returns zero triangles.
    """
    if positions_3d.shape[0] < 3:
        return positions_3d[:, :2].astype(np.float32)
    p0 = positions_3d[0]
    p1 = positions_3d[1]
    p2 = positions_3d[2]
    e1 = p1 - p0
    e2 = p2 - p0
    n = np.cross(e1, e2)
    ax, ay, az = abs(float(n[0])), abs(float(n[1])), abs(float(n[2]))
    if az >= ax and az >= ay:
        return positions_3d[:, :2].astype(np.float32)              # XY
    if ax >= ay:
        return np.stack([positions_3d[:, 1], positions_3d[:, 2]], axis=1).astype(np.float32)  # YZ
    return np.stack([positions_3d[:, 0], positions_3d[:, 2]], axis=1).astype(np.float32)      # XZ


class Scene:
    """Editable polygonal scene with stable integer IDs (C++ HalfEdgeMesh backed)."""

    def __init__(self) -> None:
        self._mesh = HalfEdgeMesh()

    # --- Mutators ---------------------------------------------------------

    def add_vertex(self, position: np.ndarray) -> int:
        """Insert a vertex at `position` (float32 (3,)) and return its ID.

        Idempotent on exact equality (delegated to C++ HalfEdgeMesh).
        """
        if position.dtype != np.float32 or position.shape != (3,):
            position = np.asarray(position, dtype=np.float32).reshape(3)
        return self._mesh.add_vertex(float(position[0]), float(position[1]), float(position[2]))

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

    def clear(self) -> None:
        """Reset the scene to empty. Renderer will re-upload empty buffers."""
        self._mesh.clear()

    # --- Lifecycle (renderer sync) ----------------------------------------

    def mark_clean(self) -> None:
        self._mesh.mark_clean()

    # --- M3b picking + face geometry helpers ---------------------------------

    def ray_pick_face(
        self,
        origin: np.ndarray,
        direction: np.ndarray,
    ) -> "RayMeshHit | None":
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
            raise ValueError(
                f"face_normal: face {f_id} is degenerate (first 3 vertices collinear)"
            )
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

    # Project-default tolerances for faces_are_coplanar.
    _ANGLE_TOL_COS = 0.9999619  # cos(0.5°)
    _DIST_TOL = 1e-4

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
        """Project-default tolerances applied. See HalfEdgeMesh.faces_are_coplanar."""
        return bool(self._mesh.faces_are_coplanar(
            f1_id, f2_id, self._ANGLE_TOL_COS, self._DIST_TOL,
        ))

    def face_edges(self, f_id: int) -> list[int]:
        """Edge IDs around the face's boundary loop, in order.

        For each consecutive vertex pair (v_i, v_{i+1}) in the boundary loop,
        looks up the edge id via the kernel's idempotent add_halfedge_pair,
        which returns the EXISTING edge id for an already-present live pair
        (no mutation). add_halfedge_pair returns the edge id directly — do
        NOT divide by 2.
        """
        if not self._mesh.face_is_live(f_id):
            raise IndexError(f"Face {f_id} is not live")
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
            raise IndexError(f"Edge {e_id} is not live")
        he_a = 2 * e_id
        he_b = 2 * e_id + 1
        f_a = self._mesh.halfedge_face(he_a)
        f_b = self._mesh.halfedge_face(he_b)
        INVALID = self._mesh.INVALID_ID
        return (
            None if f_a == INVALID else int(f_a),
            None if f_b == INVALID else int(f_b),
        )

    def edge_is_boundary(self, e_id: int) -> bool:
        """True iff the edge has fewer than two incident faces."""
        f_a, f_b = self.edge_faces(e_id)
        return f_a is None or f_b is None

    # --- Queries ----------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._mesh.is_dirty()

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

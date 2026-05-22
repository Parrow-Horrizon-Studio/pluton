"""The editable polygonal scene.

Pure-Python topology. Stable integer IDs for vertices, edges, and faces.
Idempotent mutators (`add_vertex`; `add_edge` and `add_face_from_loop` arrive
in Tasks 4 and 5) so tools never have to check existence before inserting. A single `dirty` flag tracks "has the renderer
seen the current state yet"; the renderer calls `mark_clean()` after
re-uploading buffers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import mapbox_earcut
import numpy as np

from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex


class Scene:
    """Editable polygonal scene with stable integer IDs."""

    def __init__(self) -> None:
        self._vertices: dict[int, Vertex] = {}
        self._edges: dict[int, Edge] = {}
        self._faces: dict[int, Face] = {}
        self._next_vertex_id = 0
        self._next_edge_id = 0
        self._next_face_id = 0
        # Maps position.tobytes() -> vertex_id for idempotent add_vertex.
        self._position_index: dict[bytes, int] = {}
        self._edge_index: dict[tuple[int, int], int] = {}
        self._dirty: bool = False

    # --- Mutators ---------------------------------------------------------

    def add_vertex(self, position: np.ndarray) -> int:
        """Insert a vertex at `position` (float32 (3,)) and return its ID.

        Idempotent on exact equality: re-adding the same position returns the
        existing vertex's ID. No epsilon — the snap engine produces
        deterministic positions, so float equality is the right contract.
        """
        if position.dtype != np.float32 or position.shape != (3,):
            position = np.asarray(position, dtype=np.float32).reshape(3)
        # Collapse negative zero to positive zero so -0.0 and 0.0 hash identically.
        position = position + np.float32(0.0)
        key = position.tobytes()
        existing = self._position_index.get(key)
        if existing is not None:
            return existing
        vid = self._next_vertex_id
        self._next_vertex_id += 1
        self._vertices[vid] = Vertex(id=vid, position=position.copy())
        self._position_index[key] = vid
        self._dirty = True
        return vid

    def add_edge(self, v1_id: int, v2_id: int) -> int:
        """Insert an undirected edge between two existing vertices.

        Idempotent on the unordered pair: ``add_edge(a, b)`` and
        ``add_edge(b, a)`` return the same edge ID. Rejects self-loops with
        ValueError — tools should never request one. Rejects edges referencing
        unknown vertex IDs with KeyError so topology stays coherent.
        """
        if v1_id not in self._vertices:
            raise KeyError(f"add_edge: unknown v1_id={v1_id}")
        if v2_id not in self._vertices:
            raise KeyError(f"add_edge: unknown v2_id={v2_id}")
        if v1_id == v2_id:
            raise ValueError(f"self-loop edge requested at vertex {v1_id}")
        a, b = (v1_id, v2_id) if v1_id < v2_id else (v2_id, v1_id)
        key = (a, b)
        existing = self._edge_index.get(key)
        if existing is not None:
            return existing
        eid = self._next_edge_id
        self._next_edge_id += 1
        self._edges[eid] = Edge(id=eid, v1_id=a, v2_id=b)
        self._edge_index[key] = eid
        self._dirty = True
        return eid

    def add_face_from_loop(self, ordered_vertex_ids: Sequence[int]) -> int:
        """Insert a face bounded by the given closed vertex loop.

        The loop is closed implicitly — the caller does not repeat the first
        vertex. Requires len(loop) >= 3 and that every vertex ID already
        exists in the scene.

        Ground-plane convention in M2: plane_normal is hard-coded to (0, 0, 1)
        and triangulation runs on the XY coordinates via mapbox-earcut.
        """
        loop = tuple(ordered_vertex_ids)
        if len(loop) < 3:
            raise ValueError(
                f"face needs at least 3 vertices, got {len(loop)}"
            )
        # Validate vertex existence before any partial state mutation.
        for vid in loop:
            if vid not in self._vertices:
                raise KeyError(f"add_face_from_loop: unknown vertex_id={vid}")

        # Build a (N, 2) float32 array of XY for earcut. mapbox-earcut 2.x
        # takes the 2D shape directly — DO NOT reshape to flat.
        xy = np.empty((len(loop), 2), dtype=np.float32)
        for i, vid in enumerate(loop):
            xy[i] = self._vertices[vid].position[:2]
        ring_ends = np.array([len(loop)], dtype=np.uint32)
        # earcut returns a flat uint32 array of length 3*T; reshape to (T, 3).
        # Indices are into the local ring, so map back to global vertex IDs.
        local_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        triangles = np.array(
            [[loop[i] for i in tri] for tri in local_indices],
            dtype=np.int32,
        )

        fid = self._next_face_id
        self._next_face_id += 1
        self._faces[fid] = Face(
            id=fid,
            loop_vertex_ids=loop,
            plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            triangles=triangles,
        )
        self._dirty = True
        return fid

    def clear(self) -> None:
        """Reset the scene to empty. Renderer will re-upload empty buffers."""
        self._vertices.clear()
        self._edges.clear()
        self._faces.clear()
        self._next_vertex_id = 0
        self._next_edge_id = 0
        self._next_face_id = 0
        self._position_index.clear()
        self._edge_index.clear()
        self._dirty = True

    # --- Lifecycle (renderer sync) ----------------------------------------

    def mark_clean(self) -> None:
        """Renderer calls this after consuming the current buffers."""
        self._dirty = False

    # --- Queries ----------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    def vertex(self, vid: int) -> Vertex:
        return self._vertices[vid]

    def vertices_iter(self) -> Iterable[Vertex]:
        return self._vertices.values()

    def edges_iter(self) -> Iterable[Edge]:
        return self._edges.values()

    def faces_iter(self) -> Iterable[Face]:
        return self._faces.values()

    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None:
        """Return the ID of the vertex closest to `world_xyz` within `tolerance`.

        Linear scan over all vertices. Fine for M2 (small scenes). A spatial
        index lands in M10 if profiling demands it.
        """
        best_id: int | None = None
        best_d2 = tolerance * tolerance
        for vid, v in self._vertices.items():
            d = v.position - world_xyz
            d2 = float(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            if d2 <= best_d2:
                best_d2 = d2
                best_id = vid
        return best_id

    # --- Render-buffer projection -----------------------------------------

    def edge_line_buffer(self) -> np.ndarray:
        """Flat (2*E, 3) float32 array — line-list endpoints for the GL VBO."""
        if not self._edges:
            return np.zeros((0, 3), dtype=np.float32)
        out = np.empty((2 * len(self._edges), 3), dtype=np.float32)
        for i, e in enumerate(self._edges.values()):
            out[2 * i + 0] = self._vertices[e.v1_id].position
            out[2 * i + 1] = self._vertices[e.v2_id].position
        return out

    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]:
        """Flat (3*T, 3) float32 (positions, normals) — triangle-list for the GL VBO.

        Each triangle is expanded inline. Normals are flat — every vertex of a
        triangle takes the face's `plane_normal` — so the Phong shader from M1
        renders the face with the same flat shading as the cube did.
        """
        if not self._faces:
            empty = np.zeros((0, 3), dtype=np.float32)
            return empty, empty
        total_tris = sum(int(f.triangles.shape[0]) for f in self._faces.values())
        positions = np.empty((3 * total_tris, 3), dtype=np.float32)
        normals = np.empty((3 * total_tris, 3), dtype=np.float32)
        row = 0
        for f in self._faces.values():
            for tri in f.triangles:
                positions[row + 0] = self._vertices[int(tri[0])].position
                positions[row + 1] = self._vertices[int(tri[1])].position
                positions[row + 2] = self._vertices[int(tri[2])].position
                normals[row + 0] = f.plane_normal
                normals[row + 1] = f.plane_normal
                normals[row + 2] = f.plane_normal
                row += 3
        return positions, normals

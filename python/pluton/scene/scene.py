"""The editable polygonal scene.

Pure-Python topology. Stable integer IDs for vertices, edges, and faces.
Idempotent mutators (`add_vertex`; `add_edge` and `add_face_from_loop` arrive
in Tasks 4 and 5) so tools never have to check existence before inserting. A single `dirty` flag tracks "has the renderer
seen the current state yet"; the renderer calls `mark_clean()` after
re-uploading buffers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from pluton.scene.edge import Edge
from pluton.scene.vertex import Vertex

if TYPE_CHECKING:
    from pluton.scene.face import Face


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
        ValueError — tools should never request one.
        """
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

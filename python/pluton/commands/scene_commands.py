"""Concrete commands for Scene mutations."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pluton.commands.command import Command


class AddVertexCommand(Command):
    name = "Add Vertex"

    def __init__(self, position: np.ndarray) -> None:
        self._position = np.asarray(position, dtype=np.float32).reshape(3).copy()
        self._vertex_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        if self._vertex_id is None:
            # First execution — allocate a new slot.
            self._vertex_id = scene.add_vertex(self._position)
        else:
            # Redo — restore the previously-allocated slot to preserve the ID.
            scene.restore_vertex(self._vertex_id, self._position)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._vertex_id is not None, "AddVertexCommand.undo before do"
        scene.remove_vertex(self._vertex_id)


class AddEdgeCommand(Command):
    name = "Add Edge"

    def __init__(self, v1_id: int, v2_id: int) -> None:
        self._v1, self._v2 = v1_id, v2_id
        self._edge_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        if self._edge_id is None:
            # First execution — allocate a new slot.
            self._edge_id = scene.add_edge(self._v1, self._v2)
        else:
            # Redo — restore the previously-allocated slot to preserve the ID.
            scene.restore_edge(self._edge_id, self._v1, self._v2)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._edge_id is not None, "AddEdgeCommand.undo before do"
        scene.remove_edge(self._edge_id)


class AddFaceCommand(Command):
    name = "Add Face"

    def __init__(self, loop: Sequence[int]) -> None:
        self._loop = tuple(loop)
        self._face_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        if self._face_id is None:
            # First execution — allocate a new slot.
            self._face_id = scene.add_face_from_loop(self._loop)
        else:
            # Redo — restore the previously-allocated slot to preserve the ID.
            scene.restore_face(self._face_id, self._loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._face_id is not None, "AddFaceCommand.undo before do"
        scene.remove_face(self._face_id)


class RemoveFaceCommand(Command):
    name = "Remove Face"

    def __init__(self, face_id: int) -> None:
        self._face_id = face_id
        self._captured_loop: tuple[int, ...] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._captured_loop = tuple(scene.face(self._face_id).loop_vertex_ids)
        scene.remove_face(self._face_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured_loop is not None, "RemoveFaceCommand.undo before do"
        scene.restore_face(self._face_id, self._captured_loop)


class RemoveEdgeCommand(Command):
    name = "Remove Edge"

    def __init__(self, edge_id: int) -> None:
        self._edge_id = edge_id
        self._captured: tuple[int, int] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        e = scene.edge(self._edge_id)
        self._captured = (e.v1_id, e.v2_id)
        scene.remove_edge(self._edge_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured is not None, "RemoveEdgeCommand.undo before do"
        scene.restore_edge(self._edge_id, self._captured[0], self._captured[1])


class RemoveVertexCommand(Command):
    name = "Remove Vertex"

    def __init__(self, vertex_id: int) -> None:
        self._vertex_id = vertex_id
        self._captured_pos: np.ndarray | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._captured_pos = scene.vertex(self._vertex_id).position.copy()
        scene.remove_vertex(self._vertex_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured_pos is not None, "RemoveVertexCommand.undo before do"
        scene.restore_vertex(self._vertex_id, self._captured_pos)


class _AddVertexAtId(Command):
    """Internal: re-adds a vertex at a specific ID. Used by ClearSceneCommand.undo.

    After scene.clear() the slab is empty; restore_vertex requires the slot to
    already exist.  We therefore call scene.add_vertex() so the slab grows
    back.  When the scene is empty and vertices are re-added in their original
    order the C++ HalfEdgeMesh assigns the same sequential IDs.
    """

    def __init__(self, v_id: int, position: np.ndarray) -> None:
        self._v_id = v_id
        self._position = np.asarray(position, dtype=np.float32).reshape(3).copy()

    def do(self, scene) -> None:  # noqa: ANN001
        scene.add_vertex(self._position)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_vertex(self._v_id)


class _AddEdgeAtId(Command):
    """Internal: re-adds an edge at a specific ID."""

    def __init__(self, e_id: int, v1_id: int, v2_id: int) -> None:
        self._e_id = e_id
        self._v1, self._v2 = v1_id, v2_id

    def do(self, scene) -> None:  # noqa: ANN001
        scene.add_edge(self._v1, self._v2)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_edge(self._e_id)


class _AddFaceAtId(Command):
    """Internal: re-adds a face at a specific ID."""

    def __init__(self, f_id: int, loop: Sequence[int]) -> None:
        self._f_id = f_id
        self._loop = tuple(loop)

    def do(self, scene) -> None:  # noqa: ANN001
        scene.add_face_from_loop(self._loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_face(self._f_id)


class ClearSceneCommand(Command):
    """do() captures every live entity and clears; undo() replays Add*AtId children."""

    name = "Clear Scene"

    def __init__(self) -> None:
        self._captured: list[Command] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        captured: list[Command] = []
        for v in scene.vertices_iter():
            captured.append(_AddVertexAtId(v.id, v.position))
        for e in scene.edges_iter():
            captured.append(_AddEdgeAtId(e.id, e.v1_id, e.v2_id))
        for f in scene.faces_iter():
            captured.append(_AddFaceAtId(f.id, f.loop_vertex_ids))
        self._captured = captured
        scene.clear()

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured is not None, "ClearSceneCommand.undo before do"
        for cmd in self._captured:
            cmd.do(scene)


class DissolveEdgeCommand(Command):
    """Dissolve an edge between two faces. Reversible.

    do(): on first call, validates the edge, captures the two source faces'
          vertex loops and the shared edge's vertex pair, then dissolves. On
          redo, the shared edge's id has changed (undo recreates it via
          add_face_from_loop), so we re-resolve the current edge id from the
          captured vertex pair. Boundary / dead / unresolvable edges make the
          command a clean no-op (do + undo both return early), keeping the
          undo stack consistent.
    undo(): removes the merged face and restores the two source faces from
            their captured loops. The shared edge is recreated implicitly by
            add_face_from_loop (with a fresh id — see redo handling above).
    """

    name = "Dissolve Edge"

    def __init__(self, edge_id: int) -> None:
        self._edge_id = edge_id
        self._shared_verts: tuple[int, int] | None = None
        self._captured_f1: tuple[int, ...] | None = None
        self._captured_f2: tuple[int, ...] | None = None
        self._merged_face_id: int | None = None
        self._was_noop: bool = False

    def do(self, scene) -> None:  # noqa: ANN001
        if self._captured_f1 is None:
            # First execution — validate + capture descriptors for undo/redo.
            try:
                faces = scene.edge_faces(self._edge_id)
            except KeyError:
                self._was_noop = True  # dead edge
                return
            if faces[0] is None or faces[1] is None:
                self._was_noop = True  # boundary edge (only one incident face)
                return
            f1, f2 = faces
            loop1 = tuple(scene.face(f1).loop_vertex_ids)
            loop2 = tuple(scene.face(f2).loop_vertex_ids)
            # The shared edge's endpoints are the vertices common to both loops.
            # dissolve targets single-shared-edge adjacency, so this is exactly 2.
            common = [v for v in loop1 if v in loop2]
            if len(common) != 2:
                self._was_noop = True
                return
            self._shared_verts = (common[0], common[1])
            self._captured_f1 = loop1
            self._captured_f2 = loop2
            edge_to_dissolve = self._edge_id
        else:
            # Redo — the original edge id is stale (undo recreated the edge with
            # a new id). Re-resolve the current edge id from the captured pair.
            # add_halfedge_pair returns the existing edge id for a live pair
            # (no mutation); it returns the edge id directly (not a half-edge id).
            assert self._shared_verts is not None
            va, vb = self._shared_verts
            edge_to_dissolve = scene._mesh.add_halfedge_pair(va, vb)

        result = scene.dissolve_edge(edge_to_dissolve)
        if result is None:
            self._was_noop = True
            return
        self._was_noop = False
        self._merged_face_id = result

    def undo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._merged_face_id is not None, "DissolveEdgeCommand.undo before do"
        assert self._captured_f1 is not None
        assert self._captured_f2 is not None

        # Remove the merged face first (frees up the boundary half-edges),
        # then restore both source faces from their captured loops. We use
        # add_face_from_loop (fresh ids) rather than restore_face — the merged
        # face occupied the tombstoned source-face slots.
        scene.remove_face(self._merged_face_id)
        scene.add_face_from_loop(self._captured_f1)
        scene.add_face_from_loop(self._captured_f2)

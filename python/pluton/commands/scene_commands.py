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
    undo(): removes the merged face, then restores the dissolved edge and BOTH
            source faces to their ORIGINAL ids via restore_edge / restore_face
            (id-preserving — NOT add_face_from_loop). This is required so that,
            inside a CompositeCommand, sibling AddFaceCommands whose new-side
            faces this dissolve consumed can still undo by their cached ids.
    """

    name = "Dissolve Edge"

    def __init__(self, edge_id: int) -> None:
        self._edge_id = edge_id
        self._shared_verts: tuple[int, int] | None = None
        self._captured_f1: tuple[int, ...] | None = None
        self._captured_f2: tuple[int, ...] | None = None
        self._f1_id: int | None = None
        self._f2_id: int | None = None
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
            self._f1_id = f1
            self._f2_id = f2
            self._captured_f1 = tuple(scene.face(f1).loop_vertex_ids)
            self._captured_f2 = tuple(scene.face(f2).loop_vertex_ids)
            # Capture the dissolved edge's true endpoints. Vertex ids are stable
            # across undo (undo recreates the edge/faces but reuses vertices), so
            # these drive the redo re-resolution below. This is guaranteed to be
            # the real edge's endpoints — no diagonal-shared-vertex ambiguity.
            e = scene.edge(self._edge_id)
            self._shared_verts = (e.v1_id, e.v2_id)
            edge_to_dissolve = self._edge_id
        else:
            # Redo — the original edge id is stale (undo recreated the edge with
            # a fresh id). Re-resolve the current live edge id from the captured
            # endpoint pair. The endpoints are always a live pair here (undo just
            # restored both faces), so add_halfedge_pair returns the existing
            # edge id idempotently (and returns the edge id directly, not a
            # half-edge id).
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
        assert self._captured_f1 is not None and self._captured_f2 is not None
        assert self._shared_verts is not None
        assert self._f1_id is not None and self._f2_id is not None

        # Remove the merged face, then restore the dissolved edge and BOTH source
        # faces to their ORIGINAL ids. Id-preserving restore (not add_face_from_loop)
        # is required so that, inside a CompositeCommand, sibling AddFaceCommands
        # whose faces this dissolve consumed can still undo by their cached ids.
        # restore_edge must run first — restore_face needs the shared edge present.
        scene.remove_face(self._merged_face_id)
        scene.restore_edge(self._edge_id, self._shared_verts[0], self._shared_verts[1])
        scene.restore_face(self._f1_id, self._captured_f1)
        scene.restore_face(self._f2_id, self._captured_f2)


class SplitEdgeCommand(Command):
    """Split an edge at parameter t, inserting a vertex. Reversible.

    do(): first call performs the split via scene.split_edge and captures BOTH
          the originals (edge endpoints, incident face ids+loops) and the created
          ids (vertex w, two edges, up to two faces) plus the rebuilt loops.
          Redo restores every created entity to its FIRST-RUN id (id-preserving),
          so a sibling command in the same gesture composite that cached the new
          vertex id stays valid across undo/redo (the M3c atomic-undo concern).
    undo(): removes the created faces/edges/vertex, then restores the original
            edge and faces to their ORIGINAL ids (restore_edge before restore_face).
    Invalid/degenerate splits make the command a clean no-op.
    """

    name = "Split Edge"

    def __init__(self, edge_id: int, t: float) -> None:
        self._edge_id = edge_id
        self._t = float(t)
        self._was_noop = False
        self._done_once = False
        # originals
        self._orig_verts: tuple[int, int] | None = None  # (va, vb) = edge endpoints
        self._orig_faces: list[tuple[int, tuple[int, ...]]] = []  # (id, loop) captured
        self._w_pos: np.ndarray | None = None
        # created (first-run ids, reused on redo)
        self.new_vertex_id: int | None = None
        self._e1: int | None = None
        self._e2: int | None = None
        self._new_faces: list[tuple[int, tuple[int, ...]]] = []  # (id, loop-with-w)

    def do(self, scene) -> None:  # noqa: ANN001
        if not self._done_once:
            self._first_do(scene)
        else:
            self._redo(scene)

    def _first_do(self, scene) -> None:  # noqa: ANN001
        try:
            e = scene.edge(self._edge_id)
        except KeyError:
            self._was_noop = True
            self._done_once = True
            return
        va, vb = e.v1_id, e.v2_id
        fa, fb = scene.edge_faces(self._edge_id)
        captured_faces: list[tuple[int, tuple[int, ...]]] = []
        for fid in (fa, fb):
            if fid is not None:
                captured_faces.append((fid, tuple(scene.face(fid).loop_vertex_ids)))

        res = scene.split_edge(self._edge_id, self._t)
        if res is None:
            self._was_noop = True
            self._done_once = True
            return

        self._orig_verts = (va, vb)
        self._orig_faces = captured_faces
        self._w_pos = scene.vertex(res.vertex).position.copy()
        self.new_vertex_id = res.vertex
        self._e1, self._e2 = res.edge_a, res.edge_b
        self._new_faces = []
        for fid in (res.face_a, res.face_b):
            if fid is not None:
                self._new_faces.append((fid, tuple(scene.face(fid).loop_vertex_ids)))
        self._done_once = True
        self._was_noop = False

    def _redo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._orig_verts is not None and self._w_pos is not None
        assert self.new_vertex_id is not None and self._e1 is not None and self._e2 is not None
        va, vb = self._orig_verts
        w = self.new_vertex_id
        scene.restore_vertex(w, self._w_pos)
        for fid, _loop in self._orig_faces:
            scene.remove_face(fid)
        scene.remove_edge(self._edge_id)
        scene.restore_edge(self._e1, va, w)
        scene.restore_edge(self._e2, w, vb)
        for fid, loop in self._new_faces:
            scene.restore_face(fid, loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._orig_verts is not None
        assert self.new_vertex_id is not None and self._e1 is not None and self._e2 is not None
        for fid, _loop in self._new_faces:
            scene.remove_face(fid)
        scene.remove_edge(self._e1)
        scene.remove_edge(self._e2)
        scene.remove_vertex(self.new_vertex_id)
        va, vb = self._orig_verts
        scene.restore_edge(self._edge_id, va, vb)
        for fid, loop in self._orig_faces:
            scene.restore_face(fid, loop)

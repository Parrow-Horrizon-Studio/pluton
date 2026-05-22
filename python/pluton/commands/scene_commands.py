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
        self._vertex_id = scene.add_vertex(self._position)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._vertex_id is not None, "AddVertexCommand.undo before do"
        scene.remove_vertex(self._vertex_id)


class AddEdgeCommand(Command):
    name = "Add Edge"

    def __init__(self, v1_id: int, v2_id: int) -> None:
        self._v1, self._v2 = v1_id, v2_id
        self._edge_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._edge_id = scene.add_edge(self._v1, self._v2)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._edge_id is not None, "AddEdgeCommand.undo before do"
        scene.remove_edge(self._edge_id)


class AddFaceCommand(Command):
    name = "Add Face"

    def __init__(self, loop: Sequence[int]) -> None:
        self._loop = tuple(loop)
        self._face_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._face_id = scene.add_face_from_loop(self._loop)

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

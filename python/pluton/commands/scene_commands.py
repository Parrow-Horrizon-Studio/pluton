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

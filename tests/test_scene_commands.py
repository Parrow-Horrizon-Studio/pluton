"""Tests for AddVertex / AddEdge / AddFace / Remove* / ClearScene commands."""

from __future__ import annotations

import numpy as np


def _three_vertex_scene():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    return s, v0, v1, v2


def test_add_vertex_command_round_trip():
    from pluton.commands.scene_commands import AddVertexCommand
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([3.0, 4.0, 0.0], dtype=np.float32)
    cmd = AddVertexCommand(pos)

    cmd.do(s)
    assert len(list(s.vertices_iter())) == 1

    cmd.undo(s)
    assert len(list(s.vertices_iter())) == 0

    cmd.do(s)
    assert len(list(s.vertices_iter())) == 1


def test_add_edge_command_round_trip():
    from pluton.commands.scene_commands import AddEdgeCommand
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    cmd = AddEdgeCommand(v0, v1)

    cmd.do(s)
    assert len(list(s.edges_iter())) == 1

    cmd.undo(s)
    assert len(list(s.edges_iter())) == 0


def test_add_face_command_round_trip():
    from pluton.commands.scene_commands import AddFaceCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    cmd = AddFaceCommand((v0, v1, v2))

    cmd.do(s)
    assert len(list(s.faces_iter())) == 1

    cmd.undo(s)
    assert len(list(s.faces_iter())) == 0


def test_remove_face_command_round_trip():
    from pluton.commands.scene_commands import AddFaceCommand, RemoveFaceCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    add = AddFaceCommand((v0, v1, v2))
    add.do(s)
    f = next(iter(s.faces_iter())).id

    remove = RemoveFaceCommand(f)
    remove.do(s)
    assert len(list(s.faces_iter())) == 0

    remove.undo(s)
    assert len(list(s.faces_iter())) == 1
    assert next(iter(s.faces_iter())).id == f


def test_remove_edge_command_round_trip():
    from pluton.commands.scene_commands import AddEdgeCommand, RemoveEdgeCommand
    from pluton.scene import Scene

    s, v0, v1, _ = _three_vertex_scene()
    add = AddEdgeCommand(v0, v1)
    add.do(s)
    e = next(iter(s.edges_iter())).id

    remove = RemoveEdgeCommand(e)
    remove.do(s)
    assert len(list(s.edges_iter())) == 0

    remove.undo(s)
    assert len(list(s.edges_iter())) == 1


def test_remove_vertex_command_round_trip():
    from pluton.commands.scene_commands import RemoveVertexCommand
    from pluton.scene import Scene

    s = Scene()
    v = s.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))

    remove = RemoveVertexCommand(v)
    remove.do(s)
    assert len(list(s.vertices_iter())) == 0

    remove.undo(s)
    assert len(list(s.vertices_iter())) == 1
    restored = next(iter(s.vertices_iter()))
    assert restored.id == v
    np.testing.assert_array_equal(restored.position, np.array([1.0, 2.0, 0.0], dtype=np.float32))


def test_clear_scene_command_captures_and_restores():
    from pluton.commands.scene_commands import ClearSceneCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    s.add_face_from_loop((v0, v1, v2))
    assert len(list(s.vertices_iter())) == 3
    assert len(list(s.edges_iter())) == 3
    assert len(list(s.faces_iter())) == 1

    cmd = ClearSceneCommand()
    cmd.do(s)
    assert len(list(s.vertices_iter())) == 0
    assert len(list(s.edges_iter())) == 0
    assert len(list(s.faces_iter())) == 0

    cmd.undo(s)
    # All IDs restored.
    verts = list(s.vertices_iter())
    edges = list(s.edges_iter())
    faces = list(s.faces_iter())
    assert len(verts) == 3
    assert len(edges) == 3
    assert len(faces) == 1
    assert {v.id for v in verts} == {v0, v1, v2}

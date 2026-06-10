"""DissolveEdgeCommand: do, undo, redo round-trips."""

from __future__ import annotations

import numpy as np

from pluton.commands.scene_commands import DissolveEdgeCommand
from pluton.scene.scene import Scene


def _two_quads_sharing_edge(scene: Scene) -> tuple[int, int, int]:
    """Returns (f1, f2, shared_edge_id) — identical setup to test_scene_dissolve."""
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
    v4 = scene.add_vertex(np.array([2, 0, 0], dtype=np.float32))
    v5 = scene.add_vertex(np.array([2, 1, 0], dtype=np.float32))
    scene.add_edge(v0, v1)
    e_shared = scene.add_edge(v1, v2)
    scene.add_edge(v2, v3)
    scene.add_edge(v3, v0)
    scene.add_edge(v1, v4)
    scene.add_edge(v4, v5)
    scene.add_edge(v5, v2)
    f1 = scene.add_face_from_loop([v0, v1, v2, v3])
    f2 = scene.add_face_from_loop([v1, v4, v5, v2])
    return f1, f2, e_shared


def test_do_removes_shared_edge_and_merges_faces():
    scene = Scene()
    f1, f2, e_shared = _two_quads_sharing_edge(scene)

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)

    # The two source faces are gone; one merged face has 6 vertices.
    live_faces = [f.id for f in scene.faces_iter()]
    assert f1 not in live_faces
    assert f2 not in live_faces
    assert len(live_faces) == 1
    assert len(scene.face(live_faces[0]).loop_vertex_ids) == 6


def test_undo_restores_both_original_faces():
    scene = Scene()
    f1_orig, f2_orig, e_shared = _two_quads_sharing_edge(scene)
    pre_face_count = sum(1 for _ in scene.faces_iter())
    pre_edge_count = sum(1 for _ in scene.edges_iter())

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)
    cmd.undo(scene)

    post_face_count = sum(1 for _ in scene.faces_iter())
    post_edge_count = sum(1 for _ in scene.edges_iter())
    assert post_face_count == pre_face_count
    assert post_edge_count == pre_edge_count


def test_do_returns_none_op_on_boundary_edge():
    """Command on a boundary edge does nothing; undo also does nothing.
    The undo stack must stay consistent (no exceptions)."""
    scene = Scene()
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2); scene.add_edge(v2, v0)
    f = scene.add_face_from_loop([v0, v1, v2])
    e_boundary = scene.face_edges(f)[0]

    cmd = DissolveEdgeCommand(e_boundary)
    cmd.do(scene)    # should not raise
    cmd.undo(scene)  # should not raise

    # Mesh unchanged.
    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene.face(f).loop_vertex_ids == (v0, v1, v2)


def test_do_undo_redo_round_trip():
    scene = Scene()
    f1_orig, f2_orig, e_shared = _two_quads_sharing_edge(scene)

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)

    cmd.undo(scene)
    cmd.do(scene)  # redo

    # After redo the mesh must be back to the MERGED state: exactly one live
    # face, a hexagon. Redo re-resolves the (now-changed) shared edge id from
    # the captured vertex pair, so it genuinely re-merges (not a no-op).
    live_faces = [f.id for f in scene.faces_iter()]
    assert len(live_faces) == 1
    merged_id_after_redo = live_faces[0]
    assert scene._mesh.face_is_live(merged_id_after_redo)
    assert len(scene.face(merged_id_after_redo).loop_vertex_ids) == 6

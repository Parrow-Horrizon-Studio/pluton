"""Every face-keyed sidecar survives the destroy-and-rebuild inside split_edge.

Before M7.5c these all failed: HalfEdgeMesh::split_edge removes both incident
faces and rebuilds them with new ids, and nothing carried the sidecars across.
"""

import numpy as np

from pluton.commands.scene_commands import SplitEdgeCommand
from pluton.scene.scene import Scene, Side, TexturePlacement


def _painted_quad(scene, material_id=7):
    ids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    ]
    f = scene.add_face_from_loop(ids)
    scene.set_face_material(f, material_id, Side.FRONT)
    return f, ids


def test_material_survives_a_split():
    s = Scene()
    f, ids = _painted_quad(s)
    e = s.edge_between(ids[0], ids[1])
    res = s.split_edge(e, 0.25)
    assert res is not None and res.face_a is not None
    assert s.face_material(res.face_a, Side.FRONT) == 7


def test_back_material_survives_a_split():
    s = Scene()
    f, ids = _painted_quad(s)
    s.set_face_material(f, 3, Side.BACK)
    e = s.edge_between(ids[0], ids[1])
    res = s.split_edge(e, 0.25)
    assert s.face_material(res.face_a, Side.BACK) == 3


def test_placement_survives_a_split():
    s = Scene()
    f, ids = _painted_quad(s)
    s.set_face_placement(f, TexturePlacement(0.25, 0.5, 2.0, 0.75), Side.FRONT)
    e = s.edge_between(ids[0], ids[1])
    res = s.split_edge(e, 0.25)
    got = s.face_placement(res.face_a, Side.FRONT)
    assert (got.offset_u, got.offset_v, got.scale, got.rotation) == (0.25, 0.5, 2.0, 0.75)


def test_stored_uvs_gain_one_lerped_corner():
    s = Scene()
    f, ids = _painted_quad(s)
    # UVs parallel to the loop, which is ids[0..3] in order.
    s.set_face_uvs(f, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], Side.FRONT)
    e = s.edge_between(ids[0], ids[1])
    res = s.split_edge(e, 0.25)

    new_loop = s.face_loop(res.face_a)
    uvs = s.face_uvs(res.face_a, Side.FRONT)
    assert uvs is not None
    assert uvs.shape == (5, 2)
    inserted_at = new_loop.index(res.vertex)
    # 0.25 from (0,0) toward (1,0). NOT 0.5: a midpoint implementation and a
    # copy-the-neighbour implementation both pass a t=0.5 test.
    np.testing.assert_allclose(uvs[inserted_at], [0.25, 0.0], atol=1e-6)


def test_the_old_faces_entries_are_left_in_place_for_undo():
    s = Scene()
    f, ids = _painted_quad(s)
    e = s.edge_between(ids[0], ids[1])
    s.split_edge(e, 0.25)
    # The dead face keeps its entry; ids are never reused so this is safe, and
    # restore_face on undo relies on it.
    assert s._face_materials_front[f] == 7


def test_undo_then_redo_keeps_the_material_on_the_live_face():
    s = Scene()
    f, ids = _painted_quad(s)
    e = s.edge_between(ids[0], ids[1])
    cmd = SplitEdgeCommand(e, 0.25)

    cmd.do(s)
    assert any(s.face_material(fc.id, Side.FRONT) == 7 for fc in s.faces_iter())

    cmd.undo(s)
    assert s.face_material(f, Side.FRONT) == 7

    cmd.do(s)
    assert any(s.face_material(fc.id, Side.FRONT) == 7 for fc in s.faces_iter())


def test_a_boundary_edge_split_transfers_only_the_one_real_face():
    s = Scene()
    f, ids = _painted_quad(s)
    e = s.edge_between(ids[0], ids[1])
    res = s.split_edge(e, 0.25)
    # A lone quad's edges are all boundary, so one side has no face at all.
    assert res.face_b is None
    assert s.face_material(res.face_a, Side.FRONT) == 7

"""Scene.split_face: sub-loop construction and the kernel call (M7.6a)."""

import numpy as np
from pluton.scene.scene import Scene


def _quad(scene, z=0.0):
    ids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
    ]
    return scene.add_face_from_loop(ids), ids


def test_a_chord_between_opposite_corners_makes_two_triangles():
    s = Scene()
    fid, v = _quad(s)
    s.add_edge(v[0], v[2])

    out = s.split_face(fid, [v[0], v[2]])

    assert out is not None
    a, b = out
    assert sorted([len(s.face_loop(a)), len(s.face_loop(b))]) == [3, 3]
    assert len(list(s.faces_iter())) == 2


def test_a_chord_with_an_interior_vertex_keeps_it_on_both_children():
    """The chain's interior vertices belong to BOTH children's loops, once
    each, which is what makes them a shared boundary rather than a slit."""
    s = Scene()
    fid, v = _quad(s)
    mid = s.add_vertex(np.array((0.5, 0.5, 0.0), dtype=np.float32))
    s.add_edge(v[0], mid)
    s.add_edge(mid, v[2])

    out = s.split_face(fid, [v[0], mid, v[2]])

    assert out is not None
    a, b = out
    assert mid in s.face_loop(a)
    assert mid in s.face_loop(b)
    assert sorted([len(s.face_loop(a)), len(s.face_loop(b))]) == [4, 4]


def test_both_children_keep_the_parents_normal():
    s = Scene()
    fid, v = _quad(s)
    parent_normal = s.face_normal(fid).copy()
    s.add_edge(v[0], v[2])

    a, b = s.split_face(fid, [v[0], v[2]])

    for child in (a, b):
        assert float(np.dot(s.face_normal(child), parent_normal)) > 0.999


def test_a_chain_whose_ends_are_not_both_on_the_loop_is_refused():
    s = Scene()
    fid, v = _quad(s)
    stray = s.add_vertex(np.array((5.0, 5.0, 0.0), dtype=np.float32))
    s.add_edge(v[0], stray)

    assert s.split_face(fid, [v[0], stray]) is None


def test_a_chain_of_fewer_than_two_vertices_is_refused():
    s = Scene()
    fid, v = _quad(s)
    assert s.split_face(fid, [v[0]]) is None


def test_a_refused_split_leaves_the_face_alone():
    s = Scene()
    fid, v = _quad(s)
    assert s.split_face(fid, [v[0], v[1]]) is None  # adjacent corners: no interior
    assert len(list(s.faces_iter())) == 1
    assert len(s.face_loop(fid)) == 4


def test_a_dead_face_is_refused():
    s = Scene()
    fid, v = _quad(s)
    s.remove_face(fid)
    assert s.split_face(fid, [v[0], v[2]]) is None


def test_a_chain_with_a_duplicate_vertex_is_refused():
    s = Scene()
    fid, v = _quad(s)
    s.add_edge(v[0], v[2])
    assert s.split_face(fid, [v[0], v[2], v[0]]) is None
    assert len(list(s.faces_iter())) == 1
    assert len(s.face_loop(fid)) == 4


def test_an_interior_chain_vertex_on_the_parents_loop_is_refused():
    """A chain vertex between the ends must not itself already be a loop
    vertex: that would make it a second chord end, not an interior point of
    a chain, and the two sub-loops built from it would not be simple."""
    s = Scene()
    fid, v = _quad(s)
    s.add_edge(v[0], v[1])
    assert s.split_face(fid, [v[0], v[1], v[2]]) is None
    assert len(list(s.faces_iter())) == 1
    assert len(s.face_loop(fid)) == 4


def test_identical_first_and_last_chain_vertices_are_refused():
    s = Scene()
    fid, v = _quad(s)
    mid = s.add_vertex(np.array((0.5, 0.5, 0.0), dtype=np.float32))
    s.add_edge(v[0], mid)
    assert s.split_face(fid, [v[0], mid, v[0]]) is None
    assert len(list(s.faces_iter())) == 1
    assert len(s.face_loop(fid)) == 4

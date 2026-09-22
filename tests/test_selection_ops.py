"""Tests for pluton.selection_ops: pure selection derivations.

Every test here builds a bare Scene and calls the function directly. No
widget, no QApplication, no Model unless the function under test needs one.
"""

from __future__ import annotations

import numpy as np
import pytest


def _quad_pair():
    """Two quads sharing one edge, lying in the z=0 plane.

        d---c---f
        |   |   |
        a---b---e

    Returns (scene, ids) where ids is a dict of the named vertices, the two
    face ids and the shared edge id.
    """
    from pluton.scene import Scene

    scene = Scene()
    a = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    d = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    e = scene.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    f = scene.add_vertex(np.array([2.0, 1.0, 0.0], dtype=np.float32))
    left = scene.add_face_from_loop((a, b, c, d))
    right = scene.add_face_from_loop((b, e, f, c))
    shared = scene.edge_between(b, c)
    assert shared is not None
    return scene, {
        "a": a, "b": b, "c": c, "d": d, "e": e, "f": f,
        "left": left, "right": right, "shared": shared,
    }


def test_bounding_edges_returns_all_four_edges_of_a_quad():
    from pluton.selection_ops import bounding_edges

    scene, ids = _quad_pair()
    got = bounding_edges(scene, {ids["left"]})
    assert len(got) == 4
    assert ids["shared"] in got


def test_bounding_edges_unions_two_faces_and_counts_the_shared_edge_once():
    from pluton.selection_ops import bounding_edges

    scene, ids = _quad_pair()
    got = bounding_edges(scene, {ids["left"], ids["right"]})
    # Four edges each, one shared: 4 + 4 - 1 == 7.
    assert len(got) == 7


def test_bounding_edges_skips_a_dead_face_id():
    from pluton.selection_ops import bounding_edges

    scene, ids = _quad_pair()
    got = bounding_edges(scene, {ids["left"], 9999})
    assert len(got) == 4


def test_adjacent_faces_of_the_shared_edge_is_both_quads():
    from pluton.selection_ops import adjacent_faces

    scene, ids = _quad_pair()
    got = adjacent_faces(scene, {ids["shared"]})
    assert got == {ids["left"], ids["right"]}


def test_adjacent_faces_drops_the_none_side_of_a_boundary_edge():
    from pluton.selection_ops import adjacent_faces

    scene, ids = _quad_pair()
    outer = scene.edge_between(ids["a"], ids["b"])
    got = adjacent_faces(scene, {outer})
    assert got == {ids["left"]}


def test_adjacent_faces_of_a_naked_edge_is_empty():
    from pluton.scene import Scene
    from pluton.selection_ops import adjacent_faces

    scene = Scene()
    p = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    q = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    naked = scene.add_edge(p, q)
    assert adjacent_faces(scene, {naked}) == set()


def test_adjacent_faces_skips_a_dead_edge_id():
    from pluton.selection_ops import adjacent_faces

    scene, ids = _quad_pair()
    assert adjacent_faces(scene, {ids["shared"], 9999}) == {ids["left"], ids["right"]}


def test_incident_edges_of_the_shared_corner_finds_every_touching_edge():
    from pluton.selection_ops import incident_edges

    scene, ids = _quad_pair()
    got = incident_edges(scene, {ids["b"]})
    # b touches a-b, b-c (shared) and b-e.
    assert len(got) == 3
    assert ids["shared"] in got


def test_incident_edges_of_no_vertices_is_empty():
    from pluton.selection_ops import incident_edges

    scene, _ids = _quad_pair()
    assert incident_edges(scene, set()) == set()


@pytest.mark.parametrize("fn_name", ["bounding_edges", "adjacent_faces", "incident_edges"])
def test_neighbour_queries_return_a_plain_set_of_ints(fn_name):
    """Callers union these into Selection sets, which hold ints. A numpy
    integer would compare equal but hash into a set that later fails an
    `id in selection.edges` check against a plain int in some code paths."""
    import pluton.selection_ops as ops

    scene, ids = _quad_pair()
    seed = {"bounding_edges": {ids["left"]},
            "adjacent_faces": {ids["shared"]},
            "incident_edges": {ids["b"]}}[fn_name]
    got = getattr(ops, fn_name)(scene, seed)
    assert isinstance(got, set)
    assert all(type(x) is int for x in got)

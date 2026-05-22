"""Unit tests for the Python scene data model (Vertex, Edge, Face, Scene)."""

from __future__ import annotations

import numpy as np
import pytest


def test_vertex_holds_id_and_position():
    from pluton.scene import Vertex

    v = Vertex(id=7, position=np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert v.id == 7
    np.testing.assert_array_equal(v.position, np.array([1.0, 2.0, 3.0], dtype=np.float32))


def test_vertex_is_frozen():
    from pluton.scene import Vertex

    v = Vertex(id=0, position=np.array([0.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(Exception):
        v.id = 1  # type: ignore[misc]


def test_edge_holds_id_and_two_vertex_ids():
    from pluton.scene import Edge

    e = Edge(id=3, v1_id=10, v2_id=20)
    assert e.id == 3
    assert e.v1_id == 10
    assert e.v2_id == 20


def test_face_holds_id_loop_normal_triangles():
    from pluton.scene import Face

    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    f = Face(
        id=5,
        loop_vertex_ids=(0, 1, 2, 3),
        plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        triangles=triangles,
    )
    assert f.id == 5
    assert f.loop_vertex_ids == (0, 1, 2, 3)
    np.testing.assert_array_equal(f.plane_normal, np.array([0.0, 0.0, 1.0], dtype=np.float32))
    np.testing.assert_array_equal(f.triangles, triangles)

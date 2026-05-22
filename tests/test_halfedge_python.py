"""Tests for the nanobind bindings exposing HalfEdgeMesh to Python."""

from __future__ import annotations

import numpy as np
import pytest


def test_halfedge_mesh_constructs_empty():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    assert m.vertex_slab_size() == 0
    assert m.halfedge_slab_size() == 0
    assert m.face_slab_size() == 0


def test_invalid_id_constant():
    from pluton._core import HalfEdgeMesh

    assert HalfEdgeMesh.INVALID_ID == 0xFFFFFFFF


def test_add_vertex_returns_int_id():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    assert v0 == 0
    assert v1 == 1
    assert list(m.vertex_position(v0)) == [0.0, 0.0, 0.0]


def test_add_halfedge_pair_and_face():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v0)
    f = m.add_face_from_loop([v0, v1, v2], [0, 1, 2])
    assert f == 0
    assert m.face_is_live(f)
    assert list(m.face_loop_vertices(f)) == [v0, v1, v2]


def test_remove_face_throws_on_double_remove():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v0)
    f = m.add_face_from_loop([v0, v1, v2], [0, 1, 2])
    m.remove_face(f)
    with pytest.raises(Exception):  # std::out_of_range → IndexError in nanobind
        m.remove_face(f)


def test_buffer_projections_return_lists():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    m.add_halfedge_pair(v0, v1)

    buf = list(m.edge_line_buffer())
    assert len(buf) == 6

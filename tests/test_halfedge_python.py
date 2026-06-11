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


def test_face_loop_vertices_returns_ordered_boundary_ids():
    """M3a contract M3b depends on: face_loop_vertices returns the boundary
    loop vertex IDs in insertion order. PushPullTool reads this to know which
    source-face vertices to extrude."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(0.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    mesh.add_halfedge_pair(v1, v2)
    mesh.add_halfedge_pair(v2, v3)
    mesh.add_halfedge_pair(v3, v0)
    # Two-triangle fan for the rectangle: (v0, v1, v2) + (v0, v2, v3).
    f = mesh.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    loop = mesh.face_loop_vertices(f)
    assert list(loop) == [v0, v1, v2, v3]


def test_face_triangles_returns_flat_triangulation_buffer():
    """M3a contract M3b depends on: face_triangles returns a flat list of vertex
    IDs (3 per triangle). ray_intersect_mesh walks this to test ray-triangle
    intersection per face."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(0.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    mesh.add_halfedge_pair(v1, v2)
    mesh.add_halfedge_pair(v2, v3)
    mesh.add_halfedge_pair(v3, v0)
    f = mesh.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    tris = list(mesh.face_triangles(f))
    assert len(tris) == 6  # 2 triangles × 3 vertices
    assert tris == [v0, v1, v2, v0, v2, v3]


def test_face_triangles_raises_on_invalid_face_id():
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    with pytest.raises(Exception):  # IndexError or out_of_range translated to a Python exception
        mesh.face_triangles(42)


def test_dissolve_edge_binding_round_trip():
    """nanobind smoke test: M3c dissolve_edge binding returns a valid face id
    after dissolving the shared edge between two triangles."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(2.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    e_shared = mesh.add_halfedge_pair(v1, v2)  # add_halfedge_pair returns the edge id
    mesh.add_halfedge_pair(v2, v0)
    mesh.add_halfedge_pair(v1, v3)
    mesh.add_halfedge_pair(v3, v2)
    mesh.add_face_from_loop([v0, v1, v2], [v0, v1, v2])
    mesh.add_face_from_loop([v1, v3, v2], [v1, v3, v2])

    new_face = mesh.dissolve_edge(e_shared)
    assert new_face != HalfEdgeMesh.INVALID_ID
    assert mesh.face_is_live(new_face)
    assert not mesh.edge_is_live(e_shared)


def test_faces_are_coplanar_binding():
    """nanobind smoke test: M3c faces_are_coplanar accepts float tolerances and
    returns a bool."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    # Two coplanar triangles on the XY plane.
    v0 = mesh.add_vertex(0,0,0); v1 = mesh.add_vertex(1,0,0); v2 = mesh.add_vertex(0,1,0)
    v3 = mesh.add_vertex(5,5,0); v4 = mesh.add_vertex(6,5,0); v5 = mesh.add_vertex(5,6,0)
    mesh.add_halfedge_pair(v0, v1); mesh.add_halfedge_pair(v1, v2); mesh.add_halfedge_pair(v2, v0)
    mesh.add_halfedge_pair(v3, v4); mesh.add_halfedge_pair(v4, v5); mesh.add_halfedge_pair(v5, v3)
    f1 = mesh.add_face_from_loop([v0, v1, v2], [v0, v1, v2])
    f2 = mesh.add_face_from_loop([v3, v4, v5], [v3, v4, v5])

    assert mesh.faces_are_coplanar(f1, f2, 0.9999619, 1e-4) is True
    # Loosen → still True; tighten dist → still True since both on z=0
    assert mesh.faces_are_coplanar(f1, f2, 0.5, 1e-6) is True


def test_split_edge_binding_smoke():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(1.0, 1.0, 0.0)
    v3 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    e = m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v3)
    m.add_halfedge_pair(v3, v0)
    m.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    res = m.split_edge(e, 0.5)
    assert res is not None
    assert m.vertex_is_live(res.vertex)
    assert m.edge_is_live(res.edge_a)
    assert m.edge_is_live(res.edge_b)
    # Boundary quad → single incident face rebuilt to 5 vertices.
    live = res.face_a if res.face_a != HalfEdgeMesh.INVALID_ID else res.face_b
    assert len(m.face_loop_vertices(live)) == 5
    # Out-of-range t → None.
    assert m.split_edge(res.edge_a, 1.0) is None

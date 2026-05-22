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


# ---------------------------------------------------------------------------
# Scene tests (Task 3)
# ---------------------------------------------------------------------------


def test_scene_starts_empty():
    from pluton.scene import Scene

    s = Scene()
    assert len(list(s.vertices_iter())) == 0
    assert len(list(s.edges_iter())) == 0
    assert len(list(s.faces_iter())) == 0
    assert s.dirty is False


def test_add_vertex_returns_new_id_when_position_is_new():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    assert v0 != v1
    assert s.dirty is True


def test_add_vertex_is_idempotent_on_exact_match():
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([2.0, 3.0, 0.0], dtype=np.float32)
    v0 = s.add_vertex(pos)
    v1 = s.add_vertex(pos.copy())  # different array object, same exact values
    assert v0 == v1


def test_clear_resets_dirty_flag_and_removes_everything():
    from pluton.scene import Scene

    s = Scene()
    s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    s.mark_clean()
    assert s.dirty is False

    s.clear()
    assert len(list(s.vertices_iter())) == 0
    assert len(list(s.edges_iter())) == 0
    assert len(list(s.faces_iter())) == 0
    assert s.dirty is True


def test_vertex_lookup_by_id():
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([5.0, 6.0, 0.0], dtype=np.float32)
    vid = s.add_vertex(pos)
    v = s.vertex(vid)
    assert v.id == vid
    np.testing.assert_array_equal(v.position, pos)


# ---------------------------------------------------------------------------
# Hardening tests (Task 2 carry-overs)
# ---------------------------------------------------------------------------


def test_vertex_is_hashable_by_id():
    from pluton.scene import Vertex

    a = Vertex(id=7, position=np.array([1.0, 2.0, 3.0], dtype=np.float32))
    b = Vertex(id=7, position=np.array([9.0, 9.0, 9.0], dtype=np.float32))
    c = Vertex(id=8, position=np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert hash(a) == hash(b)  # same id → same hash
    assert a == b               # equality by id
    assert a != c               # different id → not equal
    s = {a, b, c}
    assert len(s) == 2          # works in a set


def test_vertex_position_is_immutable():
    from pluton.scene import Vertex

    v = Vertex(id=0, position=np.array([1.0, 2.0, 3.0], dtype=np.float32))
    with pytest.raises(ValueError):
        v.position[0] = 99.0  # array writability locked


def test_face_position_arrays_are_immutable():
    from pluton.scene import Face

    f = Face(
        id=0,
        loop_vertex_ids=(0, 1, 2),
        plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        triangles=np.array([[0, 1, 2]], dtype=np.int32),
    )
    with pytest.raises(ValueError):
        f.plane_normal[0] = 99.0
    with pytest.raises(ValueError):
        f.triangles[0, 0] = 99


def test_add_vertex_collapses_negative_zero():
    """`-0.0` and `0.0` must dedupe to the same vertex (computed coords can produce -0.0)."""
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([-0.0, 0.0, 0.0], dtype=np.float32))
    assert v0 == v1
    assert len(list(s.vertices_iter())) == 1


# ---------------------------------------------------------------------------
# add_edge tests (Task 4)
# ---------------------------------------------------------------------------


def test_add_edge_returns_new_id():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    e = s.add_edge(v0, v1)
    assert isinstance(e, int)
    assert e == 0  # first edge in a fresh scene starts at 0


def test_add_edge_is_idempotent_unordered():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    a = s.add_edge(v0, v1)
    b = s.add_edge(v1, v0)  # swapped order
    assert a == b


def test_add_edge_rejects_self_loop():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(ValueError):
        s.add_edge(v0, v0)


def test_add_edge_canonicalises_endpoints():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    eid = s.add_edge(v1, v0)
    e = next(iter(s.edges_iter()))
    assert e.id == eid
    assert e.v1_id == min(v0, v1)
    assert e.v2_id == max(v0, v1)


def test_add_edge_rejects_unknown_vertex_ids():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(KeyError):
        s.add_edge(v0, 999)  # 999 doesn't exist
    with pytest.raises(KeyError):
        s.add_edge(999, v0)  # both directions
    # No edge should have been added.
    assert len(list(s.edges_iter())) == 0


# ---------------------------------------------------------------------------
# add_face_from_loop tests (Task 5)
# ---------------------------------------------------------------------------


def test_add_face_from_loop_creates_face_and_triangulates():
    from pluton.scene import Scene

    s = Scene()
    # A unit square on Z=0
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))

    fid = s.add_face_from_loop((v0, v1, v2, v3))

    faces = list(s.faces_iter())
    assert len(faces) == 1
    f = faces[0]
    assert f.id == fid
    assert f.loop_vertex_ids == (v0, v1, v2, v3)
    # Ground plane normal is +Z
    np.testing.assert_allclose(f.plane_normal, np.array([0.0, 0.0, 1.0], dtype=np.float32))
    # Square triangulates to 2 triangles
    assert f.triangles.shape == (2, 3)


def test_add_face_from_loop_rejects_fewer_than_three_vertices():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))

    with pytest.raises(ValueError):
        s.add_face_from_loop((v0, v1))


def test_add_face_from_loop_triangulates_concave_polygon():
    from pluton.scene import Scene

    s = Scene()
    # An L-shape (6 vertices, concave) on Z=0
    pts = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    vids = [
        s.add_vertex(np.array([x, y, 0.0], dtype=np.float32)) for (x, y) in pts
    ]

    s.add_face_from_loop(tuple(vids))

    f = next(iter(s.faces_iter()))
    # An L-shape has 6 vertices, so earcut produces 4 triangles
    assert f.triangles.shape == (4, 3)


def test_add_face_from_loop_rejects_unknown_vertex_id():
    """Phantom vertex IDs in the loop must raise — topology coherence."""
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(KeyError):
        s.add_face_from_loop((v0, v1, 999))
    assert len(list(s.faces_iter())) == 0


def test_add_face_from_loop_accepts_list_and_stores_as_tuple():
    """Accept any Sequence; the stored loop_vertex_ids must be a tuple."""
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))

    fid = s.add_face_from_loop([v0, v1, v2])  # list, not tuple

    f = next(iter(s.faces_iter()))
    assert isinstance(f.loop_vertex_ids, tuple)
    assert f.loop_vertex_ids == (v0, v1, v2)

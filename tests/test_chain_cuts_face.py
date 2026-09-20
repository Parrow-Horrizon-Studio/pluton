"""chain_cuts_face: which face, if any, a drawn chain divides (M7.6a)."""

import numpy as np
from pluton.scene.scene import Scene
from pluton.tools.shape_support import chain_cuts_face


def _quad(s, z=0.0, size=2.0):
    v = [
        s.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (size, 0, z), (size, size, z), (0, size, z)]
    ]
    return s.add_face_from_loop(v), v


def test_a_chord_between_opposite_corners_cuts_the_face():
    s = Scene()
    fid, v = _quad(s)
    s.add_edge(v[0], v[2])
    assert chain_cuts_face(s, [v[0], v[2]]) == fid


def test_a_chain_with_an_interior_vertex_cuts_the_face():
    s = Scene()
    fid, v = _quad(s)
    mid = s.add_vertex(np.array((1.0, 0.5, 0.0), dtype=np.float32))
    s.add_edge(v[0], mid)
    s.add_edge(mid, v[2])
    assert chain_cuts_face(s, [v[0], mid, v[2]]) == fid


def test_a_closing_loop_is_never_a_split():
    """Snapping back onto the first vertex is the face-creation path."""
    s = Scene()
    fid, v = _quad(s)
    assert chain_cuts_face(s, [v[0], v[1], v[2], v[0]]) is None


def test_a_chain_running_along_the_boundary_does_not_cut():
    """Two adjacent corners. The segment lies ON the loop rather than across
    the interior, so its midpoint sits on the boundary rather than strictly
    inside it. This is the case the midpoint test exists for."""
    s = Scene()
    fid, v = _quad(s)
    assert chain_cuts_face(s, [v[0], v[1]]) is None


def test_a_chain_whose_interior_leaves_the_plane_does_not_cut():
    s = Scene()
    fid, v = _quad(s)
    off = s.add_vertex(np.array((1.0, 1.0, 5.0), dtype=np.float32))
    s.add_edge(v[0], off)
    s.add_edge(off, v[2])
    assert chain_cuts_face(s, [v[0], off, v[2]]) is None


def test_a_chain_whose_interior_leaves_the_polygon_does_not_cut():
    """In plane, but outside the face. A concave parent is where this bites,
    so build one: an L shape whose notch a straight chord would cross."""
    s = Scene()
    pts = [(0, 0, 0), (3, 0, 0), (3, 1, 0), (1, 1, 0), (1, 3, 0), (0, 3, 0)]
    v = [s.add_vertex(np.array(p, dtype=np.float32)) for p in pts]
    s.add_face_from_loop(v)
    outside = s.add_vertex(np.array((2.5, 2.5, 0.0), dtype=np.float32))
    s.add_edge(v[1], outside)
    s.add_edge(outside, v[4])
    assert chain_cuts_face(s, [v[1], outside, v[4]]) is None


def test_an_interior_chain_vertex_that_is_on_the_loop_does_not_cut():
    s = Scene()
    fid, v = _quad(s)
    assert chain_cuts_face(s, [v[0], v[1], v[2]]) is None


def test_a_chain_between_two_different_faces_does_not_cut():
    """Two disjoint quads. Each end lies on a boundary loop, but no single
    face's loop contains both, so there is no candidate at all -- distinct
    from the zero-survivors-after-filtering cases above."""
    s = Scene()
    fid1, v1 = _quad(s, z=0.0)
    fid2, v2 = _quad(s, z=10.0)
    assert fid1 != fid2
    assert chain_cuts_face(s, [v1[0], v2[2]]) is None

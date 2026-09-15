import numpy as np
import pytest

from pluton.scene.scene import Scene, Side


def _quad(scene, z=0.0):
    ids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
    ]
    return scene.add_face_from_loop(ids)


def test_a_face_has_no_stored_uvs_by_default():
    s = Scene()
    f = _quad(s)
    assert s.face_uvs(f, Side.FRONT) is None
    assert s.face_uvs(f, Side.BACK) is None


def test_set_and_read_back():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], Side.FRONT)
    got = s.face_uvs(f, Side.FRONT)
    assert got is not None
    assert got.shape == (4, 2)
    assert got.dtype == np.float32
    np.testing.assert_allclose(got, [[0, 0], [1, 0], [1, 1], [0, 1]])


def test_the_two_sides_are_independent():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    assert s.face_uvs(f, Side.BACK) is None
    s.set_face_uvs(f, [(0.5, 0.5)] * 4, Side.BACK)
    np.testing.assert_allclose(s.face_uvs(f, Side.FRONT), np.zeros((4, 2)))


def test_clear_removes_them():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    s.clear_face_uvs(f, Side.FRONT)
    assert s.face_uvs(f, Side.FRONT) is None


def test_faces_with_uvs_lists_both_sides():
    s = Scene()
    f1 = _quad(s)
    f2 = _quad(s, z=1.0)
    s.set_face_uvs(f1, [(0.0, 0.0)] * 4, Side.FRONT)
    s.set_face_uvs(f2, [(0.0, 0.0)] * 4, Side.BACK)
    assert set(s.faces_with_uvs()) == {(f1, Side.FRONT), (f2, Side.BACK)}


def test_setting_uvs_marks_the_scene_dirty():
    s = Scene()
    f = _quad(s)
    s.mark_clean()
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    assert s.dirty


def test_clearing_absent_uvs_does_not_dirty_the_scene():
    s = Scene()
    f = _quad(s)
    s.mark_clean()
    s.clear_face_uvs(f, Side.FRONT)
    assert not s.dirty


def test_a_wrong_length_array_is_rejected():
    s = Scene()
    f = _quad(s)
    with pytest.raises(ValueError, match="4 corners"):
        s.set_face_uvs(f, [(0.0, 0.0), (1.0, 0.0)], Side.FRONT)


def test_clear_drops_every_stored_array():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    s.clear()
    assert s.faces_with_uvs() == []


def test_the_returned_array_is_not_a_live_view():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    got = s.face_uvs(f, Side.FRONT)
    got[0, 0] = 9.0
    np.testing.assert_allclose(s.face_uvs(f, Side.FRONT)[0], [0.0, 0.0])

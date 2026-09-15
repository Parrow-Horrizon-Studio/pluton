import numpy as np
import pytest

from pluton.io.document_codec import geometry_from_dict, geometry_to_dict
from pluton.io.errors import PlutonFormatError
from pluton.io.pluton_file import SCHEMA_VERSION
from pluton.scene.scene import Scene, Side


def _quad(scene, z=0.0):
    ids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
    ]
    return scene.add_face_from_loop(ids)


def test_schema_version_is_seven():
    assert SCHEMA_VERSION == 7


def test_a_document_with_no_stored_uvs_writes_empty_dicts():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    assert data["face_uvs"] == {}
    assert data["face_uvs_back"] == {}


def test_stored_uvs_round_trip():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], Side.FRONT)
    data = geometry_to_dict(s)
    assert data["face_uvs"] == {"0": [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]}

    loaded = Scene()
    geometry_from_dict(loaded, data)
    new_face = next(iter(loaded.faces_iter())).id
    np.testing.assert_allclose(
        loaded.face_uvs(new_face, Side.FRONT), [[0, 0], [1, 0], [1, 1], [0, 1]]
    )


def test_the_two_sides_round_trip_independently():
    s = Scene()
    f = _quad(s)
    s.set_face_uvs(f, [(0.0, 0.0)] * 4, Side.FRONT)
    s.set_face_uvs(f, [(0.5, 0.5)] * 4, Side.BACK)
    loaded = Scene()
    geometry_from_dict(loaded, geometry_to_dict(s))
    new_face = next(iter(loaded.faces_iter())).id
    np.testing.assert_allclose(loaded.face_uvs(new_face, Side.FRONT), np.zeros((4, 2)))
    np.testing.assert_allclose(loaded.face_uvs(new_face, Side.BACK), np.full((4, 2), 0.5))


def test_a_v0_8_0_document_without_the_keys_still_loads():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    del data["face_uvs"]
    del data["face_uvs_back"]
    loaded = Scene()
    geometry_from_dict(loaded, data)  # must not raise
    assert loaded.faces_with_uvs() == []


def test_a_wrong_length_uv_array_is_corruption_not_a_fallback():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    data["face_uvs"] = {"0": [0.0, 0.0, 1.0, 0.0]}  # 2 corners for a 4-corner face
    with pytest.raises(PlutonFormatError, match="face_uvs"):
        geometry_from_dict(Scene(), data)


def test_an_odd_length_uv_array_is_rejected():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    data["face_uvs"] = {"0": [0.0, 0.0, 1.0]}
    with pytest.raises(PlutonFormatError, match="face_uvs"):
        geometry_from_dict(Scene(), data)


def test_an_out_of_range_face_index_is_rejected():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    data["face_uvs"] = {"9": [0.0, 0.0] * 4}
    with pytest.raises(PlutonFormatError, match="face_uvs"):
        geometry_from_dict(Scene(), data)


def test_a_non_integer_face_index_is_rejected():
    s = Scene()
    _quad(s)
    data = geometry_to_dict(s)
    data["face_uvs"] = {"abc": [0.0, 0.0] * 4}
    with pytest.raises(PlutonFormatError, match="face_uvs"):
        geometry_from_dict(Scene(), data)

import numpy as np
import pytest

from pluton.io.document_codec import geometry_from_dict, geometry_to_dict
from pluton.io.errors import PlutonFormatError
from pluton.scene.scene import Scene


def _square(scene: Scene) -> list[int]:
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)
    return vids


def test_geometry_roundtrip_painted_face():
    src = Scene()
    _square(src)
    fid = next(iter(src.faces_iter())).id
    src.set_face_material(fid, 5)

    data = geometry_to_dict(src)
    assert len(data["vertices"]) == 4
    assert len(data["faces"]) == 1
    assert data["face_materials"] == {"0": 5}

    dst = Scene()
    geometry_from_dict(dst, data)
    assert len(list(dst.vertices_iter())) == 4
    assert len(list(dst.faces_iter())) == 1
    new_fid = next(iter(dst.faces_iter())).id
    assert dst.face_material(new_fid) == 5


def test_geometry_roundtrip_compacts_id_gaps():
    src = Scene()
    vids = _square(src)
    # Add a loose vertex, then delete it -> leaves an id gap in the kernel.
    loose = src.add_vertex(np.array((9, 9, 9), dtype=np.float32))
    src.remove_vertex(loose)

    data = geometry_to_dict(src)
    assert len(data["vertices"]) == 4  # gap compacted away

    dst = Scene()
    geometry_from_dict(dst, data)
    got = sorted(tuple(round(float(c), 3) for c in v.position) for v in dst.vertices_iter())
    want = sorted(tuple(round(float(c), 3) for c in src.vertex(v).position) for v in vids)
    assert got == want


def test_geometry_from_dict_rejects_bad_index():
    dst = Scene()
    bad = {"vertices": [[0, 0, 0]], "edges": [[0, 7]], "faces": [], "face_materials": {}}
    with pytest.raises(PlutonFormatError):
        geometry_from_dict(dst, bad)

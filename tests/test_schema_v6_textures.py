"""M7.5b Task 7: schema 6, additive, with blobs beside document.json."""

from __future__ import annotations

import json
import zipfile

import numpy as np
from pluton.document import DocumentSettings
from pluton.io.document_codec import geometry_from_dict, geometry_to_dict
from pluton.io.pluton_file import SCHEMA_VERSION
from pluton.scene.scene import Scene, Side, TexturePlacement
from pluton.viewport.camera import Camera

_PNG = b"\x89PNG\r\n\x1a\nfake-but-stable-bytes"


def _camera():
    return Camera()


def _doc():
    return DocumentSettings()


def _square(scene, z=0.0):
    v = [
        scene.add_vertex(np.array([0.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, z], dtype=np.float32)),
    ]
    for a, b in zip(v, v[1:] + v[:1], strict=True):
        scene.add_edge(a, b)
    return scene.add_face_from_loop(v)


def test_the_schema_version_is_six():
    assert SCHEMA_VERSION == 6


def test_placement_round_trips_per_side():
    s = Scene()
    f = _square(s)
    s.set_face_placement(f, TexturePlacement(0.25, -0.5, 2.0, 1.0), Side.FRONT)
    s.set_face_placement(f, TexturePlacement(scale=3.0), Side.BACK)

    out = Scene()
    geometry_from_dict(out, geometry_to_dict(s))
    assert out.face_placement(f, Side.FRONT) == TexturePlacement(0.25, -0.5, 2.0, 1.0)
    assert out.face_placement(f, Side.BACK).scale == 3.0


def test_unadjusted_faces_are_not_written():
    # Task 3 clears identity placements, so the dicts hold only adjusted faces.
    # Writing every face would bloat every document that ever touched a texture.
    s = Scene()
    _square(s)
    d = geometry_to_dict(s)
    assert d["face_placements"] == {}
    assert d["face_placements_back"] == {}


def test_placement_is_keyed_by_face_index_not_face_id():
    # Matches the face_materials convention. A single-face fixture cannot tell
    # the two apart, because face 0 has index 0, so build two and delete one.
    s = Scene()
    a = _square(s)
    b = _square(s, z=1.0)
    s.remove_face(a)
    s.set_face_placement(b, TexturePlacement(scale=2.0))
    d = geometry_to_dict(s)
    assert list(d["face_placements"].keys()) == ["0"]
    assert b != 0


def test_a_schema_5_payload_without_placement_keys_still_loads():
    s = Scene()
    _square(s)
    d = geometry_to_dict(s)
    del d["face_placements"]
    del d["face_placements_back"]
    out = Scene()
    geometry_from_dict(out, d)  # must not raise
    assert out.faces_with_placement() == []


def test_texture_records_and_blobs_round_trip_through_a_real_file(tmp_path):
    from pluton.io.pluton_file import load_document, save_document
    from pluton.model.model import Model
    from pluton.viewport.render_style import RenderStyle

    model = Model()
    tex = model.textures.add("brick.png", _PNG, "png", 8, 8, True)
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    model.materials.edit(mat.id, texture_id=tex.id, texture_size=(2.0, 3.0))

    path = tmp_path / "t.pluton"
    save_document(path, model, _camera(), _doc(), RenderStyle())
    loaded = load_document(path)

    back = loaded.model.textures.get(tex.id)
    assert back is not None
    assert back.data == _PNG
    assert back.has_transparency is True
    assert loaded.model.materials.get(mat.id).texture_size == (2.0, 3.0)


def test_the_blob_is_a_sibling_entry_not_base64_in_the_json(tmp_path):
    from pluton.io.pluton_file import save_document
    from pluton.model.model import Model
    from pluton.viewport.render_style import RenderStyle

    model = Model()
    tex = model.textures.add("brick.png", _PNG, "png", 8, 8, False)
    path = tmp_path / "t.pluton"
    save_document(path, model, _camera(), _doc(), RenderStyle())

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert f"textures/{tex.id}.png" in names
        assert zf.read(f"textures/{tex.id}.png") == _PNG
        doc = json.loads(zf.read("document.json"))
    assert "data" not in json.dumps(doc["textures"][0])


def test_a_document_referencing_a_missing_blob_still_opens(tmp_path):
    # Spec 1.8. Rewriting the zip without the texture entry simulates a file
    # that was truncated or hand-edited; the open must succeed untextured.
    from pluton.io.pluton_file import load_document, save_document
    from pluton.model.model import Model
    from pluton.viewport.render_style import RenderStyle

    model = Model()
    tex = model.textures.add("brick.png", _PNG, "png", 8, 8, False)
    src = tmp_path / "a.pluton"
    save_document(src, model, _camera(), _doc(), RenderStyle())

    dst = tmp_path / "b.pluton"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            if not item.filename.startswith("textures/"):
                zout.writestr(item, zin.read(item.filename))

    loaded = load_document(dst)
    assert loaded.model.textures.get(tex.id).data == b""

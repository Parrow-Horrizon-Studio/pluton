import subprocess
import sys

import numpy as np
from pluton.io.obj_codec import parse_obj
from pluton.io.obj_io import export_obj, model_to_objdoc
from pluton.model.model import Model
from pluton.scene.scene import Side
from pluton.viewport.uv_resolve import resolve_face_uvs

FAKE_PNG = b"\x89PNG\r\n\x1a\n-fake-bytes"


def _model_with_stored_uvs():
    model = Model()
    mesh = model.root.mesh
    ids = [
        mesh.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    ]
    fid = mesh.add_face_from_loop(ids)
    mesh.set_face_uvs(fid, [(0.0, 0.0), (0.25, 0.0), (0.5, 0.5), (0.75, 1.0)], Side.FRONT)
    return model, fid


def test_export_writes_a_vt_per_corner():
    model, _ = _model_with_stored_uvs()
    doc = model_to_objdoc(model, resolver=resolve_face_uvs)
    face = doc.objects[0].faces[0]
    assert face.uv_indices is not None
    assert len(face.uv_indices) == len(face.vertex_indices)


def test_exported_uvs_are_the_stored_values():
    model, _ = _model_with_stored_uvs()
    doc = model_to_objdoc(model, resolver=resolve_face_uvs)
    face = doc.objects[0].faces[0]
    got = [doc.uvs[t] for t in face.uv_indices]
    np.testing.assert_allclose(got, [(0.0, 0.0), (0.25, 0.0), (0.5, 0.5), (0.75, 1.0)], atol=1e-5)


def test_an_untextured_model_still_exports_projected_uvs():
    model = Model()
    mesh = model.root.mesh
    ids = [
        mesh.add_vertex(np.array(p, dtype=np.float32)) for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
    ]
    mesh.add_face_from_loop(ids)
    doc = model_to_objdoc(model, resolver=resolve_face_uvs)
    assert doc.objects[0].faces[0].uv_indices is not None


def test_export_without_a_resolver_writes_no_uvs():
    model, _ = _model_with_stored_uvs()
    doc = model_to_objdoc(model)
    assert doc.uvs == ()
    assert doc.objects[0].faces[0].uv_indices is None


def test_the_texture_image_is_written_beside_the_obj(tmp_path):
    model, _ = _model_with_stored_uvs()
    tex = model.textures.add("brick", FAKE_PNG, "png", 4, 8, False)
    mat = model.materials.add_custom("brick", (1.0, 1.0, 1.0))
    model.materials.edit(mat.id, texture_id=tex.id)
    model.root.mesh.set_face_material(
        next(iter(model.root.mesh.faces_iter())).id, mat.id, Side.FRONT
    )

    out = tmp_path / "m.obj"
    export_obj(out, model)
    image = tmp_path / "brick.png"
    assert image.is_file()
    assert image.read_bytes() == FAKE_PNG
    assert "map_Kd brick.png" in (tmp_path / "m.mtl").read_text(encoding="utf-8")


def test_a_round_trip_preserves_the_uvs(tmp_path):
    model, _ = _model_with_stored_uvs()
    out = tmp_path / "m.obj"
    export_obj(out, model)
    back = parse_obj(out.read_text(encoding="utf-8"), None)
    face = back.objects[0].faces[0]
    got = [back.uvs[t] for t in face.uv_indices]
    np.testing.assert_allclose(got, [(0.0, 0.0), (0.25, 0.0), (0.5, 0.5), (0.75, 1.0)], atol=1e-5)


def test_obj_io_imports_without_qt():
    """pluton.io must never reach Qt, even transitively.

    export_obj imports resolve_face_uvs lazily so pluton/io stays Qt-free at
    module scope. This runs the check in a clean subprocess interpreter so it
    is not polluted by anything the test session has already imported.
    """
    code = (
        "import sys\n"
        "import pluton.io.obj_io\n"
        "qt = [m for m in sys.modules if 'PySide6' in m]\n"
        "assert qt == [], qt\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

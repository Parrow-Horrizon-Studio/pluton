import numpy as np
import pytest
from pluton.io import export_obj, read_obj_document
from pluton.io.errors import PlutonFormatError
from pluton.model.model import Model


def _painted_model():
    model = Model()
    vids = [model.root.mesh.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    model.root.mesh.add_face_from_loop(vids)
    fid = next(iter(model.root.mesh.faces_iter())).id
    m = model.materials.add_custom("Brick Red", (0.7, 0.27, 0.22))
    model.root.mesh.set_face_material(fid, m.id)
    return model


def test_export_obj_writes_obj_and_mtl(tmp_path):
    path = tmp_path / "house.obj"
    export_obj(path, _painted_model())
    assert path.exists()
    mtl = tmp_path / "house.mtl"
    assert mtl.exists()
    obj_text = path.read_text()
    assert "mtllib house.mtl" in obj_text
    assert "o Model" in obj_text
    assert "f 1 2 3 4" in obj_text
    assert "newmtl Brick_Red" in mtl.read_text()


def test_export_obj_no_materials_writes_no_mtl(tmp_path):
    model = Model()
    vids = [model.root.mesh.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0))]
    model.root.mesh.add_face_from_loop(vids)
    path = tmp_path / "plain.obj"
    export_obj(path, model)
    assert path.exists()
    assert not (tmp_path / "plain.mtl").exists()
    assert "mtllib" not in path.read_text()


def test_export_obj_atomic_old_file_survives_failure(tmp_path, monkeypatch):
    path = tmp_path / "keep.obj"
    export_obj(path, _painted_model())
    original = path.read_bytes()
    import pluton.io.obj_io as oi
    monkeypatch.setattr(oi, "model_to_objdoc",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    import pytest
    with pytest.raises(RuntimeError):
        export_obj(path, _painted_model())
    assert path.read_bytes() == original
    assert not (tmp_path / "keep.obj.tmp").exists()


def test_read_obj_document_reads_sidecar_mtl(tmp_path):
    (tmp_path / "m.mtl").write_text("newmtl Red\nKd 0.7 0.2 0.2\n")
    (tmp_path / "m.obj").write_text(
        "mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl Red\nf 1 2 3\n")
    doc = read_obj_document(tmp_path / "m.obj")
    assert doc.materials["Red"] == (0.7, 0.2, 0.2)
    assert doc.objects[0].faces[0].material == "Red"


def test_read_obj_document_missing_mtl_is_non_fatal(tmp_path):
    (tmp_path / "m.obj").write_text("mtllib nope.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    doc = read_obj_document(tmp_path / "m.obj")   # no exception
    assert doc.materials == {}
    assert len(doc.objects[0].faces) == 1


def test_read_obj_document_corrupt_raises(tmp_path):
    (tmp_path / "bad.obj").write_text("v 0 0 0\nv 1 0 0\nf 1 2 9\n")
    with pytest.raises(PlutonFormatError):
        read_obj_document(tmp_path / "bad.obj")

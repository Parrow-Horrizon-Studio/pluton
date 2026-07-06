import json
import zipfile

import numpy as np
import pytest
from pluton.document import DocumentSettings
from pluton.io import (
    PlutonFormatError,
    PlutonVersionError,
    load_document,
    save_document,
)
from pluton.model.model import Model
from pluton.viewport.camera import Camera


def _model_with_box():
    model = Model()
    vids = [model.root.mesh.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    model.root.mesh.add_face_from_loop(vids)
    return model


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "house.pluton"
    save_document(path, _model_with_box(), Camera(), DocumentSettings())
    loaded = load_document(path)
    assert len(list(loaded.model.root.mesh.faces_iter())) == 1


def test_load_rejects_newer_schema(tmp_path):
    path = tmp_path / "future.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "pluton", "schema_version": 999}))
        zf.writestr("document.json", "{}")
    with pytest.raises(PlutonVersionError):
        load_document(path)


def test_load_rejects_foreign_format(tmp_path):
    path = tmp_path / "alien.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "sketchup", "schema_version": 1}))
        zf.writestr("document.json", "{}")
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_load_rejects_non_zip(tmp_path):
    path = tmp_path / "garbage.pluton"
    path.write_text("not a zip at all")
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_load_rejects_missing_document_entry(tmp_path):
    path = tmp_path / "incomplete.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "pluton", "schema_version": 1}))
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_save_is_atomic_old_file_survives_failure(tmp_path, monkeypatch):
    path = tmp_path / "keep.pluton"
    save_document(path, _model_with_box(), Camera(), DocumentSettings())
    original = path.read_bytes()

    import pluton.io.pluton_file as pf
    monkeypatch.setattr(pf, "document_to_dict",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        save_document(path, _model_with_box(), Camera(), DocumentSettings())
    assert path.read_bytes() == original  # untouched
    assert not (tmp_path / "keep.pluton.tmp").exists()  # temp cleaned up

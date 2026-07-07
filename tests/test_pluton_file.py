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
from pluton.units import Units, UnitSystem
from pluton.viewport.camera import Camera


def _model_with_box():
    model = Model()
    vids = [model.root.mesh.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    model.root.mesh.add_face_from_loop(vids)
    return model


def _add_box(scene):
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)


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


def test_rich_document_roundtrip_through_real_zip_and_json(tmp_path):
    """End-to-end save/load through the REAL zip + json.dumps/loads path (not just
    the codec-dict level), exercising the format's headline guarantees together:
    shared-component identity, nested groups with non-identity transforms, tag
    visibility, custom materials on painted faces, camera state, and imperial
    units. The narrower codec-level version of this scenario lives in
    test_document_codec.test_document_roundtrip_camera_units_materials_tags."""
    model = Model()

    # Root: geometry + a painted face using a custom material.
    _add_box(model.root.mesh)
    root_fid = next(iter(model.root.mesh.faces_iter())).id
    teal = model.materials.add_custom("Teal", (0.1, 0.6, 0.6))
    model.root.mesh.set_face_material(root_fid, teal.id)

    # Hidden tag, applied to one instance.
    hidden_tag = model.tags.add("Hidden Stuff")
    model.tags.set_visible(hidden_tag.id, False)

    # Shared component definition, placed as two instances under root.
    chair = model.new_definition("Chair", is_group=False)
    _add_box(chair.mesh)
    chair_inst_1 = model.new_instance(chair)
    chair_inst_2 = model.new_instance(chair, transform=np.array([
        [1, 0, 0, 5],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ], dtype=np.float64))
    chair_inst_2.tag_id = hidden_tag.id
    model.root.children.append(chair_inst_1)
    model.root.children.append(chair_inst_2)

    # Nested group: a group definition with its own geometry, placed with a
    # non-identity transform (translation + non-uniform-looking scale-free rotation
    # substitute — keep it a simple affine transform, exactness is what's checked).
    group_def = model.new_definition("Group 1", is_group=True)
    _add_box(group_def.mesh)
    group_transform = np.array([
        [2, 0, 0, 1],
        [0, 1, 0, 2],
        [0, 0, 3, 3],
        [0, 0, 0, 1],
    ], dtype=np.float64)
    group_inst = model.new_instance(group_def, transform=group_transform)
    model.root.children.append(group_inst)

    # Non-default camera.
    cam = Camera()
    cam.position = np.array([10, -20, 30], dtype=np.float32)
    cam.fov_y_deg = 60.0

    # Imperial units.
    doc = DocumentSettings()
    doc.set_units(Units(system=UnitSystem.IMPERIAL, imperial_denominator=8))

    path = tmp_path / "rich.pluton"
    save_document(path, model, cam, doc)
    loaded = load_document(path)

    loaded_root = loaded.model.root
    assert len(loaded_root.children) == 3
    loaded_chair_1, loaded_chair_2, loaded_group_inst = loaded_root.children

    # Shared component: both instances point at the SAME Definition object.
    assert loaded_chair_1.definition is loaded_chair_2.definition
    assert loaded_chair_1.definition.name == "Chair"

    # Per-child transforms and tag_ids survive.
    assert np.allclose(loaded_chair_1.transform, np.eye(4))
    assert loaded_chair_1.tag_id == 0
    assert np.allclose(loaded_chair_2.transform, chair_inst_2.transform)
    assert loaded_chair_2.tag_id == hidden_tag.id

    # Nested group: its own definition + geometry + non-identity transform.
    assert loaded_group_inst.definition.is_group is True
    assert loaded_group_inst.definition.name == "Group 1"
    assert len(list(loaded_group_inst.definition.mesh.faces_iter())) == 1
    assert np.allclose(loaded_group_inst.transform, group_transform)

    # Painted face's material id + the custom material itself survive.
    loaded_root_fid = next(iter(loaded_root.mesh.faces_iter())).id
    assert loaded_root.mesh.face_material(loaded_root_fid) == teal.id
    assert loaded.model.materials.get(teal.id).name == "Teal"

    # Hidden tag's visibility survives.
    assert loaded.model.tags.is_visible(hidden_tag.id) is False

    # Counters restored so post-load edits won't collide with loaded ids.
    assert loaded.model._next_def_id == model._next_def_id
    assert loaded.model._next_inst_id == model._next_inst_id

    # Camera state survives.
    assert tuple(round(float(x), 3) for x in loaded.camera_state.position) == (10.0, -20.0, 30.0)
    assert round(loaded.camera_state.fov_y_deg, 3) == 60.0

    # Imperial units survive.
    assert loaded.units.system is UnitSystem.IMPERIAL
    assert loaded.units.imperial_denominator == 8

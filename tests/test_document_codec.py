import numpy as np
import pytest
from pluton.document import DocumentSettings
from pluton.io.document_codec import (
    CameraState,
    document_from_dict,
    document_to_dict,
    geometry_from_dict,
    geometry_to_dict,
    model_from_dict,
    model_to_dict,
)
from pluton.io.errors import PlutonFormatError
from pluton.model.model import Model
from pluton.scene.scene import Scene
from pluton.units import Units, UnitSystem
from pluton.viewport.camera import Camera


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


def _add_box(scene):
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)


def test_model_roundtrip_shared_component_is_one_definition_and_shared():
    model = Model()
    comp = model.new_definition("Chair", is_group=False)
    _add_box(comp.mesh)
    i1 = model.new_instance(comp)
    i2 = model.new_instance(comp)
    model.root.children.extend([i1, i2])

    data = model_to_dict(model)
    chair_records = [d for d in data["definitions"] if d["name"] == "Chair"]
    assert len(chair_records) == 1  # emitted once despite two instances

    loaded = model_from_dict(data)
    kids = loaded.root.children
    assert len(kids) == 2
    assert kids[0].definition is kids[1].definition  # sharing preserved (identity)


def test_model_roundtrip_restores_counters_and_tag_ids():
    model = Model()
    g = model.new_definition("Grp", is_group=True)
    inst = model.new_instance(g)
    inst.tag_id = 7
    model.root.children.append(inst)

    loaded = model_from_dict(model_to_dict(model))
    assert loaded._next_def_id == model._next_def_id
    assert loaded._next_inst_id == model._next_inst_id
    assert loaded.root.children[0].tag_id == 7


def test_model_from_dict_rejects_dangling_definition_ref():
    data = {
        "next_def_id": 2, "next_inst_id": 1, "root_id": 0,
        "definitions": [{
            "id": 0, "name": "Model", "is_group": False,
            "geometry": {"vertices": [], "edges": [], "faces": [], "face_materials": {}},
            "children": [{"id": 0, "definition_id": 99,
                          "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                          "tag_id": 0}],
        }],
    }
    with pytest.raises(PlutonFormatError):
        model_from_dict(data)


def test_document_roundtrip_camera_units_materials_tags():
    model = Model()
    _add_box(model.root.mesh)
    fid = next(iter(model.root.mesh.faces_iter())).id
    teal = model.materials.add_custom("Teal", (0.1, 0.6, 0.6))
    model.root.mesh.set_face_material(fid, teal.id)
    walls = model.tags.add("Walls")
    model.tags.set_visible(walls.id, False)

    cam = Camera()
    cam.position = np.array([3, -4, 5], dtype=np.float32)
    doc = DocumentSettings()
    doc.set_units(Units(system=UnitSystem.IMPERIAL, imperial_denominator=8))

    data = document_to_dict(model, cam, doc)
    loaded = document_from_dict(data)

    assert loaded.units.system is UnitSystem.IMPERIAL
    assert loaded.units.imperial_denominator == 8
    assert tuple(round(x, 3) for x in loaded.camera_state.position) == (3.0, -4.0, 5.0)
    assert loaded.model.materials.get(teal.id).name == "Teal"
    assert loaded.model.tags.is_visible(walls.id) is False
    new_fid = next(iter(loaded.model.root.mesh.faces_iter())).id
    assert loaded.model.root.mesh.face_material(new_fid) == teal.id


def test_camera_state_apply_to_roundtrip():
    cam = Camera()
    cam.position = np.array([1, 2, 3], dtype=np.float32)
    cam.fov_y_deg = 33.0
    state = CameraState.from_dict(CameraState.from_camera(cam).to_dict())
    target = Camera()
    state.apply_to(target)
    assert tuple(round(float(x), 3) for x in target.position) == (1.0, 2.0, 3.0)
    assert round(target.fov_y_deg, 3) == 33.0


def test_document_from_dict_wraps_structural_errors():
    with pytest.raises(PlutonFormatError):
        document_from_dict({"model": {}})  # missing keys everywhere

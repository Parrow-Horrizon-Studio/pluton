import numpy as np
import pytest
from pluton.io.document_codec import (
    geometry_from_dict,
    geometry_to_dict,
    model_from_dict,
    model_to_dict,
)
from pluton.io.errors import PlutonFormatError
from pluton.model.model import Model
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

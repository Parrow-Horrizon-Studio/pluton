import numpy as np

from pluton.io.obj_codec import parse_obj
from pluton.io.obj_io import build_obj_into_model
from pluton.model.model import Model
from pluton.scene.scene import Side

QUAD = (
    "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
    "vt 0.1 0.2\nvt 0.3 0.4\nvt 0.5 0.6\nvt 0.7 0.8\n"
    "f 1/1 2/2 3/3 4/4\n"
)


def _import(obj_text):
    model = Model()
    doc = parse_obj(obj_text, None)
    build_obj_into_model(doc, model, model.root)
    return model.root.mesh


def test_the_kernel_loop_matches_the_order_the_importer_passed():
    # The positional UV mapping depends on this. Verified, not assumed.
    mesh = _import(QUAD)
    fid = next(iter(mesh.faces_iter())).id
    loop = mesh.face_loop(fid)
    positions = [tuple(round(float(c), 6) for c in mesh.vertex(v).position) for v in loop]
    assert positions == [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]


def test_imported_uvs_land_in_loop_order():
    mesh = _import(QUAD)
    fid = next(iter(mesh.faces_iter())).id
    got = mesh.face_uvs(fid, Side.FRONT)
    assert got is not None
    np.testing.assert_allclose(got, [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]], rtol=1e-6)


def test_both_sides_receive_the_array():
    mesh = _import(QUAD)
    fid = next(iter(mesh.faces_iter())).id
    np.testing.assert_allclose(
        mesh.face_uvs(fid, Side.FRONT), mesh.face_uvs(fid, Side.BACK), rtol=1e-6
    )


def test_a_face_without_vt_gets_no_stored_array():
    mesh = _import("v 0 0 0\nv 1 0 0\nv 1 1 0\nf 1 2 3\n")
    fid = next(iter(mesh.faces_iter())).id
    assert mesh.face_uvs(fid, Side.FRONT) is None


def test_a_uv_seam_gives_two_faces_different_uvs_on_one_welded_vertex():
    # Two triangles sharing the edge (1,0,0)-(1,1,0), with different UVs there.
    obj = (
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 2 0 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0.25 0.75\nvt 0.5 0.5\n"
        "f 1/1 2/2 3/3\n"
        "f 2/4 4/5 3/1\n"
    )
    mesh = _import(obj)
    faces = [f.id for f in mesh.faces_iter()]
    assert len(faces) == 2
    uv_a = mesh.face_uvs(faces[0], Side.FRONT)
    uv_b = mesh.face_uvs(faces[1], Side.FRONT)
    # The vertex at (1,0,0) is welded to one kernel id but carries (1,0) on the
    # first face and (0.25,0.75) on the second. Per-vertex storage could not
    # express this; per-corner storage does.
    np.testing.assert_allclose(uv_a[1], [1.0, 0.0], rtol=1e-6)
    np.testing.assert_allclose(uv_b[0], [0.25, 0.75], rtol=1e-6)


def test_a_mixed_document_stores_uvs_only_where_they_exist():
    obj = (
        "v 0 0 0\nv 1 0 0\nv 1 1 0\n"
        "v 3 0 0\nv 4 0 0\nv 4 1 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\n"
        "f 1/1 2/2 3/3\n"
        "f 4 5 6\n"
    )
    mesh = _import(obj)
    stored = [f for f, s in mesh.faces_with_uvs() if s is Side.FRONT]
    assert len(stored) == 1


def test_uvs_survive_a_grouped_import():
    obj = "o thing\n" + QUAD
    model = Model()
    doc = parse_obj(obj, None)
    build_obj_into_model(doc, model, model.root)
    defn = model.root.children[0].definition
    fid = next(iter(defn.mesh.faces_iter())).id
    got = defn.mesh.face_uvs(fid, Side.FRONT)
    assert got is not None
    np.testing.assert_allclose(got, [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]], rtol=1e-6)

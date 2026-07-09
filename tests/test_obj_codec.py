import pytest
from pluton.io.errors import PlutonFormatError
from pluton.io.obj_codec import (
    ObjDocument,
    ObjFace,
    ObjObject,
    parse_obj,
    sanitize_material_name,
    write_obj,
)


def test_sanitize_material_name():
    assert sanitize_material_name("Brick Red") == "Brick_Red"
    assert sanitize_material_name("  a  b ") == "a_b"
    assert sanitize_material_name("") == "material"


def test_write_obj_quad_with_material():
    doc = ObjDocument(
        vertices=((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
        objects=(ObjObject("Wall", (ObjFace((0, 1, 2, 3), "Brick_Red"),)),),
        materials={"Brick_Red": (0.70, 0.27, 0.22)},
        has_object_tags=True,
    )
    obj_text, mtl_text = write_obj(doc, "house.mtl")
    lines = obj_text.splitlines()
    assert "mtllib house.mtl" in lines
    assert "v 0.000000 0.000000 0.000000" in lines
    assert "o Wall" in lines
    assert "usemtl Brick_Red" in lines
    assert "f 1 2 3 4" in lines  # 1-based, n-gon preserved
    assert "newmtl Brick_Red" in mtl_text
    assert "Kd 0.700000 0.270000 0.220000" in mtl_text


def test_write_obj_no_materials_returns_none_mtl():
    doc = ObjDocument(
        vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        objects=(ObjObject("Tri", (ObjFace((0, 1, 2), None),)),),
        materials={},
        has_object_tags=True,
    )
    obj_text, mtl_text = write_obj(doc)
    assert mtl_text is None
    assert "mtllib" not in obj_text
    assert "usemtl" not in obj_text  # unpainted face emits no usemtl
    assert "f 1 2 3" in obj_text


def test_parse_multi_object_with_materials():
    obj = "\n".join([
        "mtllib x.mtl",
        "v 0 0 0", "v 1 0 0", "v 1 1 0", "v 0 1 0",
        "o A", "usemtl Red", "f 1 2 3 4",
        "o B", "f 1 2 3",           # triangle, no material
    ])
    mtl = "newmtl Red\nKd 0.7 0.2 0.2\n"
    doc = parse_obj(obj, mtl)
    assert doc.has_object_tags is True
    assert len(doc.vertices) == 4
    assert [o.name for o in doc.objects] == ["A", "B"]
    assert doc.objects[0].faces[0].vertex_indices == (0, 1, 2, 3)  # 1-based -> 0-based, n-gon
    assert doc.objects[0].faces[0].material == "Red"
    assert doc.objects[1].faces[0].material is None
    assert doc.materials["Red"] == (0.7, 0.2, 0.2)


def test_parse_flat_file_has_no_object_tags():
    doc = parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", None)
    assert doc.has_object_tags is False
    assert len(doc.objects) == 1
    assert doc.objects[0].faces[0].vertex_indices == (0, 1, 2)


def test_parse_face_triplets_and_negative_indices():
    # a/vt/vn triplets -> take the v index; negative = relative to verts so far
    doc = parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1/1/1 2/2/2 -1//3\n", None)
    assert doc.objects[0].faces[0].vertex_indices == (0, 1, 2)  # -1 -> last (index 2)


def test_parse_bad_face_index_raises():
    with pytest.raises(PlutonFormatError):
        parse_obj("v 0 0 0\nv 1 0 0\nf 1 2 9\n", None)   # 9 out of range
    with pytest.raises(PlutonFormatError):
        parse_obj("v 0 0 0\nf 1 x 2\n", None)            # non-numeric


def test_round_trip_write_then_parse():
    doc = ObjDocument(
        vertices=((0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (1, 1, 1)),
        objects=(
            ObjObject("Quad", (ObjFace((0, 1, 2, 3), "Teal"),)),
            ObjObject("Tri", (ObjFace((0, 1, 4), None),)),
        ),
        materials={"Teal": (0.1, 0.6, 0.6)},
        has_object_tags=True,
    )
    obj_text, mtl_text = write_obj(doc, "x.mtl")
    back = parse_obj(obj_text, mtl_text)
    assert [o.name for o in back.objects] == ["Quad", "Tri"]
    assert back.objects[0].faces[0].vertex_indices == (0, 1, 2, 3)
    assert back.objects[0].faces[0].material == "Teal"
    assert back.objects[1].faces[0].material is None
    assert back.materials["Teal"] == (0.1, 0.6, 0.6)
    assert back.has_object_tags is True

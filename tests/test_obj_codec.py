from pluton.io.obj_codec import (
    ObjDocument,
    ObjFace,
    ObjObject,
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

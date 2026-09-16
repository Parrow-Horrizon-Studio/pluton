from pluton.io.obj_codec import parse_obj


def test_map_kd_is_captured():
    mtl = "newmtl brick\nKd 1.0 1.0 1.0\nmap_Kd brick.png\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {"brick": "brick.png"}


def test_map_kd_keeps_a_subdirectory_path():
    mtl = "newmtl brick\nmap_Kd textures/brick.png\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {"brick": "textures/brick.png"}


def test_map_kd_options_are_skipped():
    mtl = "newmtl brick\nmap_Kd -s 1 1 1 brick.png\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {"brick": "brick.png"}


def test_map_kd_filename_with_spaces_survives():
    mtl = "newmtl brick\nmap_Kd my brick.png\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {"brick": "my brick.png"}


def test_a_material_without_map_kd_gets_no_entry():
    mtl = "newmtl plain\nKd 0.5 0.5 0.5\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {}


def test_colors_still_parse_alongside_textures():
    mtl = "newmtl brick\nKd 0.25 0.5 0.75\nmap_Kd brick.png\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.materials == {"brick": (0.25, 0.5, 0.75)}
    assert doc.material_textures == {"brick": "brick.png"}


def test_a_document_with_no_mtl_has_no_textures():
    doc = parse_obj("v 0 0 0\n", None)
    assert doc.material_textures == {}


def test_a_malformed_map_kd_with_no_filename_is_ignored():
    mtl = "newmtl brick\nmap_Kd\n"
    doc = parse_obj("v 0 0 0\n", mtl)
    assert doc.material_textures == {}

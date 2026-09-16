"""Texture import for OBJ. No QApplication: the decoder is injected (spec D7)."""

from pluton.io.obj_codec import parse_obj
from pluton.io.obj_io import build_obj_into_model, read_obj_texture_bytes
from pluton.model.model import Model

FAKE_PNG = b"\x89PNG\r\n\x1a\n-fake-bytes"


def _stub_decoder(data):
    """Stands in for texture_cache.decode_image without importing Qt."""
    if not data.startswith(b"\x89PNG"):
        return None
    return ("png", 4, 8, False)


def _write_obj_tree(tmp_path, map_kd="brick.png", write_image=True):
    obj = tmp_path / "m.obj"
    obj.write_text(
        "mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nvt 0 0\nvt 1 0\nvt 1 1\n"
        "usemtl brick\nf 1/1 2/2 3/3\n",
        encoding="utf-8",
    )
    (tmp_path / "m.mtl").write_text(
        f"newmtl brick\nKd 1 1 1\nmap_Kd {map_kd}\n", encoding="utf-8"
    )
    if write_image:
        target = tmp_path / map_kd
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FAKE_PNG)
    return obj


def test_texture_bytes_are_read_from_beside_the_obj(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    assert read_obj_texture_bytes(obj, doc) == {"brick": FAKE_PNG}


def test_a_subdirectory_texture_resolves(tmp_path):
    obj = _write_obj_tree(tmp_path, map_kd="tex/brick.png")
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    assert read_obj_texture_bytes(obj, doc) == {"brick": FAKE_PNG}


def test_a_missing_image_file_is_skipped_not_fatal(tmp_path):
    obj = _write_obj_tree(tmp_path, write_image=False)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    assert read_obj_texture_bytes(obj, doc) == {}


def test_a_dotdot_texture_outside_the_document_directory_is_skipped(tmp_path):
    doc_dir = tmp_path / "proj"
    doc_dir.mkdir()
    obj = doc_dir / "m.obj"
    obj.write_text(
        "mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nvt 0 0\nvt 1 0\nvt 1 1\n"
        "usemtl brick\nf 1/1 2/2 3/3\n",
        encoding="utf-8",
    )
    (doc_dir / "m.mtl").write_text(
        "newmtl brick\nKd 1 1 1\nmap_Kd ../secret.png\n", encoding="utf-8"
    )
    # The real file exists, one level above the document directory, so this
    # proves containment rather than merely proving the file was absent.
    (tmp_path / "secret.png").write_bytes(FAKE_PNG)
    doc = parse_obj(obj.read_text(), (doc_dir / "m.mtl").read_text())
    assert read_obj_texture_bytes(obj, doc) == {}


def test_an_absolute_path_texture_outside_the_document_directory_is_skipped(tmp_path):
    doc_dir = tmp_path / "proj"
    doc_dir.mkdir()
    obj = doc_dir / "m.obj"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    abs_target = outside_dir / "secret.png"
    abs_target.write_bytes(FAKE_PNG)
    obj.write_text(
        "mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nvt 0 0\nvt 1 0\nvt 1 1\n"
        "usemtl brick\nf 1/1 2/2 3/3\n",
        encoding="utf-8",
    )
    (doc_dir / "m.mtl").write_text(
        f"newmtl brick\nKd 1 1 1\nmap_Kd {abs_target}\n", encoding="utf-8"
    )
    doc = parse_obj(obj.read_text(), (doc_dir / "m.mtl").read_text())
    assert read_obj_texture_bytes(obj, doc) == {}


def test_an_imported_texture_lands_in_the_library(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    model = Model()
    build_obj_into_model(
        doc, model, model.root, texture_bytes={"brick": FAKE_PNG}, decoder=_stub_decoder
    )
    textures = model.textures.textures()
    assert len(textures) == 1
    assert textures[0].data == FAKE_PNG
    assert (textures[0].width, textures[0].height) == (4, 8)
    assert textures[0].image_format == "png"


def test_the_material_points_at_the_imported_texture(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    model = Model()
    build_obj_into_model(
        doc, model, model.root, texture_bytes={"brick": FAKE_PNG}, decoder=_stub_decoder
    )
    brick = next(m for m in model.materials.materials() if m.name == "brick")
    assert brick.texture_id == model.textures.textures()[0].id


def test_undecodable_bytes_are_skipped_and_the_material_stays_untextured(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    model = Model()
    build_obj_into_model(
        doc, model, model.root, texture_bytes={"brick": b"not-an-image"}, decoder=_stub_decoder
    )
    assert model.textures.textures() == []
    brick = next(m for m in model.materials.materials() if m.name == "brick")
    assert brick.texture_id is None


def test_import_without_a_decoder_imports_geometry_and_no_textures(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    model = Model()
    result = build_obj_into_model(doc, model, model.root)
    assert model.textures.textures() == []
    assert result.summary.faces_imported == 1


def test_reimporting_the_same_document_does_not_duplicate_the_texture(tmp_path):
    obj = _write_obj_tree(tmp_path)
    doc = parse_obj(obj.read_text(), (tmp_path / "m.mtl").read_text())
    model = Model()
    build_obj_into_model(
        doc, model, model.root, texture_bytes={"brick": FAKE_PNG}, decoder=_stub_decoder
    )
    build_obj_into_model(
        doc, model, model.root, texture_bytes={"brick": FAKE_PNG}, decoder=_stub_decoder
    )
    textures = model.textures.textures()
    assert len(textures) == 1
    brick = next(m for m in model.materials.materials() if m.name == "brick")
    assert brick.texture_id == textures[0].id


def test_the_io_package_imports_no_qt():
    """Spec D7: pluton/io stays Qt-free so its tests need no QApplication."""
    import pathlib

    root = pathlib.Path("python/pluton/io")
    offenders = [
        p.name
        for p in root.glob("*.py")
        if "PySide6" in p.read_text(encoding="utf-8")
        or "texture_cache" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []

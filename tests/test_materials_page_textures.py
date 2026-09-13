"""M7.5b Task 9: choosing and clearing a material's texture."""

from __future__ import annotations

import struct
import zlib


def _png(w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4 : (y + 1) * w * 4]) for y in range(h))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


_IMG = _png(2, 2, [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 9, 9, 9, 255])


def test_choosing_a_texture_goes_through_the_command_stack(main_window, tmp_path):
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)

    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    depth = len(main_window._command_stack._undo)

    page._choose_texture(chooser=lambda: str(path))

    assert len(main_window._command_stack._undo) == depth + 1
    tid = model.materials.get(mat.id).texture_id
    assert tid is not None
    assert model.textures.get(tid).data == _IMG


def test_one_undo_reverses_the_whole_import(main_window, tmp_path):
    # Import is two commands, add-the-texture and point-the-material-at-it.
    # Composed, so a single Ctrl+Z puts the document back exactly.
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)

    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    page._choose_texture(chooser=lambda: str(path))
    tid = model.materials.get(mat.id).texture_id

    main_window._command_stack.undo()
    assert model.materials.get(mat.id).texture_id is None
    assert model.textures.get(tid) is None


def test_a_corrupt_image_changes_nothing(main_window, tmp_path):
    # Spec 1.8: fails with a message, no library change, no undo entry.
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)

    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image at all")
    depth = len(main_window._command_stack._undo)
    problems: list[str] = []

    page._choose_texture(chooser=lambda: str(bad), on_error=problems.append)

    assert problems, "the user must be told"
    assert len(main_window._command_stack._undo) == depth
    assert model.textures.textures() == []
    assert model.materials.get(mat.id).texture_id is None


def test_cancelling_the_dialog_changes_nothing(main_window):
    page = main_window._materials_page
    model = main_window._model
    depth = len(main_window._command_stack._undo)
    page._choose_texture(chooser=lambda: None)
    assert len(main_window._command_stack._undo) == depth
    assert model.textures.textures() == []


def test_clearing_a_texture_is_undoable(main_window, tmp_path):
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)
    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    page._choose_texture(chooser=lambda: str(path))
    tid = model.materials.get(mat.id).texture_id

    page._clear_texture()
    assert model.materials.get(mat.id).texture_id is None
    # The texture itself is KEPT, per spec D11: undoing a material edit must be
    # able to restore its image.
    assert model.textures.get(tid) is not None

    main_window._command_stack.undo()
    assert model.materials.get(mat.id).texture_id == tid


def test_editing_the_texture_size_goes_through_the_stack(main_window):
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)
    depth = len(main_window._command_stack._undo)

    page._apply_texture_size(2.0, 3.0)

    assert len(main_window._command_stack._undo) == depth + 1
    assert model.materials.get(mat.id).texture_size == (2.0, 3.0)


def test_a_textured_swatch_differs_from_an_untextured_one(main_window, tmp_path):
    # A swatch that renders a textured material as a flat colour tells the user
    # the wrong thing about what painting will do.
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)
    plain = page._swatch_appearance(model.materials.get(mat.id))

    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    page._choose_texture(chooser=lambda: str(path))

    assert page._swatch_appearance(model.materials.get(mat.id)) != plain


# --- M7.5b final review, item 5: size fields follow the texture -------------


def test_the_texture_size_fields_are_disabled_without_a_texture(main_window, tmp_path):
    # Clear Texture already tracked texture_id; the two size spins did not, so
    # a material that samples nothing still offered an edit that pushes an
    # undoable command and invalidates the renderer's uv_key to change a
    # number no pixel can read. Asserted across a real import and a real
    # clear, not by calling _sync_editor, so a version that only got the
    # enablement right on the first paint is caught.
    page = main_window._materials_page
    model = main_window._model
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    page.set_library(model.materials)
    page.set_active(mat.id)

    assert model.materials.get(mat.id).texture_id is None
    assert not page._texture_width_spin.isEnabled()
    assert not page._texture_height_spin.isEnabled()
    assert not page._clear_texture_btn.isEnabled()

    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    page._choose_texture(chooser=lambda: str(path))

    assert page._texture_width_spin.isEnabled()
    assert page._texture_height_spin.isEnabled()

    page._clear_texture()

    assert not page._texture_width_spin.isEnabled()
    assert not page._texture_height_spin.isEnabled()


def test_selecting_an_untextured_material_disables_the_size_fields_again(main_window, tmp_path):
    # Switching the active material must re-evaluate the enablement, not leave
    # it latched from whichever material was shown before.
    page = main_window._materials_page
    model = main_window._model
    textured = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    plain = model.materials.add_custom("Plaster", (0.9, 0.9, 0.9))
    page.set_library(model.materials)
    page.set_active(textured.id)
    path = tmp_path / "brick.png"
    path.write_bytes(_IMG)
    page._choose_texture(chooser=lambda: str(path))
    assert page._texture_width_spin.isEnabled()

    page.set_active(plain.id)

    assert not page._texture_width_spin.isEnabled()
    assert not page._texture_height_spin.isEnabled()

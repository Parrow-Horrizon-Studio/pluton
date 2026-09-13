"""M7.5b Task 11: an optional preview image in the container."""

from __future__ import annotations

import zipfile

from pluton.document import DocumentSettings
from pluton.io.pluton_file import load_document, save_document
from pluton.model.model import Model
from pluton.viewport.camera import Camera
from pluton.viewport.render_style import RenderStyle

_PNG = b"\x89PNG\r\n\x1a\npretend-thumbnail"


def _camera():
    return Camera()


def _doc():
    return DocumentSettings()


def test_a_save_without_a_thumbnail_writes_no_entry_and_still_succeeds(tmp_path):
    # The headless path. Every existing test saves this way, so a save that
    # required a thumbnail would break the whole suite.
    path = tmp_path / "a.pluton"
    save_document(path, Model(), _camera(), _doc(), RenderStyle())
    with zipfile.ZipFile(path) as zf:
        assert "thumbnail.png" not in zf.namelist()
    assert load_document(path) is not None


def test_a_supplied_thumbnail_is_written_verbatim(tmp_path):
    path = tmp_path / "b.pluton"
    save_document(path, Model(), _camera(), _doc(), RenderStyle(), thumbnail=_PNG)
    with zipfile.ZipFile(path) as zf:
        assert zf.read("thumbnail.png") == _PNG


def test_a_thumbnail_does_not_disturb_the_document(tmp_path):
    # The entry is a sibling; nothing about document.json changes.
    plain, withthumb = tmp_path / "c.pluton", tmp_path / "d.pluton"
    model = Model()
    save_document(plain, model, _camera(), _doc(), RenderStyle())
    save_document(withthumb, model, _camera(), _doc(), RenderStyle(), thumbnail=_PNG)
    with zipfile.ZipFile(plain) as a, zipfile.ZipFile(withthumb) as b:
        assert a.read("document.json") == b.read("document.json")


def test_a_file_with_a_thumbnail_loads_normally(tmp_path):
    # An unknown-to-the-loader sibling entry must be ignored, not rejected.
    path = tmp_path / "e.pluton"
    save_document(path, Model(), _camera(), _doc(), RenderStyle(), thumbnail=_PNG)
    assert load_document(path) is not None

"""M7.5b Task 5: decoding images and caching GL textures."""

from __future__ import annotations

import struct
import zlib

import numpy as np
from pluton.model.texture import TextureLibrary
from pluton.viewport.texture_cache import TextureCache, decode_image, sniff_format


def _png(w: int, h: int, rgba: list[int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4 : (y + 1) * w * 4]) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


_OPAQUE = _png(2, 2, [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 9, 9, 9, 255])
_CUTOUT = _png(2, 2, [255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 255, 9, 9, 9, 0])


def test_decoding_needs_no_qapplication():
    # Verified at plan time. If this ever fails, every headless test touching
    # textures needs a Qt fixture and the testing story changes.
    from PySide6.QtGui import QGuiApplication

    assert QGuiApplication.instance() is None
    assert decode_image(_OPAQUE) is not None
    assert QGuiApplication.instance() is None


def test_decode_reports_size_and_rgba_pixels():
    img = decode_image(_OPAQUE)
    assert (img.width, img.height) == (2, 2)
    assert img.pixels.shape == (2, 2, 4)
    assert img.pixels.dtype == np.uint8


def test_an_rgba_image_with_no_transparent_texel_is_not_translucent():
    # The whole point. QImage.hasAlphaChannel() is True here because the FORMAT
    # has alpha, but every texel is opaque. Trusting that flag would put this
    # image in the sorted translucent pass for nothing.
    assert decode_image(_OPAQUE).has_transparency is False


def test_an_image_with_a_transparent_texel_is_translucent():
    assert decode_image(_CUTOUT).has_transparency is True


def test_corrupt_bytes_decode_to_none_rather_than_raising():
    # Spec 1.8: import fails with a message and no library change.
    assert decode_image(b"not an image at all") is None
    assert decode_image(b"") is None


def test_sniff_format_recognises_png_and_rejects_junk():
    assert sniff_format(_OPAQUE) == "png"
    assert sniff_format(b"not an image at all") is None


def test_sniff_format_recognises_jpeg():
    assert sniff_format(b"\xff\xd8\xff\xe0" + b"\x00" * 16) == "jpeg"


class _RecordingGL:
    """Stands in for the GL module, recording calls instead of making them."""

    def __init__(self):
        self.calls: list[tuple] = []
        self._next = 100

    def glGenTextures(self, _n):
        self._next += 1
        self.calls.append(("gen", self._next))
        return self._next

    def glDeleteTextures(self, ids):
        self.calls.append(("delete", tuple(ids) if hasattr(ids, "__iter__") else (ids,)))

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            self.calls.append((name,))

        return _noop


def _lib_with(data: bytes):
    lib = TextureLibrary()
    img = decode_image(data)
    return lib, lib.add("t.png", data, "png", img.width, img.height, img.has_transparency)


def test_a_texture_uploads_once_and_is_cached():
    lib, tex = _lib_with(_OPAQUE)
    gl = _RecordingGL()
    cache = TextureCache(gl=gl)

    first = cache.texture_for(tex)
    second = cache.texture_for(tex)
    assert first == second
    assert [c for c in gl.calls if c[0] == "gen"] == [("gen", 101)]


def test_invalidate_forces_a_re_upload_and_deletes_the_old_id():
    lib, tex = _lib_with(_OPAQUE)
    gl = _RecordingGL()
    cache = TextureCache(gl=gl)

    first = cache.texture_for(tex)
    cache.invalidate(tex.id)
    second = cache.texture_for(tex)
    assert second != first
    assert ("delete", (first,)) in gl.calls


def test_a_texture_with_no_bytes_yields_no_gl_id():
    # A document referencing a missing container entry loads with empty data
    # (Task 1). That must render untextured, not crash the frame.
    lib = TextureLibrary()
    tex = lib.add("gone.png", b"", "png", 4, 4, False)
    cache = TextureCache(gl=_RecordingGL())
    assert cache.texture_for(tex) is None


def test_release_all_deletes_every_uploaded_texture():
    lib, tex = _lib_with(_OPAQUE)
    other = lib.add("b.png", _CUTOUT, "png", 2, 2, True)
    gl = _RecordingGL()
    cache = TextureCache(gl=gl)
    a = cache.texture_for(tex)
    b = cache.texture_for(other)

    cache.release_all()
    deleted = {i for c in gl.calls if c[0] == "delete" for i in c[1]}
    assert {a, b} <= deleted
    assert cache.texture_for(tex) != a  # re-uploads after release

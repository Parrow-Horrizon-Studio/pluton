"""M7.5b Task 9: wiring TextureCache.invalidate/release_all to real callers.

Task 6 built TextureCache.invalidate() and release_all() but left them with no
caller anywhere (task-6-report.md). Task 9 owns wiring both: evict_stale_textures()
reconciles the cache against the model's TextureLibrary after an undo/redo (an
undone import removes a Texture record), and release_all_textures() is the
document-close path (New / Open), where the incoming Model's TextureLibrary
restarts id numbering from 1 -- the same ints a stale GL upload could still be
cached under.

Mirrors test_renderer_buffer_eviction.py's approach: construct SceneRenderer()
directly (no GL context needed) and inject a recording GL stand-in so
invalidate()/release_all() never touch real GL.
"""

from __future__ import annotations

from pluton.model.texture import TextureLibrary
from pluton.viewport.scene_renderer import SceneRenderer
from pluton.viewport.texture_cache import TextureCache


class _RecordingGL:
    def __init__(self):
        self.calls: list[tuple] = []

    def glDeleteTextures(self, ids):
        self.calls.append(("delete", tuple(ids) if hasattr(ids, "__iter__") else (ids,)))

    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            self.calls.append((name,))

        return _noop


def _renderer_with_fake_gl() -> tuple[SceneRenderer, _RecordingGL]:
    r = SceneRenderer()
    assert r._initialized is False  # no GL context needed to construct
    gl = _RecordingGL()
    r._texture_cache = TextureCache(gl=gl)
    return r, gl


def test_evict_stale_textures_drops_ids_no_longer_in_the_library():
    r, gl = _renderer_with_fake_gl()
    textures = TextureLibrary()
    kept = textures.add("kept.png", b"x", "png", 1, 1, False)
    # Simulate an upload having happened for a texture that has since been
    # removed from the library (e.g. AddTextureCommand.undo()).
    r._texture_cache._ids[999] = 42
    r._texture_cache._ids[kept.id] = 7

    r.evict_stale_textures(textures)

    assert 999 not in r._texture_cache.cached_ids()
    assert kept.id in r._texture_cache.cached_ids()
    assert ("delete", (42,)) in gl.calls


def test_evict_stale_textures_also_drops_a_remembered_decode_failure():
    r, gl = _renderer_with_fake_gl()
    textures = TextureLibrary()
    r._texture_cache._failed.add(999)

    r.evict_stale_textures(textures)

    assert 999 not in r._texture_cache.cached_ids()


def test_release_all_textures_clears_the_whole_cache():
    r, gl = _renderer_with_fake_gl()
    r._texture_cache._ids[1] = 10
    r._texture_cache._ids[2] = 11

    r.release_all_textures()

    assert r._texture_cache.cached_ids() == frozenset()
    deleted = {i for c in gl.calls if c[0] == "delete" for i in c[1]}
    assert {10, 11} <= deleted

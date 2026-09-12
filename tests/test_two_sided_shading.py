"""M7.5a Task 6: per-side material resolution feeding the shader."""

from __future__ import annotations

import re

import numpy as np
import pytest
from pluton.model.material import MaterialLibrary
from pluton.viewport import scene_renderer as sr
from pluton.viewport.face_batches import FaceBatch
from pluton.viewport.render_style import BACK_DEFAULT_COLOR, FaceStyle, RenderStyle
from pluton.viewport.scene_renderer import _PHONG_UNIFORMS, _load_shader_source, resolve_batch_sides

_BACK_UNIFORMS = (
    "u_material_ambient_back",
    "u_material_diffuse_back",
    "u_material_specular_back",
    "u_material_shininess_back",
    "u_alpha_back",
)

# `uniform <type> <name>;` — trailing comments are allowed after the semicolon.
_UNIFORM_DECL = re.compile(r"^\s*uniform\s+\w+\s+(\w+)\s*;", re.MULTILINE)


def _lib():
    lib = MaterialLibrary()
    red = lib.add_custom("Red", (0.8, 0.1, 0.1))
    blue = lib.add_custom("Blue", (0.1, 0.1, 0.8))
    return lib, red.id, blue.id


def _declared_uniforms(shader: str) -> set[str]:
    return set(_UNIFORM_DECL.findall(_load_shader_source(shader)))


def _frag_main_body() -> str:
    return _load_shader_source("phong.frag").split("void main()", 1)[1]


def test_the_two_sides_resolve_to_different_diffuse():
    lib, red, blue = _lib()
    batch = FaceBatch(front_material_id=red, back_material_id=blue, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    assert front.diffuse != back.diffuse
    assert front.diffuse[0] > front.diffuse[2]  # red-dominant
    assert back.diffuse[2] > back.diffuse[0]  # blue-dominant


def test_an_unpainted_back_uses_the_back_default_not_the_front_default():
    lib, red, _ = _lib()
    batch = FaceBatch(front_material_id=red, back_material_id=0, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    # The back must be the distinct blue-grey, not the front's red and not the
    # front default. A resolver that ignored side entirely would fail here.
    assert back.diffuse == pytest.approx(BACK_DEFAULT_COLOR, abs=1e-3)
    assert back.diffuse != pytest.approx(front.diffuse)


def test_both_sides_unpainted_still_differ():
    lib, _, _ = _lib()
    batch = FaceBatch(front_material_id=0, back_material_id=0, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    assert front.diffuse != pytest.approx(back.diffuse)


def test_a_translucent_side_makes_the_whole_batch_blend():
    lib, red, blue = _lib()
    lib.edit(blue, alpha=0.3)
    batch = FaceBatch(front_material_id=red, back_material_id=blue, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    # blend and depth_write are per-BATCH, taken from whichever side is more
    # translucent (correction 4), so the opaque front reports them too.
    assert front.blend is True
    assert back.blend is True
    assert front.depth_write is False
    assert back.depth_write is False


def test_an_all_opaque_batch_writes_depth():
    lib, red, blue = _lib()
    batch = FaceBatch(front_material_id=red, back_material_id=blue, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    assert front.blend is False
    assert front.depth_write is True


def test_metallic_and_roughness_reach_the_resolved_uniforms():
    lib, red, _ = _lib()
    lib.edit(red, metallic=1.0, roughness=0.05)
    batch = FaceBatch(front_material_id=red, back_material_id=0, first=0, count=3)
    front, _ = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.SHADED), dimmed=False
    )
    # a smooth metal: no diffuse, tight highlight
    assert front.diffuse == pytest.approx((0.0, 0.0, 0.0))
    assert front.shininess > 100.0


def test_wireframe_style_skips_both_sides():
    lib, red, blue = _lib()
    batch = FaceBatch(front_material_id=red, back_material_id=blue, first=0, count=3)
    front, back = resolve_batch_sides(
        batch, lib, RenderStyle(face_style=FaceStyle.WIREFRAME), dimmed=False
    )
    assert front.draw_faces is False
    assert back.draw_faces is False


# --- Uniform wiring ---------------------------------------------------------
#
# The shader itself cannot run in this suite, so the three tests below close
# the loop on its plumbing by source inspection instead: every uniform the
# shader declares has a cached location, is actually read in main(), and is
# assigned a value during a face draw. A back uniform that is declared but
# never set (or set but never declared) would otherwise pass every test above
# and simply render wrong.


def test_every_phong_shader_uniform_has_a_cached_location():
    declared = _declared_uniforms("phong.vert") | _declared_uniforms("phong.frag")
    assert declared == set(_PHONG_UNIFORMS)


def test_every_fragment_uniform_is_read_in_main():
    body = _frag_main_body()
    for name in _declared_uniforms("phong.frag"):
        assert name in body, f"{name} is declared but never read; GL will optimize it out"


def test_the_fragment_shader_declares_a_back_uniform_set():
    declared = _declared_uniforms("phong.frag")
    for name in _BACK_UNIFORMS:
        assert name in declared


def test_the_fragment_shader_flips_the_normal_for_back_facing_fragments():
    """Guards the back-face normal flip against silent removal.

    Culling is disabled, so without the flip a back-facing fragment shades
    against a normal pointing away from the viewer. There is no GL context in
    this suite, so a source assertion is the only available guard.
    """
    body = _frag_main_body()
    assert "gl_FrontFacing" in body
    assert re.search(r"N\s*=\s*-\s*N\s*;", body), "back-facing normal is never flipped"


class _GLRecorder:
    """Stand-in for the OpenGL module that records which uniform locations
    were written. Every attribute resolves to a no-op callable, so it also
    satisfies the GL constants the draw path passes straight through."""

    def __init__(self) -> None:
        self.written: set[int] = set()

    def __getattr__(self, name: str):
        def _call(*args, **kwargs):
            if name.startswith("glUniform") and args:
                self.written.add(int(args[0]))
            return 0

        return _call


def test_a_face_draw_sets_every_cached_phong_uniform(monkeypatch):
    """Kills a uniform that is cached but never assigned in the draw path.

    A missing `_set_vec3(locs["u_material_diffuse_back"], ...)` leaves the
    uniform at its GL default (zero) and every other test in this file still
    passes.
    """
    recorder = _GLRecorder()
    monkeypatch.setattr(sr, "GL", recorder)

    renderer = sr.SceneRenderer.__new__(sr.SceneRenderer)
    renderer._phong_program = 1
    renderer._phong_locs = {name: i for i, name in enumerate(_PHONG_UNIFORMS)}
    buf = sr._DefBuffers(face_vao=1, face_count=3)

    lib, red, blue = _lib()
    batch = FaceBatch(front_material_id=red, back_material_id=blue, first=0, count=3)
    front, back = resolve_batch_sides(batch, lib, RenderStyle(), dimmed=False)

    renderer._draw_definition_faces(
        buf,
        np.eye(4),
        np.eye(4),
        np.zeros(3),
        np.eye(4),
        front=front,
        back=back,
        first=0,
        count=3,
    )

    missing = {
        name for name, loc in renderer._phong_locs.items() if loc not in recorder.written
    }
    assert not missing, f"uniforms never set during a face draw: {sorted(missing)}"

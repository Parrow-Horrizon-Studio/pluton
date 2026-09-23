"""The sky/ground pass: shader plumbing by source inspection, plus the skip rule.

The fragment shader's horizon arithmetic runs on the GPU and there is nothing
here to call, so these tests pin the seams instead: the Python uniform tuple
against the GLSL declarations, and the predicate that decides whether the pass
runs at all.
"""

import re

from pluton.viewport.environment import PLAIN_WHITE, SKY_AND_GROUND, STUDIO, environment_pass_needed
from pluton.viewport.scene_renderer import _ENVIRONMENT_UNIFORMS, _load_shader_source

_UNIFORM_DECL = re.compile(r"^\s*uniform\s+\w+\s+(\w+)\s*;", re.MULTILINE)


def _declared(shader: str) -> set[str]:
    return set(_UNIFORM_DECL.findall(_load_shader_source(shader)))


def _frag_main_body() -> str:
    return _load_shader_source("environment.frag").split("void main()", 1)[1]


def test_every_environment_uniform_has_a_cached_location():
    """The tuple the renderer caches locations from must match the GLSL exactly.

    Discriminates: drop "u_ground_opacity" from _ENVIRONMENT_UNIFORMS and this
    fails; the ground would then draw at whatever opacity the uninitialised
    uniform held.
    """
    declared = _declared("environment.vert") | _declared("environment.frag")
    assert declared == set(_ENVIRONMENT_UNIFORMS)


def test_every_fragment_uniform_is_read_in_main():
    """A declared-and-set uniform that main() ignores renders wrong silently."""
    body = _frag_main_body()
    for name in _declared("environment.frag"):
        assert name in body, f"{name} is declared but never read in main()"


def test_the_fragment_shader_splits_on_the_ray_z_component():
    """Z-up: sky is ray.z > 0, ground is ray.z < 0, and the horizon is z == 0.

    Pinned by source because getting this wrong (using .y, the Y-up convention)
    produces a horizon perpendicular to the real one, which no other test here
    can see.
    """
    body = _frag_main_body()
    assert "ray.z" in body
    assert "ray.y" not in body


def test_the_pass_is_skipped_when_both_halves_are_disabled():
    assert environment_pass_needed(SKY_AND_GROUND) is True
    assert environment_pass_needed(PLAIN_WHITE) is False
    assert environment_pass_needed(STUDIO) is False

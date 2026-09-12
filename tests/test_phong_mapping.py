"""M7.5a Task 2: PBR parameters mapped onto the Blinn-Phong uniforms."""

from __future__ import annotations

import pytest
from pluton.viewport.render_style import (
    BACK_DEFAULT_COLOR,
    FaceShading,
    FaceStyle,
    RenderStyle,
    face_uniforms,
    phong_material_for,
    resolve_face_pass,
)

RED = (0.8, 0.1, 0.1)


def test_a_dielectric_keeps_its_full_diffuse():
    m = phong_material_for(RED, metallic=0.0)
    assert m.diffuse == pytest.approx(RED)


def test_a_metal_has_no_diffuse_and_takes_its_specular_from_base_color():
    m = phong_material_for(RED, metallic=1.0)
    assert m.diffuse == pytest.approx((0.0, 0.0, 0.0))
    assert m.specular == pytest.approx(RED)


def test_a_dielectric_specular_is_the_standard_f0_not_the_base_color():
    m = phong_material_for(RED, metallic=0.0)
    assert m.specular == pytest.approx((0.04, 0.04, 0.04))
    # and is emphatically not the base color, which a naive mapping would use
    assert m.specular != pytest.approx(RED)


def test_metallic_interpolates_between_the_two():
    half = phong_material_for(RED, metallic=0.5)
    assert half.diffuse == pytest.approx(tuple(c * 0.5 for c in RED))
    assert half.specular == pytest.approx(tuple(0.04 * 0.5 + c * 0.5 for c in RED))


def test_lower_roughness_gives_a_tighter_highlight():
    smooth = phong_material_for(RED, roughness=0.1)
    rough = phong_material_for(RED, roughness=0.9)
    assert smooth.shininess > rough.shininess


def test_shininess_is_clamped_at_both_ends():
    assert phong_material_for(RED, roughness=0.0001).shininess <= 256.0
    assert phong_material_for(RED, roughness=1.0).shininess >= 1.0


def test_ambient_tracks_base_color_and_fades_with_metallic():
    dielectric = phong_material_for(RED, metallic=0.0)
    metal = phong_material_for(RED, metallic=1.0)
    assert dielectric.ambient[0] > 0.0
    assert metal.ambient == pytest.approx((0.0, 0.0, 0.0))


def test_material_alpha_multiplies_into_the_resolved_alpha():
    m = phong_material_for(RED)
    fu = face_uniforms(
        FaceShading.LIT, bg=(0.1, 0.1, 0.1), material=m, xray=False, material_alpha=0.25
    )
    assert fu.alpha == pytest.approx(0.25)


def test_material_alpha_and_xray_compose():
    m = phong_material_for(RED)
    fu = face_uniforms(
        FaceShading.LIT, bg=(0.1, 0.1, 0.1), material=m, xray=True, material_alpha=0.5
    )
    # XRAY_ALPHA is 0.35; a translucent material under X-Ray is more transparent
    # than either alone, so the two multiply rather than one winning.
    assert fu.alpha == pytest.approx(0.35 * 0.5)


def test_a_translucent_material_blends_and_stops_writing_depth():
    m = phong_material_for(RED)
    r = resolve_face_pass(
        RenderStyle(face_style=FaceStyle.SHADED),
        dimmed=False,
        bg=(0.1, 0.1, 0.1),
        material=m,
        dim_ambient=(0.0, 0.0, 0.0),
        dim_diffuse=(0.0, 0.0, 0.0),
        dim_alpha=1.0,
        material_alpha=0.4,
    )
    assert r.blend is True
    assert r.depth_write is False


def test_an_opaque_material_still_writes_depth():
    m = phong_material_for(RED)
    r = resolve_face_pass(
        RenderStyle(face_style=FaceStyle.SHADED),
        dimmed=False,
        bg=(0.1, 0.1, 0.1),
        material=m,
        dim_ambient=(0.0, 0.0, 0.0),
        dim_diffuse=(0.0, 0.0, 0.0),
        dim_alpha=1.0,
        material_alpha=1.0,
    )
    assert r.blend is False
    assert r.depth_write is True


def test_the_back_default_is_distinct_from_the_front_default():
    from pluton.model.material import _DEFAULT_SWATCH_COLOR

    assert BACK_DEFAULT_COLOR != _DEFAULT_SWATCH_COLOR
    # and distinguishable, not a near-identical shade
    delta = sum(abs(a - b) for a, b in zip(BACK_DEFAULT_COLOR, _DEFAULT_SWATCH_COLOR))
    assert delta > 0.2

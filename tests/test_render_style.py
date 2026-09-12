from __future__ import annotations

from pluton.viewport.render_style import (
    FACE_STYLE_TABLE,
    MONO_COLOR,
    XRAY_ALPHA,
    FaceShading,
    FaceStyle,
    FaceUniforms,
    PhongMaterial,
    RenderStyle,
    face_uniforms,
    resolve_face_pass,
)


def test_render_style_defaults_to_shaded_no_xray():
    rs = RenderStyle()
    assert rs.face_style is FaceStyle.SHADED
    assert rs.xray is False


def test_face_style_table_covers_all_styles():
    assert set(FACE_STYLE_TABLE) == set(FaceStyle)


def test_face_style_table_draw_faces_and_shading():
    assert FACE_STYLE_TABLE[FaceStyle.WIREFRAME].draw_faces is False
    assert FACE_STYLE_TABLE[FaceStyle.WIREFRAME].shading is None
    assert FACE_STYLE_TABLE[FaceStyle.HIDDEN_LINE].shading is FaceShading.FLAT_BG
    assert FACE_STYLE_TABLE[FaceStyle.MONOCHROME].shading is FaceShading.UNIFORM
    assert FACE_STYLE_TABLE[FaceStyle.SHADED].shading is FaceShading.LIT
    for style in (FaceStyle.HIDDEN_LINE, FaceStyle.MONOCHROME, FaceStyle.SHADED):
        assert FACE_STYLE_TABLE[style].draw_faces is True


_BG = (0.15, 0.15, 0.18)
_MAT = PhongMaterial(
    ambient=(0.10, 0.10, 0.11),
    diffuse=(0.65, 0.65, 0.70),
    specular=(0.10, 0.10, 0.10),
    shininess=16.0,
)


def test_face_uniforms_lit_uses_material_opaque():
    fu = face_uniforms(FaceShading.LIT, bg=_BG, material=_MAT, xray=False)
    assert isinstance(fu, FaceUniforms)
    assert fu.diffuse == _MAT.diffuse
    assert fu.ambient == _MAT.ambient
    assert fu.specular == _MAT.specular
    assert fu.shininess == _MAT.shininess
    assert fu.alpha == 1.0


def test_face_uniforms_uniform_uses_mono_diffuse():
    fu = face_uniforms(FaceShading.UNIFORM, bg=_BG, material=_MAT, xray=False)
    assert fu.diffuse == MONO_COLOR
    assert fu.ambient == _MAT.ambient        # keeps material ambient → still "lit"
    assert fu.specular == _MAT.specular
    assert fu.alpha == 1.0


def test_face_uniforms_flat_bg_is_unlit_background_fill():
    fu = face_uniforms(FaceShading.FLAT_BG, bg=_BG, material=_MAT, xray=False)
    assert fu.ambient == _BG                 # output == background (unlit)
    assert fu.diffuse == (0.0, 0.0, 0.0)
    assert fu.specular == (0.0, 0.0, 0.0)
    assert fu.shininess == _MAT.shininess
    assert fu.alpha == 1.0


def test_face_uniforms_xray_lowers_alpha_for_every_shading():
    for shading in (FaceShading.LIT, FaceShading.UNIFORM, FaceShading.FLAT_BG):
        fu = face_uniforms(shading, bg=_BG, material=_MAT, xray=True)
        assert fu.alpha == XRAY_ALPHA


_DIM_AMBIENT = (0.30, 0.30, 0.31)
_DIM_DIFFUSE = (0.40, 0.40, 0.42)
_DIM_ALPHA = 0.35


def _resolve(style, dimmed=False):
    return resolve_face_pass(
        style, dimmed=dimmed, bg=_BG, material=_MAT,
        dim_ambient=_DIM_AMBIENT, dim_diffuse=_DIM_DIFFUSE, dim_alpha=_DIM_ALPHA,
    )


def test_resolve_shaded_default_is_opaque_depth_writing():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=False))
    assert rp.draw_faces is True
    assert rp.diffuse == _MAT.diffuse
    assert rp.alpha == 1.0
    assert rp.blend is False
    assert rp.depth_write is True


def test_resolve_wireframe_skips_face_pass():
    rp = _resolve(RenderStyle(FaceStyle.WIREFRAME))
    assert rp.draw_faces is False


def test_resolve_xray_enables_blend_and_disables_depth_write():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=True))
    assert rp.alpha == XRAY_ALPHA
    assert rp.blend is True
    assert rp.depth_write is False


def test_resolve_dim_only_matches_legacy_035_alpha():
    # dim (non-active context) with X-Ray off must reproduce the M4e dim look:
    # dim colors + 0.35 alpha + blend, depth writes preserved.
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=False), dimmed=True)
    assert rp.ambient == _DIM_AMBIENT
    assert rp.diffuse == _DIM_DIFFUSE
    assert rp.alpha == _DIM_ALPHA
    assert rp.blend is True
    assert rp.depth_write is True


def test_resolve_dim_and_xray_no_longer_multiply_into_near_invisibility():
    # This test used to assert `alpha == XRAY_ALPHA * _DIM_ALPHA` == 0.1225,
    # pinning the product that M7.5b (#107) replaced with a cap. It was not in
    # the set of tests the fix was expected to move, so it is worth being
    # explicit about why it did.
    #
    # The reported defect is about a translucent MATERIAL compounding with the
    # dim pass (0.4 became an effective 0.14). X-Ray is the same situation
    # arrived at from the other direction: XRAY_ALPHA is 0.35, which is
    # already exactly the dim floor, so multiplying dropped dimmed X-Ray
    # geometry to 0.1225 -- fainter than the defect being fixed. Under
    # min(fu.alpha, dim_alpha) an already-transparent face is not made more
    # transparent for also being dimmed, and that rule cannot be applied to
    # translucent materials while exempting X-Ray: it is one line composing
    # one alpha.
    #
    # The dim cue itself does not depend on this. _DIM_AMBIENT / _DIM_DIFFUSE
    # still override both colour terms (asserted above in
    # test_resolve_dim_only_matches_legacy_035_alpha), so dimmed X-Ray
    # geometry still reads as "not the thing you are editing"; it simply stops
    # doing so by becoming nearly invisible.
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=True), dimmed=True)
    assert rp.alpha == XRAY_ALPHA
    assert rp.alpha > XRAY_ALPHA * _DIM_ALPHA  # the old product, named explicitly
    assert rp.ambient == _DIM_AMBIENT  # the dim cue still lands
    assert rp.depth_write is False

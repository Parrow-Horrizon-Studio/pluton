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


def test_resolve_dim_and_xray_compose_alpha():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=True), dimmed=True)
    assert rp.alpha == XRAY_ALPHA * _DIM_ALPHA
    assert rp.depth_write is False

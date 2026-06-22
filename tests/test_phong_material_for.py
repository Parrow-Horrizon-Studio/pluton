from __future__ import annotations

from pluton.viewport.render_style import (
    PhongMaterial,
    _AMBIENT_FACTOR,
    _DEFAULT_SHININESS,
    _DEFAULT_SPECULAR,
    phong_material_for,
)


def test_phong_material_for_maps_color_to_uniforms():
    pm = phong_material_for((0.70, 0.27, 0.22))
    assert isinstance(pm, PhongMaterial)
    assert pm.diffuse == (0.70, 0.27, 0.22)
    assert pm.ambient == (0.70 * _AMBIENT_FACTOR, 0.27 * _AMBIENT_FACTOR, 0.22 * _AMBIENT_FACTOR)
    assert pm.specular == _DEFAULT_SPECULAR
    assert pm.shininess == _DEFAULT_SHININESS


def test_defaults_mirror_scene_renderer_constants():
    # Guard against drift between the painted-face look and the default look.
    from pluton.viewport.scene_renderer import _MATERIAL_SHININESS, _MATERIAL_SPECULAR
    assert _DEFAULT_SPECULAR == _MATERIAL_SPECULAR
    assert _DEFAULT_SHININESS == _MATERIAL_SHININESS

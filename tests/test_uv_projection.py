"""M7.5b Task 2: projecting face corners to UVs, and placing the result."""

from __future__ import annotations

import numpy as np
import pytest
from pluton.viewport.uv_projection import apply_placement, plane_basis, project_corners

_SQ = np.array(
    [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 2.0, 0.0], [0.0, 2.0, 0.0]], dtype=np.float64
)
_UP = np.array([0.0, 0.0, 1.0])
_CENTRE = np.array([1.0, 1.0, 0.0])


def test_the_basis_is_orthonormal_and_perpendicular_to_the_normal():
    for n in ([0, 0, 1], [1, 0, 0], [0, 1, 0], [1, 1, 1], [0.3, -0.7, 0.2]):
        u, v = plane_basis(np.asarray(n, dtype=np.float64))
        nn = np.asarray(n, dtype=np.float64) / np.linalg.norm(n)
        assert np.linalg.norm(u) == pytest.approx(1.0)
        assert np.linalg.norm(v) == pytest.approx(1.0)
        assert float(np.dot(u, v)) == pytest.approx(0.0, abs=1e-9)
        assert float(np.dot(u, nn)) == pytest.approx(0.0, abs=1e-9)
        assert float(np.dot(v, nn)) == pytest.approx(0.0, abs=1e-9)


def test_the_basis_is_deterministic_for_a_given_normal():
    # plane_basis takes no vertex argument, so this only pins purity/
    # determinism: same normal in, same basis out. The actual guarantee that
    # the basis does not depend on vertex order comes from the function's
    # signature (no vertex list to leak through) and is exercised end to end,
    # at the project_corners level, by
    # test_rotating_the_corner_list_does_not_move_the_uvs below.
    u1, v1 = plane_basis(_UP)
    u2, v2 = plane_basis(_UP.copy())
    assert np.allclose(u1, u2)
    assert np.allclose(v1, v2)


def test_rotating_the_corner_list_does_not_move_the_uvs():
    # The invariant test_the_basis_is_deterministic_for_a_given_normal cannot
    # reach: an edge-derived basis would give each physical corner a different
    # UV depending on where the loop starts. Rolling the corner list must not
    # move any physical corner's UV, because the basis comes from the normal
    # alone, never from positions[0] or positions[1].
    rolled = np.roll(_SQ, 1, axis=0)
    original_uvs = project_corners(_SQ, _UP, _CENTRE, (1.0, 1.0))
    rolled_uvs = project_corners(rolled, _UP, _CENTRE, (1.0, 1.0))
    np.testing.assert_allclose(rolled_uvs, np.roll(original_uvs, 1, axis=0), atol=1e-6)


def test_a_unit_texture_on_a_two_unit_square_tiles_twice():
    # texture_size is the image's extent in MODEL UNITS, so a 1x1 texture on a
    # 2x2 face spans 2 tiles across. A projection that normalised the face to
    # 0..1 instead would give a span of 1 and never tile.
    uvs = project_corners(_SQ, _UP, _CENTRE, (1.0, 1.0))
    span_u = float(uvs[:, 0].max() - uvs[:, 0].min())
    span_v = float(uvs[:, 1].max() - uvs[:, 1].min())
    assert span_u == pytest.approx(2.0)
    assert span_v == pytest.approx(2.0)


def test_a_wider_texture_tiles_fewer_times_across():
    # Kills a projection that ignores texture_size, and one that multiplies
    # where it should divide.
    uvs = project_corners(_SQ, _UP, _CENTRE, (4.0, 1.0))
    span_u = float(uvs[:, 0].max() - uvs[:, 0].min())
    span_v = float(uvs[:, 1].max() - uvs[:, 1].min())
    assert span_u == pytest.approx(0.5)
    assert span_v == pytest.approx(2.0)


def test_the_face_centroid_maps_to_the_uv_origin():
    uvs = project_corners(_SQ, _UP, _CENTRE, (1.0, 1.0))
    assert float(uvs[:, 0].mean()) == pytest.approx(0.0, abs=1e-6)
    assert float(uvs[:, 1].mean()) == pytest.approx(0.0, abs=1e-6)


def test_a_vertical_face_projects_without_collapsing():
    # The XY-only trap: a face whose normal is +X has zero extent in X, so any
    # projection that drops the Z axis collapses it to a line and every UV
    # lands on one axis.
    wall = np.array(
        [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 2.0, 2.0], [0.0, 0.0, 2.0]], dtype=np.float64
    )
    uvs = project_corners(wall, np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 1.0]), (1.0, 1.0))
    assert float(uvs[:, 0].max() - uvs[:, 0].min()) == pytest.approx(2.0)
    assert float(uvs[:, 1].max() - uvs[:, 1].min()) == pytest.approx(2.0)


def test_projection_returns_float32_two_columns():
    uvs = project_corners(_SQ, _UP, _CENTRE, (1.0, 1.0))
    assert uvs.shape == (4, 2)
    assert uvs.dtype == np.float32


def test_an_empty_corner_set_projects_to_nothing():
    uvs = project_corners(np.zeros((0, 3)), _UP, _CENTRE, (1.0, 1.0))
    assert uvs.shape == (0, 2)
    assert uvs.dtype == np.float32


def test_the_identity_placement_changes_nothing():
    uvs = project_corners(_SQ, _UP, _CENTRE, (1.0, 1.0))
    assert np.allclose(apply_placement(uvs, 0.0, 0.0, 1.0, 0.0), uvs)


def test_offset_shifts_the_uvs():
    uvs = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    moved = apply_placement(uvs, 0.25, -0.5, 1.0, 0.0)
    assert np.allclose(moved, [[0.25, -0.5], [1.25, -0.5]])


def test_a_larger_scale_makes_the_texture_appear_larger():
    # scale 2 means the image covers twice as much surface, so the UV span
    # HALVES. Kills an implementation that multiplies instead of divides.
    uvs = np.array([[0.0, 0.0], [2.0, 0.0]], dtype=np.float32)
    scaled = apply_placement(uvs, 0.0, 0.0, 2.0, 0.0)
    assert float(scaled[1, 0] - scaled[0, 0]) == pytest.approx(1.0)


def test_rotation_turns_the_uvs_about_the_origin():
    uvs = np.array([[1.0, 0.0]], dtype=np.float32)
    turned = apply_placement(uvs, 0.0, 0.0, 1.0, np.pi / 2.0)
    assert turned[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert turned[0, 1] == pytest.approx(1.0, abs=1e-6)


def test_scale_is_applied_before_rotation_and_offset_last():
    # Pins the documented order. A different order passes every test above,
    # because each of those exercises one parameter at a time, and would put
    # Task 10's fields and Task 12's drag out of step with the renderer.
    uvs = np.array([[2.0, 0.0]], dtype=np.float32)
    out = apply_placement(uvs, 10.0, 0.0, 2.0, np.pi / 2.0)
    # scale: (2,0) -> (1,0);  rotate 90 deg: -> (0,1);  offset: -> (10,1)
    assert out[0, 0] == pytest.approx(10.0, abs=1e-6)
    assert out[0, 1] == pytest.approx(1.0, abs=1e-6)


def test_placement_returns_float32():
    out = apply_placement(np.zeros((3, 2), dtype=np.float32), 0.0, 0.0, 1.0, 0.0)
    assert out.dtype == np.float32


def test_the_module_imports_nothing_from_model_scene_qt_or_gl():
    import subprocess
    import sys

    code = (
        "import pluton.viewport.uv_projection, sys; "
        "bad = [m for m in sys.modules if m.startswith(('PySide6','OpenGL','pluton.model','pluton.scene'))]; "
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"

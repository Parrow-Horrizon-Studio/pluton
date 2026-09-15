"""Stored UVs replace the projection as the bake's base, with placement on top."""

import numpy as np

from pluton.scene.scene import Scene, Side, TexturePlacement
from pluton.viewport.scene_renderer import build_face_uvs, build_face_uvs_both_sides


def _quad(scene, z=0.0):
    ids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
    ]
    return scene.add_face_from_loop(ids)


def test_without_stored_uvs_the_bake_is_unchanged():
    s = Scene()
    _quad(s)
    before = build_face_uvs(s, None, Side.FRONT)
    assert before.shape[0] == 6  # a quad is 2 triangles
    # Golden pin on the projection path itself (not a self-comparison): the
    # unit quad's centroid is (0.5, 0.5), and with nothing stored the bake
    # must equal the centroid-relative projection, captured here as literals.
    expected = np.array(
        [
            [-0.5, 0.5],
            [-0.5, -0.5],
            [0.5, -0.5],
            [0.5, -0.5],
            [0.5, 0.5],
            [-0.5, 0.5],
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(before, expected, atol=1e-6)


def test_stored_uvs_land_on_the_right_corners():
    s = Scene()
    f = _quad(s)
    # A distinct UV per loop corner so a mis-mapped corner is unmissable.
    stored = [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0), (0.3, 0.0)]
    s.set_face_uvs(f, stored, Side.FRONT)

    uvs = build_face_uvs(s, None, Side.FRONT)
    idx = s.face_triangle_loop_indices()
    assert uvs.shape == (6, 2)
    for corner in range(6):
        np.testing.assert_allclose(uvs[corner], stored[int(idx[corner])], atol=1e-6)


def test_the_other_side_still_projects():
    s = Scene()
    f = _quad(s)
    # Capture the pure projection for BACK before anything is stored anywhere.
    projected_back = build_face_uvs(s, None, Side.BACK)

    s.set_face_uvs(f, [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0), (0.3, 0.0)], Side.FRONT)
    front, back = build_face_uvs_both_sides(s, None)

    np.testing.assert_allclose(back, projected_back, atol=1e-6)
    assert not np.allclose(front, back)


def test_placement_composes_on_top_of_stored_uvs():
    s = Scene()
    f = _quad(s)
    stored = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    s.set_face_uvs(f, stored, Side.FRONT)
    plain = build_face_uvs(s, None, Side.FRONT)

    s.set_face_placement(f, TexturePlacement(0.5, 0.25, 1.0, 0.0), Side.FRONT)
    offset = build_face_uvs(s, None, Side.FRONT)

    # Pin the base itself, not just the delta between plain and offset: without
    # this, offset - plain would cancel the base entirely and only exercise
    # apply_placements' linearity, which this task does not touch.
    idx = s.face_triangle_loop_indices()
    for corner in range(6):
        expected_base = np.array(stored[int(idx[corner])])
        np.testing.assert_allclose(plain[corner], expected_base, atol=1e-6)
        # Offset with unit scale and no rotation is a pure translation of the base.
        np.testing.assert_allclose(offset[corner], expected_base + [0.5, 0.25], atol=1e-6)


def test_one_stored_face_among_many_leaves_the_others_projected():
    s = Scene()
    f1 = _quad(s, z=0.0)
    f2 = _quad(s, z=1.0)
    projected_both = build_face_uvs(s, None, Side.FRONT)

    stored = [(0.0, 0.0), (0.1, 0.0), (0.2, 0.0), (0.3, 0.0)]
    s.set_face_uvs(f1, stored, Side.FRONT)
    mixed = build_face_uvs(s, None, Side.FRONT)

    face_per_tri = s.face_triangle_face_ids()
    idx = s.face_triangle_loop_indices()
    for corner in range(mixed.shape[0]):
        owning = int(face_per_tri[corner // 3])
        if owning == f2:
            np.testing.assert_allclose(mixed[corner], projected_both[corner], atol=1e-6)
        elif owning == f1:
            np.testing.assert_allclose(mixed[corner], stored[int(idx[corner])], atol=1e-6)
    assert not np.allclose(mixed, projected_both)

"""Unit tests for the snap & inference engine (3D, screen-space)."""

from __future__ import annotations

import numpy as np


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def _screen_of(cam, world):
    """Pixel coords that project onto `world` in a 1280x800 viewport."""
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), 1280, 800)
    return (sx, sy)


def test_endpoint_snap_in_3d_off_the_ground():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    vid = scene.add_vertex(np.array([1.0, 2.0, 3.0], dtype=np.float32))  # off-ground
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 2.0, 3.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == vid
    np.testing.assert_allclose(res.world_position, scene.vertex(vid).position, atol=1e-4)


def test_midpoint_snap_in_3d():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([0.0, 4.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 2.0, 2.0])  # the midpoint
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.MIDPOINT
    assert res.edge_id == e
    assert abs(res.edge_t - 0.5) < 1e-3
    np.testing.assert_allclose(res.world_position, [0.0, 2.0, 2.0], atol=1e-3)


def test_grid_fallback_on_empty_ground():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    cursor = _screen_of(cam, [2.3, -1.4, 0.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.GRID
    np.testing.assert_allclose(res.world_position, [2.0, -1.0, 0.0], atol=1e-3)


def test_none_when_scene_is_none():
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    cam = _camera_at_default()
    res = eng.snap((640.0, 400.0), (1280, 800), cam, None)  # type: ignore[arg-type]
    assert res.kind == SnapKind.NONE


def test_selection_prefers_precedence_then_depth():
    from pluton.viewport.snap_engine import SnapEngine, SnapKind, _Candidate

    eng = SnapEngine()
    near = np.zeros(3, dtype=np.float32)
    cands = [
        _Candidate(SnapKind.ON_FACE, near, screen_dist=1.0, depth=5.0, label="f"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=3.0, depth=9.0, label="e"),
        _Candidate(SnapKind.MIDPOINT, near, screen_dist=2.0, depth=1.0, label="m"),
    ]
    chosen = eng._select(cands)
    assert chosen.kind == SnapKind.ENDPOINT  # precedence beats smaller screen_dist

    two = [
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=9.0, label="far"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=2.0, label="near"),
    ]
    assert eng._select(two).label == "near"


def test_closest_points_two_lines_perpendicular_crossing():
    from pluton.viewport.snap_engine import _closest_points_two_lines

    p1 = np.array([0, 0, 0], np.float32); d1 = np.array([1, 0, 0], np.float32)
    p2 = np.array([3, 0, 1], np.float32); d2 = np.array([0, 1, 0], np.float32)
    _, _, c1, c2 = _closest_points_two_lines(p1, d1, p2, d2)
    np.testing.assert_allclose(c1, [3, 0, 0], atol=1e-5)
    np.testing.assert_allclose(c2, [3, 0, 1], atol=1e-5)


def test_closest_point_on_segment_to_ray_clamps():
    from pluton.viewport.snap_engine import _closest_point_on_segment_to_ray

    ro = np.array([5, 0, 10], np.float32); rd = np.array([0, 0, -1], np.float32)
    a = np.array([0, 0, 0], np.float32); b = np.array([2, 0, 0], np.float32)
    pt, t = _closest_point_on_segment_to_ray(ro, rd, a, b)
    np.testing.assert_allclose(pt, [2, 0, 0], atol=1e-5)  # clamped to far endpoint
    assert t == 1.0


def test_precedence_rank_orders_endpoint_above_on_face():
    from pluton.viewport.snap_engine import SnapKind, _PRECEDENCE_RANK

    assert _PRECEDENCE_RANK[SnapKind.ENDPOINT] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]
    assert _PRECEDENCE_RANK[SnapKind.MIDPOINT] < _PRECEDENCE_RANK[SnapKind.ON_EDGE]
    assert _PRECEDENCE_RANK[SnapKind.ON_EDGE] < _PRECEDENCE_RANK[SnapKind.ON_FACE]
    assert _PRECEDENCE_RANK[SnapKind.ON_FACE] < _PRECEDENCE_RANK[SnapKind.GRID]
    assert _PRECEDENCE_RANK[SnapKind.INTERSECTION] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]


def test_on_edge_snap_to_interior_point():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 0.0, 2.0])  # quarter point, far from midpoint(2,0,2)
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_EDGE
    assert res.edge_id == e
    assert abs(res.edge_t - 0.25) < 5e-2
    np.testing.assert_allclose(res.world_position, [1.0, 0.0, 2.0], atol=5e-2)


def test_on_face_snap_over_a_face():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([-1.0, -1.0, 1.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, -1.0, 1.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([-1.0, 1.0, 1.0], dtype=np.float32))
    for a, b in [(v0, v1), (v1, v2), (v2, v3), (v3, v0)]:
        scene.add_edge(a, b)
    f = scene.add_face_from_loop([v0, v1, v2, v3])
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 0.0, 1.0])  # face center
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_FACE
    assert res.face_id == f
    np.testing.assert_allclose(res.world_position[2], 1.0, atol=1e-3)


def test_endpoint_beats_midpoint_full_pipeline():
    """Full-pipeline precedence (not just _select): a vertex under the cursor
    wins over the edge's midpoint/on-edge candidates."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([0.0, 0.3, 2.0], dtype=np.float32))  # short edge
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 0.0, 2.0])  # exactly on v0
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == v0

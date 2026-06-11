"""Unit tests for the snap & inference engine."""

from __future__ import annotations

import numpy as np
import pytest


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def test_grid_snap_to_nearest_integer_meter():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    cursor_world = np.array([2.3, -1.4, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (0.0, 0.0), cam, scene)
    assert result.kind == SnapKind.GRID
    np.testing.assert_allclose(result.world_position, [2.0, -1.0, 0.0], atol=1e-5)


def test_endpoint_snap_when_cursor_near_existing_vertex():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    vid = scene.add_vertex(np.array([3.0, 4.0, 0.0], dtype=np.float32))
    cam = _camera_at_default()
    # Cursor a tenth of a metre off the vertex — well within endpoint tolerance.
    cursor_world = np.array([3.05, 4.02, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.ENDPOINT
    assert result.vertex_id == vid
    np.testing.assert_array_equal(result.world_position, scene.vertex(vid).position)


def test_midpoint_snap_when_cursor_near_edge_midpoint():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    # Midpoint of (0,0)-(4,0) is (2,0). Cursor very close.
    cursor_world = np.array([2.05, 0.05, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.MIDPOINT
    np.testing.assert_allclose(result.world_position, [2.0, 0.0, 0.0], atol=1e-5)
    assert result.vertex_id is None


def test_axis_lock_when_drawing_near_x_axis_direction():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    # Anchor at origin; cursor near the +X axis (slight Y offset)
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cursor_world = np.array([5.0, 0.05, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.AXIS_LOCK
    assert result.axis == 0  # X axis
    # Snapped point projected onto X axis is (5, 0, 0)
    np.testing.assert_allclose(result.world_position, [5.0, 0.0, 0.0], atol=1e-5)


def test_returns_none_when_cursor_world_is_none():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    result = eng.snap(None, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.NONE
    assert result.axis is None
    assert result.vertex_id is None
    assert result.label == "—"


def test_endpoint_beats_midpoint():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    # An edge where the midpoint and one endpoint are both within tolerance
    v0 = scene.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([2.4, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    # Midpoint is (2.2, 0). Cursor close to v0 — within tolerance of both.
    cursor_world = np.array([2.05, 0.0, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.ENDPOINT
    assert result.vertex_id == v0


def test_midpoint_beats_axis_lock():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    # Cursor near midpoint (2,0) AND axis-locked-to-X-from-origin.
    cursor_world = np.array([2.05, 0.02, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.MIDPOINT


def test_axis_lock_beats_grid():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    # (3.0, 0.02) is on the +X axis-lock direction; grid snap would be (3,0).
    # Both produce the same point in this case — but axis-lock label / kind wins.
    cursor_world = np.array([3.0, 0.02, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.AXIS_LOCK


def test_returns_none_when_scene_is_none():
    """Snap with scene=None must not crash — returns NONE like the no-cursor case."""
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    cam = _camera_at_default()
    cursor_world = np.array([1.0, 1.0, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, None)  # type: ignore[arg-type]
    assert result.kind == SnapKind.NONE


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

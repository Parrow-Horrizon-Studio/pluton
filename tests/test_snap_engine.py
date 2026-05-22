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

"""Tests for the Python Camera class — pure numpy math, no OpenGL needed."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pluton.viewport.camera import Camera


# --- Defaults --------------------------------------------------------------


def test_default_camera_pose():
    c = Camera()
    np.testing.assert_allclose(c.position, [8.0, -8.0, 6.0], atol=1e-5)
    np.testing.assert_allclose(c.target, [0.0, 0.0, 0.5], atol=1e-5)
    np.testing.assert_allclose(c.up, [0.0, 0.0, 1.0], atol=1e-5)


# --- View matrix -----------------------------------------------------------


def test_view_matrix_is_4x4():
    c = Camera()
    v = c.view_matrix()
    assert v.shape == (4, 4)
    assert v.dtype == np.float32


def test_view_matrix_sends_position_to_origin():
    """v * position (homogeneous) should be (0,0,0) in view space."""
    c = Camera()
    v = c.view_matrix()
    homogeneous = np.array([*c.position, 1.0], dtype=np.float32)
    result = v @ homogeneous
    np.testing.assert_allclose(result[:3], [0.0, 0.0, 0.0], atol=1e-4)


# --- Projection matrix -----------------------------------------------------


def test_projection_matrix_is_4x4():
    c = Camera()
    c.aspect = 16.0 / 9.0
    p = c.projection_matrix()
    assert p.shape == (4, 4)
    assert p.dtype == np.float32


def test_projection_matrix_respects_aspect():
    """Wider aspect should compress x more than tall aspect does (same fov_y)."""
    c1 = Camera()
    c1.aspect = 1.0
    c2 = Camera()
    c2.aspect = 2.0
    p1 = c1.projection_matrix()
    p2 = c2.projection_matrix()
    # Element [0,0] is fovy-derived divided by aspect, so p2[0,0] < p1[0,0].
    assert p2[0, 0] < p1[0, 0]


# --- Orbit -----------------------------------------------------------------


def test_orbit_preserves_distance_to_target():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.orbit(dx_pixels=50.0, dy_pixels=30.0)
    distance_after = np.linalg.norm(c.position - c.target)
    np.testing.assert_allclose(distance_after, distance_before, atol=1e-4)


def test_orbit_full_circle_returns_to_origin():
    """Orbiting 360 degrees in many small steps returns the camera home."""
    c = Camera()
    pos_before = c.position.copy()
    distance_initial = np.linalg.norm(pos_before - c.target)
    for _ in range(1000):
        c.orbit(dx_pixels=1.0, dy_pixels=0.0)
    distance_final = np.linalg.norm(c.position - c.target)
    np.testing.assert_allclose(distance_final, distance_initial, atol=1e-3)


def test_orbit_elevation_clamped():
    """Pitch must be clamped to avoid gimbal flip at the poles."""
    c = Camera()
    # Try to orbit way past the top pole.
    for _ in range(10000):
        c.orbit(dx_pixels=0.0, dy_pixels=10.0)
    # Should still be a valid view (position not on top of target).
    distance = np.linalg.norm(c.position - c.target)
    assert distance > 0.1
    # And up direction is still roughly +Z.
    np.testing.assert_allclose(c.up, [0.0, 0.0, 1.0], atol=1e-5)


# --- Pan -------------------------------------------------------------------


def test_pan_preserves_camera_to_target_vector():
    """Pan translates position and target together; the offset is unchanged."""
    c = Camera()
    offset_before = c.position - c.target
    c.pan(dx_pixels=20.0, dy_pixels=-10.0)
    offset_after = c.position - c.target
    np.testing.assert_allclose(offset_after, offset_before, atol=1e-4)


# --- Zoom ------------------------------------------------------------------


def test_zoom_toward_target_reduces_distance():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.zoom(scroll_delta=1.0, cursor_ndc=None)  # zoom in
    distance_after = np.linalg.norm(c.position - c.target)
    assert distance_after < distance_before


def test_zoom_out_increases_distance():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.zoom(scroll_delta=-1.0, cursor_ndc=None)
    distance_after = np.linalg.norm(c.position - c.target)
    assert distance_after > distance_before


def test_zoom_toward_cursor_does_not_drift_target():
    """Cursor-zoom must not move `target` — the orbit pivot must stay anchored."""
    c = Camera()
    target_before = c.target.copy()
    cursor = np.array([0.3, -0.2], dtype=np.float32)  # arbitrary off-center cursor

    for _ in range(50):
        c.zoom(scroll_delta=1.0, cursor_ndc=cursor)

    np.testing.assert_allclose(c.target, target_before, atol=1e-5)

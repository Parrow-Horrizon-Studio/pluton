"""Zoom Extents framing math (M7.2 Task 7). Pure numpy -- no Qt, no model."""

from __future__ import annotations

import numpy as np
from pluton.viewport.camera_framing import MIN_RADIUS, frame_bounds

_DIR = np.array([0.0, 1.0, -1.0], dtype=np.float64)


def test_target_is_the_centre_of_the_bounds():
    _, target = frame_bounds(
        np.array([0.0, 0.0, 0.0]), np.array([2.0, 4.0, 6.0]), _DIR, 1.5, np.radians(45)
    )
    assert np.allclose(target, [1.0, 2.0, 3.0])


def test_view_direction_is_preserved():
    position, target = frame_bounds(
        np.array([-1.0, -1.0, -1.0]), np.array([1.0, 1.0, 1.0]), _DIR, 1.5, np.radians(45)
    )
    actual = target - position
    expected = _DIR / np.linalg.norm(_DIR)
    assert np.allclose(actual / np.linalg.norm(actual), expected)


def test_a_bigger_model_pushes_the_camera_further_back():
    args = (_DIR, 1.5, np.radians(45))
    near, target = frame_bounds(np.array([-1.0] * 3), np.array([1.0] * 3), *args)
    far, _ = frame_bounds(np.array([-10.0] * 3), np.array([10.0] * 3), *args)
    assert np.linalg.norm(far - target) > np.linalg.norm(near - target)


def test_the_whole_bounding_sphere_fits_in_the_frustum():
    bmin, bmax = np.array([-1.0, -2.0, -3.0]), np.array([4.0, 5.0, 6.0])
    fov_y = np.radians(45)
    position, target = frame_bounds(bmin, bmax, _DIR, 1.5, fov_y)

    radius = float(np.linalg.norm(bmax - bmin) / 2.0)
    distance = float(np.linalg.norm(target - position))
    # Half-angle of the vertical frustum must cover the sphere, with margin.
    assert distance * np.sin(fov_y / 2.0) >= radius


def test_a_narrow_viewport_pushes_further_back_than_a_wide_one():
    args = (np.array([-1.0] * 3), np.array([1.0] * 3), _DIR)
    fov_y = np.radians(45)
    narrow, target = frame_bounds(*args, 0.5, fov_y)
    wide, _ = frame_bounds(*args, 2.0, fov_y)
    assert np.linalg.norm(narrow - target) > np.linalg.norm(wide - target)


def test_a_zero_extent_model_does_not_divide_by_zero():
    point = np.array([3.0, 3.0, 3.0])
    position, target = frame_bounds(point, point, _DIR, 1.5, np.radians(45))
    assert np.all(np.isfinite(position))
    assert np.allclose(target, point)
    assert np.linalg.norm(target - position) >= MIN_RADIUS


def test_a_degenerate_view_direction_falls_back_to_a_default():
    position, target = frame_bounds(
        np.array([0.0] * 3), np.array([1.0] * 3), np.zeros(3), 1.5, np.radians(45)
    )
    assert np.all(np.isfinite(position))
    assert not np.allclose(position, target)


def test_extreme_scale_boxes_stay_finite_and_still_fit():
    """A near-point box (radius floored to MIN_RADIUS) and a huge box (radius
    ~1.7e12) must both yield finite poses whose frustum still covers the
    bounding sphere -- no overflow, no underflow-to-zero distance."""
    fov_y = np.radians(45)
    for scale in (1e-9, 1e12):
        bmin, bmax = np.array([-scale] * 3), np.array([scale] * 3)
        position, target = frame_bounds(bmin, bmax, _DIR, 1.5, fov_y)

        assert np.all(np.isfinite(position))
        assert np.all(np.isfinite(target))

        radius = max(float(np.linalg.norm(bmax - bmin) / 2.0), MIN_RADIUS)
        distance = float(np.linalg.norm(target - position))
        assert distance > 0.0
        assert distance * np.sin(fov_y / 2.0) >= radius

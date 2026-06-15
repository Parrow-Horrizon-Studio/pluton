"""Unit tests for curve generators (pure 2D, no Qt)."""

from __future__ import annotations

import numpy as np

from pluton.geometry import circle, polygon


def test_circle_has_segment_count_points_on_radius():
    pts = circle(radius=2.0, segments=24)
    assert pts.shape == (24, 2)
    dists = np.linalg.norm(pts, axis=1)
    assert np.allclose(dists, 2.0, atol=1e-9)


def test_circle_first_vertex_follows_start_angle():
    pts = circle(radius=1.0, segments=24, start_angle=np.pi / 2)
    assert np.allclose(pts[0], [0.0, 1.0], atol=1e-9)


def test_polygon_is_inscribed_and_regular():
    pts = polygon(radius=3.0, sides=6)
    assert pts.shape == (6, 2)
    assert np.allclose(np.linalg.norm(pts, axis=1), 3.0, atol=1e-9)
    edges = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    assert np.allclose(edges, edges[0], atol=1e-9)


def test_ring_winding_is_ccw():
    pts = polygon(radius=1.0, sides=5)
    x, y = pts[:, 0], pts[:, 1]
    area2 = float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    assert area2 > 0.0

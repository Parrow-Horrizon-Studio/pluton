"""Offset polygon maths and its collapse clamp (M7.4 Task 4)."""

from __future__ import annotations

import numpy as np
import pytest
from pluton.tools.sweep_support import offset_polygon

Z = np.array([0.0, 0.0, 1.0], dtype=np.float64)


def _rect(w, h):
    return np.array(
        [[0.0, 0.0, 0.0], [w, 0.0, 0.0], [w, h, 0.0], [0.0, h, 0.0]], dtype=np.float64
    )


def test_outward_offset_keeps_edges_parallel():
    pts, clamped = offset_polygon(_rect(4.0, 2.0), Z, -0.5)
    # Outward by 0.5 on every side: 5 x 3 centred on the original.
    assert clamped == pytest.approx(-0.5)
    assert pts[:, 0].min() == pytest.approx(-0.5)
    assert pts[:, 0].max() == pytest.approx(4.5)
    assert pts[:, 1].min() == pytest.approx(-0.5)
    assert pts[:, 1].max() == pytest.approx(2.5)


def test_inward_offset_shrinks_by_the_distance_on_every_side():
    pts, clamped = offset_polygon(_rect(4.0, 2.0), Z, 0.25)
    assert clamped == pytest.approx(0.25)
    assert pts[:, 0].min() == pytest.approx(0.25)
    assert pts[:, 0].max() == pytest.approx(3.75)


def test_the_clamp_is_half_the_short_side_on_a_rectangle():
    # A 4x2 rectangle collapses to a line at 1.0, so the clamp is exactly 1.0
    # and asking for more returns the clamped value, not the requested one.
    _pts, clamped = offset_polygon(_rect(4.0, 2.0), Z, 5.0)
    assert clamped == pytest.approx(1.0)


def test_clamping_is_reported_so_the_caller_need_not_recompute_it():
    _pts, clamped = offset_polygon(_rect(4.0, 2.0), Z, 5.0)
    assert clamped < 5.0


def test_a_concave_loop_still_yields_a_simple_polygon():
    # An L shape. Its analytic per-edge limit is optimistic: the reflex
    # corner self-intersects before any single edge collapses, so the
    # binary-search stage has to catch it.
    l_shape = np.array(
        [
            [0.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
            [4.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
            [1.0, 4.0, 0.0],
            [0.0, 4.0, 0.0],
        ],
        dtype=np.float64,
    )
    pts, clamped = offset_polygon(l_shape, Z, 3.0)
    assert clamped <= 3.0
    assert _is_simple(pts)


def _is_simple(pts) -> bool:
    """No two non-adjacent edges of the closed polygon intersect."""
    n = len(pts)
    for i in range(n):
        a1, a2 = pts[i][:2], pts[(i + 1) % n][:2]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            b1, b2 = pts[j][:2], pts[(j + 1) % n][:2]
            if _segments_cross(a1, a2, b1, b2):
                return False
    return True


def _segments_cross(p1, p2, p3, p4) -> bool:
    def side(a, b, c):
        return np.sign(np.cross(b - a, c - a))

    d1, d2 = side(p3, p4, p1), side(p3, p4, p2)
    d3, d4 = side(p1, p2, p3), side(p1, p2, p4)
    return bool(d1 != d2 and d3 != d4)

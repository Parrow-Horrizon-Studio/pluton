"""M7.5a Task 5: back-to-front ordering primitives."""

from __future__ import annotations

import numpy as np
import pytest
from pluton.viewport.translucency import (
    order_back_to_front,
    transform_points,
    triangle_centroids,
    triangle_order_to_vertex_order,
)


def test_triangle_centroids_averages_each_triple():
    positions = np.array(
        [
            [0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 3.0, 0.0],   # centroid (1, 1, 0)
            [0.0, 0.0, 6.0], [6.0, 0.0, 6.0], [0.0, 6.0, 6.0],   # centroid (2, 2, 6)
        ],
        dtype=np.float64,
    )
    got = triangle_centroids(positions)
    assert got.shape == (2, 3)
    assert got[0] == pytest.approx([1.0, 1.0, 0.0])
    assert got[1] == pytest.approx([2.0, 2.0, 6.0])


def test_transform_points_is_column_vector():
    # 90 degrees about +Z, then translate by (10, 0, 0).
    m = np.array(
        [
            [0.0, -1.0, 0.0, 10.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    got = transform_points(np.array([[1.0, 0.0, 0.0]]), m)
    # column-vector: (1,0,0) rotates to (0,1,0), then translates to (10,1,0).
    # A row-vector reading would give (0,-1,0)+(10,0,0) = (10,-1,0), so the
    # sign of y is the discriminating bit.
    assert got[0] == pytest.approx([10.0, 1.0, 0.0])


def test_order_back_to_front_puts_the_farthest_first():
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    order = order_back_to_front(pts, np.array([0.0, 0.0, 0.0]))
    # distances 0, 10, 5 -> farthest first is index 1, then 2, then 0
    assert order.tolist() == [1, 2, 0]


def test_order_back_to_front_follows_the_camera():
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    from_origin = order_back_to_front(pts, np.array([0.0, 0.0, 0.0]))
    from_far_side = order_back_to_front(pts, np.array([20.0, 0.0, 0.0]))
    # Moving the camera to the other side must reverse the order. A sort that
    # ignored the camera, or used a fixed axis, would return the same list.
    assert from_origin.tolist() == list(reversed(from_far_side.tolist()))


def test_order_back_to_front_is_a_permutation():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(17, 3))
    order = order_back_to_front(pts, np.array([1.0, 2.0, 3.0]))
    assert sorted(order.tolist()) == list(range(17))


def test_order_back_to_front_handles_an_empty_input():
    order = order_back_to_front(np.zeros((0, 3)), np.array([0.0, 0.0, 0.0]))
    assert order.shape == (0,)


def test_triangle_order_expands_to_vertex_order():
    # swap two triangles -> their three vertices each move together, in order
    got = triangle_order_to_vertex_order(np.array([1, 0], dtype=np.int64))
    assert got.tolist() == [3, 4, 5, 0, 1, 2]


def test_triangle_order_expansion_is_a_permutation():
    got = triangle_order_to_vertex_order(np.array([2, 0, 1], dtype=np.int64))
    assert sorted(got.tolist()) == list(range(9))

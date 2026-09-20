"""Screen-space layout for infinite guide lines and guide points.

A guide has no endpoints, so its plan is the visible portion: clipped against
the camera near plane in 3D, then against the viewport rectangle in 2D.
"""

from __future__ import annotations

import numpy as np
from pluton.units import Units

W, H = 1280, 800


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = W / H
    return cam


def _plan(annotation, cam):
    from pluton.annotations.draw_plan import plan_annotation

    return plan_annotation(annotation, None, cam, W, H, Units())


def _inside(x, y, pad=2.0):
    return -pad <= x <= W + pad and -pad <= y <= H + pad


def test_a_guide_through_the_view_lays_out_one_segment_inside_the_viewport():
    from pluton.model.annotation import Guide

    plan = _plan(Guide(1, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), _camera_at_default())
    assert plan is not None
    assert len(plan.segments_px) == 1
    x1, y1, x2, y2 = plan.segments_px[0]
    assert _inside(x1, y1) and _inside(x2, y2)
    assert np.hypot(x2 - x1, y2 - y1) > 10.0, "a visible guide must not collapse to a point"


def test_a_guide_entirely_behind_the_camera_lays_out_nothing():
    from pluton.model.annotation import Guide

    cam = _camera_at_default()
    origin, direction = cam.ray_from_screen(W / 2, H / 2, W, H)
    behind = np.asarray(origin, dtype=np.float64) - np.asarray(direction, dtype=np.float64) * 50.0
    # A guide through a point well behind the eye, running perpendicular to the view.
    perp = np.cross(np.asarray(direction, dtype=np.float64), np.array([0.0, 0.0, 1.0]))

    plan = _plan(Guide(1, tuple(behind), tuple(perp)), cam)
    assert plan is None or plan.segments_px == []


def test_a_guide_nearly_edge_on_to_the_view_does_not_produce_runaway_coordinates():
    """The failure mode of projecting two far-apart samples instead of clipping."""
    from pluton.model.annotation import Guide

    cam = _camera_at_default()
    _origin, direction = cam.ray_from_screen(W / 2, H / 2, W, H)
    d = np.asarray(direction, dtype=np.float64)
    d = d / float(np.linalg.norm(d))
    # Tilt a hair off the view direction so the guide runs almost straight away.
    almost = d + np.array([0.0, 0.0, 1e-3])

    plan = _plan(Guide(1, (0.0, 0.0, 0.0), tuple(almost)), cam)
    if plan is None or not plan.segments_px:
        return  # fully clipped is a valid answer
    for x1, y1, x2, y2 in plan.segments_px:
        for v in (x1, y1, x2, y2):
            assert abs(v) < 1e5, f"runaway screen coordinate {v}"


def test_a_guide_point_lays_out_a_small_cross():
    from pluton.model.annotation import GuidePoint

    plan = _plan(GuidePoint(1, (0.0, 0.0, 0.0)), _camera_at_default())
    assert plan is not None
    assert len(plan.segments_px) == 2, "a guide point draws as a two-stroke cross"


def test_a_guide_point_far_outside_the_viewport_lays_out_nothing():
    """Regression: projecting a point does not by itself exclude points that
    are in front of the camera but well off to the side. Unlike a guide's
    infinite line (clipped to the viewport by _clip_segment_to_viewport), an
    unguarded guide point would otherwise emit a cross at wildly
    out-of-range pixel coordinates instead of nothing."""
    from pluton.model.annotation import GuidePoint

    cam = _camera_at_default()
    origin, direction = cam.ray_from_screen(50 * W, H / 2, W, H)
    far_off_screen = (
        np.asarray(origin, dtype=np.float64) + np.asarray(direction, dtype=np.float64) * 10.0
    )

    plan = _plan(GuidePoint(1, tuple(far_off_screen)), cam)
    assert plan is None or plan.segments_px == []

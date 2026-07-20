from __future__ import annotations

import numpy as np
from pluton.annotations.draw_plan import plan_annotation
from pluton.model.annotation import Dimension
from pluton.units import Units


class _FlatCamera:
    """Orthographic-ish stand-in: x,y map straight to pixels, z is depth."""

    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)


def _plan(dim, camera=None):
    return plan_annotation(dim, np.eye(4), camera or _FlatCamera(), 640, 480, Units())


def test_dimension_plan_has_line_ticks_extensions_and_text():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    assert plan is not None
    # 1 dimension line + 2 extension lines + 2 ticks = 5 segments
    assert len(plan.segments_px) == 5
    assert len(plan.texts) == 1
    assert len(plan.hit_boxes) >= 1


def test_dimension_text_is_derived_from_world_distance():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    # 4 m at default (metric) units
    assert "4" in plan.texts[0].text


def test_dimension_text_follows_the_world_transform_scale():
    # a 2x uniform scale makes the same local 4 m measure 8 m in the world
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    m = np.eye(4)
    m[0, 0] = m[1, 1] = m[2, 2] = 2.0
    plan = plan_annotation(d, m, _FlatCamera(), 640, 480, Units())
    assert "8" in plan.texts[0].text


def test_dimension_line_sits_at_the_offset_not_on_the_geometry():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    # geometry is at world y=0 -> screen y=200; offset -2 -> screen y=220
    ys = [seg[1] for seg in plan.segments_px] + [seg[3] for seg in plan.segments_px]
    assert max(ys) > 215.0


def test_point_behind_camera_yields_no_plan():
    class _Behind:
        def world_to_screen(self, world_xyz, width, height):
            return None

    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    assert _plan(d, _Behind()) is None


def test_degenerate_zero_length_dimension_yields_no_plan():
    d = Dimension(1, (1.0, 1.0, 0.0), (1.0, 1.0, 0.0), (0.0, -2.0, 0.0))
    assert _plan(d) is None

"""Pure geometry for the Roof tool (M7c).

roof_solid builds a parametric Gable / Hip / Shed roof as ONE closed solid
(shared vertex list, outward-wound faces) in a canonical footprint frame:
origin at the footprint centre; +X = across-ridge span, +Y = along-ridge span,
+Z = up; base at z=0. No Model/Scene/Qt/GL deps.

_rot_z is a small 4x4 Z-rotation helper the tool uses to orient the canonical
roof onto the drawn footprint (kept here so the geometry frame conventions live
in one place).
"""
from __future__ import annotations

import numpy as np

_MAX_SLOPE_DEG = 85.0


def _rot_z(theta: float) -> np.ndarray:
    """4x4 rotation about +Z by theta radians."""
    c, s = float(np.cos(theta)), float(np.sin(theta))
    return np.array(
        [[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _finish(verts):
    return [(float(x), float(y), float(z)) for (x, y, z) in verts]


def roof_solid(kind, width, depth, angle):
    """Return (vertices, faces) for a Gable/Hip/Shed roof, or ([], []) if degenerate.

    kind: "shed" (mono-pitch), "gable" (full-depth ridge), or "hip" (ridge set
    back from both ends; pyramidal when depth <= width). angle is in degrees.
    """
    w = float(width)
    d = float(depth)
    a = float(angle)
    if w <= 0.0 or d <= 0.0 or a <= 0.0 or a > _MAX_SLOPE_DEG:
        return [], []
    t = float(np.tan(np.radians(a)))
    hw, hd = w / 2.0, d / 2.0

    if kind == "shed":
        big_h = w * t
        verts = [
            (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
            (hw, -hd, big_h), (hw, hd, big_h),                              # high edge 4,5
        ]
        faces = [
            (0, 3, 2, 1),      # base (-Z)
            (0, 4, 5, 3),      # sloped top
            (1, 2, 5, 4),      # high wall (+X)
            (0, 1, 4),         # -Y side
            (2, 3, 5),         # +Y side
        ]
        return _finish(verts), faces

    if kind == "gable":
        h = hw * t
        verts = [
            (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
            (0.0, -hd, h), (0.0, hd, h),                                    # ridge 4,5
        ]
        faces = [
            (0, 3, 2, 1),      # base
            (1, 2, 5, 4),      # +X slope
            (3, 0, 4, 5),      # -X slope
            (0, 1, 4),         # -Y gable end
            (2, 3, 5),         # +Y gable end
        ]
        return _finish(verts), faces

    # "hip" is added in Task 2; until then any unrecognised kind -> empty.
    return [], []

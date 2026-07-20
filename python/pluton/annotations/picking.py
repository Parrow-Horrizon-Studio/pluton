"""Screen-space annotation picking (M7d).

Hit-tests the SAME draw plan the painter renders, so anything visible is
clickable and nothing invisible is.
"""
from __future__ import annotations

from pluton.annotations.draw_plan import plan_annotation


def _inside(box, x, y):
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def _box_distance_sq(box, x, y):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return (cx - x) ** 2 + (cy - y) ** 2


def pick_annotation(cursor_px, annotations, world_transform, camera, width, height, units):
    """Return the id of the nearest annotation under the cursor, or None."""
    x, y = float(cursor_px[0]), float(cursor_px[1])
    best_id = None
    best_d2 = float("inf")
    for ann in annotations:
        plan = plan_annotation(ann, world_transform, camera, width, height, units)
        if plan is None:
            continue
        for box in plan.hit_boxes:
            if not _inside(box, x, y):
                continue
            d2 = _box_distance_sq(box, x, y)
            if d2 < best_d2:
                best_d2 = d2
                best_id = plan.annotation_id
    return best_id

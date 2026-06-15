"""Selection picking — pure screen-space (project to pixels via world_to_screen,
2D point-to-segment distance). Independent of the drawing-snap precedence:
selection wants the edge or face under the cursor, not a vertex/midpoint snap.
"""

from __future__ import annotations

import math

PICK_PIXEL_TOLERANCE = 8.0  # screen-space; matches the M3d snap feel


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    """2D distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def pick_selectable(cursor_screen, viewport_size, camera, scene):  # noqa: ANN001
    """Return ("edge", id) for the nearest edge within PICK_PIXEL_TOLERANCE of
    the cursor (screen-space); else ("face", id) under the cursor ray; else None.
    Edge-priority: thin targets are harder to hit, so they win over the face."""
    px, py = float(cursor_screen[0]), float(cursor_screen[1])
    w, h = int(viewport_size[0]), int(viewport_size[1])

    best_edge: int | None = None
    best_d = PICK_PIXEL_TOLERANCE
    for e in scene.edges_iter():
        p1 = scene.vertex(e.v1_id).position
        p2 = scene.vertex(e.v2_id).position
        s1 = camera.world_to_screen(p1, w, h)
        s2 = camera.world_to_screen(p2, w, h)
        if s1 is None or s2 is None:
            continue
        d = _point_segment_distance(px, py, s1[0], s1[1], s2[0], s2[1])
        if d <= best_d:
            best_d = d
            best_edge = e.id
    if best_edge is not None:
        return ("edge", best_edge)

    origin, direction = camera.ray_from_screen(px, py, w, h)
    hit = scene.ray_pick_face(origin, direction)
    if hit is not None:
        return ("face", int(hit.face_id))
    return None

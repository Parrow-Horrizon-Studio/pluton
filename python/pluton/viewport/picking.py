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


def _point_in_rect(px, py, rect) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= px <= x1 and y0 <= py <= y1


def _ccw(ax, ay, bx, by, cx, cy) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segments_cross(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    """True if segment AB properly straddles segment CD (and vice-versa)."""
    d1 = _ccw(cx, cy, dx, dy, ax, ay)
    d2 = _ccw(cx, cy, dx, dy, bx, by)
    d3 = _ccw(ax, ay, bx, by, cx, cy)
    d4 = _ccw(ax, ay, bx, by, dx, dy)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _segment_intersects_rect(ax, ay, bx, by, rect) -> bool:
    if _point_in_rect(ax, ay, rect) or _point_in_rect(bx, by, rect):
        return True
    x0, y0, x1, y1 = rect
    sides = (
        (x0, y0, x1, y0), (x1, y0, x1, y1),
        (x1, y1, x0, y1), (x0, y1, x0, y0),
    )
    for cx, cy, dx, dy in sides:
        if _segments_cross(ax, ay, bx, by, cx, cy, dx, dy):
            return True
    return False


def _normalize_rect(rect):
    x0, y0, x1, y1 = rect
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def entities_in_box(rect_px, mode, viewport_size, camera, scene):  # noqa: ANN001
    """Return (edge_ids: set, face_ids: set) inside rect_px under the given mode.
    mode="window": only fully-enclosed; mode="crossing": anything touched."""
    rect = _normalize_rect(rect_px)
    w, h = int(viewport_size[0]), int(viewport_size[1])
    edges: set[int] = set()
    faces: set[int] = set()

    def proj(world):
        return camera.world_to_screen(world, w, h)

    for e in scene.edges_iter():
        s1 = proj(scene.vertex(e.v1_id).position)
        s2 = proj(scene.vertex(e.v2_id).position)
        if mode == "window":
            if s1 is not None and s2 is not None and \
               _point_in_rect(s1[0], s1[1], rect) and _point_in_rect(s2[0], s2[1], rect):
                edges.add(e.id)
        else:  # crossing
            if s1 is None or s2 is None:
                if (s1 is not None and _point_in_rect(s1[0], s1[1], rect)) or \
                   (s2 is not None and _point_in_rect(s2[0], s2[1], rect)):
                    edges.add(e.id)
            elif _segment_intersects_rect(s1[0], s1[1], s2[0], s2[1], rect):
                edges.add(e.id)

    for f in scene.faces_iter():
        loop = scene.face_loop(f.id)
        pts = [proj(scene.vertex(v).position) for v in loop]
        if mode == "window":
            if all(p is not None and _point_in_rect(p[0], p[1], rect) for p in pts):
                faces.add(f.id)
        else:  # crossing
            touched = any(p is not None and _point_in_rect(p[0], p[1], rect) for p in pts)
            if not touched:
                n = len(pts)
                for i in range(n):
                    p, q = pts[i], pts[(i + 1) % n]
                    if p is not None and q is not None and \
                       _segment_intersects_rect(p[0], p[1], q[0], q[1], rect):
                        touched = True
                        break
            if touched:
                faces.add(f.id)

    return edges, faces

"""Pure screen-space layout for annotations (M7d).

plan_annotation turns an annotation plus a camera into screen-space primitives:
line segments, text placements and hit boxes. It is the SINGLE source of truth —
the QPainter renderer draws the plan and the picker hit-tests the same plan, so
what the user can click is exactly what they can see.

Numpy only: no Qt, no GL, no Model imports. All sizes are in pixels, so the
annotation keeps a constant on-screen size at any zoom.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pluton.units import format_length

# Pixel constants (annotation styling is fixed in M7d — see design D11).
FONT_PX = 12.0
CHAR_W_PX = 0.55 * FONT_PX  # rough advance width, enough for hit boxes
_TEXT_GAP_PX = 5.0  # text sits this far above the dimension line
_EXT_GAP_PX = 4.0  # extension line starts this far off the geometry
_EXT_OVERSHOOT_PX = 6.0  # ...and runs this far past the dimension line
_TICK_PX = 6.0  # half-length of a 45-degree tick
_LANDING_PX = 26.0  # horizontal landing under the text
_ARROW_PX = 9.0  # arrowhead stroke length
_ARROW_SPREAD = 0.42  # radians each side of the leader direction
_EPS = 1e-9
_GUIDE_CROSS_PX = 5.0  # half-length of each stroke of a guide point's cross
_NEAR_PAD = 1e-4  # push the clipped point just in front of the near plane
_VISIBLE_SPAN = 1.0e4  # world units drawn each way from a guide's closest approach to
# the eye. An infinite line has to be bounded to something the 2D viewport clip can
# handle in floating point; the viewport clip is what actually decides what is drawn,
# this constant just has to be generous enough to outlast a typical camera.far.


@dataclass
class TextDraw:
    text: str
    x: float
    y: float
    align: str = "center"  # "center" | "left" | "right"


@dataclass
class AnnotationDraw:
    annotation_id: int
    segments_px: list = field(default_factory=list)  # (x1, y1, x2, y2)
    texts: list = field(default_factory=list)  # TextDraw
    hit_boxes: list = field(default_factory=list)  # (x0, y0, x1, y1)
    kind: str = "annotation"  # the source annotation's `kind`, for kind-specific painting


def _world_matrix(world_transform):
    """`world_transform` as a 4x4 float64 matrix, treating None as identity.

    Guides are context-local like every other annotation, but a caller with no
    context to transform through (e.g. a bare layout test) passes None rather
    than constructing an identity matrix itself.
    """
    if world_transform is None:
        return np.eye(4, dtype=np.float64)
    return np.asarray(world_transform, dtype=np.float64)


def _to_world(point, world_transform):
    p = np.asarray(point, dtype=np.float64)
    return (_world_matrix(world_transform) @ np.append(p, 1.0))[:3]


def _vec_to_world(vec, world_transform):
    v = np.asarray(vec, dtype=np.float64)
    return _world_matrix(world_transform)[:3, :3] @ v


def _project(world_point, camera, width, height):
    hit = camera.world_to_screen(np.asarray(world_point, dtype=np.float64), width, height)
    if hit is None:
        return None
    return np.array([float(hit[0]), float(hit[1])], dtype=np.float64)


def _unit(v):
    n = float(np.linalg.norm(v))
    if n < _EPS:
        return None
    return v / n


def _text_box(text, x, y, align):
    w = max(len(text), 1) * CHAR_W_PX
    h = FONT_PX
    if align == "center":
        x0 = x - w / 2.0
    elif align == "right":
        x0 = x - w
    else:
        x0 = x
    return (x0, y - h, x0 + w, y)


def _segment_box(seg, pad=3.0):
    x0, y0, x1, y1 = seg
    return (min(x0, x1) - pad, min(y0, y1) - pad, max(x0, x1) + pad, max(y0, y1) + pad)


def plan_annotation(annotation, world_transform, camera, width, height, units):
    """Return an AnnotationDraw for `annotation`, or None if it cannot be drawn."""
    if getattr(annotation, "kind", None) == "dimension":
        return _plan_dimension(annotation, world_transform, camera, width, height, units)
    if getattr(annotation, "kind", None) == "label":
        return _plan_label(annotation, world_transform, camera, width, height)
    if getattr(annotation, "kind", None) == "guide":
        return _plan_guide(annotation, world_transform, camera, width, height)
    if getattr(annotation, "kind", None) == "guide_point":
        return _plan_guide_point(annotation, world_transform, camera, width, height)
    return None


def _plan_dimension(dim, world_transform, camera, width, height, units):
    p1_w = _to_world(dim.p1, world_transform)
    p2_w = _to_world(dim.p2, world_transform)
    off_w = _vec_to_world(dim.offset, world_transform)
    measured = float(np.linalg.norm(p2_w - p1_w))
    if measured < _EPS:
        return None

    p1_px = _project(p1_w, camera, width, height)
    p2_px = _project(p2_w, camera, width, height)
    d1_px = _project(p1_w + off_w, camera, width, height)
    d2_px = _project(p2_w + off_w, camera, width, height)
    if p1_px is None or p2_px is None or d1_px is None or d2_px is None:
        return None

    along = _unit(d2_px - d1_px)
    if along is None:
        return None
    perp = np.array([-along[1], along[0]], dtype=np.float64)

    plan = AnnotationDraw(annotation_id=dim.id, kind=dim.kind)

    # dimension line
    dim_seg = (float(d1_px[0]), float(d1_px[1]), float(d2_px[0]), float(d2_px[1]))
    plan.segments_px.append(dim_seg)

    # extension lines: small gap off the geometry, slight overshoot past the line
    for geom_px, dim_px in ((p1_px, d1_px), (p2_px, d2_px)):
        direction = _unit(dim_px - geom_px)
        if direction is None:
            continue
        start = geom_px + direction * _EXT_GAP_PX
        end = dim_px + direction * _EXT_OVERSHOOT_PX
        plan.segments_px.append((float(start[0]), float(start[1]), float(end[0]), float(end[1])))

    # 45-degree tick terminators, bisecting along/perp at each end
    tick_dir = _unit(along + perp)
    if tick_dir is not None:
        for end_px in (d1_px, d2_px):
            a = end_px - tick_dir * _TICK_PX
            b = end_px + tick_dir * _TICK_PX
            plan.segments_px.append((float(a[0]), float(a[1]), float(b[0]), float(b[1])))

    # measurement text, above the line on the side away from the geometry
    mid_dim = (d1_px + d2_px) / 2.0
    mid_geom = (p1_px + p2_px) / 2.0
    away = perp if float(np.dot(perp, mid_dim - mid_geom)) >= 0.0 else -perp
    text_at = mid_dim + away * _TEXT_GAP_PX
    label = format_length(measured, units)
    text = TextDraw(text=label, x=float(text_at[0]), y=float(text_at[1]), align="center")
    plan.texts.append(text)

    plan.hit_boxes.append(_text_box(label, text.x, text.y, text.align))
    plan.hit_boxes.append(_segment_box(dim_seg))
    return plan


def collect_annotation_plans(model, camera, width, height, units):
    """Return (plan, dimmed) for every visible annotation in the model.

    Annotations render from every context — dimmed when not active — exactly
    matching how geometry behaves: `dimmed` is `model.definition_is_dimmed(defn)`,
    the SAME predicate the renderer uses for geometry, so a definition never
    disagrees with itself about whether it is dimmed. At the root (no active
    path) nothing is dimmed, even for a group that is not the active context.
    Picking remains active-context-only (see #95) -- this helper is only
    used for drawing.

    Pure: no Qt, no GL. `model` is used only via traverse_visible() and
    definition_is_dimmed(), so this stays a plain function call, not a new
    import, keeping this module free of Model imports.
    """
    out = []
    for defn, world in model.traverse_visible():
        dimmed = model.definition_is_dimmed(defn)
        for ann in defn.annotations:
            plan = plan_annotation(ann, world, camera, width, height, units)
            if plan is not None:
                out.append((plan, dimmed))
    return out


def _plan_label(label, world_transform, camera, width, height):
    anchor_w = _to_world(label.anchor, world_transform)
    text_w = _to_world(label.text_pos, world_transform)
    anchor_px = _project(anchor_w, camera, width, height)
    text_px = _project(text_w, camera, width, height)
    if anchor_px is None or text_px is None:
        return None

    plan = AnnotationDraw(annotation_id=label.id, kind=label.kind)
    to_right = float(text_px[0]) >= float(anchor_px[0])
    sign = 1.0 if to_right else -1.0
    # the landing runs from the elbow toward the text side
    elbow = np.array([float(text_px[0]) - sign * _LANDING_PX, float(text_px[1])])

    leader = (float(anchor_px[0]), float(anchor_px[1]), float(elbow[0]), float(elbow[1]))
    landing = (float(elbow[0]), float(elbow[1]), float(text_px[0]), float(text_px[1]))
    plan.segments_px.append(leader)
    plan.segments_px.append(landing)

    # arrowhead: two strokes fanned about the leader direction, tip at the anchor
    direction = _unit(elbow - anchor_px)
    if direction is not None:
        for spread in (_ARROW_SPREAD, -_ARROW_SPREAD):
            c, s = float(np.cos(spread)), float(np.sin(spread))
            rotated = np.array(
                [direction[0] * c - direction[1] * s, direction[0] * s + direction[1] * c]
            )
            tail = anchor_px + rotated * _ARROW_PX
            plan.segments_px.append(
                (float(anchor_px[0]), float(anchor_px[1]), float(tail[0]), float(tail[1]))
            )

    align = "left" if to_right else "right"
    text = TextDraw(
        text=label.text,
        x=float(text_px[0]),
        y=float(text_px[1]) - _TEXT_GAP_PX * 0.4,
        align=align,
    )
    plan.texts.append(text)
    plan.hit_boxes.append(_text_box(label.text, text.x, text.y, align))
    plan.hit_boxes.append(_segment_box(leader))
    return plan


def _clip_line_to_near_plane(origin, direction, camera):
    """The visible span of an infinite 3D line, as two world points, or None.

    Clipping in 3D before projecting is not optional. `world_to_screen` is
    meaningless behind the eye, so sampling two far-apart points and projecting
    them produces mirrored or runaway coordinates whenever the line crosses the
    near plane, which an infinite line usually does.
    """
    # Camera is a dataclass: `position` and `target` are ATTRIBUTES, not methods.
    eye = np.asarray(camera.position, dtype=np.float64).reshape(3)
    fwd = np.asarray(camera.target, dtype=np.float64).reshape(3) - eye
    fwd = fwd / float(np.linalg.norm(fwd))
    near = float(camera.near) + _NEAR_PAD

    o = np.asarray(origin, dtype=np.float64).reshape(3)
    d = np.asarray(direction, dtype=np.float64).reshape(3)
    d = d / float(np.linalg.norm(d))

    # Signed distance in front of the near plane, as a function of t: f(t) = a + b*t
    a = float(np.dot(o - eye, fwd)) - near
    b = float(np.dot(d, fwd))

    span = _VISIBLE_SPAN  # world units of line drawn each way from the closest point
    # Parameter of the point on the line closest to the eye, so the drawn span is
    # centred on the part of the line the user is actually looking at.
    t_mid = float(np.dot(eye - o, d))
    lo, hi = t_mid - span, t_mid + span

    if abs(b) < 1e-12:
        return None if a <= 0.0 else (o + d * lo, o + d * hi)
    t_cross = -a / b
    if b > 0.0:
        lo = max(lo, t_cross)
    else:
        hi = min(hi, t_cross)
    if hi <= lo:
        return None
    return (o + d * lo, o + d * hi)


def _clip_segment_to_viewport(x1, y1, x2, y2, width, height):
    """Liang-Barsky clip of a 2D segment to the viewport, or None if outside."""
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1), (dx, width - x1), (-dy, y1), (dy, height - y1)):
        if abs(p) < 1e-12:
            if q < 0.0:
                return None
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    if t1 <= t0:
        return None
    return (x1 + t0 * dx, y1 + t0 * dy, x1 + t1 * dx, y1 + t1 * dy)


def _plan_guide(guide, world_transform, camera, width, height):
    origin = _to_world(guide.origin, world_transform)
    direction = _vec_to_world(guide.direction, world_transform)
    span = _clip_line_to_near_plane(origin, direction, camera)
    if span is None:
        return AnnotationDraw(annotation_id=guide.id, kind=guide.kind)
    p_a = _project(span[0], camera, width, height)
    p_b = _project(span[1], camera, width, height)
    if p_a is None or p_b is None:
        return AnnotationDraw(annotation_id=guide.id, kind=guide.kind)
    clipped = _clip_segment_to_viewport(p_a[0], p_a[1], p_b[0], p_b[1], width, height)
    if clipped is None:
        return AnnotationDraw(annotation_id=guide.id, kind=guide.kind)
    draw = AnnotationDraw(annotation_id=guide.id, kind=guide.kind)
    draw.segments_px.append(clipped)
    draw.hit_boxes.append(_segment_box(clipped))
    return draw


def _plan_guide_point(point, world_transform, camera, width, height):
    projected = _project(_to_world(point.position, world_transform), camera, width, height)
    if projected is None:
        return AnnotationDraw(annotation_id=point.id, kind=point.kind)
    x, y = float(projected[0]), float(projected[1])
    # _project only excludes points behind the eye (see world_to_screen), not
    # points off to the side: a guide point needs its own viewport bounds
    # check, the way a guide's infinite line gets one from
    # _clip_segment_to_viewport. Without this, a construction point far
    # outside the current view still emits a cross at wildly out-of-range
    # pixel coordinates.
    if not (0.0 <= x <= width and 0.0 <= y <= height):
        return AnnotationDraw(annotation_id=point.id, kind=point.kind)
    r = _GUIDE_CROSS_PX
    draw = AnnotationDraw(annotation_id=point.id, kind=point.kind)
    draw.segments_px.append((x - r, y - r, x + r, y + r))
    draw.segments_px.append((x - r, y + r, x + r, y - r))
    draw.hit_boxes.append(_segment_box(draw.segments_px[0]))
    return draw

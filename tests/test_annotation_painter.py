"""Tests for the M7d annotation painter (Task 4).

paint_annotation_plans is deliberately painter-agnostic: it works against any
object exposing setPen/drawLine/drawText, so these tests use a recording stub
instead of a real QPainter (keeping the suite headless).
"""

from __future__ import annotations

from pluton.annotations.draw_plan import AnnotationDraw, TextDraw
from pluton.viewport.annotation_painter import paint_annotation_plans


class _RecordingPainter:
    """Stands in for a QPainter. Exposes Qt's camelCase method names (setPen /
    drawLine / drawText) as instance attributes bound to snake_case methods,
    since ruff's N802 forbids camelCase `def` names but the painter contract
    paint_annotation_plans calls against is Qt's, not ours."""

    def __init__(self):
        self.lines = []
        self.texts = []
        self.pens = []
        self.setPen = self._set_pen
        self.drawLine = self._draw_line
        self.drawText = self._draw_text

    def _set_pen(self, pen):
        self.pens.append(pen)

    def _draw_line(self, x1, y1, x2, y2):
        self.lines.append((x1, y1, x2, y2))

    def _draw_text(self, x, y, s):
        self.texts.append((x, y, s))


def _plan(ann_id=1):
    return AnnotationDraw(
        annotation_id=ann_id,
        segments_px=[(0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0)],
        texts=[TextDraw("3600", 5.0, -2.0, "center")],
        hit_boxes=[],
    )


def test_paints_every_segment_and_text():
    p = _RecordingPainter()
    paint_annotation_plans(p, [_plan()], (0.1, 0.1, 0.1), set(), (0.2, 0.5, 0.9))
    assert len(p.lines) == 2
    assert len(p.texts) == 1
    assert p.texts[0][2] == "3600"


def test_selected_annotation_uses_the_selection_pen():
    """The selected colour must be the one actually passed to setPen — not
    merely that *a* pen was set (which would pass even if the selection
    branch were inverted)."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    paint_annotation_plans(p, [_plan(7)], color, {7}, selected_color)
    assert p.pens == [selected_color]


def test_unselected_annotation_uses_the_default_pen():
    """Complementary case: an annotation NOT in selected_ids must get the
    default colour, not the selection colour."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    paint_annotation_plans(p, [_plan(7)], color, set(), selected_color)
    assert p.pens == [color]


def test_empty_plan_list_draws_nothing():
    p = _RecordingPainter()
    paint_annotation_plans(p, [], (0.1, 0.1, 0.1), set(), (0.2, 0.5, 0.9))
    assert p.lines == [] and p.texts == []

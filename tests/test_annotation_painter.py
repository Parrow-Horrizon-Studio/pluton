"""Tests for the M7d annotation painter (Task 4).

paint_annotation_plans is deliberately painter-agnostic: it works against any
object exposing setPen/drawLine/drawText, so these tests use a recording stub
instead of a real QPainter (keeping the suite headless).
"""

from __future__ import annotations

import numpy as np
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


def test_hovered_annotation_uses_the_hover_pen():
    """Task 10b: a hovered (but not selected) annotation must be painted with
    the hover colour, distinct from both the default and the selected pen."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    hover_color = (0.45, 0.70, 1.00)
    paint_annotation_plans(
        p, [_plan(7)], color, set(), selected_color, hovered_id=7, hover_color=hover_color
    )
    assert p.pens == [hover_color]


def test_unhovered_annotation_uses_the_default_pen_when_hover_param_set():
    """A hovered_id that doesn't match this plan's id must not leak the hover
    colour onto an unrelated annotation."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    hover_color = (0.45, 0.70, 1.00)
    paint_annotation_plans(
        p, [_plan(7)], color, set(), selected_color, hovered_id=99, hover_color=hover_color
    )
    assert p.pens == [color]


def test_hovered_and_selected_annotation_uses_the_selected_pen_not_hover():
    """Precedence: selected beats hover, exactly as it does for edges/faces/
    instances (Task 10b design decision)."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    hover_color = (0.45, 0.70, 1.00)
    paint_annotation_plans(
        p, [_plan(7)], color, {7}, selected_color, hovered_id=7, hover_color=hover_color
    )
    assert p.pens == [selected_color]


def test_no_hovered_id_uses_the_default_pen():
    """Backward-compatible default: omitting hovered_id/hover_color entirely
    (as the pre-Task-10b callers do) must behave exactly as before."""
    p = _RecordingPainter()
    color = (0.1, 0.1, 0.1)
    selected_color = (0.2, 0.5, 0.9)
    paint_annotation_plans(p, [_plan(7)], color, set(), selected_color)
    assert p.pens == [color]


class _RecordingQPainter:
    """Stands in for QPainter inside ViewportWidget._paint_annotations.

    `self` in that method is a duck-typed stand-in below, not a real
    QPaintDevice, so the real QPainter can't be constructed against it. This
    fake is swapped in via monkeypatch (PySide6.QtGui.QPainter is looked up
    fresh on each call because the method does a local `from PySide6.QtGui
    import QPainter`), so the method under test runs unmodified.

    Exposes Qt's camelCase method names as instance attributes bound to
    snake_case methods, matching the _RecordingPainter convention above
    (ruff's N802 forbids camelCase `def` names, but the contract here is
    Qt's, not ours).
    """

    class RenderHint:
        Antialiasing = 1  # only value the method under test references

    last = None  # set to the most recently constructed instance

    def __init__(self, _device):
        self.pens = []
        self.texts = []
        self.setRenderHint = self._set_render_hint
        self.setFont = self._set_font
        self.setPen = self._set_pen
        self.drawLine = self._draw_line
        self.drawText = self._draw_text
        type(self).last = self

    def _set_render_hint(self, *args, **kwargs):
        pass

    def _set_font(self, *args, **kwargs):
        pass

    def _set_pen(self, pen):
        self.pens.append(pen)

    def _draw_line(self, x1, y1, x2, y2):
        pass

    def _draw_text(self, x, y, s):
        self.texts.append((x, y, s))

    def end(self):
        pass


class _FakeContext:
    def __init__(self, annotations):
        self.annotations = annotations


class _FakeModel:
    def __init__(self, annotations):
        self.active_context = _FakeContext(annotations)
        self.active_world_transform = np.eye(4)


class _FakeViewport:
    """Duck-typed stand-in for ViewportWidget: exposes exactly what
    _paint_annotations reads from `self`, without needing a real QWidget/
    QApplication (ViewportWidget._paint_annotations is called directly as an
    unbound method against this)."""

    def __init__(self, model, camera):
        self.model = model
        self.camera = camera
        self.selection = None
        self._units_provider = None  # the case under test: no provider set

    def width(self):
        return 800

    def height(self):
        return 600


def test_paint_annotations_defaults_to_real_units_when_no_provider_set(monkeypatch):
    """Regression test for the M7d Task 4 review (Finding 1).

    MainWindow does not currently call set_units_provider, so `units` being
    None is the default configuration today, not an edge case. Before the
    fix, _paint_annotations passed units=None straight through to
    plan_annotation -> _plan_dimension -> format_length(measured, None),
    which crashes: AttributeError: 'NoneType' object has no attribute
    'system'. It must default to a real pluton.units.Units() instead,
    matching every other units provider in the codebase (wall/opening/roof
    options bars).

    This calls the real _paint_annotations method (not a reimplementation of
    its units logic), faking only QPainter -- since `self` here isn't an
    actual QPaintDevice -- to keep the test headless with no QApplication or
    real window.
    """
    from pluton.model.annotation import Dimension
    from pluton.viewport.camera import Camera
    from pluton.viewport.viewport_widget import ViewportWidget
    from PySide6 import QtGui

    monkeypatch.setattr(QtGui, "QPainter", _RecordingQPainter)

    dim = Dimension(id=1, p1=(0.0, 0.0, 0.0), p2=(1.0, 0.0, 0.0), offset=(0.0, 0.0, 0.2))
    fake_viewport = _FakeViewport(_FakeModel([dim]), Camera())

    ViewportWidget._paint_annotations(fake_viewport)  # must not raise

    drawn_strings = [text for _x, _y, text in _RecordingQPainter.last.texts]
    assert drawn_strings == ["1 m"]


def test_paint_annotations_paints_the_hovered_annotation_with_the_hover_pen(monkeypatch):
    """Task 10b wiring test: _paint_annotations must thread the active tool's
    hovered annotation id (surfaced via ToolOverlay.hovered_annotation_id --
    the same per-frame channel paintGL already uses for edge/face/instance
    hover) through to paint_annotation_plans.

    Reachable headlessly: paintGL passes the tool's freshly-computed
    ToolOverlay into _paint_annotations as an explicit argument, so this test
    can hand in a plain ToolOverlay instance directly -- no real GL widget,
    QApplication, or ToolManager needed.
    """
    import numpy as np
    from pluton.model.annotation import Dimension
    from pluton.tools.tool import ToolOverlay
    from pluton.viewport.camera import Camera
    from pluton.viewport.viewport_widget import ViewportWidget
    from PySide6 import QtGui

    monkeypatch.setattr(QtGui, "QPainter", _RecordingQPainter)

    dim = Dimension(id=1, p1=(0.0, 0.0, 0.0), p2=(1.0, 0.0, 0.0), offset=(0.0, 0.0, 0.2))
    fake_viewport = _FakeViewport(_FakeModel([dim]), Camera())
    overlay = ToolOverlay(
        rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
        rubber_band_color=(0.0, 0.0, 0.0),
        snap_marker_position=None,
        snap_marker_color=(0.0, 0.0, 0.0),
        hovered_annotation_id=1,
    )

    ViewportWidget._paint_annotations(fake_viewport, overlay)

    from PySide6.QtGui import QColor
    hover_pen = _RecordingQPainter.last.pens[0]
    assert isinstance(hover_pen, QColor)
    assert hover_pen != QColor(30, 30, 30)  # must not be the plain default pen

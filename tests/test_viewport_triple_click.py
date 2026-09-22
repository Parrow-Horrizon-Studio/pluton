"""ViewportWidget synthesizes the triple-click Qt never sends.

These tests drive the widget's mousePressEvent directly with a stub tool and
an injected clock, so no test here sleeps.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


class _RecordingTool:
    """Minimal Tool stand-in that records which hooks fired.

    `anchor_or_none` and `has_active_gesture` are here because
    ViewportWidget._snap_for_event reads both on every press (anchor for
    axis-lock, has_active_gesture for the M7.6b lifecycle edge) before any
    tool-specific hook runs at all; they are unrelated to the triple-click
    gesture this test module exercises but are required for mousePressEvent
    to reach that hook without raising.
    """

    def __init__(self):
        self.presses = 0
        self.doubles = 0
        self.triples = 0

    has_active_gesture = False
    anchor_or_none = None

    @property
    def measurement_text(self):
        return None

    def on_mouse_press(self, event, snap):
        self.presses += 1

    def on_mouse_double_click(self, event, snap):
        self.doubles += 1

    def on_mouse_triple_click(self, event, snap):
        self.triples += 1

    def on_mouse_move(self, event, snap):
        return None

    def on_mouse_release(self, event, snap):
        return None

    def overlay(self):
        return None


class _ToolManager:
    def __init__(self, tool):
        self.active = tool


def _press_event(x, y):
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(x), float(y)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _widget(qtbot, clock):
    from pluton.viewport.viewport_widget import ViewportWidget

    w = ViewportWidget()
    qtbot.addWidget(w)
    tool = _RecordingTool()
    w.tool_manager = _ToolManager(tool)
    w.set_now_ms_provider(lambda: clock[0])
    return w, tool


def test_three_quick_presses_fire_the_triple_click_hook_once(qtbot):
    clock = [0.0]
    w, tool = _widget(qtbot, clock)
    for t in (0.0, 120.0, 240.0):
        clock[0] = t
        w.mousePressEvent(_press_event(100, 100))
    assert tool.triples == 1


def test_two_quick_presses_do_not_fire_the_triple_click_hook(qtbot):
    clock = [0.0]
    w, tool = _widget(qtbot, clock)
    for t in (0.0, 120.0):
        clock[0] = t
        w.mousePressEvent(_press_event(100, 100))
    assert tool.triples == 0


def test_every_press_still_reaches_on_mouse_press(qtbot):
    """The triple-click hook is ADDITIVE. The third press must still drive
    the ordinary press path, or box-select's press/drag/release breaks."""
    clock = [0.0]
    w, tool = _widget(qtbot, clock)
    for t in (0.0, 120.0, 240.0):
        clock[0] = t
        w.mousePressEvent(_press_event(100, 100))
    assert tool.presses == 3


def test_three_slow_presses_do_not_fire_the_triple_click_hook(qtbot):
    clock = [0.0]
    w, tool = _widget(qtbot, clock)
    for t in (0.0, 5000.0, 10000.0):
        clock[0] = t
        w.mousePressEvent(_press_event(100, 100))
    assert tool.triples == 0


def test_three_quick_presses_far_apart_do_not_fire_the_hook(qtbot):
    clock = [0.0]
    w, tool = _widget(qtbot, clock)
    for t, x in ((0.0, 100), (120.0, 400), (240.0, 700)):
        clock[0] = t
        w.mousePressEvent(_press_event(x, 100))
    assert tool.triples == 0


def test_a_tool_without_the_hook_does_not_crash(qtbot):
    """Tool supplies a default no-op, but a bare stub in some other test
    might not. Dispatch must not assume the attribute exists."""
    clock = [0.0]
    w, _tool = _widget(qtbot, clock)

    class _Bare:
        has_active_gesture = False
        anchor_or_none = None

        @property
        def measurement_text(self):
            return None

        def on_mouse_press(self, event, snap):
            return None

        def overlay(self):
            return None

    w.tool_manager = _ToolManager(_Bare())
    for t in (0.0, 120.0, 240.0):
        clock[0] = t
        w.mousePressEvent(_press_event(100, 100))


def test_the_base_tool_supplies_a_no_op_triple_click_hook():
    """Tool is an ABC (activate/deactivate/overlay/anchor_or_none/etc. are
    abstract), so it cannot be instantiated directly -- see
    tests/test_tool_release_plumbing.py::test_tool_default_on_mouse_release_is_noop
    for the established pattern this follows: a minimal concrete subclass
    that implements only the abstract members, to exercise the base class's
    default hook."""
    import numpy as np
    from pluton.tools.tool import Tool, ToolOverlay

    class _Min(Tool):
        @property
        def name(self):
            return "Min"

        @property
        def shortcut(self):
            return "Z"

        @property
        def id(self):
            return "min"

        @property
        def has_active_gesture(self):
            return False

        def activate(self, ctx):
            pass

        def deactivate(self):
            pass

        def overlay(self):
            return ToolOverlay(
                rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
                rubber_band_color=(1, 1, 1),
                snap_marker_position=None,
                snap_marker_color=(1, 1, 1),
            )

        @property
        def anchor_or_none(self):
            return None

    assert _Min().on_mouse_triple_click(None, None) is None

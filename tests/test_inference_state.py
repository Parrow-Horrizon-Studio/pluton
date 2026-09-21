"""Hover-dwell acquisition and inference locking.

The clock is injected, so dwell is a value here and never a timer. Every test
that advances time does so by mutating the list the fake clock reads.
"""

from __future__ import annotations

import numpy as np


class _FakeClock:
    """A millisecond clock the test advances by hand."""

    def __init__(self) -> None:
        self.ms = 0.0

    def __call__(self) -> float:
        return self.ms


def _vertex_snap(vertex_id=7, position=(1.0, 2.0, 3.0)):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.ENDPOINT,
        world_position=np.array(position, dtype=np.float32),
        axis=None,
        vertex_id=vertex_id,
        label="Endpoint",
    )


def test_dwell_shorter_than_the_threshold_acquires_nothing():
    from pluton.viewport.inference import DWELL_MS, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)

    state.observe(_vertex_snap(), (100.0, 100.0))
    clock.ms += DWELL_MS - 1
    state.observe(_vertex_snap(), (100.0, 100.0))

    assert state.acquired is None


def test_dwell_at_the_threshold_acquires_the_vertex():
    from pluton.viewport.inference import DWELL_MS, AcquiredKind, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)

    state.observe(_vertex_snap(vertex_id=7), (100.0, 100.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(vertex_id=7), (100.0, 100.0))

    assert state.acquired is not None
    assert state.acquired.kind == AcquiredKind.VERTEX
    assert state.acquired.entity_id == 7


def test_moving_off_the_candidate_restarts_the_dwell():
    from pluton.viewport.inference import DWELL_MS, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)

    state.observe(_vertex_snap(), (100.0, 100.0))
    clock.ms += DWELL_MS - 10
    # A jump larger than PIXEL_TOLERANCE resets the timer even though the same
    # entity is still reported.
    state.observe(_vertex_snap(), (140.0, 100.0))
    clock.ms += 20
    state.observe(_vertex_snap(), (140.0, 100.0))

    assert state.acquired is None


def test_a_new_entity_replaces_the_acquisition():
    from pluton.viewport.inference import DWELL_MS, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)

    state.observe(_vertex_snap(vertex_id=7), (100.0, 100.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(vertex_id=7), (100.0, 100.0))
    assert state.acquired.entity_id == 7

    state.observe(_vertex_snap(vertex_id=9, position=(5.0, 5.0, 5.0)), (300.0, 300.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(vertex_id=9, position=(5.0, 5.0, 5.0)), (300.0, 300.0))
    assert state.acquired.entity_id == 9


def test_axis_lock_toggles_off_on_a_second_press():
    from pluton.viewport.inference import InferenceState

    state = InferenceState(now_ms=_FakeClock())
    state.toggle_axis_lock(2)
    assert state.lock is not None
    assert state.lock.axis == 2
    state.toggle_axis_lock(2)
    assert state.lock is None


def test_a_different_axis_replaces_the_lock_rather_than_clearing_it():
    from pluton.viewport.inference import InferenceState

    state = InferenceState(now_ms=_FakeClock())
    state.toggle_axis_lock(2)
    state.toggle_axis_lock(0)
    assert state.lock is not None
    assert state.lock.axis == 0


def test_ending_a_gesture_releases_both_lock_and_acquisition():
    from pluton.viewport.inference import DWELL_MS, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)
    state.observe(_vertex_snap(), (100.0, 100.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(), (100.0, 100.0))
    state.toggle_axis_lock(1)

    state.end_gesture()

    assert state.lock is None
    assert state.acquired is None


def test_apply_lock_returns_the_snap_untouched_when_no_lock_is_active():
    from pluton.viewport.camera import Camera
    from pluton.viewport.inference import InferenceState

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    state = InferenceState(now_ms=_FakeClock())
    snap = _vertex_snap()

    out = state.apply_lock(snap, cam, (1280, 800), (400.0, 300.0))
    assert out is snap


def test_an_axis_lock_runs_through_the_gesture_anchor():
    """Spec 2.3 / D6: an arrow key constrains the line being drawn to an axis.

    The line therefore passes through the point the gesture started from.
    The test this replaces asserted the opposite ("blue / Z, through the
    origin"), which made a line from an anchor at (5, 5, 0) commit to a
    point with x = y = 0: axis-aligned with respect to nothing the user had
    drawn.
    """
    from pluton.viewport.camera import Camera
    from pluton.viewport.inference import InferenceState
    from pluton.viewport.snap_engine import SnapKind

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    state = InferenceState(now_ms=_FakeClock())
    anchor = np.array([5.0, 5.0, 0.0], dtype=np.float64)
    state.toggle_axis_lock(0)  # red / X

    out = state.apply_lock(_vertex_snap(), cam, (1280, 800), (700.0, 250.0), anchor=anchor)
    assert out.kind == SnapKind.AXIS_LOCK
    assert out.axis == 0
    # On the X axis THROUGH THE ANCHOR: y and z stay at the anchor's own.
    assert abs(float(out.world_position[1]) - 5.0) < 1e-4
    assert abs(float(out.world_position[2])) < 1e-4
    # And the cursor still chooses the distance along it, so x has moved off
    # the anchor rather than the whole result collapsing onto the anchor.
    assert abs(float(out.world_position[0]) - 5.0) > 1e-3


def test_an_axis_lock_ignores_the_acquired_reference_once_there_is_an_anchor():
    """An acquired vertex must not displace the axis lock's line.

    Pinning it to the acquired point is From-Point behaviour (a different
    inference, with its own kind and its own precedence slot), not an axis
    lock, and it silently changed what the arrow key meant depending on
    whether the cursor had happened to rest on something first.
    """
    from pluton.viewport.camera import Camera
    from pluton.viewport.inference import DWELL_MS, InferenceState

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    clock = _FakeClock()
    state = InferenceState(now_ms=clock)
    state.observe(_vertex_snap(position=(0.0, -9.0, 0.0)), (100.0, 100.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(position=(0.0, -9.0, 0.0)), (100.0, 100.0))
    assert state.acquired is not None

    anchor = np.array([5.0, 5.0, 0.0], dtype=np.float64)
    state.toggle_axis_lock(0)
    out = state.apply_lock(_vertex_snap(), cam, (1280, 800), (700.0, 250.0), anchor=anchor)
    assert abs(float(out.world_position[1]) - 5.0) < 1e-4


def test_an_axis_lock_with_no_gesture_falls_back_to_the_acquired_point():
    """Armed before anything is drawn, the lock still has to resolve.

    With no anchor there is nothing to constrain, so the line falls back to
    the acquired reference (and, failing that, the world origin) rather than
    refusing to produce a point.
    """
    from pluton.viewport.camera import Camera
    from pluton.viewport.inference import DWELL_MS, InferenceState

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    clock = _FakeClock()
    state = InferenceState(now_ms=clock)
    state.observe(_vertex_snap(position=(2.0, 3.0, 0.0)), (100.0, 100.0))
    clock.ms += DWELL_MS
    state.observe(_vertex_snap(position=(2.0, 3.0, 0.0)), (100.0, 100.0))

    state.toggle_axis_lock(0)
    out = state.apply_lock(_vertex_snap(), cam, (1280, 800), (700.0, 250.0))
    assert abs(float(out.world_position[1]) - 3.0) < 1e-4

    state.clear_acquisition()
    out = state.apply_lock(_vertex_snap(), cam, (1280, 800), (700.0, 250.0))
    assert abs(float(out.world_position[1])) < 1e-4


def test_the_viewport_hands_the_gesture_anchor_to_the_active_lock(qtbot):
    """The end-to-end half of C1: `_snap_for_event` owns the anchor.

    Before the fix `apply_lock` had no parameter for it and `MainWindow`'s
    arrow-key handler had no access to it, so the anchor could not reach the
    lock however the lock was written.
    """
    from pluton.model.model import Model
    from pluton.viewport.snap_engine import SnapKind
    from pluton.viewport.viewport_widget import ViewportWidget

    anchor = np.array([5.0, 5.0, 0.0], dtype=np.float32)

    class _Tool:
        @property
        def anchor_or_none(self):
            return anchor

        @property
        def has_active_gesture(self):
            return True

    class _Mgr:
        def __init__(self):
            self.active = _Tool()

    widget = ViewportWidget(model=Model(), tool_manager=_Mgr())
    qtbot.addWidget(widget)
    widget.resize(1280, 800)
    widget.camera.aspect = 1280.0 / 800.0
    widget.inference.toggle_axis_lock(0)  # Right arrow / red X

    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(800.0, 400.0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    result = widget._snap_for_event(event)
    assert result.kind == SnapKind.AXIS_LOCK
    assert abs(float(result.world_position[1]) - 5.0) < 1e-3
    assert abs(float(result.world_position[2])) < 1e-3


def _edge_snap(edge_id=3, position=(0.0, 0.0, 0.0)):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.MIDPOINT,
        world_position=np.array(position, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="Midpoint",
        edge_id=edge_id,
    )


def _axis_snap(axis=2, position=(0.0, 0.0, 5.0)):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.AXIS_LOCK,
        world_position=np.array(position, dtype=np.float32),
        axis=axis,
        vertex_id=None,
        label="on Blue Axis",
    )


def test_toggle_edge_lock_with_nothing_acquired_is_a_no_op():
    from pluton.viewport.inference import InferenceState

    state = InferenceState(now_ms=_FakeClock())
    state.toggle_edge_lock()

    assert state.lock is None


def test_toggle_edge_lock_locks_to_the_acquired_edge_and_toggles_off():
    from pluton.viewport.inference import DWELL_MS, InferenceState

    clock = _FakeClock()
    state = InferenceState(now_ms=clock)
    direction = (1.0, 0.0, 0.0)

    state.observe(_edge_snap(), (100.0, 100.0), edge_direction=direction)
    clock.ms += DWELL_MS
    state.observe(_edge_snap(), (100.0, 100.0), edge_direction=direction)
    assert state.acquired is not None
    assert state.acquired.direction is not None

    state.toggle_edge_lock()
    assert state.lock is not None
    np.testing.assert_allclose(state.lock.direction, [1.0, 0.0, 0.0])

    state.toggle_edge_lock()
    assert state.lock is None


def test_shift_lock_set_from_an_axis_bearing_snap_and_cleared_on_release():
    from pluton.viewport.inference import InferenceState

    state = InferenceState(now_ms=_FakeClock())

    state.set_shift_lock(True, _axis_snap(axis=2))
    assert state.lock is not None
    assert state.lock.axis == 2

    state.set_shift_lock(False, None)
    assert state.lock is None


def test_an_arrow_armed_axis_lock_survives_a_shift_press_and_release():
    """Regression for Important 1: a Shift release anywhere in the app (the
    eventFilter that drives set_shift_lock is installed application-wide)
    must not discard a lock some other control armed."""
    from pluton.viewport.inference import InferenceState

    state = InferenceState(now_ms=_FakeClock())
    state.toggle_axis_lock(0)
    assert state.lock is not None

    state.set_shift_lock(True, None)
    state.set_shift_lock(False, None)

    assert state.lock is not None
    assert state.lock.axis == 0


def test_a_shift_lock_with_no_axis_is_not_cleared_by_toggle_edge_lock():
    """Regression for Minor 2: before the `source` field existed, a Shift
    lock formed against a snap with no axis (e.g. a midpoint or on-face
    inference) had `lock.axis is None`, indistinguishable from an edge lock's
    own `axis is None`, so Down would wrongly toggle it off believing it was
    toggling an edge lock. Built by hand: InferenceState.set_shift_lock only
    derives a direction from an axis-bearing snap today, but the two lock
    kinds must never be confused regardless of how the direction was formed.
    """
    from pluton.viewport.inference import InferenceState, Lock

    state = InferenceState(now_ms=_FakeClock())
    state._lock = Lock(
        origin=np.zeros(3),
        direction=np.array([0.0, 1.0, 0.0]),
        axis=None,
        label="Some Inference",
        source="shift",
    )

    state.toggle_edge_lock()

    assert state.lock is not None
    assert state.lock.source == "shift"


def _mutable_tool():
    """A stand-in tool whose gesture can be turned off between frames."""

    class _Tool:
        def __init__(self):
            self.gesture = True
            self.anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        @property
        def anchor_or_none(self):
            return self.anchor if self.gesture else None

        @property
        def has_active_gesture(self):
            return self.gesture

    return _Tool()


def _move_event(x, y):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(float(x), float(y)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_the_viewport_releases_lock_and_acquisition_when_the_gesture_ends(qtbot):
    """Spec 2.3: "a lock also releases when the gesture ends".

    Before the fix `end_gesture` had no production caller at all, so a lock
    armed in one gesture, and a reference dwelled on once, both survived for
    the rest of the session: every later Line, Rectangle or Push/Pull drag
    was still being resolved against them.
    """
    from pluton.model.model import Model
    from pluton.viewport.inference import Acquired, AcquiredKind
    from pluton.viewport.viewport_widget import ViewportWidget

    tool = _mutable_tool()

    class _Mgr:
        def __init__(self):
            self.active = tool

    widget = ViewportWidget(model=Model(), tool_manager=_Mgr())
    qtbot.addWidget(widget)
    widget.resize(1280, 800)
    widget.camera.aspect = 1280.0 / 800.0

    widget.inference.toggle_axis_lock(0)
    widget.inference._acquired = Acquired(
        kind=AcquiredKind.EDGE,
        position=np.zeros(3),
        direction=np.array([1.0, 0.0, 0.0]),
        entity_id=3,
    )

    # A frame mid-gesture leaves both in place.
    widget._snap_for_event(_move_event(700.0, 400.0))
    assert widget.inference.lock is not None
    assert widget.inference.acquired is not None

    # The tool finishes; the next frame releases both.
    tool.gesture = False
    widget._snap_for_event(_move_event(705.0, 402.0))
    assert widget.inference.lock is None
    assert widget.inference.acquired is None


def test_the_viewport_drops_the_acquisition_when_the_active_context_changes(qtbot):
    """An Acquired is a world point plus a per-context entity id.

    Crossing a group boundary invalidates both at once: the position no
    longer names the thing it was taken from, and the id may name a
    different edge in the context now underneath it.
    """
    from pluton.model.model import Model
    from pluton.viewport.inference import Acquired, AcquiredKind
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget(model=Model())
    qtbot.addWidget(widget)
    widget.inference._acquired = Acquired(
        kind=AcquiredKind.EDGE,
        position=np.zeros(3),
        direction=np.array([1.0, 0.0, 0.0]),
        entity_id=3,
    )

    widget.on_active_context_changed()

    assert widget.inference.acquired is None


def test_main_window_drops_the_acquisition_on_enter_and_exit(qtbot):
    """The wiring half: MainWindow is what SelectTool notifies."""
    from pluton.ui.main_window import MainWindow
    from pluton.viewport.inference import Acquired, AcquiredKind

    win = MainWindow()
    qtbot.addWidget(win)
    win._viewport.inference._acquired = Acquired(
        kind=AcquiredKind.VERTEX,
        position=np.zeros(3),
        direction=None,
        entity_id=1,
    )

    win._on_active_context_changed()

    assert win._viewport.inference.acquired is None

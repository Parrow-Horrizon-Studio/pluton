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


def test_an_active_lock_pins_the_result_to_the_locked_line():
    from pluton.viewport.camera import Camera
    from pluton.viewport.inference import InferenceState
    from pluton.viewport.snap_engine import SnapKind

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    state = InferenceState(now_ms=_FakeClock())
    state.toggle_axis_lock(2)  # blue / Z, through the origin

    out = state.apply_lock(_vertex_snap(), cam, (1280, 800), (700.0, 250.0))
    assert out.kind == SnapKind.AXIS_LOCK
    assert out.axis == 2
    # A point on the Z axis through the origin has x = y = 0.
    assert abs(float(out.world_position[0])) < 1e-4
    assert abs(float(out.world_position[1])) < 1e-4


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

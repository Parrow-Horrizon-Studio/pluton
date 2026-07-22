import numpy as np

from pluton.io.document_codec import CameraState
from pluton.viewport.camera import Camera
from pluton.viewport.view_animator import ViewAnimator


def _state(pos, target=(0.0, 0.0, 0.0)):
    return CameraState(position=tuple(pos), target=tuple(target),
                       up=(0.0, 0.0, 1.0), fov_y_deg=45.0)


def test_on_value_writes_interpolated_pose(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 2.0, 0.0))
    a._from, a._to = s0, s1
    a._on_value(1.0)
    assert np.allclose(cam.position, (0.0, 2.0, 0.0), atol=1e-6)


def test_start_finishes_on_target(qtbot):
    cam = Camera()
    ticks = []
    a = ViewAnimator(cam, on_tick=lambda: ticks.append(1))
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 1.0))
    with qtbot.waitSignal(a.finished, timeout=3000):
        a.start(s0, s1)
    assert np.allclose(cam.position, (0.0, 3.0, 1.0), atol=1e-5)
    assert not a.is_running
    assert ticks   # on_tick fired during the animation


def test_cancel_stops_before_target(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 0.0))
    a.start(s0, s1)
    a._on_value(0.5)          # advance partway deterministically
    a.cancel()
    assert not a.is_running
    # Camera is somewhere on the arc, not at the target:
    assert not np.allclose(cam.position, (0.0, 3.0, 0.0), atol=1e-3)


def test_retarget_midflight(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    a.start(_state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 0.0)))
    a._on_value(0.5)
    # Retarget from wherever the camera is now to a new destination:
    from_now = CameraState.from_camera(cam)
    a.start(from_now, _state((5.0, 0.0, 0.0)))
    assert a.is_running
    a.cancel()

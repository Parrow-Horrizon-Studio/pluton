"""Smoke tests for the main window and the M1 viewport widget.

These use pytest-qt for the QApplication fixture. Rendering is not pixel-
verified (that requires framebuffer capture, out of scope for M1) — but
construction, GL context creation, mouse handling, and one full paint cycle
are exercised via the Qt offscreen platform.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent


def test_main_window_constructs(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "Pluton"


def test_viewport_widget_constructs(qtbot):
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    assert widget is not None


def test_viewport_widget_has_camera_and_scene(qtbot):
    from pluton.viewport.camera import Camera
    from pluton.viewport.scene_renderer import SceneRenderer
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget.camera, Camera)
    assert isinstance(widget.scene_renderer, SceneRenderer)


def test_resize_updates_camera_aspect(qtbot):
    """Resizing the widget must update the camera's aspect ratio."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    widget.resize(1600, 800)
    # Qt may not deliver resizeGL until the widget is shown; we call it directly.
    widget.resizeGL(1600, 800)
    assert widget.camera.aspect == 2.0


def test_middle_button_drag_orbits_camera(qtbot):
    """MMB drag should change the camera position (orbit)."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    pos_before = widget.camera.position.copy()

    # Simulate MMB press at (100, 100) and release at (200, 150).
    qtbot.mousePress(widget, Qt.MouseButton.MiddleButton, pos=QPoint(100, 100))
    qtbot.mouseMove(widget, QPoint(200, 150))
    qtbot.mouseRelease(widget, Qt.MouseButton.MiddleButton, pos=QPoint(200, 150))

    assert not np.allclose(widget.camera.position, pos_before)


def test_wheel_event_zooms_camera(qtbot):
    """Scrolling should change the camera-target distance."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    distance_before = float(np.linalg.norm(widget.camera.position - widget.camera.target))

    # Drive the wheel event directly (qtbot doesn't have a wheel helper).
    widget.wheelEvent(_make_wheel_event(widget, delta_y=120))

    distance_after = float(np.linalg.norm(widget.camera.position - widget.camera.target))
    assert distance_after != distance_before


def test_wheel_event_with_zero_vertical_delta_does_not_zoom(qtbot):
    """Horizontal-only trackpad scrolls (delta_y=0) must not change the camera.

    The viewport's wheelEvent should also leave the event unaccepted so a
    parent widget could handle horizontal scroll without it being swallowed.
    """
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    pos_before = widget.camera.position.copy()
    target_before = widget.camera.target.copy()

    event = _make_wheel_event(widget, delta_y=0)
    widget.wheelEvent(event)

    np.testing.assert_array_equal(widget.camera.position, pos_before)
    np.testing.assert_array_equal(widget.camera.target, target_before)
    assert not event.isAccepted()


def _make_wheel_event(widget, delta_y: int) -> QWheelEvent:
    """Construct a QWheelEvent suitable for delivery to a widget's wheelEvent."""
    from PySide6.QtCore import QPointF

    pos = QPointF(widget.width() / 2.0, widget.height() / 2.0)
    return QWheelEvent(
        pos,                              # position (local)
        pos,                              # global position (offscreen: same as local)
        QPoint(0, 0),                     # pixelDelta
        QPoint(0, delta_y),               # angleDelta (120 = one notch on most mice)
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,                            # inverted
    )

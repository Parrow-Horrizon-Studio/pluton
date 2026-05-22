"""Smoke tests for the main window and the M1 viewport widget.

These use pytest-qt for the QApplication fixture. Rendering is not pixel-
verified (that requires framebuffer capture, out of scope for M1) — but
construction, GL context creation, mouse handling, and one full paint cycle
are exercised via the Qt offscreen platform.
"""

from __future__ import annotations

import numpy as np
import pytest
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
    """Scrolling should move the camera position along the zoom direction.

    Since the viewport always passes cursor_ndc to camera.zoom, both position
    and target move together (pure zoom, no rotation). The camera-to-target
    distance is preserved; it is camera.position that moves.
    """
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    pos_before = widget.camera.position.copy()

    # Drive the wheel event directly (qtbot doesn't have a wheel helper).
    widget.wheelEvent(_make_wheel_event(widget, delta_y=120))

    assert not np.allclose(widget.camera.position, pos_before), (
        "camera position should have moved after a wheel zoom"
    )


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


def test_keyboard_l_activates_line_tool(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)
    qtbot.keyClick(window, Qt.Key.Key_L)
    assert window._tool_manager.active is not None
    assert window._tool_manager.active.name == "Line"


def test_keyboard_r_activates_rectangle_tool(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)
    qtbot.keyClick(window, Qt.Key.Key_R)
    assert window._tool_manager.active.name == "Rectangle"


def test_esc_two_stage_cancel_then_deactivate(qtbot):
    """First ESC cancels gesture; second ESC deactivates the tool entirely."""
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # Activate the Line tool, start a gesture.
    qtbot.keyClick(window, Qt.Key.Key_L)
    assert window._tool_manager.active is not None
    # Drive a first click via the active tool directly (skipping the mouse
    # plumbing because the QOpenGLWidget doesn't render the offscreen ray).
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    active = window._tool_manager.active
    snap = SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="Grid",
    )
    active.on_mouse_press(None, snap)  # type: ignore[arg-type]
    assert active.has_active_gesture is True

    # First ESC: cancels the gesture, tool stays active.
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert window._tool_manager.active is not None  # tool still active
    assert active.has_active_gesture is False       # gesture cleared

    # Second ESC: deactivates the tool entirely.
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert window._tool_manager.active is None      # no active tool


def test_ctrl_n_clears_scene(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)
    # Seed the scene with a vertex.
    window._scene.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))
    assert len(list(window._scene.vertices_iter())) == 1
    qtbot.keyClick(window, Qt.Key.Key_N, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 0


def test_ctrl_z_undoes_completed_rectangle(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # Activate Rectangle, simulate two clicks via the tool directly.
    qtbot.keyClick(window, Qt.Key.Key_R)
    from pluton.viewport.snap_engine import SnapKind, SnapResult
    active = window._tool_manager.active

    def snap_at(x, y):
        return SnapResult(
            kind=SnapKind.GRID,
            world_position=np.array([x, y, 0.0], dtype=np.float32),
            axis=None,
            vertex_id=None,
            label="Grid",
        )

    active.on_mouse_press(None, snap_at(0.0, 0.0))  # type: ignore[arg-type]
    active.on_mouse_press(None, snap_at(3.0, 2.0))  # type: ignore[arg-type]
    assert len(list(window._scene.faces_iter())) == 1

    qtbot.keyClick(window, Qt.Key.Key_Z, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.faces_iter())) == 0

    qtbot.keyClick(window, Qt.Key.Key_Y, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.faces_iter())) == 1


def test_ctrl_n_is_undoable(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # Seed the scene with two vertices.
    window._scene.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))
    window._scene.add_vertex(np.array([3.0, 4.0, 0.0], dtype=np.float32))
    assert len(list(window._scene.vertices_iter())) == 2

    qtbot.keyClick(window, Qt.Key.Key_N, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 0

    qtbot.keyClick(window, Qt.Key.Key_Z, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 2

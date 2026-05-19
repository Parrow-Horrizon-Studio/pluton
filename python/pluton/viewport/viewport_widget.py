"""The 3D viewport widget — a QOpenGLWidget driving the M1 scene.

Owns a Camera (Python/numpy) and a SceneRenderer (GL resources). Translates
Qt mouse events into camera operations:

  * MMB drag         -> orbit
  * Shift + MMB drag -> pan
  * Scroll wheel     -> zoom toward cursor
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pluton.viewport.camera import Camera
from pluton.viewport.scene_renderer import SceneRenderer


class ViewportWidget(QOpenGLWidget):
    """The 3D viewport. Renders cube + grid + axes; orbits via mouse."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.camera = Camera()
        self.scene_renderer = SceneRenderer()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Receive mouse-tracking events without requiring a button press.
        self.setMouseTracking(True)

        self._last_mouse_pos: QPoint | None = None
        self._dragging_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._dragging_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    # --- GL lifecycle -----------------------------------------------------

    def initializeGL(self) -> None:
        self.scene_renderer.initialize_gl()

    def resizeGL(self, w: int, h: int) -> None:
        if self.scene_renderer._initialized:
            self.scene_renderer.resize(w, h)
        self.camera.aspect = float(w) / max(float(h), 1.0)

    def paintGL(self) -> None:
        self.scene_renderer.render(self.camera)

    # --- Mouse handling ---------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.MiddleButton
            self._dragging_modifiers = event.modifiers()
            self._last_mouse_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._dragging_button == Qt.MouseButton.MiddleButton
            and self._last_mouse_pos is not None
        ):
            current = event.position().toPoint()
            dx = float(current.x() - self._last_mouse_pos.x())
            dy = float(current.y() - self._last_mouse_pos.y())
            self._last_mouse_pos = current

            if self._dragging_modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.camera.pan(dx_pixels=dx, dy_pixels=dy)
            else:
                # Negate dy so dragging up tilts the view up (screen-y is inverted).
                self.camera.orbit(dx_pixels=dx, dy_pixels=-dy)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.NoButton
            self._last_mouse_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # angleDelta is in 1/8 of a degree; one notch = 120 units = 15 degrees.
        notches = event.angleDelta().y() / 120.0
        cursor = event.position()
        ndc = self._cursor_to_ndc(cursor.x(), cursor.y())
        self.camera.zoom(scroll_delta=notches, cursor_ndc=ndc)
        self.update()
        event.accept()

    # --- Helpers ----------------------------------------------------------

    def _cursor_to_ndc(self, x: float, y: float) -> np.ndarray:
        """Map widget-local cursor pixel to NDC [-1, +1] for x and y.

        y axis is flipped because screen-y grows downward while NDC-y grows up.
        """
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        nx = (2.0 * x / w) - 1.0
        ny = 1.0 - (2.0 * y / h)
        return np.array([nx, ny], dtype=np.float32)

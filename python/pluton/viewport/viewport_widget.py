"""The 3D viewport widget — drives the scene + snap engine + active tool.

Owns a Camera (Python/numpy) and a SceneRenderer (GL resources). Translates
Qt mouse events into:
  * MMB drag         -> camera orbit (unchanged from M1)
  * Shift + MMB drag -> camera pan   (unchanged from M1)
  * Scroll wheel     -> camera zoom  (unchanged from M1)
  * LMB / cursor-move (when a tool is active) -> snap + delegate to tool
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pluton.viewport.camera import Camera
from pluton.viewport.scene_renderer import SceneRenderer
from pluton.viewport.snap_engine import SnapEngine, SnapKind


class ViewportWidget(QOpenGLWidget):
    """The 3D viewport. Renders scene + active tool overlay; routes mouse events."""

    def __init__(self, model=None, tool_manager=None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.camera = Camera()
        self.scene_renderer = SceneRenderer()
        self.model = model
        self.tool_manager = tool_manager
        self.selection = None  # M4b — set by MainWindow (pluton.selection.Selection)
        self.snap_engine = SnapEngine()
        self._status_bar = None
        self._on_event_finished = None
        self._units_provider = None  # M7d — callable () -> pluton.units.Units (or None)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._last_mouse_pos: QPoint | None = None
        self._dragging_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._dragging_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    @property
    def scene(self):  # noqa: ANN201
        """The active scene from the model (delegates to model.active_scene)."""
        return self.model.active_scene if self.model is not None else None

    def set_status_bar(self, status_bar) -> None:  # noqa: ANN001
        self._status_bar = status_bar

    def set_event_finished_callback(self, fn) -> None:  # noqa: ANN001
        self._on_event_finished = fn

    def set_render_style(self, style) -> None:  # noqa: ANN001
        """Set the viewport display style and repaint (called from the View menu)."""
        self.scene_renderer.set_render_style(style)
        self.update()

    def set_units_provider(self, fn) -> None:
        """M7d: install a callable () -> pluton.units.Units, used by
        _paint_annotations to format dimension text. Set by MainWindow
        (mirrors set_status_bar / set_event_finished_callback)."""
        self._units_provider = fn

    # --- GL lifecycle -----------------------------------------------------

    def initializeGL(self) -> None:
        self.scene_renderer.initialize_gl()

    def resizeGL(self, w: int, h: int) -> None:
        self.scene_renderer.resize(w, h)
        self.camera.aspect = float(w) / max(float(h), 1.0)

    def paintGL(self) -> None:
        active = self.tool_manager.active if self.tool_manager is not None else None
        overlay = active.overlay() if active is not None else None
        self.scene_renderer.render(self.camera, self.model, overlay, self.selection)
        self._paint_annotations(overlay)

    # --- Mouse handling ---------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.MiddleButton
            self._dragging_modifiers = event.modifiers()
            self._last_mouse_pos = event.position().toPoint()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            active = self.tool_manager.active if self.tool_manager is not None else None
            if active is not None:
                snap = self._snap_for_event(event)
                active.on_mouse_press(event, snap)
                if self._status_bar is not None:
                    self._status_bar.set_snap(snap.label if snap.kind != SnapKind.NONE else "")
                if self._on_event_finished is not None:
                    self._on_event_finished()
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # Camera drag — unchanged from M1.
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
                self.camera.orbit(dx_pixels=dx, dy_pixels=-dy)
            self.update()
            event.accept()
            return

        # Tool delegation
        active = self.tool_manager.active if self.tool_manager is not None else None
        if active is not None:
            snap = self._snap_for_event(event)
            active.on_mouse_move(event, snap)
            if self._status_bar is not None:
                self._status_bar.set_snap(snap.label if snap.kind != SnapKind.NONE else "")
            if self._on_event_finished is not None:
                self._on_event_finished()
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            active = self.tool_manager.active if self.tool_manager is not None else None
            if active is not None:
                snap = self._snap_for_event(event)
                active.on_mouse_double_click(event, snap)
                if self._on_event_finished is not None:
                    self._on_event_finished()
                self.update()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.NoButton
            self._last_mouse_pos = None
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            active = self.tool_manager.active if self.tool_manager is not None else None
            if active is not None:
                snap = self._snap_for_event(event)
                active.on_mouse_release(event, snap)
                if self._on_event_finished is not None:
                    self._on_event_finished()
                self.update()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120.0
        if notches == 0:
            super().wheelEvent(event)
            return
        cursor = event.position()
        ndc = self._cursor_to_ndc(cursor.x(), cursor.y())
        self.camera.zoom(scroll_delta=notches, cursor_ndc=ndc)
        self.update()
        event.accept()

    # --- Helpers ----------------------------------------------------------

    def _cursor_to_ndc(self, x: float, y: float) -> np.ndarray:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        nx = (2.0 * x / w) - 1.0
        ny = 1.0 - (2.0 * y / h)
        return np.array([nx, ny], dtype=np.float32)

    def _snap_for_event(self, event: QMouseEvent):
        pos = event.position()
        active = self.tool_manager.active if self.tool_manager is not None else None
        anchor = active.anchor_or_none if active is not None else None
        wt = self.model.active_world_transform if self.model is not None else None
        return self.snap_engine.snap(
            (float(pos.x()), float(pos.y())),
            (self.width(), self.height()),
            self.camera,
            self.scene,
            anchor=anchor,
            world_transform=wt,
        )

    def _paint_annotations(self, overlay=None) -> None:
        """M7d: draw the active context's annotations in screen space, on top
        of the GL render. All layout is delegated to the pure draw_plan module
        (plan_annotation); this method only projects + paints via QPainter.

        `overlay`: Task 10b -- the active tool's ToolOverlay for this frame
        (the same object paintGL already asks the tool for and hands to
        scene_renderer.render() to draw edge/face/instance hover). Its
        `hovered_annotation_id` is threaded through to paint_annotation_plans
        so the hovered annotation gets a hover highlight too, without a new
        tool -> painter channel."""
        from PySide6.QtGui import QColor, QFont, QPainter

        from pluton.annotations.draw_plan import FONT_PX, plan_annotation
        from pluton.units import Units
        from pluton.viewport.annotation_painter import paint_annotation_plans

        if self.model is None:
            return
        annotations = self.model.active_context.annotations
        if not annotations:
            return
        width, height = self.width(), self.height()
        world = self.model.active_world_transform
        # Every other units provider in this codebase (wall/opening/roof options
        # bars) always yields a real Units object -- None is not a value
        # format_length expects, so default to Units() rather than None.
        units = self._units_provider() if self._units_provider is not None else Units()
        plans = []
        for ann in annotations:
            plan = plan_annotation(ann, world, self.camera, width, height, units)
            if plan is not None:
                plans.append(plan)
        if not plans:
            return
        selected_ids = set(self.selection.annotations) if self.selection is not None else set()
        hovered_id = overlay.hovered_annotation_id if overlay is not None else None
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            font = QFont()
            font.setPixelSize(int(FONT_PX))
            painter.setFont(font)
            paint_annotation_plans(
                painter,
                plans,
                QColor(30, 30, 30),
                selected_ids,
                QColor(51, 140, 242),
                hovered_id,
                # M4b/M4e hover blue (SelectTool._HOVER_EDGE_COLOR = (0.45, 0.70,
                # 1.00), the same colour edges/faces already hover-highlight
                # with), converted to 8-bit: round(0.45*255), round(0.70*255),
                # round(1.00*255).
                QColor(115, 178, 255),
            )
        finally:
            painter.end()

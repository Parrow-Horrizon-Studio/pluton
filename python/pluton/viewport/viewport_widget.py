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
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pluton.tools.select_tool import _HOVER_EDGE_COLOR, SelectTool
from pluton.units import Units, format_coordinates
from pluton.viewport.camera import Camera
from pluton.viewport.scene_renderer import SceneRenderer
from pluton.viewport.snap_engine import SnapEngine, SnapKind


class ViewportWidget(QOpenGLWidget):
    """The 3D viewport. Renders scene + active tool overlay; routes mouse events."""

    # M7.2 Task 14: emitted on a right-click release with the event's widget-local
    # pixel position; MainWindow resolves it into a right-click menu.
    context_menu_requested = Signal(int, int)

    def __init__(self, model=None, tool_manager=None, parent=None) -> None:
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
        self._camera_input_callback = None  # M7e — invoked when the user moves the camera

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._last_mouse_pos: QPoint | None = None
        self._dragging_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._dragging_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    @property
    def scene(self):
        """The active scene from the model (delegates to model.active_scene)."""
        return self.model.active_scene if self.model is not None else None

    def set_status_bar(self, status_bar) -> None:
        self._status_bar = status_bar

    def set_event_finished_callback(self, fn) -> None:
        self._on_event_finished = fn

    def set_render_style(self, style) -> None:
        """Set the viewport display style and repaint (called from the View menu)."""
        self.scene_renderer.set_render_style(style)
        self.update()

    def set_units_provider(self, fn) -> None:
        """M7d: install a callable () -> pluton.units.Units, used by
        _paint_annotations to format dimension text. Set by MainWindow
        (mirrors set_status_bar / set_event_finished_callback)."""
        self._units_provider = fn

    def set_camera_input_callback(self, fn) -> None:
        """M7e: install a zero-arg callable invoked when the user manipulates the
        camera (MMB orbit/pan, wheel zoom). MainWindow wires this to the view
        animator's cancel(), so a manual camera move interrupts a running tween."""
        self._camera_input_callback = fn

    def _notify_camera_input(self) -> None:
        if self._camera_input_callback is not None:
            self._camera_input_callback()

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
            self._notify_camera_input()
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
                # Coordinates ride the snap the tools already compute. That
                # ties the readout to "a tool is active" -- pressing Esc
                # blanks it (see MainWindow._on_escape's disarm branch).
                # Computing an inference point on every move regardless would
                # cost work on every event for a state users pass through,
                # not sit in.
                units = self._units_provider() if self._units_provider is not None else Units()
                self._status_bar.set_coordinates(format_coordinates(snap.world_position, units))
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
        self._notify_camera_input()
        cursor = event.position()
        ndc = self._cursor_to_ndc(cursor.x(), cursor.y())
        self.camera.zoom(scroll_delta=notches, cursor_ndc=ndc)
        self.update()
        event.accept()

    def contextMenuEvent(self, event) -> None:
        """M7.2 Task 14: emit a right-click resolution request for MainWindow.

        Suppressed while a tool is genuinely mid-gesture (a multi-click draw,
        or a click-drag in progress): right-click during one of those means
        "cancel", which Esc already handles, so this defers to that instead
        of popping a menu.

        SelectTool needs a narrower test than the others. Its
        has_active_gesture is also True for a merely non-empty selection --
        that is what lets Esc clear one -- and a right-click on an existing
        selection is the ordinary case this whole feature exists to serve,
        so treating that as "mid gesture" would swallow the most common
        right-click of all. But a live box-select drag *is* a gesture in the
        click sense, so is_box_selecting is what we consult for Select.
        """
        active = self.tool_manager.active if self.tool_manager is not None else None
        if active is not None and active.has_active_gesture:
            mid_gesture = active.is_box_selecting if isinstance(active, SelectTool) else True
            if mid_gesture:
                event.ignore()
                return
        position = event.pos()
        self.context_menu_requested.emit(position.x(), position.y())
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
        """M7d: draw every visible context's annotations in screen space, on
        top of the GL render, dimmed outside the active context exactly like
        geometry (#95 -- Task 13). All layout is delegated to the pure
        draw_plan module (collect_annotation_plans/plan_annotation); this
        method only projects + paints via QPainter.

        `overlay`: Task 10b -- the active tool's ToolOverlay for this frame
        (the same object paintGL already asks the tool for and hands to
        scene_renderer.render() to draw edge/face/instance hover). Its
        `hovered_annotation_id` is threaded through to paint_annotation_plans
        so the hovered annotation gets a hover highlight too, without a new
        tool -> painter channel.

        Picking is unaffected by this: pick_annotation and every tool's
        _pick_annotation still only ever see active_context.annotations, so
        dimmed (non-active-context) annotations are visible but not
        selectable/hoverable -- annotation ids are per-context, not globally
        unique, so a dimmed plan is never routed through the same
        paint_annotation_plans call as the selection/hover ids (which belong
        to the active context only); doing so could otherwise collide."""
        from PySide6.QtGui import QColor, QFont, QPainter

        from pluton.annotations.draw_plan import FONT_PX, collect_annotation_plans
        from pluton.viewport.annotation_painter import paint_annotation_plans
        from pluton.viewport.scene_renderer import _DIM_ALPHA_BLEND

        if self.model is None:
            return
        width, height = self.width(), self.height()
        # Every other units provider in this codebase (wall/opening/roof options
        # bars) always yields a real Units object -- None is not a value
        # format_length expects, so default to Units() rather than None.
        units = self._units_provider() if self._units_provider is not None else Units()
        plans = collect_annotation_plans(self.model, self.camera, width, height, units)
        if not plans:
            return
        active_plans = [plan for plan, dimmed in plans if not dimmed]
        dimmed_plans = [plan for plan, dimmed in plans if dimmed]

        color = QColor(30, 30, 30)
        dim_color = QColor(color)
        dim_color.setAlphaF(_DIM_ALPHA_BLEND)

        selected_ids = set(self.selection.annotations) if self.selection is not None else set()
        hovered_id = overlay.hovered_annotation_id if overlay is not None else None
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            font = QFont()
            font.setPixelSize(int(FONT_PX))
            painter.setFont(font)
            # Dimmed plans first (never selectable/hoverable -- picking stays
            # active-context-only), so the active-context plans draw on top.
            paint_annotation_plans(painter, dimmed_plans, dim_color, set(), dim_color, None, None)
            paint_annotation_plans(
                painter,
                active_plans,
                color,
                selected_ids,
                QColor(51, 140, 242),
                hovered_id,
                QColor(
                    round(_HOVER_EDGE_COLOR[0] * 255),
                    round(_HOVER_EDGE_COLOR[1] * 255),
                    round(_HOVER_EDGE_COLOR[2] * 255),
                ),
            )
        finally:
            painter.end()

"""The main application window — hosts the viewport, status bar, ToolManager, and CommandStack."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.commands import CommandStack
from pluton.commands.scene_commands import ClearSceneCommand
from pluton.document import DocumentSettings
from pluton.scene import Scene
from pluton.selection import Selection
from pluton.tools import (
    ArcTool,
    CircleTool,
    EraserTool,
    LineTool,
    MoveTool,
    PolygonTool,
    PushPullTool,
    RectangleTool,
    RotateTool,
    ScaleTool,
    SelectTool,
    TapeMeasureTool,
    ToolContext,
    ToolManager,
)
from pluton.ui.status_bar import StatusBar
from pluton.ui.value_control_box import ValueControlBox
from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Per-document settings (units etc.)
        self._doc = DocumentSettings()

        # Measurements box (VCB) — pure state, no Qt dependency.
        self._vcb = ValueControlBox()

        # Scene + tool manager + command stack
        self._scene = Scene()
        self._selection = Selection()
        self._command_stack = CommandStack()
        self._tool_manager = ToolManager()
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(PushPullTool())
        self._tool_manager.register(CircleTool())
        self._tool_manager.register(PolygonTool())
        self._tool_manager.register(ArcTool())
        self._tool_manager.register(SelectTool())
        self._tool_manager.register(EraserTool())
        self._tool_manager.register(MoveTool())
        self._tool_manager.register(RotateTool())
        self._tool_manager.register(ScaleTool())
        self._tool_manager.register(TapeMeasureTool())

        # Viewport + status bar (created BEFORE setting ToolContext so we can
        # wire the camera + widget_size_provider into the context).
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._viewport.selection = self._selection
        self._status_bar = StatusBar()

        # NOW we can build the ToolContext that includes the viewport refs.
        self._tool_manager.set_context(
            ToolContext(
                scene=self._scene,
                command_stack=self._command_stack,
                camera=self._viewport.camera,
                widget_size_provider=lambda: (self._viewport.width(), self._viewport.height()),
                selection=self._selection,
                units_provider=lambda: self._doc.units,
            )
        )

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewport, stretch=1)
        layout.addWidget(self._status_bar, stretch=0)
        self.setCentralWidget(container)

        self._viewport.set_status_bar(self._status_bar)
        self._viewport.set_event_finished_callback(self._refresh_status_text)

        # Clear selection after any undo or redo.
        self._command_stack.add_undo_listener(self._on_after_undo_redo)
        self._command_stack.add_redo_listener(self._on_after_undo_redo)

        # Keyboard shortcuts
        QShortcut(QKeySequence("L"), self, activated=lambda: self._activate("L"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self._activate("R"))
        QShortcut(QKeySequence("P"), self, activated=lambda: self._activate("P"))
        QShortcut(QKeySequence("C"), self, activated=lambda: self._activate("C"))
        QShortcut(QKeySequence("G"), self, activated=lambda: self._activate("G"))
        QShortcut(QKeySequence("A"), self, activated=lambda: self._activate("A"))
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=lambda: self._activate("Space"))
        QShortcut(QKeySequence("E"), self, activated=lambda: self._activate("E"))
        QShortcut(QKeySequence("M"), self, activated=lambda: self._activate("M"))
        QShortcut(QKeySequence("Q"), self, activated=lambda: self._activate("Q"))
        QShortcut(QKeySequence("S"), self, activated=lambda: self._activate("S"))
        QShortcut(QKeySequence("T"), self, activated=lambda: self._activate("T"))
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._on_delete_selection)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self._on_delete_selection)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self._on_tool_key(Qt.Key.Key_Up))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self._on_tool_key(Qt.Key.Key_Down))
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_finish_gesture)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._on_finish_gesture)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_clear_scene)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._on_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._on_redo)

        # Install the VCB event filter on the QApplication so it intercepts
        # key events (and ShortcutOverride) before any QShortcut fires.
        # Guard for None so headless unit tests without a QApplication still work.
        from PySide6.QtWidgets import QApplication
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

        # Units menu
        menubar = self.menuBar()
        self._units_menu = menubar.addMenu("Units")
        for label, fn in (
            ("Metric — m", lambda: self._set_units_metric("m")),
            ("Metric — cm", lambda: self._set_units_metric("cm")),
            ("Metric — mm", lambda: self._set_units_metric("mm")),
            ("Imperial — architectural", self._set_units_imperial),
        ):
            self._units_menu.addAction(label, fn)

    # --- Slots -----------------------------------------------------------

    def _refresh_status_text(self) -> None:
        active = self._tool_manager.active
        if self._vcb.active:
            self._status_bar.set_status(self._vcb.text + "▏")
        elif active is None:
            self._status_bar.set_status("")
        else:
            self._status_bar.set_status(active.status_text or "")
        self._refresh_selection_status()

    def _vcb_handle_key(self, event) -> bool:
        """Pure VCB key logic. Returns True if the key was consumed."""
        active_tool = self._tool_manager.active
        if active_tool is None:
            return False
        key = event.key()
        text = event.text()
        if self._vcb.active:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._vcb.text:
                    active_tool.apply_typed_value(self._vcb.text, self._doc.units)
                self._vcb.clear()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if key == Qt.Key.Key_Escape:
                self._vcb.clear()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if key == Qt.Key.Key_Backspace:
                self._vcb.backspace()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if text and text.isprintable() and text not in ("\r", "\n"):
                self._vcb.feed(text)
                self._refresh_status_text()
                self._viewport.update()
                return True
            return False
        # inactive: only a digit activates the box.
        if text in set("0123456789"):
            self._vcb.feed(text)
            self._refresh_status_text()
            self._viewport.update()
            return True
        return False

    def eventFilter(self, obj, event):  # noqa: N802
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            if self._vcb.active or (event.type() == QEvent.Type.KeyPress
                                    and event.text() in set("0123456789")):
                if self._vcb_handle_key(event):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._refresh_status_text()
            self._viewport.update()

    def _on_escape(self) -> None:
        active = self._tool_manager.active
        if active is None:
            return
        if active.has_active_gesture:
            from PySide6.QtGui import QKeyEvent

            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            active.on_key_press(ev)
        else:
            self._tool_manager.deactivate_current()
            self._status_bar.set_tool("")
            self._status_bar.set_snap("")
        self._refresh_status_text()
        self._viewport.update()

    def _on_finish_gesture(self) -> None:
        active = self._tool_manager.active
        if active is None or not active.has_active_gesture:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._refresh_status_text()
        self._viewport.update()

    def _on_tool_key(self, qt_key) -> None:  # noqa: ANN001
        """Forward a non-text key (e.g. Up/Down for polygon sides) to the active
        tool, but only while it has a live gesture (so arrows are inert otherwise)."""
        active = self._tool_manager.active
        if active is None or not active.has_active_gesture:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, qt_key, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._refresh_status_text()
        self._viewport.update()

    def _on_clear_scene(self) -> None:
        self._command_stack.execute(ClearSceneCommand(), self._scene)
        self._refresh_status_text()
        self._viewport.update()

    def _on_delete_selection(self) -> None:
        from pluton.commands import CompositeCommand
        from pluton.commands.scene_commands import RemoveEdgeCommand, RemoveFaceCommand

        sel = self._selection
        if sel.is_empty():
            return
        composite = CompositeCommand(name="Delete Selection")
        removed_faces: set[int] = set()
        for e_id in list(sel.edges):
            try:
                self._scene.edge(e_id)
            except KeyError:
                continue
            for f_id in self._scene.edge_faces(e_id):
                if f_id is None or f_id in removed_faces:
                    continue
                fc = RemoveFaceCommand(f_id)
                fc.do(self._scene)
                composite.children.append(fc)
                removed_faces.add(f_id)
            ec = RemoveEdgeCommand(e_id)
            ec.do(self._scene)
            composite.children.append(ec)
        for f_id in list(sel.faces):
            if f_id in removed_faces:
                continue
            try:
                self._scene.face_loop(f_id)
            except KeyError:
                continue
            fc = RemoveFaceCommand(f_id)
            fc.do(self._scene)
            composite.children.append(fc)
            removed_faces.add(f_id)
        if composite.children:
            self._command_stack.push_executed(composite)
        sel.clear()
        self._refresh_selection_status()
        self._viewport.update()

    def _refresh_selection_status(self) -> None:
        ne, nf = self._selection.counts()
        if ne == 0 and nf == 0:
            self._status_bar.set_selection("")
            return
        parts = []
        if ne:
            parts.append(f"{ne} edge" + ("s" if ne != 1 else ""))
        if nf:
            parts.append(f"{nf} face" + ("s" if nf != 1 else ""))
        self._status_bar.set_selection(", ".join(parts) + " selected")

    def _on_after_undo_redo(self) -> None:
        """Called by CommandStack listeners after every successful undo or redo."""
        self._selection.clear()
        self._refresh_selection_status()

    def _on_undo(self) -> None:
        if self._command_stack.undo(self._scene):
            self._refresh_status_text()
            self._viewport.update()

    def _on_redo(self) -> None:
        if self._command_stack.redo(self._scene):
            self._refresh_status_text()
            self._viewport.update()

    def _set_units_metric(self, unit: str) -> None:
        self._doc.set_metric(unit)
        self._refresh_status_text()
        self._viewport.update()

    def _set_units_imperial(self) -> None:
        self._doc.set_imperial()
        self._refresh_status_text()
        self._viewport.update()

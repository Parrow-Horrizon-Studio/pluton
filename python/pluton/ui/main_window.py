"""The main application window — hosts the viewport, status bar, ToolManager, and CommandStack."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.commands import CommandStack
from pluton.commands.scene_commands import ClearSceneCommand
from pluton.scene import Scene
from pluton.tools import LineTool, PushPullTool, RectangleTool, ToolContext, ToolManager
from pluton.ui.status_bar import StatusBar
from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Scene + tool manager + command stack
        self._scene = Scene()
        self._command_stack = CommandStack()
        self._tool_manager = ToolManager()
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(PushPullTool())

        # Viewport + status bar (created BEFORE setting ToolContext so we can
        # wire the camera + widget_size_provider into the context).
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._status_bar = StatusBar()

        # NOW we can build the ToolContext that includes the viewport refs.
        self._tool_manager.set_context(
            ToolContext(
                scene=self._scene,
                command_stack=self._command_stack,
                camera=self._viewport.camera,
                widget_size_provider=lambda: (self._viewport.width(), self._viewport.height()),
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

        # Keyboard shortcuts
        QShortcut(QKeySequence("L"), self, activated=lambda: self._activate("L"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self._activate("R"))
        QShortcut(QKeySequence("P"), self, activated=lambda: self._activate("P"))
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_clear_scene)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._on_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._on_redo)

    # --- Slots -----------------------------------------------------------

    def _refresh_status_text(self) -> None:
        active = self._tool_manager.active
        if active is None:
            self._status_bar.set_status("")
            return
        self._status_bar.set_status(active.status_text or "")

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

    def _on_clear_scene(self) -> None:
        self._command_stack.execute(ClearSceneCommand(), self._scene)
        self._refresh_status_text()
        self._viewport.update()

    def _on_undo(self) -> None:
        if self._command_stack.undo(self._scene):
            self._refresh_status_text()
            self._viewport.update()

    def _on_redo(self) -> None:
        if self._command_stack.redo(self._scene):
            self._refresh_status_text()
            self._viewport.update()

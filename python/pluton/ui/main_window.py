"""The main application window — hosts the viewport, status bar, and ToolManager."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.scene import Scene
from pluton.tools import LineTool, RectangleTool, ToolContext, ToolManager
from pluton.ui.status_bar import StatusBar
from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Scene + tool manager
        self._scene = Scene()
        self._tool_manager = ToolManager()
        self._tool_manager.set_context(ToolContext(scene=self._scene))
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())

        # Viewport + status bar in a vertical layout
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._status_bar = StatusBar()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewport, stretch=1)
        layout.addWidget(self._status_bar, stretch=0)
        self.setCentralWidget(container)

        # Wire the status bar to ViewportWidget updates
        self._viewport.set_status_bar(self._status_bar)

        # Keyboard shortcuts (work regardless of focus)
        QShortcut(QKeySequence("L"), self, activated=lambda: self._activate("L"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self._activate("R"))
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_clear_scene)

    # --- Slots -----------------------------------------------------------

    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._viewport.update()

    def _on_escape(self) -> None:
        # Forward to active tool's on_key_press; if no tool, no-op.
        active = self._tool_manager.active
        if active is None:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._viewport.update()

    def _on_clear_scene(self) -> None:
        self._scene.clear()
        self._viewport.update()

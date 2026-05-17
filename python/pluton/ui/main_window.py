"""The main application window."""

from PySide6.QtWidgets import QMainWindow

from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        self._viewport = ViewportWidget(self)
        self.setCentralWidget(self._viewport)

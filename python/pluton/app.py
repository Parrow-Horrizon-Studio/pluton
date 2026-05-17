"""Pluton application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from pluton import __version__
from pluton.ui.main_window import MainWindow


def main() -> int:
    """Application entry point. Returns process exit code."""
    print(f"Pluton {__version__}")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

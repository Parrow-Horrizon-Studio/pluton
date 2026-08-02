"""Pluton application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from pluton import __version__
from pluton.ui.main_window import MainWindow
from pluton.ui.window_state import APPLICATION_NAME, ORGANIZATION_NAME


def main() -> int:
    """Application entry point. Returns process exit code."""
    print(f"Pluton {__version__}")
    app = QApplication(sys.argv)
    # QSettings keys off these; without them it has no per-application store.
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

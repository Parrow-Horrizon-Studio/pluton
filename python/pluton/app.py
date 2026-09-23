"""Pluton application entry point."""

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from pluton import __version__
from pluton.ui import preferences
from pluton.ui.main_window import MainWindow
from pluton.ui.theme import apply_theme, theme_for_name
from pluton.ui.window_state import APPLICATION_NAME, ORGANIZATION_NAME


def main() -> int:
    """Application entry point. Returns process exit code."""
    print(f"Pluton {__version__}")
    app = QApplication(sys.argv)
    # QSettings keys off these; without them it has no per-application store.
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)

    # Before MainWindow() so the first icon build already uses the right
    # palette (M7.7, #101).
    apply_theme(app, theme_for_name(preferences.read_theme(QSettings())))

    window = MainWindow()
    window.show()

    # After show(), so the dialog is modal over a real window rather than over
    # nothing, and so there is no second "no document yet" code path: the
    # template applies to the live document the window already built.
    if preferences.read_show_welcome(QSettings()):
        window.show_welcome_dialog()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

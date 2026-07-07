"""Shared pytest fixtures and configuration."""

import os

import pytest


# Ensure Qt uses the offscreen platform in CI / headless environments.
# This must run BEFORE QApplication is created (i.e., before any pytest-qt fixture).
if os.environ.get("CI") == "true" or os.environ.get("QT_QPA_PLATFORM"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _no_blocking_close_dialog(monkeypatch):
    """Keep MainWindow's unsaved-changes modal from hanging test teardown.

    pytest-qt closes every qtbot-tracked widget at teardown. MainWindow.closeEvent
    (M6a) prompts via a modal QMessageBox when the document is dirty; in a headless
    run nothing dismisses it, so `.exec()` would block the whole suite forever.
    Default the prompt to "discard" for every test so a teardown-close never blocks.
    Tests that actually exercise the guard override `_prompt_discard` on the window
    instance, which shadows this class-level patch.
    """
    try:
        from pluton.ui.main_window import MainWindow
    except Exception:
        return
    monkeypatch.setattr(MainWindow, "_prompt_discard", lambda self: "discard", raising=False)

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from pluton.commands.scene_commands import ClearSceneCommand
from pluton.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _draw_something(win):
    scene = win._model.active_scene
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)


def test_command_execution_marks_dirty_and_titles(app):
    win = MainWindow()
    assert win._doc_controller.dirty is False
    assert win.windowTitle() == "Untitled — Pluton"
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    assert win._doc_controller.dirty is True
    assert win.windowTitle() == "Untitled* — Pluton"


def test_save_as_writes_file_and_marks_clean(app, tmp_path, monkeypatch):
    win = MainWindow()
    _draw_something(win)
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    assert win._doc_controller.dirty is True

    target = tmp_path / "out.pluton"
    monkeypatch.setattr(win, "_prompt_save_path", lambda: str(target))
    assert win._on_file_save_as() is True
    assert target.exists()
    assert win._doc_controller.dirty is False
    assert win.windowTitle() == "out.pluton — Pluton"


def test_guard_cancel_aborts(app):
    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "cancel"
    assert win._confirm_discard_if_dirty() is False


def test_guard_discard_proceeds(app):
    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "discard"
    assert win._confirm_discard_if_dirty() is True


def test_file_menu_has_actions(app):
    win = MainWindow()
    labels = [a.text() for a in win._file_menu.actions() if a.text()]
    assert any("New" in t for t in labels)
    assert any("Open" in t for t in labels)
    assert any("Save" in t for t in labels)


def test_close_event_ignored_when_guard_cancels(app):
    from PySide6.QtGui import QCloseEvent

    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)  # dirty
    win._prompt_discard = lambda: "cancel"
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted()  # guard refused the close, window stays open


def test_close_event_accepted_when_clean(app):
    from PySide6.QtGui import QCloseEvent

    win = MainWindow()
    assert win._doc_controller.dirty is False
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()  # nothing to lose, closes without prompting

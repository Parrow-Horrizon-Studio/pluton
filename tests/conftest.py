"""Shared pytest fixtures and configuration."""

import os

import pytest
from pluton.commands.group_commands import MakeGroupCommand
from pluton.model.model import Model

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


@pytest.fixture
def model_factory():
    """Build a fresh, empty Model."""

    def make() -> Model:
        return Model()

    return make


@pytest.fixture
def group_factory():
    """Wrap every live entity in the model's active context into one new group.

    Mirrors the MakeGroupCommand construction used by tests/test_group_commands.py
    and tests/test_make_group_tag_inherit.py: the command takes the parent
    Definition plus explicit vertex/edge/face id lists, and do(model) is called
    directly (no CommandStack -- these are test fixtures building state, not
    undoable user actions).
    """

    def make(model: Model):
        context = model.active_context
        scene = context.mesh
        vertex_ids = [v.id for v in scene.vertices_iter()]
        edge_ids = [e.id for e in scene.edges_iter()]
        face_ids = [f.id for f in scene.faces_iter()]
        command = MakeGroupCommand(context, vertex_ids, edge_ids, face_ids)
        command.do(model)
        return command.created_instance

    return make

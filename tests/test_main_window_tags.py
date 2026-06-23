from __future__ import annotations

import numpy as np
import pytest
from pluton.ui.main_window import MainWindow
from pluton.ui.tags_dock import TagsDock


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_has_tags_dock(win):
    assert isinstance(win._tags_dock, TagsDock)


def test_view_menu_has_tags_toggle(win):
    assert win._tags_dock_action in win._view_menu.actions()


def test_active_tag_tracks_dock(win):
    walls = win._model.tags.add("Walls")
    win._tags_dock._rebuild()
    win._tags_dock.set_active(walls.id)
    assert win._active_tag_id == walls.id


def test_assign_tags_selected_instances(win):
    s = win._model.active_scene
    v = [s.add_vertex(np.array([0.0, 0.0, 0.0])),
         s.add_vertex(np.array([1.0, 0.0, 0.0])),
         s.add_vertex(np.array([0.0, 1.0, 0.0]))]
    f = s.add_face_from_loop(v)
    win._selection.replace(faces=[f])
    win._on_make_group()                          # groups the face; selects the new instance
    walls = win._model.tags.add("Walls")
    win._active_tag_id = walls.id
    win._on_assign_tag()
    inst_id = next(iter(win._selection.instances))
    inst = next(i for i in win._model.active_context.children if i.id == inst_id)
    assert inst.tag_id == walls.id


def test_new_group_inherits_active_tag(win):
    walls = win._model.tags.add("Walls")
    win._active_tag_id = walls.id
    s = win._model.active_scene
    v = [s.add_vertex(np.array([0.0, 0.0, 0.0])),
         s.add_vertex(np.array([1.0, 0.0, 0.0])),
         s.add_vertex(np.array([0.0, 1.0, 0.0]))]
    f = s.add_face_from_loop(v)
    win._selection.replace(faces=[f])
    win._on_make_group()
    inst_id = next(iter(win._selection.instances))
    inst = next(i for i in win._model.active_context.children if i.id == inst_id)
    assert inst.tag_id == walls.id

"""The Outliner drives the model and follows the viewport (M7.3 Task 10)."""

from __future__ import annotations

import numpy as np
from pluton.ui.outliner_tree import OutlinerTree


def _square(window):
    scene = window._model.active_context.mesh
    v = [
        scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32)),
    ]
    scene.add_face_from_loop(v)


def _group(window):
    window._on_select_all()
    window._on_make_group()
    window._selection.clear()
    return window._model.root.children[-1]


def test_the_window_owns_a_properties_dock_and_an_outliner(main_window):
    assert main_window._properties_dock is not None
    assert isinstance(main_window._outliner, OutlinerTree)
    assert main_window._properties_dock.outliner() is main_window._outliner


def test_making_a_group_adds_an_outliner_row(main_window):
    _square(main_window)
    assert main_window._outliner.item_for(0) is None

    instance = _group(main_window)

    assert main_window._outliner.item_for(instance.id) is not None


def test_undo_removes_the_row_again(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._command_stack.undo()

    assert main_window._outliner.item_for(instance.id) is None


def test_clicking_a_row_selects_that_instance(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._outliner.instance_clicked.emit(instance.id)

    assert main_window._selection.instances == {instance.id}


def test_clicking_a_nested_row_re_roots_the_active_path(main_window):
    # Selection is only meaningful inside the active context, so selecting a
    # nested row must move the context to that row's parent chain -- otherwise
    # the id lands in a selection the active context cannot see.
    #
    # Two back-to-back _group() calls do NOT nest: _on_make_group bails out
    # unless edges or faces (not instances) are selected, so a second call
    # with only the first group's instance selected creates nothing and
    # returns that SAME instance. Genuine nesting requires entering the
    # first group and adding fresh geometry before grouping again -- the
    # same recipe tests/test_outliner_rows.py uses for its nesting cases.
    _square(main_window)
    outer = _group(main_window)
    main_window._model.enter(outer)
    _square(main_window)
    main_window._on_select_all()
    main_window._on_make_group()
    inner = main_window._model.active_context.children[-1]
    main_window._selection.clear()
    main_window._model.exit_one()

    main_window._outliner.instance_clicked.emit(inner.id)

    assert [i.id for i in main_window._model.active_path] == [outer.id]
    assert main_window._selection.instances == {inner.id}


def test_clicking_a_root_level_row_exits_back_to_the_root(main_window):
    _square(main_window)
    inner = _group(main_window)
    outer = _group(main_window)
    main_window._model.active_path = [outer]

    main_window._outliner.instance_clicked.emit(outer.id)

    assert main_window._model.active_path == []
    del inner


def test_double_clicking_a_row_enters_that_instance(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._outliner.instance_activated.emit(instance.id)

    assert [i.id for i in main_window._model.active_path] == [instance.id]


def test_the_eye_toggle_hides_through_an_undoable_command(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._outliner.hide_toggled.emit(instance.id, True)

    assert instance.hidden is True
    main_window._command_stack.undo()
    assert instance.hidden is False


def test_renaming_a_row_goes_through_an_undoable_command(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._outliner.rename_requested.emit(instance.id, "North Wing")

    assert instance.name == "North Wing"
    main_window._command_stack.undo()
    assert instance.name == ""


def test_a_viewport_selection_highlights_the_row(main_window):
    _square(main_window)
    instance = _group(main_window)

    main_window._selection.replace(instances=[instance.id])
    main_window._refresh_selection_status()

    assert main_window._outliner.item_for(instance.id).isSelected()


def test_selection_sync_does_not_rebuild_the_tree(main_window):
    # Rows must not be rebuilt on selection change: it fires many times a
    # second during a box-select drag.
    _square(main_window)
    instance = _group(main_window)
    rebuilds = []
    original = main_window._outliner.set_rows
    main_window._outliner.set_rows = lambda *a, **k: (rebuilds.append(1), original(*a, **k))[1]

    main_window._selection.replace(instances=[instance.id])
    main_window._refresh_selection_status()

    assert rebuilds == []


def test_a_stale_row_id_is_ignored(main_window):
    # An id that no longer resolves must be a no-op, not a crash.
    _square(main_window)
    _group(main_window)

    main_window._outliner.instance_clicked.emit(9999)
    main_window._outliner.instance_activated.emit(9999)
    main_window._outliner.hide_toggled.emit(9999, True)
    main_window._outliner.rename_requested.emit(9999, "x")

    assert main_window._model.active_path == []

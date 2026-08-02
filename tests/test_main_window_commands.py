"""The M7.2 command handlers (Task 9).

These run against a real MainWindow, so they need pytest-qt. Mirror the
fixture style already used by tests/test_main_window_scenes.py.
"""

from __future__ import annotations

import numpy as np


def test_select_all_selects_the_active_context(qtbot, main_window_with_square):
    window = main_window_with_square
    window._selection.clear()

    window._on_select_all()

    assert len(window._selection.edges) == 4
    assert len(window._selection.faces) == 1


def test_select_none_clears_the_selection(qtbot, main_window_with_square):
    window = main_window_with_square
    window._on_select_all()
    assert not window._selection.is_empty()

    window._on_select_none()

    assert window._selection.is_empty()


def test_select_all_on_an_empty_model_is_a_no_op(qtbot, main_window):
    main_window._on_select_all()
    assert main_window._selection.is_empty()


def test_zoom_extents_moves_the_camera_to_frame_the_model(qtbot, main_window_with_square):
    window = main_window_with_square
    camera = window._viewport.camera
    before = np.array(camera.position, dtype=float).copy()

    window._on_zoom_extents()

    after = np.array(camera.position, dtype=float)
    assert not np.allclose(before, after)
    # The target lands on the square's centre (0.5, 0.5, 0).
    assert np.allclose(np.array(camera.target, dtype=float), [0.5, 0.5, 0.0], atol=1e-4)


def test_zoom_extents_preserves_the_view_direction(qtbot, main_window_with_square):
    window = main_window_with_square
    camera = window._viewport.camera
    before = np.array(camera.target, dtype=float) - np.array(camera.position, dtype=float)
    before /= np.linalg.norm(before)

    window._on_zoom_extents()

    after = np.array(camera.target, dtype=float) - np.array(camera.position, dtype=float)
    after /= np.linalg.norm(after)
    assert np.allclose(before, after, atol=1e-5)


def test_zoom_extents_on_an_empty_model_leaves_the_camera_alone(qtbot, main_window):
    camera = main_window._viewport.camera
    before = np.array(camera.position, dtype=float).copy()

    main_window._on_zoom_extents()

    assert np.allclose(before, np.array(camera.position, dtype=float))


def test_close_group_exits_one_level(qtbot, main_window_with_group):
    window = main_window_with_group
    window._model.enter(window._model.active_context.children[-1])
    depth = len(window._model.active_path)

    window._on_close_group()

    assert len(window._model.active_path) == depth - 1


def test_close_group_at_the_root_is_a_no_op(qtbot, main_window):
    main_window._on_close_group()
    assert main_window._model.active_path == []


def test_edit_group_enters_the_selected_instance(qtbot, main_window_with_group):
    window = main_window_with_group
    instance = window._model.active_context.children[-1]
    window._selection.clear()
    window._selection.toggle_instance(instance.id)

    window._on_edit_group()

    assert window._model.active_path[-1] is instance


def test_edit_group_with_nothing_selected_is_a_no_op(qtbot, main_window):
    main_window._selection.clear()
    main_window._on_edit_group()
    assert main_window._model.active_path == []

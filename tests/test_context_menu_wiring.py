"""Right-click resolution and menu construction (M7.2 Task 14)."""

from __future__ import annotations

import numpy as np

from pluton.ui.actions import ContextTarget
from pluton.ui.context_menu import build_context_menu


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_empty_space_menu_is_built_from_the_registry(qtbot, main_window):
    menu = build_context_menu(main_window, ContextTarget.EMPTY, None)
    assert "Select All" in _labels(menu)
    assert "Zoom Extents" in _labels(menu)


def test_close_group_is_disabled_at_the_root(qtbot, main_window):
    menu = build_context_menu(main_window, ContextTarget.EMPTY, None)
    action = next(a for a in menu.actions() if a.text() == "Close Group")
    assert not action.isEnabled()


def test_instance_menu_carries_the_assign_tag_submenu(qtbot, main_window_with_group):
    window = main_window_with_group
    instance = window._model.active_context.children[-1]
    window._selection.clear()
    window._selection.toggle_instance(instance.id)

    menu = build_context_menu(window, ContextTarget.INSTANCE, instance.id)

    assign = next(a for a in menu.actions() if a.text() == "Assign Tag")
    assert assign.menu() is not None
    # One entry per tag in the library, including the Untagged sentinel.
    assert len(assign.menu().actions()) == len(window._model.tags.tags())


def test_face_menu_has_no_assign_tag_submenu(qtbot, main_window_with_square):
    # M5c is instances-only tagging (#69).
    menu = build_context_menu(main_window_with_square, ContextTarget.FACE, None)
    assert "Assign Tag" not in _labels(menu)


def test_menu_actions_are_the_same_objects_as_the_menu_bar_uses(qtbot, main_window):
    menu = build_context_menu(main_window, ContextTarget.EMPTY, None)
    action = next(a for a in menu.actions() if a.text() == "Select All")
    assert action is main_window._actions["edit_select_all"]


def test_right_click_on_empty_space_leaves_the_selection_alone(qtbot, main_window_with_square):
    window = main_window_with_square
    window._on_select_all()
    before = set(window._selection.faces)

    window._on_context_menu_requested(-100, -100)  # off-model

    assert set(window._selection.faces) == before


def test_viewport_exposes_a_context_menu_signal(qtbot, main_window):
    assert hasattr(main_window._viewport, "context_menu_requested")


def test_reenabling_after_the_menu_closes_restores_the_menu_bar(qtbot, main_window, monkeypatch):
    """The point of this task: build_context_menu disables entries on the
    SAME QAction objects the menu bar holds. If MainWindow only re-enabled
    the ones it happened to disable -- or skipped re-enabling on some early
    return -- a disabled context entry would leave the matching menu-bar
    item permanently greyed out. Exercise the real exec_menu=True path (the
    one the live signal connection uses) with QMenu.exec monkeypatched to a
    no-op so the test never enters a modal loop, then assert the menu-bar
    action came back enabled.
    """
    window = main_window
    # Replace the pop-the-menu step on the instance, NOT QMenu.exec itself:
    # PySide6 dispatches QMenu.exec straight to C++, so patching the class is
    # accepted silently but has no effect and the real modal loop runs --
    # which under the offscreen platform CI uses never returns.
    shown: list[object] = []
    monkeypatch.setattr(
        window, "_exec_context_menu", lambda menu, pos: shown.append(menu)
    )
    close_group = window._actions["edit_close_group"]

    # Confirm build_context_menu really does disable it at the root (same
    # fact test_close_group_is_disabled_at_the_root checks) before trusting
    # that the handler's re-enable pass below did any real work.
    build_context_menu(window, ContextTarget.EMPTY, None)
    assert not close_group.isEnabled()

    window._on_context_menu_requested(0, 0, exec_menu=True)  # empty space at root

    assert shown, "the exec_menu=True path did not reach _exec_context_menu"
    assert close_group.isEnabled()


def test_right_click_on_an_already_selected_face_keeps_the_multi_selection(
    qtbot, main_window, monkeypatch
):
    """Right-clicking one of several selected faces must not collapse the
    selection to just that face -- SketchUp's behaviour, and the guard
    _selection_contains/_select_only exist to preserve."""
    import pluton.ui.context_menu as context_menu_module

    window = main_window
    scene = window._model.active_context.mesh
    v1 = [
        scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32)),
    ]
    face_a = scene.add_face_from_loop(v1)
    v2 = [
        scene.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([3.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([3.0, 1.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([2.0, 1.0, 0.0], dtype=np.float32)),
    ]
    face_b = scene.add_face_from_loop(v2)
    window._selection.replace(faces=[face_a, face_b])

    monkeypatch.setattr(
        context_menu_module,
        "resolve_context_target",
        lambda *args, **kwargs: (ContextTarget.FACE, face_a),
    )

    window._on_context_menu_requested(0, 0)

    assert window._selection.faces == {face_a, face_b}

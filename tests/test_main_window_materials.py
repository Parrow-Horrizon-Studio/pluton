from __future__ import annotations

import pytest
from pluton.ui.main_window import MainWindow
from pluton.ui.materials_dock import MaterialsDock


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_main_window_has_materials_dock(win):
    assert isinstance(win._materials_dock, MaterialsDock)


def test_paint_tool_registered_under_b(win):
    assert win._tool_manager.activate_by_shortcut("B")
    assert win._tool_manager.active.name == "Paint"


def test_tool_context_exposes_material_hooks(win):
    ctx = win._tool_manager._ctx  # installed ToolContext (ToolManager stores it as _ctx)
    assert ctx.active_material_provider is not None
    assert ctx.set_active_material is not None
    # provider returns the model's active material (Default at startup)
    assert ctx.active_material_provider().id == win._model.materials.DEFAULT_ID


def test_dock_selection_updates_active_material_id(win):
    brick = next(m for m in win._model.materials.materials() if m.name == "Brick Red")
    win._materials_dock._on_pick(brick.id)
    assert win._active_material_id == brick.id


def test_paint_tool_status_text_refreshes_without_error(win):
    # Regression (M5b): PaintTool.status_text was missing its @property, so
    # `active.status_text or ""` stored the *bound method* in the status bar,
    # raising "sequence item …: expected str instance, method found" from the
    # status-bar join on every mouse move. It must resolve to a plain string.
    import inspect

    from pluton.tools.paint_tool import PaintTool

    assert isinstance(inspect.getattr_static(PaintTool, "status_text"), property)
    win._activate("B")  # activates Paint AND sets the status-bar tool name
    win._refresh_status_text()  # would raise TypeError before the fix
    text = win._status_bar.text()
    assert isinstance(text, str)
    assert "Paint" in text


def test_view_menu_has_materials_dock_toggle(win):
    # The toggle action is registered in the View menu and controls the dock.
    assert win._materials_dock_action in win._view_menu.actions()
    assert win._materials_dock_action.isCheckable()
    # Closing the dock (== its close button) unchecks the action.
    # (Use isHidden()/action-checked rather than isVisible(), which is always
    # False here because the offscreen top-level window is never shown.)
    win._materials_dock.hide()
    assert win._materials_dock.isHidden()
    assert not win._materials_dock_action.isChecked()
    # Triggering the menu action re-shows the dock.
    win._materials_dock_action.trigger()
    assert not win._materials_dock.isHidden()
    assert win._materials_dock_action.isChecked()

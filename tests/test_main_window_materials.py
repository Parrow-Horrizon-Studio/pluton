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

from __future__ import annotations

from pluton.tools.roof_tool import RoofTool
from pluton.ui.main_window import MainWindow


def test_roof_tool_registered_with_o(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("O")
    assert isinstance(w._tool_manager.active, RoofTool)


def test_o_key_shortcut_registered(qtbot):
    from PySide6.QtGui import QShortcut

    w = MainWindow()
    qtbot.addWidget(w)
    keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
    assert "O" in keys


def test_roof_options_bar_visible_only_for_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("O")
    w._refresh_tool_options()
    assert w._roof_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")   # line tool
    w._refresh_tool_options()
    assert not w._roof_options_bar.isVisibleTo(w)

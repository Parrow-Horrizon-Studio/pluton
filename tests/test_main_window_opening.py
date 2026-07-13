from __future__ import annotations

from pluton.tools.opening_tool import DoorWindowTool
from pluton.ui.main_window import MainWindow


def test_doorwindow_tool_registered_with_d(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("D")
    assert isinstance(w._tool_manager.active, DoorWindowTool)


def test_opening_options_bar_visible_only_for_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("D")
    w._refresh_tool_options()
    assert w._opening_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")   # line tool
    w._refresh_tool_options()
    assert not w._opening_options_bar.isVisibleTo(w)


def test_d_key_shortcut_registered(qtbot):
    from PySide6.QtGui import QShortcut

    w = MainWindow()
    qtbot.addWidget(w)
    keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
    assert "D" in keys

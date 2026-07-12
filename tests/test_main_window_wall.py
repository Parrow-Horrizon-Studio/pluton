"""MainWindow integration: WallTool registered under W + options bar (M7a, Task 5)."""

from __future__ import annotations

from pluton.tools.wall_tool import WallTool
from pluton.ui.main_window import MainWindow


def test_wall_tool_registered_with_w(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("W")
    assert isinstance(w._tool_manager.active, WallTool)


def test_options_bar_visible_only_for_wall(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("W")
    w._refresh_tool_options()                 # the hook MainWindow calls on tool switch
    assert w._wall_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")  # line tool
    w._refresh_tool_options()
    assert not w._wall_options_bar.isVisibleTo(w)

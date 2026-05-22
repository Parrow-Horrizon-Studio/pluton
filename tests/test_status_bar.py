"""Unit tests for the bottom status bar widget."""

from __future__ import annotations


def test_status_bar_starts_empty(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    assert bar.text() == ""


def test_status_bar_shows_tool_only_when_no_snap(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("")
    assert bar.text() == "Line · —"


def test_status_bar_shows_tool_and_snap(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("Endpoint")
    assert bar.text() == "Line · Endpoint"


def test_status_bar_clear_tool_blanks_everything(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("Grid")
    bar.set_tool("")  # no active tool
    assert bar.text() == ""

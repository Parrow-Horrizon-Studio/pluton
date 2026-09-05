"""`pluton.tools` re-exports concrete tool classes lazily (PEP 562
`__getattr__`) instead of importing them eagerly at package-init time, so
that a Qt-free submodule such as `pluton.tools.sweep_support` does not pull
in PySide6 merely because Python runs the package's `__init__.py` before the
submodule itself (M7.4 Task 3).
"""

from __future__ import annotations

import pytest

import pluton.tools as tools_pkg

# Every name the package advertises, and the module each must come from.
_EXPECTED = {
    "ArcTool": "pluton.tools.arc_tool",
    "CircleTool": "pluton.tools.circle_tool",
    "EraserTool": "pluton.tools.erase_tool",
    "LineTool": "pluton.tools.line_tool",
    "MoveTool": "pluton.tools.move_tool",
    "PolygonTool": "pluton.tools.polygon_tool",
    "PushPullTool": "pluton.tools.push_pull_tool",
    "RectangleTool": "pluton.tools.rectangle_tool",
    "RotateTool": "pluton.tools.rotate_tool",
    "ScaleTool": "pluton.tools.scale_tool",
    "SelectTool": "pluton.tools.select_tool",
    "TapeMeasureTool": "pluton.tools.tape_measure_tool",
    "Tool": "pluton.tools.tool",
    "ToolContext": "pluton.tools.tool",
    "ToolManager": "pluton.tools.tool_manager",
    "ToolOverlay": "pluton.tools.tool",
}


def test_all_matches_the_expected_export_set():
    assert set(tools_pkg.__all__) == set(_EXPECTED)


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_each_public_name_resolves_to_the_right_class(name: str):
    import importlib

    resolved = getattr(tools_pkg, name)
    expected_module = importlib.import_module(_EXPECTED[name])
    assert resolved is getattr(expected_module, name)


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError):
        tools_pkg.NotARealTool


def test_dir_reports_the_public_names():
    assert sorted(dir(tools_pkg)) == sorted(_EXPECTED)

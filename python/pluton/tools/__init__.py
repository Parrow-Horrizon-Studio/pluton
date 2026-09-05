"""Tool framework: Tool ABC, ToolOverlay, ToolManager, and concrete tools.

M2 ships LineTool and RectangleTool against this framework. M3's PushPullTool
and M4's full roster plug into the same shapes.

Concrete tool classes are re-exported lazily (PEP 562 module `__getattr__`)
rather than imported eagerly at package-init time. Most tool modules import
PySide6 for event types; importing any of them unconditionally here meant
importing ANY submodule of `pluton.tools` — including a Qt-free one, such as
`pluton.tools.sweep_support` — transitively loaded PySide6, since Python
always runs a package's `__init__.py` before the submodule itself. Lazy
attribute access keeps `from pluton.tools import PushPullTool` working
unchanged while letting Qt-free submodules stay Qt-free on import.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pluton.tools.arc_tool import ArcTool
    from pluton.tools.circle_tool import CircleTool
    from pluton.tools.erase_tool import EraserTool
    from pluton.tools.line_tool import LineTool
    from pluton.tools.move_tool import MoveTool
    from pluton.tools.polygon_tool import PolygonTool
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.rectangle_tool import RectangleTool
    from pluton.tools.rotate_tool import RotateTool
    from pluton.tools.scale_tool import ScaleTool
    from pluton.tools.select_tool import SelectTool
    from pluton.tools.tape_measure_tool import TapeMeasureTool
    from pluton.tools.tool import Tool, ToolContext, ToolOverlay
    from pluton.tools.tool_manager import ToolManager

__all__ = [
    "ArcTool",
    "CircleTool",
    "EraserTool",
    "LineTool",
    "MoveTool",
    "PolygonTool",
    "PushPullTool",
    "RectangleTool",
    "RotateTool",
    "ScaleTool",
    "SelectTool",
    "TapeMeasureTool",
    "Tool",
    "ToolContext",
    "ToolManager",
    "ToolOverlay",
]

_MODULE_BY_NAME = {
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
    "ToolOverlay": "pluton.tools.tool",
    "ToolManager": "pluton.tools.tool_manager",
}


def __getattr__(name: str):
    module_name = _MODULE_BY_NAME.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)

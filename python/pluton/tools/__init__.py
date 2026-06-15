"""Tool framework: Tool ABC, ToolOverlay, ToolManager, and concrete tools.

M2 ships LineTool and RectangleTool against this framework. M3's PushPullTool
and M4's full roster plug into the same shapes.
"""

from __future__ import annotations

from pluton.tools.arc_tool import ArcTool
from pluton.tools.circle_tool import CircleTool
from pluton.tools.erase_tool import EraserTool
from pluton.tools.line_tool import LineTool
from pluton.tools.polygon_tool import PolygonTool
from pluton.tools.push_pull_tool import PushPullTool
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.select_tool import SelectTool
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["ArcTool", "CircleTool", "EraserTool", "LineTool", "PolygonTool", "PushPullTool", "RectangleTool", "SelectTool", "Tool", "ToolContext", "ToolManager", "ToolOverlay"]

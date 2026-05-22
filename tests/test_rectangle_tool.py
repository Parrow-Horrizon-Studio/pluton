"""Unit tests for the Rectangle tool."""

from __future__ import annotations

import numpy as np


def _snap_at(world):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="Grid",
    )


def test_rectangle_tool_idle_overlay_is_empty():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    tool = RectangleTool()
    tool.activate(ToolContext(scene=Scene()))
    overlay = tool.overlay()
    assert overlay.rubber_band_segments.shape == (0, 3)


def test_rectangle_tool_first_click_starts_drag():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    # Scene is still empty until the second click commits.
    assert len(list(scene.vertices_iter())) == 0


def test_rectangle_tool_two_clicks_commit_four_verts_four_edges_one_face():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((3.0, 2.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.edges_iter())) == 4
    assert len(list(scene.faces_iter())) == 1


def test_rectangle_tool_zero_area_drops_gesture():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((1.0, 1.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((1.0, 1.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.faces_iter())) == 0


def test_rectangle_tool_has_active_gesture_reflects_state():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    assert tool.has_active_gesture is False

    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    assert tool.has_active_gesture is True

    tool.on_mouse_press(None, _snap_at((1.0, 1.0, 0.0)))  # type: ignore[arg-type]  # commit
    assert tool.has_active_gesture is False


def test_rectangle_tool_esc_cancels_mid_drag():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]

    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)

    overlay = tool.overlay()
    assert overlay.rubber_band_segments.shape == (0, 3)
    assert len(list(scene.vertices_iter())) == 0


def test_rectangle_tool_pushes_composite_to_command_stack():
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    stack = CommandStack()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((3.0, 2.0, 0.0)))  # type: ignore[arg-type]

    assert stack.can_undo
    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.faces_iter())) == 0

    stack.redo(scene)
    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.faces_iter())) == 1

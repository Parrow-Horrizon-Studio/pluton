"""LineTool: drawing a chord across a face divides it (M7.6a task 5).

Reuses the _FakeEvent / _snap / _make_tool idiom from test_line_tool_split.py.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.line_tool import LineTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind, SnapResult


class _FakeEvent:
    """LineTool.on_mouse_press/on_key_press never touch the event; a stub suffices."""


def _snap(kind, pos, **kw):
    return SnapResult(
        kind=kind, world_position=np.array(pos, dtype=np.float32),
        axis=kw.get("axis"), vertex_id=kw.get("vertex_id"),
        label=kw.get("label", ""), edge_id=kw.get("edge_id"),
        face_id=kw.get("face_id"), edge_t=kw.get("edge_t"),
    )


def _make_tool(scene):
    stack = CommandStack()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack,
                              camera=None, widget_size_provider=None))
    return tool, stack


def _enter():
    return QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)


def _quad(scene, z=0.0, size=2.0):
    v = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, z), (size, 0, z), (size, size, z), (0, size, z)]
    ]
    return scene.add_face_from_loop(v), v


def test_drawing_a_chord_then_enter_splits_the_face_into_two():
    scene = Scene()
    fid, v = _quad(scene)
    tool, stack = _make_tool(scene)

    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=v[0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [2, 2, 0], vertex_id=v[2]))
    tool.on_key_press(_enter())

    assert sum(1 for _ in scene.faces_iter()) == 2
    assert not scene._mesh.face_is_live(fid)
    assert stack.can_undo


def test_one_undo_after_a_splitting_line_returns_to_one_face():
    """The split must land in the SAME undo step as the line: one Ctrl+Z,
    not two, restores the original single face."""
    scene = Scene()
    fid, v = _quad(scene)
    tool, stack = _make_tool(scene)

    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=v[0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [2, 2, 0], vertex_id=v[2]))
    tool.on_key_press(_enter())
    assert sum(1 for _ in scene.faces_iter()) == 2

    stack.undo()

    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene._mesh.face_is_live(fid)


def test_a_line_that_does_not_cross_a_face_leaves_face_count_unchanged():
    scene = Scene()
    fid, v = _quad(scene)
    tool, stack = _make_tool(scene)

    # Two adjacent corners: the segment runs along the boundary, not across
    # the interior -- chain_cuts_face rejects this (see its own test suite).
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=v[0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [2, 0, 0], vertex_id=v[1]))
    tool.on_key_press(_enter())

    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene._mesh.face_is_live(fid)


def test_closing_a_loop_still_creates_a_face_and_does_not_split():
    """Loop closure is the face-creation path (branch 1 in on_mouse_press),
    never a split -- chain_cuts_face rejects chain[0] == chain[-1] itself,
    so no special-casing is needed here."""
    scene = Scene()
    tool, stack = _make_tool(scene)

    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.GRID, [0, 0, 0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.GRID, [2, 0, 0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.GRID, [2, 2, 0]))
    first_vid = tool._gesture_vertex_ids[0]
    tool.on_mouse_press(
        _FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=first_vid)
    )

    assert sum(1 for _ in scene.faces_iter()) == 1
    assert tool.has_active_gesture is False
    assert stack.can_undo


def test_double_click_finishes_the_polyline_and_can_split():
    scene = Scene()
    fid, v = _quad(scene)
    tool, stack = _make_tool(scene)

    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=v[0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [2, 2, 0], vertex_id=v[2]))
    tool.on_mouse_double_click(
        _FakeEvent(), _snap(SnapKind.ENDPOINT, [2, 2, 0], vertex_id=v[2])
    )

    assert sum(1 for _ in scene.faces_iter()) == 2
    assert tool.has_active_gesture is False
    assert stack.can_undo

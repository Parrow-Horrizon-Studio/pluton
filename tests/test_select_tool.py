"""Gesture tests for the Select tool (click / Shift / empty-clear / hover)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent


def _cam(w, h):
    from pluton.viewport.camera import Camera
    c = Camera()
    c.aspect = float(w) / float(h)
    return c


def _press(x, y, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)


def _release(x, y, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods)


def _scene_with_quad():
    from pluton.scene import Scene
    s = Scene()
    a = s.add_vertex(np.array([-1, -1, 0], dtype=np.float32))
    b = s.add_vertex(np.array([1, -1, 0], dtype=np.float32))
    c = s.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    d = s.add_vertex(np.array([-1, 1, 0], dtype=np.float32))
    fid = s.add_face_from_loop((a, b, c, d))
    e_ab = s.add_edge(a, b)
    return s, fid, e_ab


def _make_tool(scene, sel, w=800, h=600):
    from pluton.tools import ToolContext
    from pluton.tools.select_tool import SelectTool
    cam = _cam(w, h)
    tool = SelectTool()
    tool.activate(ToolContext(scene=scene, camera=cam,
                              widget_size_provider=lambda: (w, h), selection=sel))
    return tool, cam


def _click(tool, cam, world, w=800, h=600, mods=Qt.KeyboardModifier.NoModifier):
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), w, h)
    tool.on_mouse_press(_press(sx, sy, mods), None)
    tool.on_mouse_release(_release(sx, sy, mods), None)


def test_click_selects_edge_under_cursor(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, -1.0, 0.0])
    assert sel.edges == {e_ab}
    assert sel.faces == set()


def test_click_face_interior_selects_face(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, 0.0, 0.0])
    assert sel.faces == {fid}


def test_plain_click_replaces(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, -1.0, 0.0])
    assert sel.edges == {e_ab}
    assert sel.faces == set()


def test_shift_click_toggles(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    shift = Qt.KeyboardModifier.ShiftModifier
    _click(tool, cam, [0.0, -1.0, 0.0], mods=shift)
    _click(tool, cam, [0.0, 0.0, 0.0], mods=shift)
    assert sel.edges == {e_ab} and sel.faces == {fid}
    _click(tool, cam, [0.0, -1.0, 0.0], mods=shift)
    assert sel.edges == set() and sel.faces == {fid}


def test_empty_click_clears(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    tool.on_mouse_press(_press(3.0, 3.0), None)
    tool.on_mouse_release(_release(3.0, 3.0), None)
    assert sel.is_empty()


def test_esc_clears_selection(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)
    assert sel.is_empty()

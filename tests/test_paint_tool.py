from __future__ import annotations

from pluton.model.material import Material
from pluton.tools import paint_tool as paint_tool_mod
from pluton.tools.paint_tool import PaintTool
from pluton.tools.tool import ToolContext
from PySide6.QtCore import QPointF, Qt


class _FakeScene:
    def __init__(self):
        self._mats: dict[int, int] = {}

    def face_material(self, fid):
        return self._mats.get(fid, 0)

    def set_face_material(self, fid, mid):
        if mid == 0:
            self._mats.pop(fid, None)
        else:
            self._mats[fid] = mid

    def clear_face_material(self, fid):
        self._mats.pop(fid, None)


class _FakeStack:
    def __init__(self):
        self.pushed: list = []

    def push_executed(self, cmd, target):
        self.pushed.append((cmd, target))


class _Event:
    def __init__(self, alt=False):
        self._alt = alt

    def position(self):
        return QPointF(10.0, 10.0)

    def modifiers(self):
        return Qt.KeyboardModifier.AltModifier if self._alt else Qt.KeyboardModifier.NoModifier


def _tool(monkeypatch, scene, stack, active_mat, pick=7):
    monkeypatch.setattr(
        paint_tool_mod, "pick_selectable",
        lambda *a, **k: ("face", pick) if pick is not None else None,
    )
    captured: dict = {}
    ctx = ToolContext(
        scene=scene,
        command_stack=stack,
        camera=object(),
        widget_size_provider=lambda: (100, 100),
        model=None,
        active_material_provider=lambda: active_mat,
        set_active_material=lambda mid: captured.__setitem__("sampled", mid),
    )
    t = PaintTool()
    t.activate(ctx)
    return t, captured


RED = Material(3, "Brick Red", (0.70, 0.27, 0.22))


def test_paint_pushes_command_and_applies(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(), snap=None)
    assert scene.face_material(7) == 3
    assert len(stack.pushed) == 1


def test_alt_click_samples_without_command(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 5)
    t, captured = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(alt=True), snap=None)
    assert captured["sampled"] == 5
    assert stack.pushed == []
    assert scene.face_material(7) == 5


def test_no_op_when_material_unchanged(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 3)
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(), snap=None)
    assert stack.pushed == []


def test_miss_does_nothing(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=None)
    t.on_mouse_press(_Event(), snap=None)
    assert stack.pushed == []


def test_shortcut_is_b():
    assert PaintTool().shortcut == "B"

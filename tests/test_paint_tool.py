from __future__ import annotations

import numpy as np
from pluton.model.material import Material
from pluton.scene.scene import Side
from pluton.tools import paint_tool as paint_tool_mod
from pluton.tools.paint_tool import PaintTool
from pluton.tools.tool import ToolContext
from PySide6.QtCore import QPointF, Qt


class _FakeScene:
    def __init__(self):
        self._mats: dict[tuple[int, Side], int] = {}

    def face_material(self, fid, side=Side.FRONT):
        return self._mats.get((fid, side), 0)

    def set_face_material(self, fid, mid, side=Side.FRONT):
        if mid == 0:
            self._mats.pop((fid, side), None)
        else:
            self._mats[(fid, side)] = mid

    def clear_face_material(self, fid, side=Side.FRONT):
        self._mats.pop((fid, side), None)

    def face_normal(self, fid):
        # Fixed +Z normal; paired with _FakeCamera's ray this resolves FRONT
        # (Task 10's side_for_ray is exercised directly and via
        # test_paint_stroke.py -- this double only needs a stable side so
        # the click/no-op/alt-click behaviour above it stays testable).
        return np.array([0.0, 0.0, 1.0])


class _FakeCamera:
    def ray_from_screen(self, x, y, w, h):
        # Looking straight down at the +Z-normal face from above: FRONT.
        return np.array([0.0, 0.0, 5.0]), np.array([0.0, 0.0, -1.0])


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
        camera=_FakeCamera(),
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
    # A plain click is a one-face stroke: press paints it live, release is
    # what pushes the (single-child) CompositeCommand for undo.
    t.on_mouse_press(_Event(), snap=None)
    assert scene.face_material(7) == 3  # visible immediately, before release
    t.on_mouse_release(_Event(), snap=None)
    assert len(stack.pushed) == 1


def test_alt_click_samples_without_command(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 5)
    t, captured = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(alt=True), snap=None)
    t.on_mouse_release(_Event(alt=True), snap=None)
    assert captured["sampled"] == 5
    assert stack.pushed == []
    assert scene.face_material(7) == 5


def test_no_op_when_material_unchanged(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 3)
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(), snap=None)
    t.on_mouse_release(_Event(), snap=None)
    # Repainting a face with its current material is a no-op guard inside the
    # stroke: press paints nothing, so release finds an empty stroke and
    # pushes nothing (not just "press alone touches nothing").
    assert stack.pushed == []


def test_miss_does_nothing(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=None)
    t.on_mouse_press(_Event(), snap=None)
    t.on_mouse_release(_Event(), snap=None)
    assert stack.pushed == []


def test_shortcut_is_b():
    assert PaintTool().shortcut == "B"

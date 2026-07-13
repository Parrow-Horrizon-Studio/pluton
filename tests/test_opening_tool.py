from __future__ import annotations

import numpy as np
from pluton.commands.command_stack import CommandStack
from pluton.geometry.wall import wall_box
from pluton.model.model import Model
from pluton.tools.opening_tool import DoorWindowTool
from pluton.tools.tool import ToolContext


class _FakeCamera:
    def __init__(self, origin, direction):
        self._o = np.asarray(origin, np.float64)
        self._d = np.asarray(direction, np.float64)

    def ray_from_screen(self, cx, cy, w, h):
        return self._o, self._d


class _Event:
    def __init__(self, x=10.0, y=10.0):
        self._x, self._y = x, y

    def position(self):
        class _P:
            def __init__(self, x, y):
                self._x, self._y = x, y

            def x(self):
                return self._x

            def y(self):
                return self._y

        return _P(self._x, self._y)


def _model_with_wall():
    model = Model()
    verts, faces = wall_box((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.2, 2.4)
    defn = model.new_definition("Wall", is_group=True)
    ids = [defn.mesh.add_vertex(np.array(v, dtype=np.float32)) for v in verts]
    for loop in faces:
        defn.mesh.add_face_from_loop([ids[i] for i in loop])
    model.active_context.children.append(model.new_instance(defn))
    return model


def _ctx(model, stack, camera):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model, camera=camera,
        widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def test_place_on_wall_face_creates_one_instance():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    cam = _FakeCamera((1.0, 5.0, 1.2), (0.0, -1.0, 0.0))   # ray hits y=+0.1 face
    tool.activate(_ctx(model, stack, cam))
    tool.on_mouse_move(_Event(), None)                      # builds the preview
    before = len(model.active_context.children)
    tool.on_mouse_press(_Event(), None)                     # places the opening
    assert len(model.active_context.children) == before + 1
    placed = model.active_context.children[-1].definition
    assert placed.is_group is False and placed.name == "Door"


def test_no_face_no_placement():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    cam = _FakeCamera((50.0, 50.0, 50.0), (0.0, 0.0, 1.0))  # misses
    tool.activate(_ctx(model, stack, cam))
    before = len(model.active_context.children)
    tool.on_mouse_move(_Event(), None)
    tool.on_mouse_press(_Event(), None)
    assert len(model.active_context.children) == before   # miss -> nothing added


def test_window_kind_places_window():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    tool.kind = "window"
    cam = _FakeCamera((1.0, 5.0, 1.2), (0.0, -1.0, 0.0))
    tool.activate(_ctx(model, stack, cam))
    tool.on_mouse_move(_Event(), None)
    tool.on_mouse_press(_Event(), None)
    assert model.active_context.children[-1].definition.name == "Window"

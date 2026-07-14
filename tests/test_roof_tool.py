from __future__ import annotations

import numpy as np
from pluton.commands.command_stack import CommandStack
from pluton.model.model import Model
from pluton.tools.roof_tool import RoofTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


class _Snap:
    def __init__(self, x, y, z=0.0, kind=SnapKind.ON_FACE):
        self.kind = kind
        self.world_position = np.array([x, y, z], dtype=np.float64)


def _ctx(model, stack):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model,
        camera=None, widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def _place(tool, ax, ay, bx, by):
    tool.on_mouse_press(None, _Snap(ax, ay))
    tool.on_mouse_move(None, _Snap(bx, by))
    tool.on_mouse_press(None, _Snap(bx, by))


def test_footprint_drag_places_one_roof():
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.activate(_ctx(model, stack))
    _place(tool, 0.0, 0.0, 4.0, 6.0)
    assert len(model.active_context.children) == 1
    defn = model.active_context.children[-1].definition
    assert defn.is_group is True and defn.name == "Roof"


def test_ridge_runs_along_longer_edge_by_default():
    # footprint 4 (x) x 8 (y): ridge should run along Y (the longer edge), so the
    # roof's apex line spans ~8 in Y and the cross-section spans ~4 in X.
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.kind = "gable"
    tool.activate(_ctx(model, stack))
    _place(tool, 0.0, 0.0, 4.0, 8.0)
    inst = model.active_context.children[-1]
    m = inst.transform
    verts = [(m @ np.append(np.array(v), 1.0))[:3]
             for v in _defn_local_verts(inst.definition)]
    a = np.array(verts)
    # X extent ~4 (across ridge), Y extent ~8 (along ridge)
    assert np.isclose(a[:, 0].max() - a[:, 0].min(), 4.0, atol=1e-6)
    assert np.isclose(a[:, 1].max() - a[:, 1].min(), 8.0, atol=1e-6)


def test_no_footprint_no_placement_on_degenerate():
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.activate(_ctx(model, stack))
    _place(tool, 1.0, 1.0, 1.0, 1.0)   # zero-area footprint
    assert len(model.active_context.children) == 0


def _defn_local_verts(defn):
    return [v.position for v in defn.mesh.vertices_iter()]

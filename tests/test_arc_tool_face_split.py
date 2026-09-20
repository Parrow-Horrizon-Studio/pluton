"""ArcTool: drawing an arc across a face divides it (M7.6a task 5, fix round 1).

Mirrors tests/test_line_tool_face_split.py. Before this file, chain_cuts_face
and SplitFaceCommand were wired into ArcTool._commit_polyline with no
automated coverage at all -- every existing test_arc_tool.py case draws into
an empty scene, so the split branch was never entered.
"""

from __future__ import annotations

import numpy as np
from pluton.commands.command_stack import CommandStack
from pluton.geometry.transforms import mat_translate
from pluton.model.model import Model
from pluton.scene.scene import Scene
from pluton.tools.arc_tool import ArcTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind, SnapResult


def _snap(kind, pos, **kw):
    return SnapResult(
        kind=kind,
        world_position=np.array(pos, dtype=np.float32),
        axis=kw.get("axis"),
        vertex_id=kw.get("vertex_id"),
        label=kw.get("label", ""),
        edge_id=kw.get("edge_id"),
        face_id=kw.get("face_id"),
        edge_t=kw.get("edge_t"),
    )


def _make_tool(scene, model=None):
    stack = CommandStack()
    tool = ArcTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=stack,
            camera=None,
            widget_size_provider=None,
            model=model,
        )
    )
    return tool, stack


def _quad(scene, origin=(0.0, 0.0, 0.0), size=4.0):
    ox, oy, oz = origin
    v = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [
            (ox, oy, oz),
            (ox + size, oy, oz),
            (ox + size, oy + size, oz),
            (ox, oy + size, oz),
        ]
    ]
    return scene.add_face_from_loop(v), v


def _draw_arc_across(tool, start, end, bulge):
    """Three clicks: chord start, chord end, bulge point -- the ArcTool
    commits on the third click."""
    tool.on_mouse_press(None, _snap(SnapKind.ENDPOINT, start, vertex_id=None))
    tool.on_mouse_press(None, _snap(SnapKind.ENDPOINT, end, vertex_id=None))
    tool.on_mouse_press(None, _snap(SnapKind.GRID, bulge))


def test_an_arc_drawn_across_a_face_splits_it():
    scene = Scene()
    fid, _v = _quad(scene)
    tool, stack = _make_tool(scene)

    # Chord along the diagonal, small bulge kept well inside the quad so the
    # whole 12-segment arc stays strictly interior between the two corners.
    _draw_arc_across(tool, (0, 0, 0), (4, 4, 0), (2.2, 1.8, 0))

    assert sum(1 for _ in scene.faces_iter()) == 2
    assert not scene._mesh.face_is_live(fid)
    assert stack.can_undo


def test_one_undo_after_a_splitting_arc_returns_to_one_face():
    """Same same-undo-step guarantee as LineTool: the split must be folded
    into the arc's own composite, not pushed as a second undo entry."""
    scene = Scene()
    fid, _v = _quad(scene)
    tool, stack = _make_tool(scene)

    _draw_arc_across(tool, (0, 0, 0), (4, 4, 0), (2.2, 1.8, 0))
    assert sum(1 for _ in scene.faces_iter()) == 2
    edges_after_split = sum(1 for _ in scene.edges_iter())

    stack.undo()

    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene._mesh.face_is_live(fid)
    # The arc's own edges must be gone too, not just the split half of the
    # gesture (see the equivalent LineTool undo test for why this is the
    # assertion that actually discriminates a correctly-folded undo step).
    assert sum(1 for _ in scene.edges_iter()) < edges_after_split
    assert stack.can_undo is False


def test_an_arc_that_does_not_cross_a_face_leaves_face_count_unchanged():
    scene = Scene()
    fid, _v = _quad(scene)
    tool, _stack = _make_tool(scene)

    # Drawn entirely away from the quad.
    _draw_arc_across(tool, (10, 0, 0), (12, 0, 0), (11, 1, 0))

    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene._mesh.face_is_live(fid)


def test_an_arc_split_reaches_through_a_non_identity_world_transform():
    """Drawn inside a translated group: the snap positions this test passes
    are WORLD-space (the convention every tool uses), while the quad's own
    vertices live in the group's LOCAL frame -- build_open_polyline's
    world->local conversion has to run and land on the same local vertices
    for chain_cuts_face to find anything to split at all."""
    translation = [5.0, 0.0, 0.0]
    wt = mat_translate(translation)
    model = Model()
    grp_def = model.new_definition("Grp", is_group=True)
    scene = grp_def.mesh
    fid, _v = _quad(scene)

    grp_inst = model.new_instance(grp_def, wt)
    model.root.children.append(grp_inst)
    model.enter(grp_inst)

    tool, stack = _make_tool(scene, model=model)
    # LOCAL (0,0,0)/(4,4,0) -> WORLD (5,0,0)/(9,4,0).
    _draw_arc_across(tool, (5, 0, 0), (9, 4, 0), (7.2, 1.8, 0))

    assert sum(1 for _ in scene.faces_iter()) == 2
    assert not scene._mesh.face_is_live(fid)
    assert stack.can_undo

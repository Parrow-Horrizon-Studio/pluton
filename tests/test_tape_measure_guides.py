"""M7.6b Task 7: Tape Measure creates construction guides.

Reuses tests/test_tape_measure_tool.py's fixture and event-synthesis helpers
(`_press`, `_snap`, `_ctx`-style shape) rather than inventing new ones, plus a
`_move`/`_release` pair for the drag half of the new gestures.
"""

from __future__ import annotations

import types

import numpy as np
from pluton.commands import CommandStack
from pluton.model import Model
from pluton.tools.tape_measure_tool import TapeMeasureTool
from pluton.tools.tool import ToolContext
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

U = Units()


def _press(modifiers=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )


def _move():
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(0, 0),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(modifiers=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        modifiers,
    )


def _snap(p, kind=SnapKind.ENDPOINT, vertex_id=None, edge_id=None, face_id=None, edge_t=None):
    return types.SimpleNamespace(
        kind=kind,
        world_position=np.asarray(p, np.float32),
        axis=None,
        vertex_id=vertex_id,
        edge_id=edge_id,
        edge_t=edge_t,
        face_id=face_id,
    )


def _ctx(model, command_stack):
    return ToolContext(
        scene=model.active_scene,
        command_stack=command_stack,
        camera=None,
        widget_size_provider=lambda: (800, 600),
        units_provider=lambda: U,
        model=model,
    )


def _guides(model):
    return [a for a in model.active_context.annotations if a.kind == "guide"]


def _guide_points(model):
    return [a for a in model.active_context.annotations if a.kind == "guide_point"]


# ---------------------------------------------------------------------------
# Behaviour 5 FIRST: the offset-rule spike. Spec 2.4 (reasoned, not measured)
# says a guide's offset is perpendicular to the clicked edge WITHIN THE PLANE
# OF THE FACE that edge bounds. Verify with an actual vertical wall before
# trusting that rule for anything else in this file.
# ---------------------------------------------------------------------------


def _vertical_wall_model():
    """A model whose root scene holds one vertical wall: a quad face in the
    x=0 plane (so its normal is +/-X), matching
    tests/test_drawing_plane_resolution.py's own `_wall_scene` layout.

    vertex order: 0=(0,0,0) 1=(0,6,0) 2=(0,6,4) 3=(0,0,4). Edge (3, 0) is the
    wall's LEFT VERTICAL edge (y=0 fixed, z varies) -- deliberately chosen
    because it stress-tests the rule: a wrong "always fall back to the
    horizontal ground plane" implementation would try to find a direction
    perpendicular to a vertical edge that also lies in a horizontal plane,
    which does not exist (the cross product degenerates to zero), so that
    bug would fail loudly (no guide at all) rather than quietly producing a
    horizontal one.
    """
    model = Model()
    scene = model.active_scene
    vids = [
        scene.add_vertex(np.array(p, dtype=np.float32))
        for p in [(0, 0, 0), (0, 6, 0), (0, 6, 4), (0, 0, 4)]
    ]
    edge_ids = {}
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        edge_ids[(a, b)] = scene.add_edge(vids[a], vids[b])
    face_id = scene.add_face_from_loop(vids)
    return model, scene, vids, edge_ids, face_id


def test_guide_offset_is_coplanar_with_the_clicked_edges_face(qtbot):
    model, scene, vids, edge_ids, face_id = _vertical_wall_model()
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    vertical_edge_id = edge_ids[(3, 0)]
    edge = scene.edge(vertical_edge_id)
    p1 = scene.vertex(edge.v1_id).position
    p2 = scene.vertex(edge.v2_id).position
    edge_dir = (np.asarray(p2, np.float64) - np.asarray(p1, np.float64))
    edge_dir = edge_dir / np.linalg.norm(edge_dir)
    midpoint = (np.asarray(p1, np.float64) + np.asarray(p2, np.float64)) / 2.0

    press_snap = _snap(
        midpoint, kind=SnapKind.ON_EDGE, edge_id=vertical_edge_id, face_id=face_id, edge_t=0.5
    )
    t.on_mouse_press(_press(), press_snap)
    assert t._drag_active, "a click on an edge must open a drag gesture"

    # Drag purely along +Y -- NOT the wall's own edge direction (+/-Z) -- so
    # a coplanar (x == 0) result is not a coincidence of the drag direction
    # chosen.
    drag_to = midpoint + np.array([0.0, 1.5, 0.0])
    t.on_mouse_move(_move(), _snap(drag_to, kind=SnapKind.ON_FACE, face_id=face_id))
    t.on_mouse_release(_release(), _snap(drag_to, kind=SnapKind.ON_FACE, face_id=face_id))

    guides = _guides(model)
    assert len(guides) == 1, (
        "expected exactly one Guide from the edge-drag; the offset rule may "
        "have degenerated instead of resolving the wall's own plane"
    )
    guide = guides[0]

    # Coplanar with the wall (x == 0 for both the origin and the direction),
    # NOT dropped onto the horizontal ground plane.
    assert abs(guide.origin[0]) < 1e-4, f"guide origin left the wall's plane: {guide.origin}"
    assert abs(guide.direction[0]) < 1e-4, (
        f"guide direction left the wall's plane: {guide.direction}"
    )
    # And genuinely not horizontal: the clicked edge was vertical, so a
    # guide parallel to it must keep a large Z component.
    assert abs(guide.direction[2]) > 0.9, f"guide direction reads as horizontal: {guide.direction}"

    # The guide is parallel (or anti-parallel) to the clicked edge.
    assert abs(abs(float(np.dot(guide.direction, edge_dir))) - 1.0) < 1e-4

    # It undoes cleanly, as one step.
    assert stack.can_undo
    assert stack.undo()
    assert _guides(model) == []


# ---------------------------------------------------------------------------
# Behaviour 1: click an edge, drag, release -> one Guide, parallel to the edge.
# ---------------------------------------------------------------------------


def _free_edge_model():
    """A model whose root scene holds a single free edge (no face at all),
    along +X, so the offset rule falls back to the gesture's own drawing
    plane (horizontal, per resolve_drawing_plane's own fallback rule)."""
    model = Model()
    scene = model.active_scene
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 0.0], np.float32))
    edge_id = scene.add_edge(v0, v1)
    return model, scene, edge_id


def test_edge_drag_and_release_creates_one_parallel_guide(qtbot):
    model, scene, edge_id = _free_edge_model()
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    press_snap = _snap([2.0, 0.0, 0.0], kind=SnapKind.ON_EDGE, edge_id=edge_id, edge_t=0.5)
    t.on_mouse_press(_press(), press_snap)
    t.on_mouse_move(_move(), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE))
    t.on_mouse_release(_release(), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE))

    guides = _guides(model)
    assert len(guides) == 1
    guide = guides[0]
    assert abs(abs(float(guide.direction[0])) - 1.0) < 1e-6, guide.direction


# ---------------------------------------------------------------------------
# Behaviour 2: the same gesture with Ctrl held creates nothing, and the
# measure-only readout keeps working.
# ---------------------------------------------------------------------------


def test_ctrl_held_suppresses_guide_creation(qtbot):
    model, scene, edge_id = _free_edge_model()
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    press_snap = _snap([2.0, 0.0, 0.0], kind=SnapKind.ON_EDGE, edge_id=edge_id, edge_t=0.5)
    t.on_mouse_press(_press(Qt.KeyboardModifier.ControlModifier), press_snap)
    t.on_mouse_move(_move(), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE))
    t.on_mouse_release(
        _release(Qt.KeyboardModifier.ControlModifier), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE)
    )

    assert _guides(model) == []
    assert _guide_points(model) == []
    # measure-only readout intact: one point placed, cursor tracked, distance shown.
    assert t.status_text is not None
    assert "Distance" in t.status_text


# ---------------------------------------------------------------------------
# Behaviour 3: creating a guide pushes exactly one command.
# ---------------------------------------------------------------------------


def test_guide_creation_is_one_undo_step(qtbot):
    model, scene, edge_id = _free_edge_model()
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    press_snap = _snap([2.0, 0.0, 0.0], kind=SnapKind.ON_EDGE, edge_id=edge_id, edge_t=0.5)
    t.on_mouse_press(_press(), press_snap)
    t.on_mouse_move(_move(), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE))
    t.on_mouse_release(_release(), _snap([2.0, 2.0, 0.0], kind=SnapKind.ON_FACE))

    assert len(_guides(model)) == 1
    assert stack.can_undo
    assert stack.undo()
    assert _guides(model) == []
    assert not stack.can_undo


# ---------------------------------------------------------------------------
# Behaviour 4: click a vertex, drag along an axis, type a distance -> one
# GuidePoint at that distance.
# ---------------------------------------------------------------------------


def test_vertex_drag_and_typed_value_creates_one_guide_point(qtbot):
    model = Model()
    scene = model.active_scene
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], np.float32))
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    press_snap = _snap([0.0, 0.0, 0.0], kind=SnapKind.ENDPOINT, vertex_id=v0)
    t.on_mouse_press(_press(), press_snap)
    t.on_mouse_move(_move(), _snap([3.0, 0.0, 0.0], kind=SnapKind.AXIS_LOCK))

    assert t.apply_typed_value("5", U)

    points = _guide_points(model)
    assert len(points) == 1
    np.testing.assert_allclose(points[0].position, (5.0, 0.0, 0.0), atol=1e-5)
    # Typed-value commit ends the gesture like every other one-shot tool.
    assert not t._drag_active


def test_vertex_drag_typed_value_rejects_zero_and_negative(qtbot):
    model = Model()
    scene = model.active_scene
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], np.float32))
    stack = CommandStack()
    t = TapeMeasureTool()
    t.activate(_ctx(model, stack))

    t.on_mouse_press(_press(), _snap([0.0, 0.0, 0.0], kind=SnapKind.ENDPOINT, vertex_id=v0))
    t.on_mouse_move(_move(), _snap([3.0, 0.0, 0.0], kind=SnapKind.AXIS_LOCK))

    assert not t.apply_typed_value("0", U)
    assert not t.apply_typed_value("-2", U)
    assert _guide_points(model) == []

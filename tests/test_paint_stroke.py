"""M7.5a Task 10: drag-to-paint and which side gets painted."""

from __future__ import annotations

import numpy as np
from pluton.scene.scene import Side


def _faces(scene):
    return [f.id for f in scene.faces_iter()]


def test_a_stroke_across_three_faces_is_one_undo_step(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    # three coplanar squares in a row
    for i in range(3):
        v = [
            scene.add_vertex(np.array([i, 0.0, 0.0], dtype=np.float32)),
            scene.add_vertex(np.array([i + 1.0, 0.0, 0.0], dtype=np.float32)),
            scene.add_vertex(np.array([i + 1.0, 1.0, 0.0], dtype=np.float32)),
            scene.add_vertex(np.array([i, 1.0, 0.0], dtype=np.float32)),
        ]
        for a, b in zip(v, v[1:] + v[:1], strict=True):
            scene.add_edge(a, b)
        scene.add_face_from_loop(v)
    ids = _faces(scene)
    win._activate("paint")
    tool = win._tool_manager.active
    mat = win._model.materials.materials()[1]
    depth = len(win._command_stack._undo)

    tool._begin_stroke(mat.id)
    for f in ids:
        tool._paint_during_stroke(f, Side.FRONT, mat.id)
    tool._end_stroke()

    assert all(scene.face_material(f) == mat.id for f in ids)
    # three faces, ONE step. A per-face push would give three.
    assert len(win._command_stack._undo) == depth + 1
    win._command_stack.undo()
    assert all(scene.face_material(f) == 0 for f in ids)


def test_re_crossing_a_face_does_not_add_a_second_command(main_window_with_square):
    win = main_window_with_square
    scene = win._model.active_context.mesh
    f = _faces(scene)[0]
    win._activate("paint")
    tool = win._tool_manager.active
    mat = win._model.materials.materials()[1]
    depth = len(win._command_stack._undo)

    tool._begin_stroke(mat.id)
    for _ in range(5):
        tool._paint_during_stroke(f, Side.FRONT, mat.id)
    tool._end_stroke()

    assert len(win._command_stack._undo) == depth + 1
    win._command_stack.undo()
    assert scene.face_material(f) == 0, "one undo must clear it, not five"


def test_a_stroke_that_paints_nothing_pushes_nothing(main_window_with_square):
    win = main_window_with_square
    win._activate("paint")
    tool = win._tool_manager.active
    depth = len(win._command_stack._undo)
    tool._begin_stroke(1)
    tool._end_stroke()
    assert len(win._command_stack._undo) == depth


def test_the_stroke_paints_the_side_it_is_given(main_window_with_square):
    win = main_window_with_square
    scene = win._model.active_context.mesh
    f = _faces(scene)[0]
    win._activate("paint")
    tool = win._tool_manager.active
    mat = win._model.materials.materials()[1]

    tool._begin_stroke(mat.id)
    tool._paint_during_stroke(f, Side.BACK, mat.id)
    tool._end_stroke()

    assert scene.face_material(f, Side.BACK) == mat.id
    assert scene.face_material(f, Side.FRONT) == 0  # discriminating


def test_side_for_ray_reads_the_normal_direction():
    from pluton.tools.paint_tool import side_for_ray

    normal = np.array([0.0, 0.0, 1.0])
    # looking down at a face whose normal points up: we see the FRONT
    assert side_for_ray(normal, np.array([0.0, 0.0, -1.0])) is Side.FRONT
    # looking up from below at the same face: we see the BACK
    assert side_for_ray(normal, np.array([0.0, 0.0, 1.0])) is Side.BACK


def test_side_for_ray_is_not_fooled_by_a_grazing_angle():
    from pluton.tools.paint_tool import side_for_ray

    normal = np.array([0.0, 0.0, 1.0])
    nearly_edge_on = np.array([1.0, 0.0, -0.01])
    assert side_for_ray(normal, nearly_edge_on) is Side.FRONT


def test_resolve_side_uses_the_inverse_transpose_under_non_uniform_scale():
    """side_for_ray alone can't tell an inverse-transpose from a plain linear
    block: both agree on an axis-aligned face under uniform scale (they agree
    whenever the face normal already lies along one of the scale matrix's own
    axes, which an axis-aligned face always does). This test picks a face
    normal NOT aligned to any axis (from a tilted triangle) and a diagonal
    non-uniform scale, a combination where the two transforms genuinely
    disagree on direction -- and, for the ray direction chosen below, disagree
    on which SIDE it is:

      local normal n = (1, 1, 1)/sqrt(3); scale L = diag(2, 1, 1)

      correct (inverse-transpose): (L^-1)^T n = (0.5, 1, 1)/sqrt(3)
      wrong   (plain linear block): L n        = (2, 1, 1)/sqrt(3)

    Dotted with ray direction d = (1, -1, 0):
      correct . d = 0.5 - 1 = -0.5   -> FRONT
      wrong   . d = 2   - 1 =  0.5   -> BACK

    So this test fails if PaintTool._resolve_side is changed to use the plain
    linear block instead of the inverse-transpose.
    """
    from pluton.tools.paint_tool import PaintTool
    from pluton.tools.tool import ToolContext

    class _FakeScene:
        def face_normal(self, fid):
            return np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)

    class _FakeCamera:
        def ray_from_screen(self, x, y, w, h):
            return np.zeros(3), np.array([1.0, -1.0, 0.0])

    class _FakeModel:
        # diag(2, 1, 1): non-uniform, and the face normal above is not
        # aligned to any coordinate axis -- the trap case the brief warns
        # an axis-aligned or uniformly-scaled fixture cannot expose.
        active_world_transform = np.diag([2.0, 1.0, 1.0, 1.0])

    tool = PaintTool()
    tool.activate(
        ToolContext(
            scene=_FakeScene(),
            camera=_FakeCamera(),
            widget_size_provider=lambda: (100, 100),
            model=_FakeModel(),
        )
    )
    # _resolve_side calls event.position() via _cursor(); _FakeCamera ignores
    # the resulting (x, y), so any QPointF stand-in works.
    class _Event:
        def position(self):
            from PySide6.QtCore import QPointF

            return QPointF(0.0, 0.0)

    assert tool._resolve_side(_Event(), 0) is Side.FRONT

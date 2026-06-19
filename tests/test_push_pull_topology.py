"""Extrusion composite tests — topology + undo/redo round-trip."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


def _make_press():
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_move():
    return QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _live_vertex_count(scene) -> int:
    return sum(1 for _ in scene.vertices_iter())


def _live_edge_count(scene) -> int:
    return sum(1 for _ in scene.edges_iter())


def _live_face_count(scene) -> int:
    return sum(1 for _ in scene.faces_iter())


def _setup_push_pull():
    """Build a fresh Scene + REAL CommandStack + PushPullTool with one rect face."""
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.tool import ToolContext

    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    f = scene.add_face_from_loop([v0, v1, v2, v3])

    camera = MagicMock()
    camera.ray_from_screen.return_value = (
        np.array([0.5, 0.5, 5.0], dtype=np.float32),
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
    )

    command_stack = CommandStack()
    tool = PushPullTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=command_stack,
            camera=camera,
            widget_size_provider=lambda: (800, 600),
        )
    )
    return tool, scene, f, camera, command_stack


class TestPushPullCommit:
    def test_commit_a_rectangle_produces_5_new_faces_8_new_edges_4_new_verts(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        # Hover + arm.
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        # Drag to depth 2.
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        # Pre-commit counts: 4 verts, 4 edges, 1 face.
        assert _live_vertex_count(scene) == 4
        assert _live_edge_count(scene) == 4
        assert _live_face_count(scene) == 1
        # Commit (second click).
        tool.on_mouse_press(_make_press(), snap=None)
        # Post-commit counts:
        #   verts: 4 source + 4 top                = 8
        #   edges: 4 source + 4 vertical + 4 top   = 12
        #   faces: 4 sides + 1 top + 1 bottom (source removed)= 6
        assert _live_vertex_count(scene) == 8
        assert _live_edge_count(scene) == 12
        assert _live_face_count(scene) == 6
        # Every live face must have at least one triangle. Regression for the
        # XY-only earcut projection bug that made vertical side faces have 0
        # triangles (M3b visual verification turned this up).
        for face in scene.faces_iter():
            tris = list(scene._mesh.face_triangles(face.id))
            assert len(tris) >= 3, f"face {face.id} has no triangles (len={len(tris)})"
        # Source face is gone.
        with pytest.raises(KeyError):
            scene.face(source_f)
        # Tool returns to IDLE / HOVERING (DRAGGING done).
        assert tool.has_active_gesture is False

        # M3c: closed-manifold guard — every face must have at least one triangle
        # (complements the _mesh.face_triangles check; asserts via the Scene
        # Face.triangles (N,3) array that earcut produced a non-empty fan).
        for f in scene.faces_iter():
            assert len(f.triangles) > 0, (
                f"Face {f.id} (loop={f.loop_vertex_ids}) has no triangles; "
                f"earcut likely silently failed (regression of M3b XY-only bug)."
            )

        # M3c: every interior edge (two live faces) must have both half-edges
        # bound to a live face — the closed-manifold invariant for the capped box.
        for e in scene.edges_iter():
            faces = scene.edge_faces(e.id)
            if faces[0] is not None and faces[1] is not None:
                he_a = 2 * e.id
                he_b = 2 * e.id + 1
                invalid = scene._mesh.INVALID_ID
                assert scene._mesh.halfedge_face(he_a) != invalid
                assert scene._mesh.halfedge_face(he_b) != invalid

    def test_commit_pushes_one_composite_command(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        assert cmd_stack.can_undo

    def test_undo_restores_pre_commit_scene(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        assert cmd_stack.undo()
        assert _live_vertex_count(scene) == 4
        assert _live_edge_count(scene) == 4
        assert _live_face_count(scene) == 1
        face = scene.face(source_f)
        assert face.id == source_f

    def test_redo_replays_extrusion(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        cmd_stack.undo()
        cmd_stack.redo()
        assert _live_vertex_count(scene) == 8
        assert _live_edge_count(scene) == 12
        assert _live_face_count(scene) == 6

    def test_top_face_normal_matches_source_normal_direction(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        # Find the top face explicitly by its +Z normal. NOTE: M3c adds a
        # bottom cap (normal -Z) as the most-recently-added face, so the old
        # "highest id = top" heuristic no longer holds.
        top_candidates = [
            f.id
            for f in scene.faces_iter()
            if float(np.dot(scene.face_normal(f.id), [0.0, 0.0, 1.0])) > 0.5
        ]
        assert len(top_candidates) == 1
        top_face_id = top_candidates[0]
        normal = scene.face_normal(top_face_id)
        np.testing.assert_allclose(normal, [0.0, 0.0, 1.0], atol=1e-5)

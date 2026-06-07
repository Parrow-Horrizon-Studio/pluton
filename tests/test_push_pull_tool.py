"""PushPullTool — state machine + depth metric + composite-building tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


# ---- helpers ---------------------------------------------------------------


def _make_event(pos=(100.0, 100.0), button=Qt.MouseButton.LeftButton, kind=QMouseEvent.Type.MouseMove):
    return QMouseEvent(
        kind,
        QPointF(*pos),
        QPointF(*pos),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_tool_with_unit_rect():
    """Spin up a fresh Scene + PushPullTool with one unit-rect face at z=0.

    The tool is activated against a context with a mock camera + widget sizer
    that we can drive directly.
    """
    from pluton.scene import Scene
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.tool import ToolContext

    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    f = scene.add_face_from_loop([v0, v1, v2, v3])

    # Mock camera that ray_from_screen always returns "directly down from (0.5, 0.5, 5)".
    camera = MagicMock()
    camera.ray_from_screen.return_value = (
        np.array([0.5, 0.5, 5.0], dtype=np.float32),
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
    )

    cmd_stack = MagicMock()

    tool = PushPullTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=cmd_stack,
            camera=camera,
            widget_size_provider=lambda: (800, 600),
        )
    )
    return tool, scene, f, camera, cmd_stack


# ---- identity ---------------------------------------------------------------


class TestPushPullIdentity:
    def test_name_and_shortcut(self):
        from pluton.tools.push_pull_tool import PushPullTool

        tool = PushPullTool()
        assert tool.name == "Push/Pull"
        assert tool.shortcut == "P"


# ---- IDLE / HOVERING -------------------------------------------------------


class TestPushPullHovering:
    def test_starts_in_idle_state(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        assert tool.has_active_gesture is False
        overlay = tool.overlay()
        assert overlay.face_fill_polygons == []

    def test_mouse_move_over_face_transitions_to_hovering(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # The mock camera ray hits the rectangle face.
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        overlay = tool.overlay()
        assert len(overlay.face_fill_polygons) == 1
        loop = overlay.face_fill_polygons[0]
        assert loop.shape == (4, 3)
        # Should be the rectangle's 4 corners at z=0 (any order).
        np.testing.assert_allclose(
            sorted(map(tuple, loop.tolist())),
            sorted([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]),
            atol=1e-5,
        )
        assert tool.has_active_gesture is False

    def test_mouse_move_off_face_transitions_back_to_idle(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.overlay().face_fill_polygons != []
        # Move OFF — camera ray now misses.
        camera.ray_from_screen.return_value = (
            np.array([5.0, 5.0, 5.0], dtype=np.float32),
            np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.overlay().face_fill_polygons == []

    def test_status_text_is_none_in_idle(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        assert tool.status_text is None

    def test_status_text_is_none_in_hovering(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.status_text is None

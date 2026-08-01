"""VCB completions (#55): Circle segment count, signed Rotate angle, per-axis
Scale factors. Each test establishes the tool's real `apply_typed_value`
precondition (the guard state each tool checks before it will parse typed
text) rather than weakening the assertion.
"""

from __future__ import annotations

import types

import numpy as np
from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.circle_tool import CircleTool
from pluton.tools.rotate_tool import RotateTool, _Stage
from pluton.tools.scale_tool import ScaleTool
from pluton.tools.tool import ToolContext
from pluton.tools.transform_support import GripSpec
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

U = Units()


def _press():
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _snap(p):
    return types.SimpleNamespace(
        kind=SnapKind.ON_FACE,
        world_position=np.asarray(p, np.float32),
        axis=None,
        vertex_id=None,
        edge_id=None,
        edge_t=None,
        face_id=None,
    )


def _ctx(s, stack):
    return ToolContext(
        scene=s,
        command_stack=stack,
        camera=None,
        widget_size_provider=lambda: (800, 600),
        units_provider=lambda: U,
    )


# ---------------------------------------------------------------------------
# #55a — Circle segment count ("12s")
# ---------------------------------------------------------------------------


def test_circle_accepts_a_segment_count(qtbot):
    """CircleTool.apply_typed_value guards on `_state == DRAWING and _plane
    is not None` (circle_tool.py) -- established here the same way the
    existing test_circle_typed_radius does: activate + press to place the
    center, which resolves the drawing plane and enters DRAWING."""
    s = Scene()
    stack = CommandStack()
    tool = CircleTool()
    tool.activate(_ctx(s, stack))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))  # center placed -> DRAWING

    before = tool.segments
    assert tool.apply_typed_value("12s", U) is True
    assert tool.segments == 12 and tool.segments != before
    # Mirrors polygon's "Ns" completion: setting the count keeps the gesture
    # open (it does not commit geometry), same as PolygonTool.
    assert tool.has_active_gesture


# ---------------------------------------------------------------------------
# #55b — Signed Rotate angle ("-30")
# ---------------------------------------------------------------------------


def test_rotate_accepts_a_negative_angle():
    """RotateTool.apply_typed_value guards on `_stage == _Stage.HAVE_START`
    (rotate_tool.py). A fresh tool's _start_dir/_cur_dir default to the same
    vector (zero swept angle), which would let a naive `sign(sweep) *
    radians(deg)` accidentally reproduce the right sign without actually
    fixing the double-negation bug. So this sets up a mouse sweep in the
    OPPOSITE direction from the typed sign (start +X, swept to -Y, i.e. a
    -90 degree sweep) -- under the old buggy logic
    (`sign(sweep) * radians(deg)`), sign(sweep) = -1 and radians(-30) is
    negative, so the old code would produce angle = -1 * -30 deg = +30 deg
    (the explicit "-" silently cancelled). The fix must keep an explicitly
    negative typed angle negative regardless of sweep direction.
    """
    tool = RotateTool()
    tool._stage = _Stage.HAVE_START
    tool._normal = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    tool._start_dir = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    tool._cur_dir = np.array([0.0, -1.0, 0.0], dtype=np.float32)  # swept -90 deg

    assert tool.apply_typed_value("-30", U) is True
    assert tool.angle_degrees < 0


# ---------------------------------------------------------------------------
# #55c — Per-axis Scale factors ("2,1,1")
# ---------------------------------------------------------------------------


def test_scale_accepts_per_axis_factors():
    """ScaleTool.apply_typed_value guards on `_active is None` (scale_tool.py).
    Following test_scale_tool_cursor_plane.py's fixture convention: build a
    GripSpec and set tool._active directly on a fresh (never-activated) tool
    rather than going through activate()."""
    tool = ScaleTool()
    grip = GripSpec(
        position=np.array([1.0, 0.0, 0.0], np.float32),
        opposite=np.array([0.0, 0.0, 0.0], np.float32),
        axes=(0,),
    )
    tool._active = grip

    assert tool.apply_typed_value("2,1,1", U) is True
    # Real attribute name is `_factor_vec` (private; ScaleTool has no public
    # `factor_vec` property -- unlike CircleTool.segments/RotateTool.angle_degrees
    # which this task adds, this one is intentionally the internal name).
    assert tuple(round(float(f), 3) for f in tool._factor_vec) == (2.0, 1.0, 1.0)

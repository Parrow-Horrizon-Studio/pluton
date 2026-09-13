"""M7.5b Task 10: editing a face's texture placement numerically."""

from __future__ import annotations

import math

import numpy as np
from pluton.scene.scene import Side, TexturePlacement


def _square(scene):
    v = [
        scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32)),
    ]
    for a, b in zip(v, v[1:] + v[:1], strict=True):
        scene.add_edge(a, b)
    return scene.add_face_from_loop(v)


def test_editing_a_field_goes_through_the_command_stack(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    f = _square(scene)
    panel = win._properties_dock
    panel.set_placement_target(f, Side.FRONT)
    depth = len(win._command_stack._undo)

    panel._apply_placement(TexturePlacement(offset_u=0.5, scale=2.0))

    assert len(win._command_stack._undo) == depth + 1
    assert scene.face_placement(f).offset_u == 0.5
    assert scene.face_placement(f).scale == 2.0


def test_undo_restores_the_previous_placement(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    f = _square(scene)
    scene.set_face_placement(f, TexturePlacement(offset_u=1.0))
    panel = win._properties_dock
    panel.set_placement_target(f, Side.FRONT)

    panel._apply_placement(TexturePlacement(offset_u=9.0))
    win._command_stack.undo()
    assert scene.face_placement(f).offset_u == 1.0


def test_the_panel_edits_the_side_it_was_given(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    f = _square(scene)
    panel = win._properties_dock
    panel.set_placement_target(f, Side.BACK)

    panel._apply_placement(TexturePlacement(scale=3.0))
    assert scene.face_placement(f, Side.BACK).scale == 3.0
    assert scene.face_placement(f, Side.FRONT).scale == 1.0


def test_rotation_is_shown_in_degrees_and_stored_in_radians(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    f = _square(scene)
    panel = win._properties_dock
    panel.set_placement_target(f, Side.FRONT)

    panel._apply_placement_from_widgets(offset_u=0.0, offset_v=0.0, scale=1.0, rotation_deg=90.0)
    assert scene.face_placement(f).rotation == __import__("pytest").approx(math.pi / 2.0)

    panel.set_placement_target(f, Side.FRONT)
    assert panel._rotation_widget_value() == __import__("pytest").approx(90.0)


def test_setting_every_field_back_to_the_identity_clears_the_entry(main_window):
    win = main_window
    scene = win._model.active_context.mesh
    f = _square(scene)
    panel = win._properties_dock
    panel.set_placement_target(f, Side.FRONT)

    panel._apply_placement(TexturePlacement(scale=2.0))
    panel._apply_placement(TexturePlacement())
    assert scene.faces_with_placement() == []

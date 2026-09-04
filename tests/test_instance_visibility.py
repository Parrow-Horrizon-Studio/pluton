"""Per-instance hide (M7.3 Task 2): new Instance fields + the three prunes."""

from __future__ import annotations

import numpy as np


def _square(model, z=0.0):
    scene = model.active_context.mesh
    v = [
        scene.add_vertex(np.array([0.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, z], dtype=np.float32)),
    ]
    scene.add_face_from_loop(v)


def test_a_new_instance_is_named_empty_and_visible(model_factory, group_factory):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    assert instance.name == ""
    assert instance.hidden is False


def test_hiding_an_instance_removes_it_from_traverse_visible(model_factory, group_factory):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    visible = [d for d, _w in model.traverse_visible()]
    assert instance.definition in visible

    instance.hidden = True

    assert instance.definition not in [d for d, _w in model.traverse_visible()]


def test_hiding_an_instance_hides_its_whole_subtree(model_factory, group_factory):
    model = model_factory()
    _square(model)
    outer = group_factory(model)
    # Nest a second group inside outer's definition, so inner is genuinely part
    # of outer's subtree (not merely created after it).
    model.enter(outer)
    _square(model, z=1.0)
    inner = group_factory(model)
    model.exit_one()

    outer.hidden = True

    visible = [d for d, _w in model.traverse_visible()]
    assert outer.definition not in visible
    assert inner.definition not in visible


def test_an_entered_instance_stays_visible_even_when_hidden(model_factory, group_factory):
    # The active-path bypass: you must still be able to see and edit inside a
    # group you have entered, exactly as tag visibility already behaves.
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    instance.hidden = True
    model.enter(instance)

    assert instance.definition in [d for d, _w in model.traverse_visible()]


def test_a_hidden_instance_is_not_pickable(model_factory, group_factory):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    origin = np.array([0.5, 0.5, 5.0], dtype=np.float64)
    direction = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    assert model.pick_instance(origin, direction) is instance

    instance.hidden = True

    assert model.pick_instance(origin, direction) is None


def test_a_hidden_instance_contributes_no_face_to_pick_face_local(
    model_factory, group_factory
):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    origin = np.array([0.5, 0.5, 5.0], dtype=np.float64)
    direction = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    assert model.pick_face_local(origin, direction) is not None

    instance.hidden = True

    assert model.pick_face_local(origin, direction) is None


def test_an_instance_can_be_named(model_factory, group_factory):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    instance.name = "North Wing"
    assert instance.name == "North Wing"

from __future__ import annotations

import numpy as np
from pluton.commands.opening_commands import PlaceOpeningCommand
from pluton.model.model import Model


def _cmd(model, kind="door"):
    return PlaceOpeningCommand(kind, 0.9, 2.1, 0.1, np.eye(4), model.active_context)


def test_identical_placements_share_one_component_two_instances():
    model = Model()
    target = model.active_context
    _cmd(model).do(model)
    _cmd(model).do(model)
    assert len(target.children) == 2
    d0 = target.children[0].definition
    d1 = target.children[1].definition
    assert d0 is d1                       # shared Component
    assert d0.is_group is False           # a Component, not a group
    assert d0.name == "Door"


def test_different_params_distinct_definitions():
    model = Model()
    target = model.active_context
    PlaceOpeningCommand("door", 0.9, 2.1, 0.1, np.eye(4), target).do(model)
    PlaceOpeningCommand("window", 1.2, 1.2, 0.1, np.eye(4), target).do(model)
    assert target.children[0].definition is not target.children[1].definition


def test_undo_detaches_instance_but_keeps_definition_registered():
    model = Model()
    target = model.active_context
    cmd = _cmd(model)
    cmd.do(model)
    assert len(target.children) == 1
    cmd.undo(model)
    assert len(target.children) == 0
    # the Definition stays registered so a later placement reuses it
    assert ("door", 0.9, 2.1, 0.1) in model.opening_definitions
    cmd.do(model)                          # redo reuses the registered Definition
    assert len(target.children) == 1


def test_transform_is_applied_to_the_instance():
    model = Model()
    t = np.eye(4)
    t[:3, 3] = [5.0, 6.0, 0.9]
    PlaceOpeningCommand("door", 0.9, 2.1, 0.1, t, model.active_context).do(model)
    inst = model.active_context.children[-1]
    assert np.allclose(inst.transform[:3, 3], [5.0, 6.0, 0.9])


def test_degenerate_opening_adds_nothing():
    model = Model()
    PlaceOpeningCommand("door", 0.05, 2.1, 0.1, np.eye(4), model.active_context).do(model)
    assert len(model.active_context.children) == 0

"""Tests for the command framework — Command ABC, CompositeCommand, CommandStack."""

from __future__ import annotations

import numpy as np


class _RecordingCommand:
    """Test helper: records call order without needing a real Scene."""

    def __init__(self, label: str, log: list[str]) -> None:
        self._label = label
        self._log = log

    def do(self, scene) -> None:  # noqa: ANN001
        self._log.append(f"do:{self._label}")

    def undo(self, scene) -> None:  # noqa: ANN001
        self._log.append(f"undo:{self._label}")


def test_composite_do_runs_children_in_order():
    from pluton.commands import CompositeCommand

    log: list[str] = []
    composite = CompositeCommand(
        name="Test",
        children=[_RecordingCommand("a", log), _RecordingCommand("b", log), _RecordingCommand("c", log)],
    )
    composite.do(None)
    assert log == ["do:a", "do:b", "do:c"]


def test_composite_undo_runs_children_in_reverse_order():
    from pluton.commands import CompositeCommand

    log: list[str] = []
    composite = CompositeCommand(
        name="Test",
        children=[_RecordingCommand("a", log), _RecordingCommand("b", log), _RecordingCommand("c", log)],
    )
    composite.undo(None)
    assert log == ["undo:c", "undo:b", "undo:a"]


def test_command_stack_starts_empty():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert not s.can_undo
    assert not s.can_redo


def test_execute_runs_do_and_pushes_to_undo_stack():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    assert log == ["do:x"]
    assert s.can_undo
    assert not s.can_redo


def test_push_executed_appends_without_calling_do():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.push_executed(cmd)
    assert log == []  # do was NOT called
    assert s.can_undo


def test_undo_calls_command_undo_and_moves_to_redo():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    log.clear()
    assert s.undo(scene=None) is True
    assert log == ["undo:x"]
    assert not s.can_undo
    assert s.can_redo


def test_redo_runs_do_again():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    s.undo(scene=None)
    log.clear()
    assert s.redo(scene=None) is True
    assert log == ["do:x"]


def test_new_execute_clears_redo_stack():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    s = CommandStack()
    cmd_a = CompositeCommand(name="A", children=[_RecordingCommand("a", log)])
    cmd_b = CompositeCommand(name="B", children=[_RecordingCommand("b", log)])
    s.execute(cmd_a, scene=None)
    s.undo(scene=None)
    assert s.can_redo
    s.execute(cmd_b, scene=None)
    assert not s.can_redo  # new execute cleared redo


def test_undo_on_empty_returns_false():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert s.undo(scene=None) is False


def test_redo_on_empty_returns_false():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert s.redo(scene=None) is False

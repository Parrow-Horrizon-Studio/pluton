"""CommandStack: undo + redo with execute / push_executed semantics."""

from __future__ import annotations

from pluton.commands.command import Command


class CommandStack:
    """Owns the undo + redo stacks. Owned by MainWindow."""

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def execute(self, cmd: Command, scene) -> None:  # noqa: ANN001
        """Run cmd.do(scene), push to undo stack, clear redo stack."""
        cmd.do(scene)
        self._undo.append(cmd)
        self._redo.clear()

    def push_executed(self, cmd: Command) -> None:
        """Append a command whose do() was already called incrementally.

        Used by tools that build a CompositeCommand mutating the scene as
        the gesture progresses so the snap engine sees in-progress state.
        At gesture completion the tool calls push_executed(composite) to
        register it for undo without re-executing.
        """
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self, scene) -> bool:  # noqa: ANN001
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo(scene)
        self._redo.append(cmd)
        return True

    def redo(self, scene) -> bool:  # noqa: ANN001
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.do(scene)
        self._undo.append(cmd)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

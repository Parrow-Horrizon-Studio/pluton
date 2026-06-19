"""CommandStack: undo + redo with execute / push_executed semantics."""

from __future__ import annotations

from pluton.commands.command import Command


class CommandStack:
    """Owns the undo + redo stacks. Owned by MainWindow."""

    def __init__(self) -> None:
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []
        self._on_after_undo: list = []  # list[Callable[[], None]]
        self._on_after_redo: list = []  # list[Callable[[], None]]

    def add_undo_listener(self, fn) -> None:  # noqa: ANN001
        """Register a zero-arg callable to invoke after each successful undo."""
        self._on_after_undo.append(fn)

    def add_redo_listener(self, fn) -> None:  # noqa: ANN001
        """Register a zero-arg callable to invoke after each successful redo."""
        self._on_after_redo.append(fn)

    def execute(self, cmd: Command, target) -> None:  # noqa: ANN001
        """Run cmd.do(target), push (cmd, target) to undo stack, clear redo stack."""
        cmd.do(target)
        self._undo.append((cmd, target))
        self._redo.clear()

    def push_executed(self, cmd: Command, target) -> None:  # noqa: ANN001
        """Append a command whose do() was already called incrementally.

        Used by tools that build a CompositeCommand mutating the scene as
        the gesture progresses so the snap engine sees in-progress state.
        At gesture completion the tool calls push_executed(composite, scene) to
        register it for undo without re-executing.
        """
        self._undo.append((cmd, target))
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd, target = self._undo.pop()
        cmd.undo(target)
        self._redo.append((cmd, target))
        for fn in self._on_after_undo:
            fn()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd, target = self._redo.pop()
        cmd.do(target)
        self._undo.append((cmd, target))
        for fn in self._on_after_redo:
            fn()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

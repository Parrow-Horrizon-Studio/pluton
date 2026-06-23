"""Tag commands (M5c): TagInstancesCommand."""

from __future__ import annotations

from pluton.commands.command import Command

_UNTAGGED_ID = 0  # == TagLibrary.UNTAGGED_ID


class TagInstancesCommand(Command):
    """Assign a tag to a set of instances; undo restores each instance's prior tag.

    Captures each instance's previous tag at do() time (id-preserving undo).
    Group commands take the model as their target, so do/undo take `model`.
    """

    name = "Assign Tag"

    def __init__(self, instances, new_tag_id: int) -> None:
        self._instances = list(instances)
        self._new = int(new_tag_id)
        self._old: dict[int, int] = {}

    def do(self, model) -> None:  # noqa: ANN001
        for inst in self._instances:
            self._old[inst.id] = inst.tag_id
            inst.tag_id = self._new

    def undo(self, model) -> None:  # noqa: ANN001
        for inst in self._instances:
            inst.tag_id = self._old.get(inst.id, _UNTAGGED_ID)

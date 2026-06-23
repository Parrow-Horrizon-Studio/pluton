"""Tags ('Layers') for organizing objects + per-tag visibility (M5c).

Pure Python — no GL, no Qt — so it is fully unit-testable headlessly. Tags
attach to group/component Instances via Instance.tag_id; the renderer and
picking consult TagLibrary.is_visible to hide objects on a hidden tag. The
library is serialization-ready for M6 file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Tag:
    """A named tag. `visible` is mutable view state (not part of undo)."""

    id: int
    name: str
    visible: bool = True


class TagLibrary:
    """Owns the model's Tag objects: Untagged first, then user tags."""

    UNTAGGED_ID = 0

    def __init__(self) -> None:
        self._untagged = Tag(self.UNTAGGED_ID, "Untagged", True)
        self._tags: dict[int, Tag] = {self.UNTAGGED_ID: self._untagged}
        self._order: list[int] = [self.UNTAGGED_ID]
        self._next_id = 1

    def add(self, name: str) -> Tag:
        """Append a new tag with a fresh monotonic id and return it."""
        tag = Tag(self._next_id, str(name), True)
        self._tags[tag.id] = tag
        self._order.append(tag.id)
        self._next_id += 1
        return tag

    def get(self, tid: int) -> Tag:
        """Return the tag for `tid`, or the Untagged tag if unknown."""
        return self._tags.get(tid, self._untagged)

    def tags(self) -> list[Tag]:
        """All tags in display order (Untagged first)."""
        return [self._tags[i] for i in self._order]

    def set_visible(self, tid: int, visible: bool) -> None:
        """Set a tag's visibility. No-op for Untagged (always visible)."""
        if tid == self.UNTAGGED_ID:
            return
        tag = self._tags.get(tid)
        if tag is not None:
            tag.visible = bool(visible)

    def is_visible(self, tid: int) -> bool:
        """Whether entities on this tag should be drawn (Untagged always True)."""
        return self.get(tid).visible

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

    def rename(self, tid: int, name: str) -> None:
        """Rename a user tag. No-op for Untagged or an empty name."""
        if tid == self.UNTAGGED_ID:
            return
        tag = self._tags.get(tid)
        if tag is not None and name:
            tag.name = str(name)

    def is_visible(self, tid: int) -> bool:
        """Whether entities on this tag should be drawn (Untagged always True)."""
        return self.get(tid).visible

    @property
    def next_id(self) -> int:
        return self._next_id

    def to_records(self) -> list[dict]:
        """Serialize all tags in display order (Untagged first)."""
        return [{"id": t.id, "name": t.name, "visible": t.visible} for t in self.tags()]

    @classmethod
    def from_records(cls, records: list[dict], next_id: int) -> "TagLibrary":
        """Rebuild a library authoritatively from saved records (no auto-seed)."""
        lib = cls()  # seeds Untagged, then we overwrite
        lib._tags = {}
        lib._order = []
        for r in records:
            tag = Tag(int(r["id"]), str(r["name"]), bool(r["visible"]))
            lib._tags[tag.id] = tag
            lib._order.append(tag.id)
        lib._untagged = lib._tags.get(cls.UNTAGGED_ID, lib._untagged)
        lib._next_id = int(next_id)
        return lib

"""Shared, transient selection state: which edges and faces are selected.

Owned by MainWindow, handed to tools (via ToolContext) and the renderer. NOT
part of the Scene geometry model and NOT on the undo stack (selecting is not an
undoable action; only deletions are). `version` bumps on every mutation so the
renderer can cheaply detect changes.
"""

from __future__ import annotations

from collections.abc import Iterable


class Selection:
    __slots__ = ("_edges", "_faces", "_version")

    def __init__(self) -> None:
        self._edges: set[int] = set()
        self._faces: set[int] = set()
        self._version: int = 0

    @property
    def edges(self) -> set[int]:
        return self._edges

    @property
    def faces(self) -> set[int]:
        return self._faces

    @property
    def version(self) -> int:
        return self._version

    def _bump(self) -> None:
        self._version += 1

    def replace(self, *, edges: Iterable[int] = (), faces: Iterable[int] = ()) -> None:
        self._edges = set(edges)
        self._faces = set(faces)
        self._bump()

    def add(self, *, edges: Iterable[int] = (), faces: Iterable[int] = ()) -> None:
        self._edges |= set(edges)
        self._faces |= set(faces)
        self._bump()

    def toggle_edge(self, e_id: int) -> None:
        self._edges.symmetric_difference_update({e_id})
        self._bump()

    def toggle_face(self, f_id: int) -> None:
        self._faces.symmetric_difference_update({f_id})
        self._bump()

    def clear(self) -> None:
        if self._edges or self._faces:
            self._edges.clear()
            self._faces.clear()
            self._bump()

    def contains_edge(self, e_id: int) -> bool:
        return e_id in self._edges

    def contains_face(self, f_id: int) -> bool:
        return f_id in self._faces

    def is_empty(self) -> bool:
        return not self._edges and not self._faces

    def counts(self) -> tuple[int, int]:
        return (len(self._edges), len(self._faces))

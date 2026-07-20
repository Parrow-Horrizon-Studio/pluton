"""Annotation entities (M7d): linear dimensions and leader text labels.

Both store CONTEXT-LOCAL coordinates as plain 3-tuples and live in
Definition.annotations, so they ride along when their group/component moves.
Pure data — no Model/Scene/Qt/GL imports. A dimension's measurement text is
NOT stored; it is derived at draw time from the world distance and the
document's units.
"""
from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float, float]


def _pt(value) -> Point:
    x, y, z = value
    return (float(x), float(y), float(z))


@dataclass
class Dimension:
    """A linear dimension between two local points.

    `offset` is a local vector from the p1->p2 midpoint to the dimension-line
    midpoint (it positions the dimension line away from the geometry).
    """

    id: int
    p1: Point
    p2: Point
    offset: Point
    kind: str = "dimension"

    def __post_init__(self) -> None:
        self.id = int(self.id)
        self.p1 = _pt(self.p1)
        self.p2 = _pt(self.p2)
        self.offset = _pt(self.offset)


@dataclass
class Label:
    """A text note: an anchor point, where the text sits, and the text."""

    id: int
    anchor: Point
    text_pos: Point
    text: str
    kind: str = "label"

    def __post_init__(self) -> None:
        self.id = int(self.id)
        self.anchor = _pt(self.anchor)
        self.text_pos = _pt(self.text_pos)
        self.text = str(self.text)

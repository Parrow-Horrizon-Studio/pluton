"""Shared vocabulary for the snap & inference engine.

`snap_engine.py` (the selection policy) and `snap_candidates.py` (the pure
geometry generators) both need `SnapKind` and `Candidate`, and neither may
import the other without creating a cycle. This module exists so they can
share that vocabulary without importing each other: it deliberately depends
on nothing else in `pluton.viewport`.

`AcquiredKind` and `Acquired` live here too, for the same reason: Task 4's
candidate generators in `snap_candidates.py` need `AcquiredKind` without
importing `inference.py` (which is stateful and depends on this module).
`inference.py` imports both from here and re-exports them. This module must
keep depending on nothing but numpy and the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np


class SnapKind(IntEnum):
    """Snap kinds, ordered by precedence (higher wins on a tie)."""

    NONE = 0
    GRID = 1
    AXIS_LOCK = 2
    MIDPOINT = 3
    ENDPOINT = 4
    ON_FACE = 5
    ON_EDGE = 6
    INTERSECTION = 7
    PARALLEL = 8
    PERPENDICULAR = 9
    FROM_POINT = 10


@dataclass(frozen=True, slots=True)
class SnapResult:
    """The chosen snap for one cursor position."""

    kind: SnapKind
    world_position: np.ndarray
    axis: int | None  # 0=X (red), 1=Y (green), 2=Z (blue); AXIS_LOCK and FROM_POINT
    vertex_id: int | None  # only ENDPOINT
    label: str
    edge_id: int | None = None  # MIDPOINT / ON_EDGE / INTERSECTION
    face_id: int | None = None  # ON_FACE
    edge_t: float | None = None  # parameter along edge_id (drives split_edge)


@dataclass
class Candidate:
    """One in-tolerance snap candidate, before precedence selection."""

    kind: SnapKind
    world_position: np.ndarray
    screen_dist: float
    depth: float
    label: str
    vertex_id: int | None = None
    edge_id: int | None = None
    face_id: int | None = None
    axis: int | None = None
    edge_t: float | None = None


class AcquiredKind(IntEnum):
    NONE = 0
    VERTEX = 1
    EDGE = 2


@dataclass(frozen=True, slots=True)
class Acquired:
    """A reference the cursor dwelled on, and what it can infer from."""

    kind: AcquiredKind
    position: np.ndarray
    direction: np.ndarray | None
    entity_id: int

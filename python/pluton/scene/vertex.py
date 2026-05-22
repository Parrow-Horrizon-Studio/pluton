"""A single vertex in the Python scene."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Vertex:
    """A vertex with a stable integer ID and a Z-up world-space position.

    `position` is an (3,) float32 numpy array. Positions are exact — the snap
    engine produces deterministic snapped points, and `Scene.add_vertex` uses
    exact equality (not an epsilon) for idempotent insertion.
    """

    id: int
    position: np.ndarray

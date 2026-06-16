"""Pure transform math for Move / Rotate / Scale.

All functions take and return (N, 3) float32 arrays and have no dependency on
Qt, OpenGL, or the Scene. Move/Rotate/Scale tools resolve which vertices to
transform, then call these to get the new positions.
"""

from __future__ import annotations

import numpy as np


def translate(points: np.ndarray, delta) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    d = np.asarray(delta, dtype=np.float32).reshape(3)
    return (pts + d).astype(np.float32)


def rotate(points: np.ndarray, center, axis, angle_rad: float) -> np.ndarray:
    """Rotate points about the line through `center` along `axis` (Rodrigues).

    `axis` need not be unit length. Raises ValueError on a near-zero axis.
    """
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3).astype(np.float64)
    c = np.asarray(center, dtype=np.float64).reshape(3)
    k = np.asarray(axis, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(k))
    if norm < 1e-9:
        raise ValueError("rotate: degenerate (near-zero) axis")
    k = k / norm
    a = float(angle_rad)
    cos_a, sin_a = np.cos(a), np.sin(a)
    rel = pts - c
    cross = np.cross(np.broadcast_to(k, rel.shape), rel)
    dot = rel @ k
    rot = rel * cos_a + cross * sin_a + np.outer(dot, k) * (1.0 - cos_a)
    return (rot + c).astype(np.float32)


def scale(points: np.ndarray, anchor, factors) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    a = np.asarray(anchor, dtype=np.float32).reshape(3)
    f = np.asarray(factors, dtype=np.float32).reshape(3)
    return (a + (pts - a) * f).astype(np.float32)

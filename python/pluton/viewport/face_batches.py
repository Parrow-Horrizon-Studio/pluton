"""Group a definition's triangles by material into contiguous draw batches (M5b).

Pure Python + numpy — no GL — so it is fully unit-testable headlessly. The
renderer reorders its interleaved face VBO by `vertex_order` so each material's
triangles are contiguous, then issues one glDrawArrays per FaceBatch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class FaceBatch:
    """A contiguous run of same-material vertices in the (reordered) face VBO."""

    material_id: int
    first: int   # first vertex index
    count: int   # vertex count (a multiple of 3)


def plan_face_batches(
    triangle_material_ids: Sequence[int],
) -> tuple[np.ndarray, list[FaceBatch]]:
    """Stable-sort triangles by material id into contiguous batches.

    Args:
        triangle_material_ids: material id of each triangle, length T, in
            face-VBO order (e.g. Scene.face_triangle_materials()).

    Returns:
        vertex_order: int64 permutation of 0..3T-1 to apply to the (3T, .)
            vertex arrays so each material's triangles are contiguous. Identity
            when triangles are already grouped (e.g. all one material).
        batches: one FaceBatch per distinct material, ascending by material id.
            Empty when T == 0.
    """
    tri_mats = np.asarray(triangle_material_ids, dtype=np.int64)
    t = int(tri_mats.shape[0])
    if t == 0:
        return np.zeros(0, dtype=np.int64), []

    tri_order = np.argsort(tri_mats, kind="stable")          # stable: keeps in-group order
    sorted_mats = tri_mats[tri_order]
    vertex_order = (tri_order[:, None] * 3 + np.arange(3)).reshape(-1).astype(np.int64)

    batches: list[FaceBatch] = []
    uniq, starts = np.unique(sorted_mats, return_index=True)  # ascending mat id, group starts
    for k, mid in enumerate(uniq):
        tri_start = int(starts[k])
        tri_end = int(starts[k + 1]) if k + 1 < len(starts) else t
        n_tris = tri_end - tri_start
        batches.append(FaceBatch(material_id=int(mid), first=tri_start * 3, count=n_tris * 3))
    return vertex_order, batches

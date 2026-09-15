"""Carry a face's stored per-corner UVs across an edge split.

Pure arithmetic over loops and coordinate pairs. No Scene, no kernel, no numpy,
so these functions are testable in isolation and cheap to reason about.
"""

from __future__ import annotations

from collections.abc import Sequence


def transfer_uvs_across_split(
    old_uvs: Sequence[tuple[float, float]],
    old_loop: Sequence[int],
    new_loop: Sequence[int],
    w: int,
    va: int,
    vb: int,
    t: float,
) -> list[tuple[float, float]] | None:
    """`old_uvs` re-ordered onto `new_loop`, with one lerped entry for `w`.

    `t` is measured from `va` toward `vb`, which is the kernel's convention and
    is NOT necessarily the direction this face's loop traverses the edge. When
    the loop runs vb-then-va the inserted corner sits at `1 - t` along the
    loop's own direction, and using `t` there would misplace the corner on
    roughly half of a model's faces.

    Returns None when the inputs are not a single clean insertion, which is the
    caller's signal to drop that face to the projection rather than guess.
    """
    if len(old_uvs) != len(old_loop):
        return None
    if len(new_loop) != len(old_loop) + 1:
        return None

    try:
        insert_at = list(new_loop).index(w)
    except ValueError:
        return None

    n_new = len(new_loop)
    prev_v = new_loop[insert_at - 1]
    next_v = new_loop[(insert_at + 1) % n_new]

    # Position of every surviving vertex in the OLD loop, so each keeps its own
    # UV regardless of where the insertion shifted it to.
    old_index = {int(v): i for i, v in enumerate(old_loop)}
    if len(old_index) != len(old_loop):
        return None  # a repeated vertex makes the mapping ambiguous
    if prev_v not in old_index or next_v not in old_index:
        return None
    if {int(prev_v), int(next_v)} != {int(va), int(vb)}:
        return None

    uv_prev = old_uvs[old_index[int(prev_v)]]
    uv_next = old_uvs[old_index[int(next_v)]]
    frac = float(t) if int(prev_v) == int(va) else 1.0 - float(t)
    inserted = (
        uv_prev[0] + (uv_next[0] - uv_prev[0]) * frac,
        uv_prev[1] + (uv_next[1] - uv_prev[1]) * frac,
    )

    out: list[tuple[float, float]] = []
    for i, v in enumerate(new_loop):
        if i == insert_at:
            out.append(inserted)
        else:
            uv = old_uvs[old_index[int(v)]]
            out.append((float(uv[0]), float(uv[1])))
    return out

"""Read-only queries over the model graph (M7.2).

Both functions are pure: they walk the graph and return plain data, mutating
nothing. select_all_ids backs Edit > Select All; model_bounds backs
View > Zoom Extents.

Both honour the active editing context and tag visibility, so they agree with
what the user can actually see and click.
"""

from __future__ import annotations

import numpy as np

from pluton.geometry.transforms import apply_mat


def select_all_ids(model) -> tuple[set[int], set[int], set[int]]:
    """Every selectable entity in the active editing context.

    Returns (edge_ids, face_ids, instance_ids), scoped to the active context
    only -- matching how every other operation behaves -- and skipping
    instances hidden by tag visibility, so Select All never selects something
    the user cannot see. Does not reach into child definitions: an instance
    itself is selectable, but the geometry nested inside it is not part of
    this context's selection.
    """
    context = model.active_context
    scene = context.mesh

    edges = {e.id for e in scene.edges_iter()}
    faces = {f.id for f in scene.faces_iter()}
    instances = {child.id for child in context.children if model.tags.is_visible(child.tag_id)}
    return edges, faces, instances


def model_bounds(model) -> tuple[np.ndarray, np.ndarray] | None:
    """The world-space axis-aligned bounds of everything currently visible.

    Returns (min_xyz, max_xyz) as float32 arrays, or None when nothing is
    visible -- an empty model, or every tag hidden. Callers treat None as
    "nothing to frame" and do nothing.

    Walks every definition reachable via traverse_visible() (so hidden-tag
    subtrees are excluded but the active editing context is always included),
    and transforms each definition's live vertex positions into world space
    with its accumulated world transform before folding them into the box --
    a definition's own geometry is otherwise only known in local coordinates.
    """
    lo: np.ndarray | None = None
    hi: np.ndarray | None = None

    for definition, world in model.traverse_visible():
        positions = [v.position for v in definition.mesh.vertices_iter()]
        if not positions:
            continue
        local = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
        world_points = apply_mat(local, world)
        def_lo = world_points.min(axis=0)
        def_hi = world_points.max(axis=0)
        if lo is None:
            lo, hi = def_lo, def_hi
        else:
            lo = np.minimum(lo, def_lo)
            hi = np.maximum(hi, def_hi)

    if lo is None:
        return None
    return lo, hi

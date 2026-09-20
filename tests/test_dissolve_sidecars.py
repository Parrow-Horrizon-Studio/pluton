"""Scene.dissolve_edge's agree-or-drop sidecar rule (M7.6a).

Revises M7.5c's D4a ("merges are handled by neither, deliberately"): a
merged face keeps a material, placement, or per-corner UV array only when
BOTH parents carried the identical value, side by side. Disagreement --
including one side painted and the other not, since absence counts as a
value -- drops the sidecar rather than guessing a winner. This is what
makes a split-then-erase round trip lossless when the two halves still
agree, which is the whole reason M7.6a exists.
"""

from __future__ import annotations

import numpy as np
from pluton.scene.scene import DEFAULT_PLACEMENT, Scene, Side, TexturePlacement


def _two_quads_sharing_an_edge() -> tuple[Scene, int, int, int]:
    """Two adjacent unit quads on the XY plane sharing edge (v1, v2).

    Returns (scene, f1, f2, shared_edge_id).
    """
    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    v4 = s.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v5 = s.add_vertex(np.array([2.0, 1.0, 0.0], dtype=np.float32))
    f1 = s.add_face_from_loop([v0, v1, v2, v3])
    f2 = s.add_face_from_loop([v1, v4, v5, v2])
    e_shared = s.edge_between(v1, v2)
    assert e_shared is not None
    return s, f1, f2, e_shared


def test_split_then_erase_round_trip_restores_the_parents_material():
    # The case the whole rule exists for. Discriminates against the OLD
    # D4a rule ("merges are handled by neither"): that implementation would
    # leave the merged face unpainted even though both halves plainly agree.
    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([2.0, 2.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 2.0, 0.0], dtype=np.float32))
    fid = s.add_face_from_loop([v0, v1, v2, v3])
    s.set_face_material(fid, 7, Side.FRONT)
    s.add_edge(v0, v2)

    _a, _b = s.split_face(fid, [v0, v2])
    e_shared = s.edge_between(v0, v2)
    assert e_shared is not None

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert set(s.face_loop(merged)) == {v0, v1, v2, v3}
    assert s.face_material(merged, Side.FRONT) == 7


def test_two_parents_agreeing_on_material_give_the_merged_face_that_material():
    # Discriminates against an implementation that never propagates a
    # material at all (drops it unconditionally, treating "agree" the same
    # as "disagree").
    s, f1, f2, e_shared = _two_quads_sharing_an_edge()
    s.set_face_material(f1, 3, Side.FRONT)
    s.set_face_material(f2, 3, Side.FRONT)

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_material(merged, Side.FRONT) == 3


def test_two_parents_disagreeing_on_material_give_default():
    # Discriminates against an implementation that picks a winner (e.g.
    # "first parent wins") instead of dropping to Default on disagreement.
    s, f1, f2, e_shared = _two_quads_sharing_an_edge()
    s.set_face_material(f1, 3, Side.FRONT)
    s.set_face_material(f2, 4, Side.FRONT)

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_material(merged, Side.FRONT) == 0


def test_a_painted_parent_merged_with_an_unpainted_one_gives_default():
    # The specific case the brief calls out: absence counts as a value, so
    # this must NOT behave like test_two_parents_agreeing above just
    # because one side "has no opinion". Discriminates against a naive
    # merge that treats an unset sidecar as "defer to whichever parent set
    # it", which would spread the paint onto geometry the user never
    # painted.
    s, f1, _f2, e_shared = _two_quads_sharing_an_edge()
    s.set_face_material(f1, 5, Side.FRONT)
    # f2's FRONT material is left at Default (never painted).

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_material(merged, Side.FRONT) == 0


def test_the_rule_applies_independently_per_side():
    # Discriminates against an implementation that shares one decision
    # across both sides (e.g. drops BOTH sides on any single-side
    # disagreement, or copies one side's outcome onto the other).
    s, f1, f2, e_shared = _two_quads_sharing_an_edge()
    s.set_face_material(f1, 1, Side.FRONT)
    s.set_face_material(f2, 1, Side.FRONT)  # FRONT agrees
    s.set_face_material(f1, 2, Side.BACK)
    s.set_face_material(f2, 9, Side.BACK)  # BACK disagrees

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_material(merged, Side.FRONT) == 1
    assert s.face_material(merged, Side.BACK) == 0


def test_agreeing_placements_survive_the_merge_on_both_sides():
    # Discriminates against an implementation that only wires up materials
    # and leaves TexturePlacement out of the agree-or-drop rule entirely.
    s, f1, f2, e_shared = _two_quads_sharing_an_edge()
    front = TexturePlacement(offset_u=0.25, offset_v=0.5)
    back = TexturePlacement(offset_u=0.1, offset_v=0.9)
    s.set_face_placement(f1, front, Side.FRONT)
    s.set_face_placement(f2, front, Side.FRONT)
    s.set_face_placement(f1, back, Side.BACK)
    s.set_face_placement(f2, back, Side.BACK)

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_placement(merged, Side.FRONT) == front
    assert s.face_placement(merged, Side.BACK) == back


def test_disagreeing_placements_drop_to_the_default():
    s, f1, f2, e_shared = _two_quads_sharing_an_edge()
    s.set_face_placement(f1, TexturePlacement(offset_u=0.25), Side.FRONT)
    s.set_face_placement(f2, TexturePlacement(offset_u=0.75), Side.FRONT)

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    assert s.face_placement(merged, Side.FRONT) == DEFAULT_PLACEMENT


def test_stored_uvs_survive_a_split_then_dissolve_round_trip_when_they_agree():
    # A diagonal split of a quad hands each triangle child an exact copy of
    # its shared corners' UVs (no chain-vertex interpolation involved), so
    # both children agree at every vertex they hold in common. Discriminates
    # against an implementation that compares the two parents' raw UV
    # ARRAYS for equality (different lengths/orders per triangle -- always
    # unequal) instead of gathering per VERTEX, which would drop the array
    # here even though the two triangles plainly agree at every shared
    # corner.
    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([2.0, 2.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 2.0, 0.0], dtype=np.float32))
    fid = s.add_face_from_loop([v0, v1, v2, v3])
    stored = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    s.set_face_uvs(fid, stored, Side.FRONT)
    s.add_edge(v0, v2)

    _a, _b = s.split_face(fid, [v0, v2])
    e_shared = s.edge_between(v0, v2)
    assert e_shared is not None

    merged = s.dissolve_edge(e_shared)

    assert merged is not None
    uvs = s.face_uvs(merged, Side.FRONT)
    assert uvs is not None
    by_vertex = dict(zip(s.face_loop(merged), uvs, strict=True))
    for vid, expected in zip([v0, v1, v2, v3], stored, strict=True):
        got = tuple(round(float(c), 5) for c in by_vertex[vid])
        assert got == tuple(round(c, 5) for c in expected)


def test_a_parent_with_no_stored_uvs_gives_the_merged_face_none():
    s, _f1, _f2, e_shared = _two_quads_sharing_an_edge()
    merged = s.dissolve_edge(e_shared)
    assert merged is not None
    assert s.face_uvs(merged, Side.FRONT) is None

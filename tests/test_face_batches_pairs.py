"""M7.5a Task 4: pair-keyed batches and the translucent suffix."""

from __future__ import annotations

import numpy as np
from pluton.viewport.face_batches import plan_face_batches


def test_an_empty_input_gives_an_empty_plan():
    plan = plan_face_batches([], [])
    assert plan.vertex_order.shape == (0,)
    assert plan.opaque == []
    assert plan.translucent == []
    assert plan.translucent_first == 0


def test_faces_sharing_a_pair_land_in_one_batch():
    plan = plan_face_batches([1, 1, 1], [2, 2, 2])
    assert len(plan.opaque) == 1
    b = plan.opaque[0]
    assert (b.front_material_id, b.back_material_id) == (1, 2)
    assert (b.first, b.count) == (0, 9)


def test_the_same_front_with_different_backs_splits_into_two_batches():
    # The whole point of the pair key: a single-id key would merge these.
    plan = plan_face_batches([1, 1], [2, 3])
    assert len(plan.opaque) == 2
    assert {(b.front_material_id, b.back_material_id) for b in plan.opaque} == {(1, 2), (1, 3)}


def test_translucent_triangles_form_a_contiguous_suffix():
    # front ids 1,9,1,9 with 9 translucent: the two 9s must end up adjacent
    # and at the END, whatever order they arrived in.
    plan = plan_face_batches([1, 9, 1, 9], [0, 0, 0, 0], frozenset({9}))
    n_vertices = 4 * 3
    assert plan.translucent_first == 6  # two opaque triangles first
    covered = []
    for b in plan.translucent:
        assert b.first >= plan.translucent_first
        covered.extend(range(b.first, b.first + b.count))
    assert covered == list(range(plan.translucent_first, n_vertices))


def test_a_translucent_back_makes_the_whole_face_translucent():
    # Spec D5. The front is opaque; the back is not; the face goes translucent.
    plan = plan_face_batches([1], [9], frozenset({9}))
    assert plan.opaque == []
    assert len(plan.translucent) == 1
    assert plan.translucent_first == 0


def test_nothing_translucent_leaves_the_suffix_empty_and_past_the_end():
    plan = plan_face_batches([1, 2], [0, 0])
    assert plan.translucent == []
    assert plan.translucent_first == 6  # == 3T, an empty suffix


def test_the_permutation_actually_reorders_the_vertex_arrays():
    # Triangle 0 is translucent, triangle 1 is not, so they must swap.
    plan = plan_face_batches([9, 1], [0, 0], frozenset({9}))
    verts = np.arange(6 * 3).reshape(6, 3)  # 2 triangles, 3 vertices each
    reordered = verts[plan.vertex_order]
    assert reordered[0].tolist() == verts[3].tolist()
    assert plan.translucent_first == 3


def test_the_permutation_is_a_genuine_permutation():
    plan = plan_face_batches([3, 1, 2, 1], [0, 5, 0, 5], frozenset({2}))
    assert sorted(plan.vertex_order.tolist()) == list(range(12))


def test_batch_counts_cover_every_vertex_exactly_once():
    plan = plan_face_batches([1, 2, 9, 2], [0, 0, 0, 7], frozenset({9, 7}))
    covered = []
    for b in plan.opaque + plan.translucent:
        covered.extend(range(b.first, b.first + b.count))
    assert sorted(covered) == list(range(12))


def test_mismatched_side_lengths_are_rejected():
    import pytest

    with pytest.raises(ValueError):
        plan_face_batches([1, 2], [1])

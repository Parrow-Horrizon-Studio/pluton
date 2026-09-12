"""M7.5a Task 7: what draws after what.

The GL calls in the draw loop are not testable headlessly, but every *decision*
the translucent pass makes is: which definitions draw in which order, whether a
buffer needs re-planning, how the depth-sorted suffix is re-cut into batches,
and whether a sort is cached. Those are the module-level seams tested here.
"""

from __future__ import annotations

import numpy as np
import pytest
from pluton.viewport import scene_renderer
from pluton.viewport.face_batches import FaceBatch, plan_face_batches
from pluton.viewport.scene_renderer import (
    _DefBuffers,
    _reset_translucent_state,
    SceneRenderer,
    order_definitions_for_translucent_pass,
    rebuild_translucent_batches,
)


class _Fake:
    """Stands in for a Definition; the orderer only needs a centroid source."""

    def __init__(self, centroid):
        self.centroid = np.asarray(centroid, dtype=np.float64)


def _identity():
    return np.eye(4, dtype=np.float64)


def _translate(x):
    m = np.eye(4, dtype=np.float64)
    m[0, 3] = x
    return m


# --- Step 4: ordering definitions among themselves --------------------------


def test_definitions_are_ordered_farthest_first():
    near = (_Fake((0.0, 0.0, 0.0)), _identity())
    far = (_Fake((0.0, 0.0, 0.0)), _translate(50.0))
    order = order_definitions_for_translucent_pass(
        [near, far], camera_pos=np.array([0.0, 0.0, 0.0]), centroid_of=lambda d: d.centroid
    )
    assert order == [1, 0]


def test_the_world_transform_is_applied_before_sorting():
    # Both definitions have the SAME local centroid; only their world
    # transforms differ. A sort that ignored the transform would tie.
    a = (_Fake((0.0, 0.0, 0.0)), _translate(1.0))
    b = (_Fake((0.0, 0.0, 0.0)), _translate(30.0))
    order = order_definitions_for_translucent_pass(
        [a, b], camera_pos=np.array([0.0, 0.0, 0.0]), centroid_of=lambda d: d.centroid
    )
    assert order == [1, 0]


def test_moving_the_camera_reverses_the_order():
    a = (_Fake((0.0, 0.0, 0.0)), _translate(0.0))
    b = (_Fake((0.0, 0.0, 0.0)), _translate(20.0))
    near_a = order_definitions_for_translucent_pass(
        [a, b], camera_pos=np.array([-10.0, 0.0, 0.0]), centroid_of=lambda d: d.centroid
    )
    near_b = order_definitions_for_translucent_pass(
        [a, b], camera_pos=np.array([30.0, 0.0, 0.0]), centroid_of=lambda d: d.centroid
    )
    assert near_a == list(reversed(near_b))


def test_an_empty_list_orders_to_nothing():
    assert (
        order_definitions_for_translucent_pass(
            [], camera_pos=np.array([0.0, 0.0, 0.0]), centroid_of=lambda d: d.centroid
        )
        == []
    )


# --- Step 6b: re-planning when a material crosses the boundary --------------


def test_editing_alpha_moves_a_material_between_the_partitions():
    opaque_plan = plan_face_batches([1, 2], [0, 0], frozenset())
    assert opaque_plan.translucent == []

    # the same geometry, once material 2 has been edited translucent
    translucent_plan = plan_face_batches([1, 2], [0, 0], frozenset({2}))
    assert len(translucent_plan.translucent) == 1
    assert len(translucent_plan.opaque) == 1


def test_a_colour_edit_does_not_change_the_partition():
    # A colour edit leaves the translucent id set alone, so the plan is
    # identical. A renderer that re-uploaded on every edit would still pass
    # this, so it is paired with the buffer-level tests below.
    before = plan_face_batches([1, 2], [0, 0], frozenset({2}))
    after = plan_face_batches([1, 2], [0, 0], frozenset({2}))
    assert before.translucent_first == after.translucent_first
    assert [b.first for b in before.opaque] == [b.first for b in after.opaque]


class _FakeMesh:
    def __init__(self):
        self.dirty = False
        self.clean_calls = 0

    def mark_clean(self):
        self.dirty = False
        self.clean_calls += 1


class _FakeDefinition:
    def __init__(self):
        self.mesh = _FakeMesh()


@pytest.fixture
def stubbed_renderer(monkeypatch):
    """A SceneRenderer whose _upload_definition is a counted stub.

    Lets _ensure_buffers be exercised without a GL context, so the
    reuse-vs-rebuild decision can be observed directly rather than inferred.
    """
    r = SceneRenderer()
    calls = []

    def fake_upload(definition, translucent_ids):
        calls.append(translucent_ids)
        return _DefBuffers(translucent_ids=translucent_ids)

    monkeypatch.setattr(r, "_upload_definition", fake_upload)
    return r, calls


def test_an_unchanged_translucent_set_reuses_the_buffer(stubbed_renderer):
    # Kills a renderer that re-uploads unconditionally every frame: it would
    # return a fresh buffer and record a second upload call.
    r, calls = stubbed_renderer
    defn = _FakeDefinition()
    first = r._ensure_buffers(defn, frozenset({2}))
    again = r._ensure_buffers(defn, frozenset({2}))
    assert again is first
    assert len(calls) == 1


def test_a_changed_translucent_set_rebuilds_the_buffer(stubbed_renderer):
    # Kills the bug Step 6b exists for: editing a material's alpha dirties no
    # mesh, so a renderer keyed only on mesh.dirty keeps the stale partition
    # and goes on drawing the now-translucent material in the opaque pass.
    r, calls = stubbed_renderer
    defn = _FakeDefinition()
    first = r._ensure_buffers(defn, frozenset({2}))
    changed = r._ensure_buffers(defn, frozenset({2, 3}))
    assert changed is not first
    assert calls == [frozenset({2}), frozenset({2, 3})]
    assert changed.translucent_ids == frozenset({2, 3})


def test_a_dirty_mesh_still_rebuilds_the_buffer(stubbed_renderer):
    # The pre-existing invalidation must survive the new one being added.
    r, calls = stubbed_renderer
    defn = _FakeDefinition()
    r._ensure_buffers(defn, frozenset({2}))
    defn.mesh.dirty = True
    r._ensure_buffers(defn, frozenset({2}))
    assert len(calls) == 2
    assert defn.mesh.clean_calls == 2  # re-upload marks the mesh clean again


def test_an_unseen_definition_uploads_once(stubbed_renderer):
    r, calls = stubbed_renderer
    r._ensure_buffers(_FakeDefinition(), frozenset())
    assert len(calls) == 1


# --- Step 6: re-cutting the sorted suffix into batches ----------------------


def test_rebuilt_batches_split_at_every_material_change():
    # Depth order interleaves two translucent materials, so the four triangles
    # must become four single-triangle batches. A rebuild that kept the
    # upload-order batches (two batches of two) would draw half the triangles
    # with the other material's uniforms.
    sorted_pairs = np.array([[9, 0], [7, 0], [9, 0], [7, 0]], dtype=np.int64)
    batches = rebuild_translucent_batches(sorted_pairs, first_vertex=6)
    assert batches == [
        FaceBatch(front_material_id=9, back_material_id=0, first=6, count=3),
        FaceBatch(front_material_id=7, back_material_id=0, first=9, count=3),
        FaceBatch(front_material_id=9, back_material_id=0, first=12, count=3),
        FaceBatch(front_material_id=7, back_material_id=0, first=15, count=3),
    ]


def test_rebuilt_batches_merge_a_run_of_one_material():
    # The common case — one translucent material — must not fragment. Kills a
    # rebuild that emitted one batch per triangle unconditionally.
    sorted_pairs = np.array([[7, 0], [7, 0], [7, 0]], dtype=np.int64)
    batches = rebuild_translucent_batches(sorted_pairs, first_vertex=0)
    assert batches == [FaceBatch(front_material_id=7, back_material_id=0, first=0, count=9)]


def test_the_back_material_alone_splits_a_batch():
    # Batches are keyed on the (front, back) PAIR. A rebuild that compared
    # only the front id would merge these two into one batch and shade the
    # second triangle's back side wrong.
    sorted_pairs = np.array([[7, 0], [7, 5]], dtype=np.int64)
    batches = rebuild_translucent_batches(sorted_pairs, first_vertex=0)
    assert [(b.front_material_id, b.back_material_id) for b in batches] == [(7, 0), (7, 5)]


def test_rebuilt_batches_cover_the_suffix_exactly():
    sorted_pairs = np.array([[1, 0], [1, 0], [2, 0], [3, 0]], dtype=np.int64)
    batches = rebuild_translucent_batches(sorted_pairs, first_vertex=12)
    assert batches[0].first == 12
    assert sum(b.count for b in batches) == 12
    for a, b in zip(batches[:-1], batches[1:], strict=True):
        assert a.first + a.count == b.first


def test_worst_case_fragmentation_is_one_batch_per_triangle():
    # Recorded deliberately rather than capped: alternating materials in depth
    # order degenerate to one draw call per triangle. This pins the bound so
    # it is a known property of option B rather than a surprise in profiling.
    n = 64
    sorted_pairs = np.array([[1 + (i % 2), 0] for i in range(n)], dtype=np.int64)
    batches = rebuild_translucent_batches(sorted_pairs, first_vertex=0)
    assert len(batches) == n


def test_an_empty_suffix_rebuilds_to_no_batches():
    assert rebuild_translucent_batches(np.zeros((0, 2), dtype=np.int64), first_vertex=0) == []


# --- Step 6: sorting the suffix and re-uploading it -------------------------


def _tri_rows(centroid_x: float) -> np.ndarray:
    """Three interleaved (pos, normal) rows for a triangle centred at x."""
    return np.array(
        [
            [centroid_x, -0.5, 0.0, 0.0, 0.0, 1.0],
            [centroid_x, 0.5, 0.0, 0.0, 0.0, 1.0],
            [centroid_x, 0.0, 0.5, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


# Upload order groups by material pair, exactly as plan_face_batches leaves it:
# triangles 0,1 carry (7, 0); triangles 2,3 carry (9, 0). Their x positions
# interleave the two materials in depth, so a correct sort MUST re-cut the
# batches. The resulting triangle order is [3, 1, 2, 0] — neither the input
# order nor its reverse, so a no-op sort and a blind reversal both fail.
_SUFFIX_X = {0: 0.0, 1: 2.0, 2: 1.0, 3: 3.0}
_PAIR_OF_X = {0.0: (7, 0), 2.0: (7, 0), 1.0: (9, 0), 3.0: (9, 0)}
_OPAQUE_TRIS = 2
_TRANSLUCENT_FIRST = _OPAQUE_TRIS * 3


def _suffix_buffer() -> _DefBuffers:
    opaque = np.zeros((_TRANSLUCENT_FIRST, 6), dtype=np.float32)
    opaque[:, 0] = -99.0  # sentinel: the prefix must never be re-uploaded
    suffix = np.concatenate([_tri_rows(_SUFFIX_X[i]) for i in range(4)], axis=0)
    interleaved = np.concatenate([opaque, suffix], axis=0)

    plan = plan_face_batches([1, 1, 7, 7, 9, 9], [0, 0, 0, 0, 0, 0], frozenset({7, 9}))
    assert plan.translucent_first == _TRANSLUCENT_FIRST
    buf = _DefBuffers(face_vbo=1, face_count=interleaved.shape[0], plan=plan)
    _reset_translucent_state(buf, plan, interleaved)
    return buf


@pytest.fixture
def captured_gl(monkeypatch):
    """Capture glBufferSubData without a GL context."""
    uploads = []

    def fake_sub_data(target, offset, size, data):
        uploads.append((int(offset), int(size), np.asarray(data, dtype=np.float32).copy()))

    monkeypatch.setattr(scene_renderer.GL, "glBindBuffer", lambda *a: None)
    monkeypatch.setattr(scene_renderer.GL, "glBufferSubData", fake_sub_data)
    return uploads


def test_sorting_uploads_only_the_suffix_back_to_front(captured_gl):
    r = SceneRenderer()
    buf = _suffix_buffer()
    r._sort_translucent_slice(buf, _identity(), np.array([-10.0, 0.0, 0.0]))

    assert len(captured_gl) == 1
    offset, size, data = captured_gl[0]
    # Offset and size are the suffix alone: the opaque prefix is untouched.
    assert offset == _TRANSLUCENT_FIRST * 6 * 4
    assert size == 12 * 6 * 4
    rows = data.reshape(-1, 6)
    assert rows.shape[0] == 12
    assert not np.any(rows[:, 0] == -99.0)
    # Farthest first from a camera at x = -10 means descending x.
    tri_x = [float(rows[3 * i, 0]) for i in range(4)]
    assert tri_x == [3.0, 2.0, 1.0, 0.0]


def test_the_rebuilt_batches_match_the_materials_of_what_was_uploaded(captured_gl):
    # This is the reason option B was chosen over keeping plan.translucent's
    # batch ranges: after the suffix is permuted across material boundaries,
    # the original ranges name the wrong materials. Asserting each rebuilt
    # batch's range against the materials of the triangles actually uploaded
    # into it fails for a renderer that reuses plan.translucent unchanged.
    r = SceneRenderer()
    buf = _suffix_buffer()
    r._sort_translucent_slice(buf, _identity(), np.array([-10.0, 0.0, 0.0]))

    rows = captured_gl[0][2].reshape(-1, 6)
    assert len(buf.translucent_draw_batches) == 4  # fully interleaved
    for batch in buf.translucent_draw_batches:
        lo = batch.first - _TRANSLUCENT_FIRST
        for v in range(lo, lo + batch.count):
            expected = _PAIR_OF_X[float(rows[v, 0])]
            assert (batch.front_material_id, batch.back_material_id) == expected


def test_a_static_camera_does_not_re_upload(captured_gl):
    # Kills a sort that runs every frame regardless.
    r = SceneRenderer()
    buf = _suffix_buffer()
    camera = np.array([-10.0, 0.0, 0.0])
    r._sort_translucent_slice(buf, _identity(), camera)
    batches = buf.translucent_draw_batches
    r._sort_translucent_slice(buf, _identity(), camera)
    assert len(captured_gl) == 1
    assert buf.translucent_draw_batches is batches  # cached, not rebuilt


def test_moving_the_camera_re_sorts_and_re_uploads(captured_gl):
    # Kills a sort that caches on first use and never invalidates.
    r = SceneRenderer()
    buf = _suffix_buffer()
    r._sort_translucent_slice(buf, _identity(), np.array([-10.0, 0.0, 0.0]))
    r._sort_translucent_slice(buf, _identity(), np.array([+10.0, 0.0, 0.0]))
    assert len(captured_gl) == 2
    near_side = captured_gl[1][2].reshape(-1, 6)
    assert [float(near_side[3 * i, 0]) for i in range(4)] == [0.0, 1.0, 2.0, 3.0]


def test_moving_the_definition_re_sorts_and_re_uploads(captured_gl):
    # The world transform is part of the cache key: a definition dragged past
    # the camera must re-sort even though the camera never moved.
    r = SceneRenderer()
    buf = _suffix_buffer()
    camera = np.array([0.0, 0.0, 0.0])
    r._sort_translucent_slice(buf, _translate(-100.0), camera)
    r._sort_translucent_slice(buf, _translate(+100.0), camera)
    assert len(captured_gl) == 2
    # Mirrored across the camera, so the depth order flips.
    first = [float(captured_gl[0][2].reshape(-1, 6)[3 * i, 0]) for i in range(4)]
    second = [float(captured_gl[1][2].reshape(-1, 6)[3 * i, 0]) for i in range(4)]
    assert first == list(reversed(second))


def test_a_definition_with_no_translucent_faces_uploads_nothing(captured_gl):
    r = SceneRenderer()
    plan = plan_face_batches([1, 1], [0, 0], frozenset())
    buf = _DefBuffers(face_vbo=1, plan=plan)
    _reset_translucent_state(buf, plan, np.zeros((6, 6), dtype=np.float32))
    r._sort_translucent_slice(buf, _identity(), np.array([1.0, 2.0, 3.0]))
    assert captured_gl == []


def test_re_upload_clears_a_stale_sort_key(captured_gl):
    # A mesh edit or an alpha edit rebuilds the buffer in place. If the sort
    # key survived, the next frame would keep the previous frame's permutation
    # and batch ranges over completely different vertex data.
    r = SceneRenderer()
    buf = _suffix_buffer()
    camera = np.array([-10.0, 0.0, 0.0])
    r._sort_translucent_slice(buf, _identity(), camera)
    assert buf.translucent_sort_key is not None

    _reset_translucent_state(buf, buf.plan, buf.face_interleaved)
    assert buf.translucent_sort_key is None
    assert buf.translucent_draw_batches == buf.plan.translucent  # pre-sort state

    r._sort_translucent_slice(buf, _identity(), camera)
    assert len(captured_gl) == 2  # sorted again rather than trusting the stale key


def test_an_all_opaque_definition_keeps_no_cpu_copy_of_its_faces():
    # Only the translucent pass reads face_interleaved. Holding a CPU copy for
    # every opaque definition would roughly double scene face memory for a pass
    # those definitions never enter. Kills a _reset_translucent_state that
    # stores the array unconditionally.
    plan = plan_face_batches([1, 2], [0, 0], frozenset())
    buf = _DefBuffers()
    _reset_translucent_state(buf, plan, np.ones((6, 6), dtype=np.float32))
    assert buf.face_interleaved.shape[0] == 0


def test_a_translucent_definition_keeps_its_faces_for_re_sorting():
    # The paired half: the array the sort reads must actually be retained.
    buf = _suffix_buffer()
    assert buf.face_interleaved.shape[0] == _TRANSLUCENT_FIRST + 12


def test_the_local_centroid_is_the_mean_of_the_translucent_triangles():
    # The definition's own sort key for pass 2. Kills a key taken from the
    # whole mesh (which would include the opaque prefix's x = -99 sentinel).
    buf = _suffix_buffer()
    assert buf.translucent_local_centroid[0] == pytest.approx(1.5)

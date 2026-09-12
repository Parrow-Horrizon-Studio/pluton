"""M7.5b Task 4: per-corner UVs in the face vertex buffer."""

from __future__ import annotations

import numpy as np
import pytest
from pluton._core import make_box
from pluton.model.model import Model
from pluton.scene.mesh_builder import build_mesh_into_scene
from pluton.scene.scene import Scene, Side, TexturePlacement
from pluton.viewport import scene_renderer
from pluton.viewport.scene_renderer import (
    _FACE_VERTEX_FLOATS,
    _DefBuffers,
    SceneRenderer,
    build_face_uvs,
    uv_material_key,
)
from pluton.viewport.uv_projection import project_corners


def _boxed():
    model = Model()
    scene = model.root.mesh
    build_mesh_into_scene(make_box(2.0, 2.0, 2.0), scene)
    return model, scene


def _painted_box():
    model, scene = _boxed()
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    for f in scene.faces_iter():
        scene.set_face_material(f.id, mat.id)
    return model, scene, mat


def _quad_and_triangle(scene: Scene) -> tuple[int, int]:
    """A 2-triangle quad and a 1-triangle face, coplanar but separate.

    Unequal triangle counts per face, which a box does not have: any drift
    between the UV walk and the position buffer slides a whole corner block.
    """

    def v(x, y):
        return scene.add_vertex(np.array([x, y, 0.0], dtype=np.float32))

    quad = [v(0.0, 0.0), v(1.0, 0.0), v(1.0, 1.0), v(0.0, 1.0)]
    for a, b in zip(quad, quad[1:] + quad[:1], strict=True):
        scene.add_edge(a, b)
    q = scene.add_face_from_loop(quad)

    tri = [v(3.0, 0.0), v(4.0, 0.0), v(3.0, 1.0)]
    for a, b in zip(tri, tri[1:] + tri[:1], strict=True):
        scene.add_edge(a, b)
    t = scene.add_face_from_loop(tri)
    return q, t


def test_the_face_vertex_carries_position_normal_and_uv():
    assert _FACE_VERTEX_FLOATS == 8


def test_face_ids_align_one_per_triangle_with_the_buffer():
    _, scene = _boxed()
    pos, _ = scene.face_triangle_buffer()
    ids = scene.face_triangle_face_ids()
    assert ids.dtype == np.int64
    assert ids.shape[0] * 3 == np.asarray(pos).shape[0]


def test_every_reported_face_id_is_a_live_face():
    _, scene = _boxed()
    live = {f.id for f in scene.faces_iter()}
    assert set(scene.face_triangle_face_ids().tolist()) <= live


def test_face_ids_match_the_material_walk_exactly():
    # The two arrays MUST come from the same next_live_face walk. If they drift,
    # UVs land on the wrong triangles and the result looks like scrambled
    # texturing rather than an error anyone can trace.
    _, scene = _boxed()
    assert scene.face_triangle_face_ids().shape == scene.face_triangle_materials().shape


def test_face_ids_repeat_by_triangle_count_not_once_per_face():
    # Kills a walk that emits one id per face instead of one per triangle: on a
    # quad that is 1 entry where the buffer holds 2 triangles.
    model = Model()
    quad, tri = _quad_and_triangle(model.root.mesh)
    ids = model.root.mesh.face_triangle_face_ids().tolist()
    assert ids.count(quad) == 2
    assert ids.count(tri) == 1


def test_uvs_are_one_per_vertex_not_one_per_triangle():
    model, scene = _boxed()
    pos, _ = scene.face_triangle_buffer()
    uvs = build_face_uvs(scene, model)
    assert uvs.shape == (np.asarray(pos).shape[0], 2)
    assert uvs.dtype == np.float32


def test_a_two_unit_face_spans_two_tiles_of_a_unit_texture():
    # The whole point of texture_size: a 1x1 image on a 2x2 box face tiles
    # twice rather than stretching to fit.
    model, scene = _boxed()
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    model.materials.edit(mat.id, texture_size=(1.0, 1.0))
    for f in scene.faces_iter():
        scene.set_face_material(f.id, mat.id)
    uvs = build_face_uvs(scene, model)
    assert float(uvs[:, 0].max() - uvs[:, 0].min()) >= 1.9


def test_a_larger_texture_size_tiles_fewer_times():
    model, scene = _boxed()
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    for f in scene.faces_iter():
        scene.set_face_material(f.id, mat.id)

    model.materials.edit(mat.id, texture_size=(1.0, 1.0))
    small = build_face_uvs(scene, model)
    model.materials.edit(mat.id, texture_size=(4.0, 4.0))
    large = build_face_uvs(scene, model)

    def span(a):
        return float(a[:, 0].max() - a[:, 0].min())

    assert span(large) < span(small)


def test_a_face_placement_moves_only_that_face_s_uvs():
    model, scene = _boxed()
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    for f in scene.faces_iter():
        scene.set_face_material(f.id, mat.id)
    before = build_face_uvs(scene, model)

    target = next(iter(scene.faces_iter())).id
    scene.set_face_placement(target, TexturePlacement(offset_u=10.0))
    after = build_face_uvs(scene, model)

    ids = scene.face_triangle_face_ids()
    moved = np.repeat(ids == target, 3)
    assert not np.allclose(before[moved], after[moved])
    assert np.allclose(before[~moved], after[~moved])


def test_each_face_s_corner_block_holds_that_face_s_own_vertices():
    # The alignment invariant checked against the MESH rather than against the
    # walk. Every other alignment test here compares face_triangle_face_ids to
    # something that also came from face_triangle_face_ids, so a walk that
    # disagreed with the C++ face_triangle_buffer would satisfy all of them
    # consistently and still scramble texturing. This one asks the geometry:
    # the corners a face id claims must be that face's own vertices. The quad
    # sits at x in [0, 1] and the triangle at x in [3, 4], so no corner of one
    # can be mistaken for a corner of the other.
    model = Model()
    scene = model.root.mesh
    _quad_and_triangle(scene)

    positions, _ = scene.face_triangle_buffer()
    ids = scene.face_triangle_face_ids()
    assert len(set(ids.tolist())) == 2

    for f_id in set(ids.tolist()):
        own = {tuple(np.round(scene.vertex(v).position, 5)) for v in scene.face_loop(int(f_id))}
        claimed = {tuple(np.round(p, 5)) for p in positions[np.repeat(ids == f_id, 3)]}
        assert claimed <= own, f"face {f_id} claims corners it does not own"


def test_the_uvs_of_a_face_land_on_that_face_s_own_corner_block():
    # The alignment invariant with real teeth, on a mesh whose faces have
    # UNEQUAL triangle counts. Every corner must reproduce, through its OWN
    # face's plane basis and centre, the UV the builder assigned it — so a
    # walk that offsets one face's block by another's triangle count fails.
    model = Model()
    scene = model.root.mesh
    _quad_and_triangle(scene)

    positions, _ = scene.face_triangle_buffer()
    ids = scene.face_triangle_face_ids()
    uvs = build_face_uvs(scene, model)

    for f_id in dict.fromkeys(int(i) for i in ids):
        corner = np.repeat(ids == f_id, 3)
        expected = project_corners(
            positions[corner].astype(np.float64),
            np.asarray(scene.face_normal(f_id), dtype=np.float64),
            np.asarray(scene.face_center(f_id), dtype=np.float64),
            (1.0, 1.0),
        )
        assert np.allclose(uvs[corner], expected, atol=1e-5)


def test_the_back_side_reads_the_back_placement():
    model, scene = _boxed()
    mat = model.materials.add_custom("Brick", (1.0, 1.0, 1.0))
    for f in scene.faces_iter():
        scene.set_face_material(f.id, mat.id, Side.BACK)
    target = next(iter(scene.faces_iter())).id
    scene.set_face_placement(target, TexturePlacement(offset_u=5.0), Side.BACK)

    front = build_face_uvs(scene, model, Side.FRONT)
    back = build_face_uvs(scene, model, Side.BACK)
    assert not np.allclose(front, back)


def test_an_empty_scene_yields_an_empty_uv_array():
    model = Model()
    uvs = build_face_uvs(model.root.mesh, model)
    assert uvs.shape == (0, 2)
    assert uvs.dtype == np.float32


def test_an_untextured_scene_still_produces_finite_uvs():
    # Untextured faces still get UVs, because the attribute exists for every
    # vertex. They are simply never sampled. NaN or inf here would corrupt the
    # buffer for textured neighbours in the same definition.
    model, scene = _boxed()
    uvs = build_face_uvs(scene, model)
    assert np.all(np.isfinite(uvs))


# --- Step 6: the UVs reach the vertex buffer, under the batch permutation ----


def test_the_uploaded_vertex_rows_carry_uvs_under_the_batch_permutation(monkeypatch):
    # Two invariants at once, both silent when broken. The row must be 8 wide
    # (a concatenate that forgot the UV block uploads 6-wide data against a
    # 32-byte stride), and the UVs must be permuted by plan.vertex_order just
    # like positions and normals — leaving them unsorted scrambles texturing
    # only on definitions that contain translucent faces.
    model, scene = _boxed()
    glass = model.materials.add_custom("Glass", (0.3, 0.5, 0.9))
    model.materials.edit(glass.id, alpha=0.4, texture_size=(2.0, 2.0))
    for f in list(scene.faces_iter())[:3]:
        scene.set_face_material(f.id, glass.id)

    uploads: list[np.ndarray] = []
    monkeypatch.setattr(scene_renderer.GL, "glBindBuffer", lambda *a: None)
    monkeypatch.setattr(
        scene_renderer.GL,
        "glBufferData",
        lambda target, size, data, usage: uploads.append(np.asarray(data, dtype=np.float32).copy()),
    )
    r = SceneRenderer()
    monkeypatch.setattr(r, "_alloc_def_buffers", lambda: _DefBuffers(face_vbo=1, edge_vbo=2))

    buf = r._upload_definition(model.root, frozenset({glass.id}), model)
    rows = uploads[0].reshape(-1, _FACE_VERTEX_FLOATS)

    order = np.asarray(buf.plan.vertex_order)
    assert not np.array_equal(order, np.arange(rows.shape[0])), (
        "the plan did not reorder anything, so this test could not detect an "
        "unpermuted UV block"
    )
    positions, normals = scene.face_triangle_buffer()
    assert np.allclose(rows[:, 0:3], positions[order])
    assert np.allclose(rows[:, 3:6], normals[order])
    assert np.allclose(rows[:, 6:8], build_face_uvs(scene, model)[order], atol=1e-6)


def test_the_upload_records_the_uv_key_it_baked(monkeypatch):
    # _ensure_buffers compares buf.uv_key against a freshly computed one, so an
    # upload that forgot to record it would re-upload every single frame.
    model, _, mat = _painted_box()
    monkeypatch.setattr(scene_renderer.GL, "glBindBuffer", lambda *a: None)
    monkeypatch.setattr(scene_renderer.GL, "glBufferData", lambda *a: None)
    r = SceneRenderer()
    monkeypatch.setattr(r, "_alloc_def_buffers", lambda: _DefBuffers(face_vbo=1, edge_vbo=2))

    buf = r._upload_definition(model.root, frozenset(), model)
    assert buf.uv_key == uv_material_key(model.root.mesh, model)
    assert any(entry[0] == mat.id for entry in buf.uv_key)


# --- Step 6b: re-upload when a material's UV-affecting fields change ---------


def test_changing_texture_size_changes_the_uv_key():
    model, _, mat = _painted_box()
    model.materials.edit(mat.id, texture_size=(1.0, 1.0))
    before = uv_material_key(model.root.mesh, model)
    model.materials.edit(mat.id, texture_size=(4.0, 4.0))
    assert uv_material_key(model.root.mesh, model) != before


def test_changing_texture_id_changes_the_uv_key():
    model, _, mat = _painted_box()
    before = uv_material_key(model.root.mesh, model)
    model.materials.edit(mat.id, texture_id=7)
    assert uv_material_key(model.root.mesh, model) != before


def test_changing_a_colour_does_not_change_the_uv_key():
    # A colour edit must NOT force a re-upload: uniforms are read per batch at
    # draw time. Re-uploading on every colour tweak would rebuild every visible
    # definition's vertex buffer while the user drags a colour picker.
    model, _, mat = _painted_box()
    before = uv_material_key(model.root.mesh, model)
    model.materials.edit(mat.id, base_color=(0.2, 0.9, 0.3), alpha=0.5, roughness=0.1)
    assert uv_material_key(model.root.mesh, model) == before


@pytest.fixture
def uv_stubbed_renderer(monkeypatch):
    """A SceneRenderer whose _upload_definition is a counted stub.

    Same pattern as tests/test_translucent_pass.py: lets the reuse-vs-rebuild
    decision in _ensure_buffers be observed directly, with no GL context.
    """
    r = SceneRenderer()
    calls: list[tuple] = []

    def fake_upload(definition, translucent_ids, model=None):
        calls.append((translucent_ids, model))
        return _DefBuffers(
            translucent_ids=translucent_ids,
            uv_key=uv_material_key(definition.mesh, model),
        )

    monkeypatch.setattr(r, "_upload_definition", fake_upload)
    return r, calls


def test_an_unchanged_uv_key_reuses_the_buffer(uv_stubbed_renderer):
    # Kills a renderer that re-uploads unconditionally every frame, which would
    # pass every uv_material_key test above while doing no caching at all.
    r, calls = uv_stubbed_renderer
    model, _, _ = _painted_box()
    first = r._ensure_buffers(model.root, frozenset(), model)
    again = r._ensure_buffers(model.root, frozenset(), model)
    assert again is first
    assert len(calls) == 1


def test_a_changed_texture_size_rebuilds_the_buffer(uv_stubbed_renderer):
    # The bug Step 6b exists for: texture_size lives on the MaterialLibrary,
    # not the Scene, so editing it dirties no mesh. Without the uv_key check
    # the baked UVs keep tiling at the old size and the edit looks inert.
    r, calls = uv_stubbed_renderer
    model, _, mat = _painted_box()
    first = r._ensure_buffers(model.root, frozenset(), model)
    model.materials.edit(mat.id, texture_size=(4.0, 4.0))
    changed = r._ensure_buffers(model.root, frozenset(), model)
    assert changed is not first
    assert len(calls) == 2


def test_the_per_frame_staleness_check_does_not_walk_the_triangles(uv_stubbed_renderer):
    # Why uv_key_still_matches exists rather than re-deriving the key each
    # frame. face_triangle_materials walks every live face, measured at ~3.5 ms
    # for a 10k-face definition — per definition, per frame. The cached key
    # already names the materials that matter, so re-reading just those is
    # enough. Kills a revert to uv_material_key(scene, model) in the draw loop.
    r, _ = uv_stubbed_renderer
    model, scene, _ = _painted_box()
    r._ensure_buffers(model.root, frozenset(), model)

    walks = []
    real = scene.face_triangle_materials

    def counted(*args, **kwargs):
        walks.append(1)
        return real(*args, **kwargs)

    scene.face_triangle_materials = counted
    r._ensure_buffers(model.root, frozenset(), model)
    assert walks == []


def test_a_colour_edit_does_not_rebuild_the_buffer(uv_stubbed_renderer):
    # The paired half at buffer level: a colour edit must leave the VBO alone.
    r, calls = uv_stubbed_renderer
    model, _, mat = _painted_box()
    first = r._ensure_buffers(model.root, frozenset(), model)
    model.materials.edit(mat.id, base_color=(0.1, 0.2, 0.3))
    again = r._ensure_buffers(model.root, frozenset(), model)
    assert again is first
    assert len(calls) == 1

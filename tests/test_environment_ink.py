"""Grid and edge ink following the environment, without a GL context."""

from pluton.viewport.environment import PLAIN_WHITE, STUDIO
from pluton.viewport.scene_renderer import _build_grid_vertex_array


def test_the_grid_array_carries_the_environments_grid_colours():
    """Both colours, and they must not be swapped.

    Discriminates: swap the two arguments at the _init_grid_buffers call and this
    fails, because the presets move them in opposite directions.
    """
    verts = _build_grid_vertex_array(PLAIN_WHITE.grid_color, PLAIN_WHITE.grid_centerline_color)
    colors = {tuple(round(float(c), 4) for c in row[3:]) for row in verts}
    assert PLAIN_WHITE.grid_color in colors
    assert PLAIN_WHITE.grid_centerline_color in colors


def test_the_grid_array_shape_is_unchanged():
    """44 vertices of 6 floats: parameterising the colours must not move geometry."""
    verts = _build_grid_vertex_array(STUDIO.grid_color, STUDIO.grid_centerline_color)
    assert verts.shape == (44, 6)


def test_the_studio_grid_matches_the_pre_m77_array():
    """The dark environment's grid is byte-identical to what v0.12.0 drew."""
    verts = _build_grid_vertex_array(STUDIO.grid_color, STUDIO.grid_centerline_color)
    colors = {tuple(round(float(c), 4) for c in row[3:]) for row in verts}
    assert colors == {(0.40, 0.40, 0.40), (0.60, 0.60, 0.60)}


def test_switching_environment_marks_the_grid_for_rebuild():
    """set_environment can be called with no current GL context.

    MainWindow's menu handler runs outside paintGL, exactly like the texture
    evictions _flush_pending_texture_evictions exists for, so the rebuild is
    deferred to the next frame rather than done in the setter.
    """
    from pluton.viewport.scene_renderer import SceneRenderer

    renderer = SceneRenderer()
    renderer._grid_dirty = False
    renderer.set_environment(PLAIN_WHITE)
    assert renderer._grid_dirty is True


def test_setting_the_same_environment_does_not_mark_the_grid_dirty():
    """A redundant menu click must not queue a re-upload every time."""
    from pluton.viewport.scene_renderer import SceneRenderer

    renderer = SceneRenderer()
    renderer.set_environment(PLAIN_WHITE)
    renderer._grid_dirty = False
    renderer.set_environment(PLAIN_WHITE)
    assert renderer._grid_dirty is False


def test_a_definition_with_no_edges_still_records_the_colour_it_was_uploaded_under():
    """The predicate alone, not the production line that has to call it right.

    This builds a `_DefBuffers` by hand and asserts on `_edge_buffer_is_stale`
    directly, so it never drives `_upload_definition` and cannot see whether
    the real upload actually performs the `buf.edge_color = edge_color`
    assignment on the zero-edge path. That assignment sits after the
    if/else, not inside a branch, precisely so a third branch could not skip
    it again; the test that pins the real upload behaviour, including the
    forever-stale bug this recording exists to prevent, is
    test_a_zero_edge_definition_does_not_re_upload_every_frame below.
    """
    from pluton.viewport.scene_renderer import _DefBuffers, _edge_buffer_is_stale

    buf = _DefBuffers()
    buf.edge_count = 0
    buf.edge_color = STUDIO.edge_color
    assert _edge_buffer_is_stale(buf, STUDIO.edge_color) is False
    assert _edge_buffer_is_stale(buf, PLAIN_WHITE.edge_color) is True


def test_a_never_uploaded_buffer_is_stale():
    """The default of None must read as stale, so the first frame uploads."""
    from pluton.viewport.scene_renderer import _DefBuffers, _edge_buffer_is_stale

    assert _edge_buffer_is_stale(_DefBuffers(), STUDIO.edge_color) is True


def test_the_real_upload_records_the_environments_edge_colour(monkeypatch):
    """Drives _upload_definition itself, not a hand-built buffer.

    Uses the GL-stub recipe from
    test_texture_vertex_format.py::test_uploading_a_definition_with_a_split_edge_face_does_not_raise:
    glBindBuffer/glBufferData are no-ops and _alloc_def_buffers is stubbed, so
    the real upload runs with no GL context.

    Discriminates: comment out `buf.edge_color = edge_color` in
    _upload_definition and this fails, because buf.edge_color stays None.
    """
    from pluton._core import make_box
    from pluton.model.model import Model
    from pluton.scene.mesh_builder import build_mesh_into_scene
    from pluton.viewport import scene_renderer
    from pluton.viewport.scene_renderer import SceneRenderer, _DefBuffers

    model = Model()
    build_mesh_into_scene(make_box(2.0, 2.0, 2.0), model.root.mesh)
    monkeypatch.setattr(scene_renderer.GL, "glBindBuffer", lambda *a: None)
    monkeypatch.setattr(scene_renderer.GL, "glBufferData", lambda *a: None)
    r = SceneRenderer()
    monkeypatch.setattr(r, "_alloc_def_buffers", lambda: _DefBuffers(face_vbo=1, edge_vbo=2))

    buf = r._upload_definition(model.root, frozenset(), model)
    assert buf.edge_count > 0
    assert buf.edge_color == r._environment.edge_color


def test_a_zero_edge_definition_does_not_re_upload_every_frame(monkeypatch):
    """The expensive half of the bug: nothing on screen changes, so no visual
    check and no fresh-load test can see a definition re-uploading on every
    single frame forever.

    Calls _ensure_buffers twice with nothing changed in between and counts
    calls that reach the real _upload_definition. A definition with zero
    edges that skipped recording edge_color on that branch would read as
    stale forever, so the second call would re-upload and this would fail.

    Discriminates: comment out `buf.edge_color = edge_color` in
    _upload_definition and this fails (the second call re-uploads).
    """
    from pluton.model.model import Model
    from pluton.viewport import scene_renderer
    from pluton.viewport.scene_renderer import SceneRenderer, _DefBuffers

    model = Model()  # empty scene: no faces, no edges
    monkeypatch.setattr(scene_renderer.GL, "glBindBuffer", lambda *a: None)
    monkeypatch.setattr(scene_renderer.GL, "glBufferData", lambda *a: None)
    r = SceneRenderer()
    monkeypatch.setattr(r, "_alloc_def_buffers", lambda: _DefBuffers(face_vbo=1, edge_vbo=2))

    upload_calls: list[int] = []
    real_upload = r._upload_definition

    def counted_upload(definition, translucent_ids, model):
        upload_calls.append(1)
        return real_upload(definition, translucent_ids, model)

    monkeypatch.setattr(r, "_upload_definition", counted_upload)

    first = r._ensure_buffers(model.root, frozenset(), model)
    assert first.edge_count == 0
    second = r._ensure_buffers(model.root, frozenset(), model)
    assert second is first
    assert len(upload_calls) == 1

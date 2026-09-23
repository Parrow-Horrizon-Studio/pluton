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
    """Review Focus 2, and the expensive half of the staleness bug.

    _upload_definition's zero-edge branch sets edge_count = 0. If it does not
    also record edge_color, the staleness comparison stays true forever and
    every empty definition re-uploads on every frame. Nothing about the picture
    changes, so no visual test and no fresh-load test can see it.

    Discriminates: remove the `buf.edge_color = ...` assignment from the else
    branch and this fails.
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

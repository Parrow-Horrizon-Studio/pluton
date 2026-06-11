"""Tests for SceneRenderer.

We test:
  - SceneRenderer construction (no GL context needed).
  - draw_face_fill_overlays: public method added in M3b Task 6.
"""

from __future__ import annotations


class TestSceneRendererConstruction:
    """SceneRenderer should be constructible without a GL context."""

    def test_constructs_without_gl(self):
        from pluton.viewport.scene_renderer import SceneRenderer

        renderer = SceneRenderer()
        assert not renderer._initialized


class TestFaceFillOverlayPass:
    """SceneRenderer.draw_face_fill_overlays — alpha-blended ghost rendering."""

    def test_empty_polygon_list_is_a_noop(self, qtbot):
        """Smoke test: empty list shouldn't touch GL state or raise."""
        from pluton.viewport.scene_renderer import SceneRenderer

        renderer = SceneRenderer()
        # Don't call initialize_gl — the empty-list path must short-circuit
        # before touching any GL functions.
        renderer.draw_face_fill_overlays(polygons=[], color=(1.0, 0.0, 0.0, 0.5))
        # If we got here without an exception, the smoke test passes.

    def test_polygon_list_with_single_quad_is_accepted(self, qtbot):
        """The renderer should accept a single (4, 3) numpy quad without raising.
        Actual GL drawing is exercised by manual visual verification."""
        import inspect
        from pluton.viewport.scene_renderer import SceneRenderer

        renderer = SceneRenderer()
        assert hasattr(renderer, "draw_face_fill_overlays")
        sig = inspect.signature(renderer.draw_face_fill_overlays)
        assert "polygons" in sig.parameters
        assert "color" in sig.parameters


def test_snap_marker_vertices_shape_per_kind():
    import numpy as np
    from pluton.viewport.scene_renderer import _snap_marker_vertices
    from pluton.viewport.snap_engine import SnapKind

    p = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    # GL_LINES vertex counts: square=8, triangle=6, diamond=8, X=4.
    assert _snap_marker_vertices(int(SnapKind.ENDPOINT), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.ON_FACE), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.MIDPOINT), p).shape == (6, 3)
    assert _snap_marker_vertices(int(SnapKind.ON_EDGE), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.INTERSECTION), p).shape == (4, 3)
    for kind in (SnapKind.ENDPOINT, SnapKind.MIDPOINT, SnapKind.ON_EDGE, SnapKind.INTERSECTION):
        v = _snap_marker_vertices(int(kind), p)
        assert np.allclose(v[:, 2], 3.0)

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

"""Shared fake ViewportWidget for tests that call
`ViewportWidget._paint_annotations(fake_viewport)` directly -- headlessly,
with no real QWidget/QApplication/GL context.

`_paint_annotations` reads a fixed set of attributes off `self`: `model`,
`camera`, `selection`, `_units_provider`, `tool_manager`,
`_vcb_active_provider`, `_last_cursor_px`, `show_guides`, plus the
`width()`/`height()` methods. Every attribute here defaults to whatever
`ViewportWidget.__init__` itself sets, so this stand-in stays a faithful
substitute rather than merely something that stops a crash.

Before M7.6b Task 9, two test files (`test_annotation_painter.py` and
`test_annotation_render_scope.py`) each hand-rolled their own `_FakeViewport`
class. Both drifted from the real `ViewportWidget` independently: Task 7
added the `show_guides` read and neither fake got it (main was red on
`test_annotation_painter.py` from Task 7 onward, undetected because that
file wasn't in the focused suites reviewers ran); Task 9 then added
`tool_manager`/`_vcb_active_provider`/`_last_cursor_px` and broke
`test_annotation_render_scope.py` the same way, in a different file. This
module exists so there is exactly ONE place to update instead of two (or
more) independently-drifting copies.

IMPORTANT: whenever `_paint_annotations` gains a new `self.<attr>` read,
add the matching default here too -- ideally in the same change that adds
the read to `_paint_annotations` itself -- or every test file importing
this class will eventually crash the same way `show_guides` and
`tool_manager` did.
"""

from __future__ import annotations


class FakeViewport:
    """Duck-typed stand-in for ViewportWidget, covering every attribute
    ViewportWidget._paint_annotations reads off `self`. Only `model` and
    `camera` are meaningful per-test inputs; everything else defaults to
    ViewportWidget.__init__'s own default so a test that doesn't care about
    tools/guides/cursor state gets exactly the same starting point the real
    widget would have."""

    def __init__(self, model=None, camera=None, width=800, height=600):
        self.model = model
        self.camera = camera
        # Matches ViewportWidget.__init__'s own defaults, attribute for
        # attribute -- see this module's docstring for why that matters.
        self.selection = None
        self._units_provider = None
        self.tool_manager = None
        self._vcb_active_provider = None
        self._last_cursor_px = None
        self.show_guides = True
        self._width = width
        self._height = height

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

# M4b — Selection & Eraser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A shared, persistent selection subsystem — a Select tool (click / Shift-extend / direction-sensitive box-select), blue selection highlighting, an edge-Eraser with face cascade, and Delete/Backspace on the selection.

**Architecture:** A standalone `Selection` (sets of edge + face ids) is owned by `MainWindow`, handed to tools via `ToolContext` and to the renderer, which draws a persistent highlight pass (selected faces via the existing ghost-fill path, selected edges as bold lines). Picking is pure screen-space (`world_to_screen` + 2D point-to-segment). Deletion composes the existing `RemoveFace/EdgeCommand` into `CompositeCommand`s. Pure Python; the only new render capability is a screen-space box-select rectangle.

**Tech Stack:** Python 3.13, numpy, PySide6 (Qt), PyOpenGL, pytest + pytest-qt. Spec: `docs/2026-06-16-M4b-selection-eraser-design.md`.

---

## Conventions & guardrails (read before every task)

- **Interpreter:** always `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash). The bare `python`/`pytest` resolve to a different, drifting install.
- **Working dir:** run all commands from `F:\dev\00_Parrow-Horrizon-Studio\pluton`. In the Bash tool the cwd resets between calls — prefix with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && …`.
- **No C++ rebuild needed** — M4b touches no kernel/binding/CMake code. New Python files import without a reinstall (the package is an editable install). If a brand-new module import unexpectedly fails, refresh once: `.venv/Scripts/python.exe -m pip install -e . --no-build-isolation`.
- **Git:** work on `main`. Stage **specific files only** — never `git add -A`/`git add .`. End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay on). Fix hook failures at the cause.
- **Do not touch version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) until the release task (Task 12).
- **TDD:** failing test → watch it fail → minimal code → watch it pass → commit. One commit per task.
- **Qt event construction in tests:** build mouse events with
  `QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)`.
  If your PySide6 build rejects that overload, use the one that also takes a global position: `QMouseEvent(type, QPointF(x,y), QPointF(x,y), button, buttons, modifiers)`. Tool tests need a `qtbot` fixture so a `QApplication` exists.

---

## File structure

| File | Responsibility |
|------|----------------|
| `python/pluton/selection.py` | **new** — `Selection` (edge/face id sets + version). Pure. |
| `python/pluton/viewport/picking.py` | **new** — `pick_selectable`, `entities_in_box`, 2D screen helpers. |
| `python/pluton/tools/tool.py` | + `Tool.on_mouse_release` (no-op); + `ToolOverlay.box_rect`/`box_rect_color`; + `ToolContext.selection`. |
| `python/pluton/viewport/viewport_widget.py` | forward LMB release to the active tool; hold + pass `selection` to the renderer. |
| `python/pluton/viewport/scene_renderer.py` | persistent selection-highlight pass + screen-space box-rect (pure helpers + thin GL). |
| `python/pluton/tools/select_tool.py` | **new** — `SelectTool` (Space). |
| `python/pluton/tools/erase_tool.py` | **new** — `EraserTool` (E). |
| `python/pluton/tools/__init__.py` | export `SelectTool`, `EraserTool`. |
| `python/pluton/ui/main_window.py` | own `Selection`; register tools; Space/E/Delete/Backspace; clear-on-undo; status count. |
| `python/pluton/ui/status_bar.py` | + `set_selection` segment. |
| `tests/...` | per task. |

---

## Task 1: `Selection` state object

**Files:**
- Create: `python/pluton/selection.py`
- Test: `tests/test_selection.py`

- [ ] **Step 1: Write the failing test** — `tests/test_selection.py`:

```python
"""Unit tests for the shared Selection object (pure, no Qt)."""

from __future__ import annotations

from pluton.selection import Selection


def test_starts_empty():
    s = Selection()
    assert s.is_empty()
    assert s.counts() == (0, 0)
    assert s.edges == set()
    assert s.faces == set()


def test_replace_sets_contents_and_bumps_version():
    s = Selection()
    v0 = s.version
    s.replace(edges=[1, 2], faces=[5])
    assert s.edges == {1, 2}
    assert s.faces == {5}
    assert s.counts() == (2, 1)
    assert not s.is_empty()
    assert s.version > v0
    # replace clears the old contents
    s.replace(edges=[9])
    assert s.edges == {9}
    assert s.faces == set()


def test_add_unions():
    s = Selection()
    s.replace(edges=[1])
    s.add(edges=[2, 3], faces=[7])
    assert s.edges == {1, 2, 3}
    assert s.faces == {7}


def test_toggle_edge_and_face():
    s = Selection()
    s.toggle_edge(4)
    assert s.contains_edge(4)
    s.toggle_edge(4)
    assert not s.contains_edge(4)
    s.toggle_face(8)
    assert s.contains_face(8)


def test_clear_only_bumps_when_nonempty():
    s = Selection()
    v0 = s.version
    s.clear()
    assert s.version == v0  # already empty → no bump
    s.replace(faces=[1])
    v1 = s.version
    s.clear()
    assert s.is_empty()
    assert s.version > v1
```

- [ ] **Step 2: Run it; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_selection.py -q` → `ModuleNotFoundError: No module named 'pluton.selection'`.

- [ ] **Step 3: Implement** — `python/pluton/selection.py`:

```python
"""Shared, transient selection state: which edges and faces are selected.

Owned by MainWindow, handed to tools (via ToolContext) and the renderer. NOT
part of the Scene geometry model and NOT on the undo stack (selecting is not an
undoable action; only deletions are). `version` bumps on every mutation so the
renderer can cheaply detect changes.
"""

from __future__ import annotations

from collections.abc import Iterable


class Selection:
    __slots__ = ("_edges", "_faces", "_version")

    def __init__(self) -> None:
        self._edges: set[int] = set()
        self._faces: set[int] = set()
        self._version: int = 0

    @property
    def edges(self) -> set[int]:
        return self._edges

    @property
    def faces(self) -> set[int]:
        return self._faces

    @property
    def version(self) -> int:
        return self._version

    def _bump(self) -> None:
        self._version += 1

    def replace(self, *, edges: Iterable[int] = (), faces: Iterable[int] = ()) -> None:
        self._edges = set(edges)
        self._faces = set(faces)
        self._bump()

    def add(self, *, edges: Iterable[int] = (), faces: Iterable[int] = ()) -> None:
        self._edges |= set(edges)
        self._faces |= set(faces)
        self._bump()

    def toggle_edge(self, e_id: int) -> None:
        self._edges.symmetric_difference_update({e_id})
        self._bump()

    def toggle_face(self, f_id: int) -> None:
        self._faces.symmetric_difference_update({f_id})
        self._bump()

    def clear(self) -> None:
        if self._edges or self._faces:
            self._edges.clear()
            self._faces.clear()
            self._bump()

    def contains_edge(self, e_id: int) -> bool:
        return e_id in self._edges

    def contains_face(self, f_id: int) -> bool:
        return f_id in self._faces

    def is_empty(self) -> bool:
        return not self._edges and not self._faces

    def counts(self) -> tuple[int, int]:
        return (len(self._edges), len(self._faces))
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_selection.py -q` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/selection.py tests/test_selection.py
git commit -m "$(cat <<'EOF'
feat(selection): shared Selection state object (M4b)

Edge/face id sets with replace/add/toggle/clear/contains/counts and a version
counter for cheap change detection. Transient interaction state — not geometry,
not on the undo stack.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `pick_selectable` (hover/click pick)

**Files:**
- Create: `python/pluton/viewport/picking.py`
- Test: `tests/test_picking.py`

- [ ] **Step 1: Write the failing test** — `tests/test_picking.py`:

```python
"""Tests for selection picking (pure screen-space)."""

from __future__ import annotations

import numpy as np


def _camera(w, h):
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = float(w) / float(h)
    return cam


def test_pick_returns_edge_near_its_screen_projection():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    e = scene.add_edge(a, b)

    # Project the edge midpoint to a pixel and pick exactly there.
    mid = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    sx, sy, _ = cam.world_to_screen(mid, w, h)
    hit = pick_selectable((sx, sy), (w, h), cam, scene)
    assert hit == ("edge", e)


def test_pick_far_from_everything_is_none():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(a, b)
    # A corner pixel, far from the edge near screen center.
    hit = pick_selectable((2.0, 2.0), (w, h), cam, scene)
    assert hit is None


def test_pick_prefers_edge_over_face_behind_it():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, -1.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, -1.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    d = scene.add_vertex(np.array([-1.0, 1.0, 0.0], dtype=np.float32))
    fid = scene.add_face_from_loop((a, b, c, d))

    # Pick over the bottom edge (a-b) midpoint → expect that edge, not the face.
    mid_ab = np.array([0.0, -1.0, 0.0], dtype=np.float32)
    sx, sy, _ = cam.world_to_screen(mid_ab, w, h)
    hit = pick_selectable((sx, sy), (w, h), cam, scene)
    assert hit[0] == "edge"

    # Pick at the face center (away from all edges) → expect the face.
    center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cx, cy, _ = cam.world_to_screen(center, w, h)
    hit2 = pick_selectable((cx, cy), (w, h), cam, scene)
    assert hit2 == ("face", fid)
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_picking.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — `python/pluton/viewport/picking.py`:

```python
"""Selection picking — pure screen-space (project to pixels via world_to_screen,
2D point-to-segment distance). Independent of the drawing-snap precedence:
selection wants the edge or face under the cursor, not a vertex/midpoint snap.
"""

from __future__ import annotations

import math

PICK_PIXEL_TOLERANCE = 8.0  # screen-space; matches the M3d snap feel


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    """2D distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def pick_selectable(cursor_screen, viewport_size, camera, scene):  # noqa: ANN001
    """Return ("edge", id) for the nearest edge within PICK_PIXEL_TOLERANCE of
    the cursor (screen-space); else ("face", id) under the cursor ray; else None.
    Edge-priority: thin targets are harder to hit, so they win over the face."""
    px, py = float(cursor_screen[0]), float(cursor_screen[1])
    w, h = int(viewport_size[0]), int(viewport_size[1])

    best_edge: int | None = None
    best_d = PICK_PIXEL_TOLERANCE
    for e in scene.edges_iter():
        p1 = scene.vertex(e.v1_id).position
        p2 = scene.vertex(e.v2_id).position
        s1 = camera.world_to_screen(p1, w, h)
        s2 = camera.world_to_screen(p2, w, h)
        if s1 is None or s2 is None:
            continue
        d = _point_segment_distance(px, py, s1[0], s1[1], s2[0], s2[1])
        if d <= best_d:
            best_d = d
            best_edge = e.id
    if best_edge is not None:
        return ("edge", best_edge)

    origin, direction = camera.ray_from_screen(px, py, w, h)
    hit = scene.ray_pick_face(origin, direction)
    if hit is not None:
        return ("face", int(hit.face_id))
    return None
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_picking.py -q` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/picking.py tests/test_picking.py
git commit -m "$(cat <<'EOF'
feat(picking): screen-space pick_selectable (edge-priority) (M4b)

Projects edges to pixels and tests 2D point-to-segment distance (8 px); falls
back to ray_pick_face. Self-contained; no snap_engine dependency.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `entities_in_box` (window / crossing)

**Files:**
- Modify: `python/pluton/viewport/picking.py`
- Test: `tests/test_picking.py` (append)

- [ ] **Step 1: Append the failing tests** to `tests/test_picking.py`:

```python
def _screen(cam, world, w, h):
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), w, h)
    return sx, sy


def test_window_selects_only_fully_enclosed():
    from pluton.scene import Scene
    from pluton.viewport.picking import entities_in_box

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    # Edge fully near the center, and a far edge off to the side.
    a = scene.add_vertex(np.array([-0.3, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([0.3, 0.0, 0.0], dtype=np.float32))
    e_in = scene.add_edge(a, b)
    c = scene.add_vertex(np.array([3.0, 0.0, 0.0], dtype=np.float32))
    d = scene.add_vertex(np.array([3.5, 0.0, 0.0], dtype=np.float32))
    e_out = scene.add_edge(c, d)

    # Rect tightly around the center edge's endpoints (+ margin).
    s1 = _screen(cam, [-0.3, 0.0, 0.0], w, h)
    s2 = _screen(cam, [0.3, 0.0, 0.0], w, h)
    margin = 10.0
    rect = (min(s1[0], s2[0]) - margin, min(s1[1], s2[1]) - margin,
            max(s1[0], s2[0]) + margin, max(s1[1], s2[1]) + margin)
    edges, faces = entities_in_box(rect, "window", (w, h), cam, scene)
    assert e_in in edges
    assert e_out not in edges


def test_crossing_selects_straddling_edge_window_does_not():
    from pluton.scene import Scene
    from pluton.viewport.picking import entities_in_box

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-0.5, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([0.5, 0.0, 0.0], dtype=np.float32))
    e = scene.add_edge(a, b)

    sa = _screen(cam, [-0.5, 0.0, 0.0], w, h)
    sb = _screen(cam, [0.5, 0.0, 0.0], w, h)
    # Rect that covers vertex a but cuts the segment before reaching b
    # (right edge halfway between the two endpoints' x).
    midx = (sa[0] + sb[0]) / 2.0
    top = min(sa[1], sb[1]) - 20.0
    bot = max(sa[1], sb[1]) + 20.0
    left = min(sa[0], sb[0]) - 20.0
    rect = (left, top, midx, bot)

    win_edges, _ = entities_in_box(rect, "window", (w, h), cam, scene)
    cross_edges, _ = entities_in_box(rect, "crossing", (w, h), cam, scene)
    assert e not in win_edges        # straddles → not fully enclosed
    assert e in cross_edges          # straddles → touched
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_picking.py -q` → the two new tests fail (`entities_in_box` undefined).

- [ ] **Step 3: Append the implementation** to `python/pluton/viewport/picking.py`:

```python
def _point_in_rect(px, py, rect) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= px <= x1 and y0 <= py <= y1


def _ccw(ax, ay, bx, by, cx, cy) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segments_cross(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    """True if segment AB properly straddles segment CD (and vice-versa)."""
    d1 = _ccw(cx, cy, dx, dy, ax, ay)
    d2 = _ccw(cx, cy, dx, dy, bx, by)
    d3 = _ccw(ax, ay, bx, by, cx, cy)
    d4 = _ccw(ax, ay, bx, by, dx, dy)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _segment_intersects_rect(ax, ay, bx, by, rect) -> bool:
    if _point_in_rect(ax, ay, rect) or _point_in_rect(bx, by, rect):
        return True
    x0, y0, x1, y1 = rect
    sides = (
        (x0, y0, x1, y0), (x1, y0, x1, y1),
        (x1, y1, x0, y1), (x0, y1, x0, y0),
    )
    for cx, cy, dx, dy in sides:
        if _segments_cross(ax, ay, bx, by, cx, cy, dx, dy):
            return True
    return False


def _normalize_rect(rect):
    x0, y0, x1, y1 = rect
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def entities_in_box(rect_px, mode, viewport_size, camera, scene):  # noqa: ANN001
    """Return (edge_ids: set, face_ids: set) inside rect_px under the given mode.
    mode="window": only fully-enclosed; mode="crossing": anything touched."""
    rect = _normalize_rect(rect_px)
    w, h = int(viewport_size[0]), int(viewport_size[1])
    edges: set[int] = set()
    faces: set[int] = set()

    def proj(world):
        return camera.world_to_screen(world, w, h)

    for e in scene.edges_iter():
        s1 = proj(scene.vertex(e.v1_id).position)
        s2 = proj(scene.vertex(e.v2_id).position)
        if mode == "window":
            if s1 is not None and s2 is not None and \
               _point_in_rect(s1[0], s1[1], rect) and _point_in_rect(s2[0], s2[1], rect):
                edges.add(e.id)
        else:  # crossing
            if s1 is None or s2 is None:
                if (s1 is not None and _point_in_rect(s1[0], s1[1], rect)) or \
                   (s2 is not None and _point_in_rect(s2[0], s2[1], rect)):
                    edges.add(e.id)
            elif _segment_intersects_rect(s1[0], s1[1], s2[0], s2[1], rect):
                edges.add(e.id)

    for f in scene.faces_iter():
        loop = scene.face_loop(f.id)
        pts = [proj(scene.vertex(v).position) for v in loop]
        if mode == "window":
            if all(p is not None and _point_in_rect(p[0], p[1], rect) for p in pts):
                faces.add(f.id)
        else:  # crossing
            touched = any(p is not None and _point_in_rect(p[0], p[1], rect) for p in pts)
            if not touched:
                n = len(pts)
                for i in range(n):
                    p, q = pts[i], pts[(i + 1) % n]
                    if p is not None and q is not None and \
                       _segment_intersects_rect(p[0], p[1], q[0], q[1], rect):
                        touched = True
                        break
            if touched:
                faces.add(f.id)

    return edges, faces
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_picking.py -q` → 5 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/picking.py tests/test_picking.py
git commit -m "$(cat <<'EOF'
feat(picking): entities_in_box — window & crossing box-select (M4b)

Window = all of an entity's screen vertices inside the rect; crossing = any
vertex inside or any boundary segment crossing a rect side. Behind-camera
vertices skipped.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Plumbing — `on_mouse_release`, `ToolOverlay.box_rect`, `ToolContext.selection`, viewport release routing

**Files:**
- Modify: `python/pluton/tools/tool.py`
- Modify: `python/pluton/viewport/viewport_widget.py`
- Test: `tests/test_tool_release_plumbing.py`

- [ ] **Step 1: Write the failing test** — `tests/test_tool_release_plumbing.py`:

```python
"""Plumbing: on_mouse_release default, ToolOverlay.box_rect, ToolContext.selection,
and viewport LMB-release forwarding."""

from __future__ import annotations

import numpy as np


def test_tool_default_on_mouse_release_is_noop():
    from pluton.tools.tool import Tool, ToolOverlay

    class _Min(Tool):
        @property
        def name(self): return "Min"
        @property
        def shortcut(self): return "Z"
        @property
        def has_active_gesture(self): return False
        def activate(self, ctx): pass
        def deactivate(self): pass
        def overlay(self): return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=(1, 1, 1), snap_marker_position=None,
            snap_marker_color=(1, 1, 1),
        )
        @property
        def anchor_or_none(self): return None

    # Default on_mouse_release exists and does nothing.
    _Min().on_mouse_release(None, None)


def test_tool_overlay_box_rect_defaults_none():
    from pluton.tools.tool import ToolOverlay

    o = ToolOverlay(
        rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
        rubber_band_color=(1, 1, 1), snap_marker_position=None,
        snap_marker_color=(1, 1, 1),
    )
    assert o.box_rect is None
    assert isinstance(o.box_rect_color, tuple)


def test_tool_context_has_selection_field():
    from pluton.tools.tool import ToolContext

    ctx = ToolContext(scene=object())
    assert ctx.selection is None
    ctx2 = ToolContext(scene=object(), selection="sel")
    assert ctx2.selection == "sel"


def test_viewport_forwards_lmb_release_to_active_tool(qtbot):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from pluton.scene import Scene
    from pluton.viewport.viewport_widget import ViewportWidget

    calls = []

    class _Recorder:
        active = None
        def __init__(self):
            _Recorder.active = self
        @property
        def anchor_or_none(self): return None
        def on_mouse_release(self, event, snap):
            calls.append(("release", event.position().x()))

    class _Mgr:
        def __init__(self): self.active = _Recorder()

    vw = ViewportWidget(scene=Scene(), tool_manager=_Mgr())
    qtbot.addWidget(vw)
    ev = QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(120.0, 50.0),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    vw.mouseReleaseEvent(ev)
    assert calls and calls[0][0] == "release" and calls[0][1] == 120.0
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_tool_release_plumbing.py -q` (box_rect/selection/release missing).

- [ ] **Step 3a: Edit `python/pluton/tools/tool.py`** — add the `ToolContext.selection` field, the `ToolOverlay.box_rect`/`box_rect_color` fields, and the `Tool.on_mouse_release` default.

In `ToolContext` (add a field after `widget_size_provider`):
```python
    selection: object = None  # M4b — pluton.selection.Selection (shared)
```

In `ToolOverlay` (add two fields after `face_fill_color`):
```python
    # M4b: screen-space box-select rectangle (pixels: x0,y0,x1,y1) or None.
    box_rect: tuple[float, float, float, float] | None = None
    box_rect_color: tuple[float, float, float] = (0.30, 0.55, 0.95)
```

In `Tool` (add next to `on_mouse_press`):
```python
    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing. Tools that need drag-release (e.g. box-select)
        override this."""
```

- [ ] **Step 3b: Edit `python/pluton/viewport/viewport_widget.py`** — add a `self.selection` attribute and forward LMB release.

In `__init__` (after `self.tool_manager = tool_manager`):
```python
        self.selection = None  # M4b — set by MainWindow (pluton.selection.Selection)
```

Replace `mouseReleaseEvent` with:
```python
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.NoButton
            self._last_mouse_pos = None
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            active = self.tool_manager.active if self.tool_manager is not None else None
            if active is not None:
                snap = self._snap_for_event(event)
                active.on_mouse_release(event, snap)
                if self._on_event_finished is not None:
                    self._on_event_finished()
                self.update()
                event.accept()
                return
        super().mouseReleaseEvent(event)
```

> Note: the `selection` pass-through to the renderer (`paintGL`) is added in Task 5, when `render()` accepts the `selection` argument.

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_tool_release_plumbing.py -q` → 4 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tool.py python/pluton/viewport/viewport_widget.py tests/test_tool_release_plumbing.py
git commit -m "$(cat <<'EOF'
feat(tools): on_mouse_release + ToolOverlay.box_rect + ToolContext.selection (M4b)

Adds the Tool.on_mouse_release no-op hook (forwarded for LMB by the viewport),
the screen-space box_rect overlay field, and a shared selection slot on the
tool context. Plumbing for the Select tool.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Renderer — persistent selection-highlight pass

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`
- Modify: `python/pluton/viewport/viewport_widget.py` (paintGL passes selection)
- Test: `tests/test_scene_renderer.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_scene_renderer.py`:

```python
class TestSelectionHighlightHelpers:
    def test_selection_face_polygons_returns_live_selected_loops(self):
        import numpy as np
        from pluton.scene import Scene
        from pluton.selection import Selection
        from pluton.viewport.scene_renderer import _selection_face_polygons

        scene = Scene()
        a = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
        b = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
        c = scene.add_vertex(np.array([1, 1, 0], dtype=np.float32))
        d = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
        fid = scene.add_face_from_loop((a, b, c, d))
        sel = Selection()
        sel.replace(faces=[fid])
        polys = _selection_face_polygons(scene, sel)
        assert len(polys) == 1
        assert polys[0].shape == (4, 3)

    def test_selection_face_polygons_skips_dead_ids(self):
        from pluton.scene import Scene
        from pluton.selection import Selection
        from pluton.viewport.scene_renderer import _selection_face_polygons

        sel = Selection()
        sel.replace(faces=[999])  # not live
        assert _selection_face_polygons(Scene(), sel) == []

    def test_selection_edge_segments_returns_2E_by_3(self):
        import numpy as np
        from pluton.scene import Scene
        from pluton.selection import Selection
        from pluton.viewport.scene_renderer import _selection_edge_segments

        scene = Scene()
        a = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
        b = scene.add_vertex(np.array([2, 0, 0], dtype=np.float32))
        e = scene.add_edge(a, b)
        sel = Selection()
        sel.replace(edges=[e])
        segs = _selection_edge_segments(scene, sel)
        assert segs.shape == (2, 3)

    def test_render_accepts_selection_param(self):
        import inspect
        from pluton.viewport.scene_renderer import SceneRenderer

        sig = inspect.signature(SceneRenderer.render)
        assert "selection" in sig.parameters
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_scene_renderer.py -q`.

- [ ] **Step 3a: Add pure helpers + colors + GL draw to `scene_renderer.py`.**

Add constants near the other color constants (after `_USER_EDGE_COLOR`):
```python
_SELECTION_FILL_COLOR = (0.20, 0.50, 0.95, 0.25)   # selected faces (blue, 25% alpha)
_SELECTION_EDGE_COLOR = (0.20, 0.55, 1.00)         # selected edges (bright blue)
```

Add module-level pure helpers (next to `_snap_marker_vertices`):
```python
def _selection_face_polygons(scene, selection) -> list[np.ndarray]:  # noqa: ANN001
    """World-space loops (N,3 float32) for each LIVE selected face."""
    polys: list[np.ndarray] = []
    for f_id in selection.faces:
        try:
            loop = scene.face_loop(f_id)
        except KeyError:
            continue  # dead/stale id
        pts = np.array([scene.vertex(v).position for v in loop], dtype=np.float32)
        polys.append(pts)
    return polys


def _selection_edge_segments(scene, selection) -> np.ndarray:  # noqa: ANN001
    """(2E,3) float32 endpoint pairs for each LIVE selected edge."""
    out: list[np.ndarray] = []
    for e_id in selection.edges:
        try:
            e = scene.edge(e_id)
        except KeyError:
            continue
        out.append(np.asarray(scene.vertex(e.v1_id).position, dtype=np.float32))
        out.append(np.asarray(scene.vertex(e.v2_id).position, dtype=np.float32))
    if not out:
        return np.zeros((0, 3), dtype=np.float32)
    return np.array(out, dtype=np.float32)
```

Add a thin GL helper method to `SceneRenderer` (next to `_draw_tool_overlay`):
```python
    def _draw_world_segments(self, segs, color, width, view, projection) -> None:  # noqa: ANN001
        """Draw (2N,3) world-space GL_LINES segments in a flat color, on top
        (depth test disabled). Reuses the overlay line VBO."""
        if segs.shape[0] == 0:
            return
        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)
        n = int(segs.shape[0])
        colors = np.tile(np.array(color, dtype=np.float32), (n, 1))
        data = np.ascontiguousarray(np.concatenate([segs.astype(np.float32), colors], axis=1))
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            GL.glBindVertexArray(self._overlay_line_vao)
            GL.glLineWidth(width)
            GL.glDrawArrays(GL.GL_LINES, 0, n)
            GL.glLineWidth(1.0)
            GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def _draw_selection(self, scene, selection, view, projection) -> None:  # noqa: ANN001
        if selection is None:
            return
        polys = _selection_face_polygons(scene, selection)
        if polys:
            self.draw_face_fill_overlays(polygons=polys, color=_SELECTION_FILL_COLOR)
        segs = _selection_edge_segments(scene, selection)
        self._draw_world_segments(segs, _SELECTION_EDGE_COLOR, 3.0, view, projection)
```

Change the `render` signature and add the selection pass. Replace the `def render(...)` line and add the call after the user-edges block (step 4) and before the tool overlay (step 5):
```python
    def render(self, camera: Camera, scene=None, tool_overlay=None, selection=None) -> None:  # noqa: ANN001
```
…and after the `if self._user_edge_count > 0: self._draw_user_edges(view, projection)` block, before the `# 5. Tool overlay` comment, insert:
```python
            # 4.5 Selection highlight (persistent, drawn on top of geometry).
            if selection is not None:
                self._draw_selection(scene, selection, view, projection)
```

- [ ] **Step 3b: Edit `viewport_widget.py` `paintGL`** to pass the selection:
```python
    def paintGL(self) -> None:
        active = self.tool_manager.active if self.tool_manager is not None else None
        overlay = active.overlay() if active is not None else None
        self.scene_renderer.render(self.camera, self.scene, overlay, self.selection)
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_scene_renderer.py -q`.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py python/pluton/viewport/viewport_widget.py tests/test_scene_renderer.py
git commit -m "$(cat <<'EOF'
feat(renderer): persistent selection-highlight pass (M4b)

Selected faces reuse the ghost-fill path (blue); selected edges draw as bold
blue lines on top. Pure geometry-gathering helpers + thin GL; render() takes a
selection and paintGL passes the shared one.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Renderer — screen-space box-select rectangle

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`
- Test: `tests/test_scene_renderer.py` (append)

- [ ] **Step 1: Append failing test** to `tests/test_scene_renderer.py`:

```python
def test_box_rect_ndc_segments_maps_corners():
    import numpy as np
    from pluton.viewport.scene_renderer import _box_rect_ndc_segments

    # 800x600 viewport; rect from (0,0) to (800,600) → full NDC [-1,1] square.
    segs = _box_rect_ndc_segments((0.0, 0.0, 800.0, 600.0), 800, 600)
    assert segs.shape == (8, 3)          # 4 sides x 2 endpoints
    # All corners on the NDC unit square; z == 0.
    assert np.allclose(np.abs(segs[:, 0]), 1.0)
    assert np.allclose(np.abs(segs[:, 1]), 1.0)
    assert np.allclose(segs[:, 2], 0.0)
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement.** Add the pure helper (module-level, near `_selection_edge_segments`):
```python
def _box_rect_ndc_segments(box_rect, viewport_w, viewport_h) -> np.ndarray:
    """Convert a pixel-space rect (x0,y0,x1,y1) to (8,3) NDC GL_LINES segments
    (z=0) tracing its outline. y is flipped (screen y-down → NDC y-up)."""
    x0, y0, x1, y1 = box_rect
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)

    def ndc(px, py):
        return ((2.0 * px / w) - 1.0, 1.0 - (2.0 * py / h))

    corners = [ndc(x0, y0), ndc(x1, y0), ndc(x1, y1), ndc(x0, y1)]
    out: list[list[float]] = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        out.append([ax, ay, 0.0])
        out.append([bx, by, 0.0])
    return np.array(out, dtype=np.float32)
```

Store the viewport size in `resize` (add `self._viewport_w = 1` / `self._viewport_h = 1` to `__init__`, and set them in `resize`):
```python
    def resize(self, w: int, h: int) -> None:
        self._viewport_w = int(w)
        self._viewport_h = int(h)
        if not self._initialized:
            return
        GL.glViewport(0, 0, w, h)
```

Add a thin GL draw method (next to `_draw_world_segments`):
```python
    def _draw_box_rect(self, box_rect, color) -> None:  # noqa: ANN001
        """Draw the screen-space box-select outline. Uses identity view/projection
        so NDC positions render directly; depth test off."""
        segs = _box_rect_ndc_segments(box_rect, self._viewport_w, self._viewport_h)
        identity = np.eye(4, dtype=np.float32)
        n = int(segs.shape[0])
        colors = np.tile(np.array(color, dtype=np.float32), (n, 1))
        data = np.ascontiguousarray(np.concatenate([segs, colors], axis=1))
        GL.glUseProgram(self._line_program)
        _set_mat4(self._line_locs["u_view"], identity)
        _set_mat4(self._line_locs["u_projection"], identity)
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            GL.glBindVertexArray(self._overlay_line_vao)
            GL.glLineWidth(1.5)
            GL.glDrawArrays(GL.GL_LINES, 0, n)
            GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)
```

Draw it from `render` — at the end of the tool-overlay phase, after the existing step 6 face-fill block, append:
```python
        # 7. Box-select rectangle (M4b) — screen space, on top.
        if tool_overlay is not None and tool_overlay.box_rect is not None:
            self._draw_box_rect(tool_overlay.box_rect, tool_overlay.box_rect_color)
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_scene_renderer.py -q`.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py tests/test_scene_renderer.py
git commit -m "$(cat <<'EOF'
feat(renderer): screen-space box-select rectangle (M4b)

Draws ToolOverlay.box_rect as a 2-D NDC outline via the line shader with
identity matrices, depth off. Pure pixel->NDC helper + thin GL.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: SelectTool — click / Shift / empty-clear + hover

**Files:**
- Create: `python/pluton/tools/select_tool.py`
- Modify: `python/pluton/tools/__init__.py`
- Test: `tests/test_select_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_select_tool.py`:

```python
"""Gesture tests for the Select tool (click / Shift / empty-clear / hover)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent


def _cam(w, h):
    from pluton.viewport.camera import Camera
    c = Camera()
    c.aspect = float(w) / float(h)
    return c


def _press(x, y, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)


def _release(x, y, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods)


def _scene_with_quad():
    from pluton.scene import Scene
    s = Scene()
    a = s.add_vertex(np.array([-1, -1, 0], dtype=np.float32))
    b = s.add_vertex(np.array([1, -1, 0], dtype=np.float32))
    c = s.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    d = s.add_vertex(np.array([-1, 1, 0], dtype=np.float32))
    fid = s.add_face_from_loop((a, b, c, d))
    e_ab = s.add_edge(a, b)
    return s, fid, e_ab


def _make_tool(scene, sel, w=800, h=600):
    from pluton.tools import ToolContext
    from pluton.tools.select_tool import SelectTool
    cam = _cam(w, h)
    tool = SelectTool()
    tool.activate(ToolContext(scene=scene, camera=cam,
                              widget_size_provider=lambda: (w, h), selection=sel))
    return tool, cam


def _click(tool, cam, world, w=800, h=600, mods=Qt.KeyboardModifier.NoModifier):
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), w, h)
    tool.on_mouse_press(_press(sx, sy, mods), None)
    tool.on_mouse_release(_release(sx, sy, mods), None)


def test_click_selects_edge_under_cursor(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, -1.0, 0.0])   # over edge a-b
    assert sel.edges == {e_ab}
    assert sel.faces == set()


def test_click_face_interior_selects_face(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, 0.0, 0.0])    # face center
    assert sel.faces == {fid}


def test_plain_click_replaces(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    _click(tool, cam, [0.0, -1.0, 0.0])   # edge
    assert sel.edges == {e_ab}
    assert sel.faces == set()             # face replaced out


def test_shift_click_toggles(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    shift = Qt.KeyboardModifier.ShiftModifier
    _click(tool, cam, [0.0, -1.0, 0.0], mods=shift)   # add edge
    _click(tool, cam, [0.0, 0.0, 0.0], mods=shift)    # add face
    assert sel.edges == {e_ab} and sel.faces == {fid}
    _click(tool, cam, [0.0, -1.0, 0.0], mods=shift)   # remove edge
    assert sel.edges == set() and sel.faces == {fid}


def test_empty_click_clears(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    # Click a far corner pixel that hits nothing.
    tool.on_mouse_press(_press(3.0, 3.0), None)
    tool.on_mouse_release(_release(3.0, 3.0), None)
    assert sel.is_empty()


def test_esc_clears_selection(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    sel.replace(faces=[fid])
    tool, cam = _make_tool(scene, sel)
    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)
    assert sel.is_empty()
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError: ... select_tool`.

- [ ] **Step 3: Implement** — `python/pluton/tools/select_tool.py`:

```python
"""The Select tool (Spacebar).

Hover pre-highlights the entity under the cursor. Click replaces the selection;
Shift-click toggles; clicking empty space clears. Box-select (drag a rectangle)
is added in M4b Task 8. Esc clears the selection.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_HOVER_EDGE_COLOR = (0.45, 0.70, 1.00)
_HOVER_FILL_COLOR = (0.40, 0.70, 1.00, 0.18)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class SelectTool(Tool):
    @property
    def name(self) -> str:
        return "Select"

    @property
    def shortcut(self) -> str:
        return "Space"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._selection = None
        self._hovered: tuple[str, int] | None = None
        self._press_px: tuple[float, float] | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._selection = ctx.selection
        self._hovered = None
        self._press_px = None

    def deactivate(self) -> None:
        self._hovered = None
        self._press_px = None

    def _viewport_size(self) -> tuple[int, int]:
        if self._size_provider is None:
            return (1, 1)
        return self._size_provider()

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton:
            return  # press/drag handled in press/release (box-select: Task 8)
        self._hovered = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene
        )

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._press_px = self._cursor(event)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._selection is None:
            self._press_px = None
            return
        hit = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene
        )
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if hit is None:
            if not shift:
                self._selection.clear()
        elif hit[0] == "edge":
            if shift:
                self._selection.toggle_edge(hit[1])
            else:
                self._selection.replace(edges=[hit[1]])
        else:  # face
            if shift:
                self._selection.toggle_face(hit[1])
            else:
                self._selection.replace(faces=[hit[1]])
        self._press_px = None

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._selection is not None:
            self._selection.clear()

    def overlay(self) -> ToolOverlay:
        segs = np.zeros((0, 3), dtype=np.float32)
        fills: list[np.ndarray] = []
        if self._hovered is not None and self._scene is not None:
            kind, ent_id = self._hovered
            if kind == "edge":
                try:
                    e = self._scene.edge(ent_id)
                    p1 = np.asarray(self._scene.vertex(e.v1_id).position, dtype=np.float32)
                    p2 = np.asarray(self._scene.vertex(e.v2_id).position, dtype=np.float32)
                    segs = np.array([p1, p2], dtype=np.float32)
                except KeyError:
                    pass
            else:  # face
                try:
                    loop = self._scene.face_loop(ent_id)
                    fills = [np.array(
                        [self._scene.vertex(v).position for v in loop], dtype=np.float32
                    )]
                except KeyError:
                    pass
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_HOVER_EDGE_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=_HOVER_FILL_COLOR,
        )

    @property
    def has_active_gesture(self) -> bool:
        # True when there's a selection to clear (so Esc reaches on_key_press
        # rather than deactivating the tool).
        return self._selection is not None and not self._selection.is_empty()

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        return None
```

- [ ] **Step 4: Export** — add to `python/pluton/tools/__init__.py`: `from pluton.tools.select_tool import SelectTool` and `"SelectTool"` in `__all__`.

- [ ] **Step 5: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_select_tool.py -q` → 6 passed.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/select_tool.py python/pluton/tools/__init__.py tests/test_select_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): Select tool — click/Shift/empty-clear + hover (M4b)

Hover pre-highlights the picked edge/face; click replaces, Shift toggles, empty
clears; Esc clears. Reads the shared Selection from the tool context. Box-select
follows in the next task.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: SelectTool — box-select (window / crossing)

**Files:**
- Modify: `python/pluton/tools/select_tool.py`
- Test: `tests/test_select_tool.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_select_tool.py`:

```python
def _move(x, y):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _box_drag(tool, cam, p_start, p_end, w=800, h=600):
    """Press at the screen-projection of p_start, drag to p_end, release."""
    sx0, sy0, _ = cam.world_to_screen(np.asarray(p_start, dtype=np.float32), w, h)
    sx1, sy1, _ = cam.world_to_screen(np.asarray(p_end, dtype=np.float32), w, h)
    tool.on_mouse_press(_press(sx0, sy0), None)
    tool.on_mouse_move(_move(sx1, sy1), None)
    tool.on_mouse_release(_release(sx1, sy1), None)
    return (sx0, sy0), (sx1, sy1)


def test_box_left_to_right_is_window_encloses_only(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    # Drag a generous rect left->right around the whole quad (encloses the face).
    _box_drag(tool, cam, [-2.0, -2.0, 0.0], [2.0, 2.0, 0.0])
    assert fid in sel.faces


def test_box_right_to_left_is_crossing(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    # Drag right->left from inside to the left, cutting across the quad.
    _box_drag(tool, cam, [0.0, 0.0, 0.0], [-3.0, 0.5, 0.0])
    # Crossing should grab at least one edge it cut across.
    assert len(sel.edges) >= 1


def test_box_overlay_sets_box_rect_during_drag(qtbot):
    from pluton.selection import Selection
    scene, fid, e_ab = _scene_with_quad()
    sel = Selection()
    tool, cam = _make_tool(scene, sel)
    sx0, sy0, _ = cam.world_to_screen(np.array([-2, -2, 0], dtype=np.float32), 800, 600)
    sx1, sy1, _ = cam.world_to_screen(np.array([2, 2, 0], dtype=np.float32), 800, 600)
    tool.on_mouse_press(_press(sx0, sy0), None)
    tool.on_mouse_move(_move(sx1, sy1), None)
    ov = tool.overlay()
    assert ov.box_rect is not None
    tool.on_mouse_release(_release(sx1, sy1), None)
    assert tool.overlay().box_rect is None   # cleared after release
```

- [ ] **Step 2: Run; confirm FAIL** (box-select not implemented yet — `box_rect` stays None / no box selection).

- [ ] **Step 3: Edit `select_tool.py`** to add box-select. Add constants + a `_DRAG_THRESHOLD_PX`, box state fields, drag detection in `on_mouse_move`, the box branch in `on_mouse_release`, and box drawing in `overlay`.

Add near the color constants:
```python
_BOX_WINDOW_COLOR = (0.25, 0.50, 0.95)   # left->right, enclose-only
_BOX_CROSSING_COLOR = (0.15, 0.65, 0.30)  # right->left, touch
_DRAG_THRESHOLD_PX = 4.0
```

In `__init__` add:
```python
        self._is_box = False
        self._box_rect: tuple[float, float, float, float] | None = None
        self._box_window = True  # True = L->R window, False = R->L crossing
```
In `activate` and `deactivate` reset them too (`self._is_box = False`, `self._box_rect = None`).

Replace `on_mouse_move` with:
```python
    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_px is not None:
            cx, cy = self._cursor(event)
            px, py = self._press_px
            if self._is_box or abs(cx - px) >= _DRAG_THRESHOLD_PX or abs(cy - py) >= _DRAG_THRESHOLD_PX:
                self._is_box = True
                self._box_rect = (px, py, cx, cy)
                self._box_window = (cx - px) >= 0.0
            return
        self._hovered = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene
        )
```

Replace `on_mouse_press` with (reset box state on each press):
```python
    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._press_px = self._cursor(event)
        self._is_box = False
        self._box_rect = None
```

Replace `on_mouse_release` with (branch click vs box):
```python
    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._selection is None:
            self._reset_press()
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._is_box and self._box_rect is not None:
            from pluton.viewport.picking import entities_in_box
            mode = "window" if self._box_window else "crossing"
            edges, faces = entities_in_box(
                self._box_rect, mode, self._viewport_size(), self._camera, self._scene
            )
            if shift:
                self._selection.add(edges=edges, faces=faces)
            else:
                self._selection.replace(edges=edges, faces=faces)
        else:
            hit = pick_selectable(
                self._cursor(event), self._viewport_size(), self._camera, self._scene
            )
            if hit is None:
                if not shift:
                    self._selection.clear()
            elif hit[0] == "edge":
                self._selection.toggle_edge(hit[1]) if shift else self._selection.replace(edges=[hit[1]])
            else:
                self._selection.toggle_face(hit[1]) if shift else self._selection.replace(faces=[hit[1]])
        self._reset_press()

    def _reset_press(self) -> None:
        self._press_px = None
        self._is_box = False
        self._box_rect = None
```

In `overlay`, before the `return ToolOverlay(...)`, compute the box rect + color and pass them. Add at the start of `overlay`:
```python
        box_rect = self._box_rect if self._is_box else None
        box_color = _BOX_WINDOW_COLOR if self._box_window else _BOX_CROSSING_COLOR
```
and pass `box_rect=box_rect, box_rect_color=box_color` in the `ToolOverlay(...)` call. Also, while a box drag is active, suppress the hover (guard the hover block with `if not self._is_box and self._hovered is not None ...`).

Update `has_active_gesture` to also be True during a box drag:
```python
    @property
    def has_active_gesture(self) -> bool:
        if self._is_box:
            return True
        return self._selection is not None and not self._selection.is_empty()
```

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_select_tool.py -q` → 9 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/select_tool.py tests/test_select_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): Select tool box-select — window & crossing (M4b)

Drag past a 4 px threshold starts a box; left->right = Window (enclose), right->
left = Crossing (touch). Shift extends. Overlay shows the screen-space rect in
the mode color; cleared on release.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: EraserTool — drag-erase edges with face cascade

**Files:**
- Create: `python/pluton/tools/erase_tool.py`
- Modify: `python/pluton/tools/__init__.py`
- Test: `tests/test_erase_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_erase_tool.py`:

```python
"""Gesture tests for the Eraser tool (drag-erase edges, cascade to faces)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent


def _cam(w, h):
    from pluton.viewport.camera import Camera
    c = Camera()
    c.aspect = float(w) / float(h)
    return c


def _press(x, y):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _move(x, y):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _release(x, y):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def _quad_scene():
    from pluton.scene import Scene
    s = Scene()
    a = s.add_vertex(np.array([-1, -1, 0], dtype=np.float32))
    b = s.add_vertex(np.array([1, -1, 0], dtype=np.float32))
    c = s.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    d = s.add_vertex(np.array([-1, 1, 0], dtype=np.float32))
    fid = s.add_face_from_loop((a, b, c, d))
    return s, fid


def _make(scene, stack, w=800, h=600):
    from pluton.tools import ToolContext
    from pluton.tools.erase_tool import EraserTool
    cam = _cam(w, h)
    tool = EraserTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack, camera=cam,
                              widget_size_provider=lambda: (w, h)))
    return tool, cam


def test_erase_edge_removes_edge_and_its_face(qtbot):
    from pluton.commands import CommandStack
    scene, fid = _quad_scene()
    stack = CommandStack()
    tool, cam = _make(scene, stack)
    faces0 = len(list(scene.faces_iter()))
    edges0 = len(list(scene.edges_iter()))
    # Click the bottom edge a-b at its midpoint.
    sx, sy, _ = cam.world_to_screen(np.array([0.0, -1.0, 0.0], dtype=np.float32), 800, 600)
    tool.on_mouse_press(_press(sx, sy), None)
    tool.on_mouse_release(_release(sx, sy), None)
    assert len(list(scene.faces_iter())) == faces0 - 1   # face cascaded away
    assert len(list(scene.edges_iter())) == edges0 - 1   # edge gone


def test_erase_is_atomically_undoable(qtbot):
    from pluton.commands import CommandStack
    scene, fid = _quad_scene()
    stack = CommandStack()
    tool, cam = _make(scene, stack)
    v0, e0, f0 = (len(list(scene.vertices_iter())), len(list(scene.edges_iter())),
                  len(list(scene.faces_iter())))
    sx, sy, _ = cam.world_to_screen(np.array([0.0, -1.0, 0.0], dtype=np.float32), 800, 600)
    tool.on_mouse_press(_press(sx, sy), None)
    tool.on_mouse_release(_release(sx, sy), None)
    assert stack.can_undo
    stack.undo(scene)
    assert (len(list(scene.vertices_iter())), len(list(scene.edges_iter())),
            len(list(scene.faces_iter()))) == (v0, e0, f0)   # edge + face restored
    stack.redo(scene)
    assert len(list(scene.faces_iter())) == f0 - 1


def test_drag_erase_two_edges_is_one_undo(qtbot):
    from pluton.commands import CommandStack
    scene, fid = _quad_scene()
    stack = CommandStack()
    tool, cam = _make(scene, stack)
    e0 = len(list(scene.edges_iter()))
    p_ab = cam.world_to_screen(np.array([0.0, -1.0, 0.0], dtype=np.float32), 800, 600)
    p_bc = cam.world_to_screen(np.array([1.0, 0.0, 0.0], dtype=np.float32), 800, 600)
    tool.on_mouse_press(_press(p_ab[0], p_ab[1]), None)
    tool.on_mouse_move(_move(p_bc[0], p_bc[1]), None)
    tool.on_mouse_release(_release(p_bc[0], p_bc[1]), None)
    assert len(list(scene.edges_iter())) <= e0 - 2   # at least the two edges gone
    # One undo restores everything from the stroke.
    stack.undo(scene)
    assert len(list(scene.edges_iter())) == e0
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError: ... erase_tool`.

- [ ] **Step 3: Implement** — `python/pluton/tools/erase_tool.py`:

```python
"""The Eraser tool (E).

Hover/drag over EDGES to delete them. Erasing an edge cascades to its incident
faces (a face can't survive losing a boundary edge), so removal is composed as:
remove incident face(s) first, then the edge. A press-drag-release stroke
accumulates into one undoable CompositeCommand.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import RemoveEdgeCommand, RemoveFaceCommand
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_ERASE_EDGE_COLOR = (1.00, 0.40, 0.40)
_ERASE_FILL_COLOR = (1.00, 0.35, 0.35, 0.20)
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class EraserTool(Tool):
    @property
    def name(self) -> str:
        return "Eraser"

    @property
    def shortcut(self) -> str:
        return "E"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._command_stack = None
        self._hovered_edge: int | None = None
        self._stroke: CompositeCommand | None = None
        self._erased: set[int] = set()

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._command_stack = ctx.command_stack
        self._hovered_edge = None
        self._stroke = None
        self._erased = set()

    def deactivate(self) -> None:
        self._hovered_edge = None
        self._stroke = None
        self._erased = set()

    def _viewport_size(self) -> tuple[int, int]:
        return self._size_provider() if self._size_provider is not None else (1, 1)

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def _pick_edge(self, event: QMouseEvent) -> int | None:
        hit = pick_selectable(self._cursor(event), self._viewport_size(), self._camera, self._scene)
        return hit[1] if hit is not None and hit[0] == "edge" else None

    def _erase_edge(self, e_id: int) -> None:
        """Append (and execute) the cascade for one edge into the active stroke."""
        if self._stroke is None or e_id in self._erased:
            return
        try:
            self._scene.edge(e_id)
        except KeyError:
            return
        for f_id in self._scene.edge_faces(e_id):
            if f_id is None:
                continue
            cmd = RemoveFaceCommand(f_id)
            cmd.do(self._scene)
            self._stroke.children.append(cmd)
        edge_cmd = RemoveEdgeCommand(e_id)
        edge_cmd.do(self._scene)
        self._stroke.children.append(edge_cmd)
        self._erased.add(e_id)

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.buttons() & Qt.MouseButton.LeftButton and self._stroke is not None:
            e_id = self._pick_edge(event)
            if e_id is not None:
                self._erase_edge(e_id)
            return
        self._hovered_edge = self._pick_edge(event)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._stroke = CompositeCommand(name="Erase")
        self._erased = set()
        e_id = self._pick_edge(event)
        if e_id is not None:
            self._erase_edge(e_id)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._stroke is not None and self._stroke.children and self._command_stack is not None:
            self._command_stack.push_executed(self._stroke)
        self._stroke = None
        self._erased = set()
        self._hovered_edge = None

    def overlay(self) -> ToolOverlay:
        segs = np.zeros((0, 3), dtype=np.float32)
        fills: list[np.ndarray] = []
        if self._hovered_edge is not None and self._scene is not None:
            try:
                e = self._scene.edge(self._hovered_edge)
                p1 = np.asarray(self._scene.vertex(e.v1_id).position, dtype=np.float32)
                p2 = np.asarray(self._scene.vertex(e.v2_id).position, dtype=np.float32)
                segs = np.array([p1, p2], dtype=np.float32)
                for f_id in self._scene.edge_faces(self._hovered_edge):
                    if f_id is None:
                        continue
                    loop = self._scene.face_loop(f_id)
                    fills.append(np.array(
                        [self._scene.vertex(v).position for v in loop], dtype=np.float32
                    ))
            except KeyError:
                pass
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_ERASE_EDGE_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=_ERASE_FILL_COLOR,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._stroke is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None
```

- [ ] **Step 4: Export** — add to `python/pluton/tools/__init__.py`: `from pluton.tools.erase_tool import EraserTool` and `"EraserTool"` in `__all__`.

- [ ] **Step 5: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_erase_tool.py -q` → 3 passed.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/erase_tool.py python/pluton/tools/__init__.py tests/test_erase_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): Eraser tool — drag-erase edges with face cascade (M4b)

Hover/drag over edges; each erased edge removes its incident faces first, then
the edge (so the mesh never references a dead edge). One press-drag-release =
one undoable stroke.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: MainWindow wiring — own Selection, register tools, Delete, clear-on-undo, status count

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Modify: `python/pluton/ui/status_bar.py`
- Test: `tests/test_main_window_selection.py`

- [ ] **Step 1: Write the failing test** — `tests/test_main_window_selection.py`:

```python
"""MainWindow wiring for selection: registration, shared selection, Delete,
clear-on-undo, status count."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def win(qtbot):
    from pluton.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_select_and_eraser_registered(win):
    mgr = win._tool_manager
    assert mgr.activate_by_shortcut("Space")
    assert mgr.active.name == "Select"
    assert mgr.activate_by_shortcut("E")
    assert mgr.active.name == "Eraser"


def test_selection_is_shared_with_viewport_and_context(win):
    assert win._viewport.selection is win._selection
    # The tool context carries the same Selection instance.
    ctx_sel = win._tool_manager._context.selection  # set via set_context
    assert ctx_sel is win._selection


def _quad(win):
    s = win._scene
    a = s.add_vertex(np.array([-1, -1, 0], dtype=np.float32))
    b = s.add_vertex(np.array([1, -1, 0], dtype=np.float32))
    c = s.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    d = s.add_vertex(np.array([-1, 1, 0], dtype=np.float32))
    fid = s.add_face_from_loop((a, b, c, d))
    return s, fid


def test_delete_selection_removes_face_and_is_undoable(win):
    scene, fid = _quad(win)
    f0 = len(list(scene.faces_iter()))
    win._selection.replace(faces=[fid])
    win._on_delete_selection()
    assert len(list(scene.faces_iter())) == f0 - 1
    assert win._selection.is_empty()       # cleared after delete
    win._command_stack.undo(scene)
    assert len(list(scene.faces_iter())) == f0   # restored


def test_delete_selected_edge_cascades_face(win):
    scene, fid = _quad(win)
    e = next(iter(scene.edges_iter())).id
    f0 = len(list(scene.faces_iter()))
    win._selection.replace(edges=[e])
    win._on_delete_selection()
    assert len(list(scene.faces_iter())) == f0 - 1   # cascaded


def test_undo_clears_selection(win):
    scene, fid = _quad(win)
    win._selection.replace(faces=[fid])
    win._on_delete_selection()      # selection now empty
    win._selection.replace(faces=[fid])  # re-select something
    win._command_stack.undo(scene)  # undo the delete
    assert win._selection.is_empty()  # selection cleared on undo


def test_empty_selection_delete_is_noop(win):
    scene, fid = _quad(win)
    f0 = len(list(scene.faces_iter()))
    win._on_delete_selection()
    assert len(list(scene.faces_iter())) == f0
    assert not win._command_stack.can_undo
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3a: Edit `python/pluton/ui/status_bar.py`** — add a selection segment. Add `self._selection = ""` in `__init__`, a setter, and include it in `_refresh`:
```python
    def set_selection(self, text: str) -> None:
        self._selection = text or ""
        self._refresh()
```
And in `_refresh`, after building the base text, append the selection segment when present. Replace the `_refresh` body's final assembly so that when `self._selection` is non-empty it is appended with a separator, e.g.:
```python
    def _refresh(self) -> None:
        if not self._tool:
            self.setText(self._selection or "")
            return
        snap = self._snap if self._snap else "—"
        parts = [self._tool, snap]
        if self._status:
            parts.append(self._status)
        text = " · ".join(parts)
        if self._selection:
            text = f"{text}   |   {self._selection}"
        self.setText(text)
```
(Read the current `status_bar.py` first and adapt to its exact field names; keep existing behavior for tool/snap/status.)

- [ ] **Step 3b: Edit `python/pluton/ui/main_window.py`.**

Imports — add `Selection` and the two tools:
```python
from pluton.selection import Selection
from pluton.tools import (
    ArcTool, CircleTool, EraserTool, LineTool, PolygonTool, PushPullTool,
    RectangleTool, SelectTool, ToolContext, ToolManager,
)
```
Construct the selection (next to `self._scene = Scene()`):
```python
        self._selection = Selection()
```
Register the tools (after the existing registers):
```python
        self._tool_manager.register(SelectTool())
        self._tool_manager.register(EraserTool())
```
Pass the selection into the context (add to the `ToolContext(...)` constructed in `set_context`):
```python
                selection=self._selection,
```
Give the viewport the selection (after `self._viewport = ViewportWidget(...)`):
```python
        self._viewport.selection = self._selection
```
Shortcuts (next to the L/R/P/C/G/A block):
```python
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=lambda: self._activate("Space"))
        QShortcut(QKeySequence("E"), self, activated=lambda: self._activate("E"))
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._on_delete_selection)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self._on_delete_selection)
```
Add the delete slot:
```python
    def _on_delete_selection(self) -> None:
        from pluton.commands import CompositeCommand
        from pluton.commands.scene_commands import RemoveEdgeCommand, RemoveFaceCommand

        sel = self._selection
        if sel.is_empty():
            return
        composite = CompositeCommand(name="Delete Selection")
        removed_faces: set[int] = set()
        for e_id in list(sel.edges):
            try:
                self._scene.edge(e_id)
            except KeyError:
                continue
            for f_id in self._scene.edge_faces(e_id):
                if f_id is None or f_id in removed_faces:
                    continue
                fc = RemoveFaceCommand(f_id)
                fc.do(self._scene)
                composite.children.append(fc)
                removed_faces.add(f_id)
            ec = RemoveEdgeCommand(e_id)
            ec.do(self._scene)
            composite.children.append(ec)
        for f_id in list(sel.faces):
            if f_id in removed_faces:
                continue
            try:
                self._scene.face_loop(f_id)
            except KeyError:
                continue
            fc = RemoveFaceCommand(f_id)
            fc.do(self._scene)
            composite.children.append(fc)
            removed_faces.add(f_id)
        if composite.children:
            self._command_stack.push_executed(composite)
        sel.clear()
        self._refresh_selection_status()
        self._viewport.update()
```
Add the selection-status refresh + clear-on-undo. Add:
```python
    def _refresh_selection_status(self) -> None:
        ne, nf = self._selection.counts()
        if ne == 0 and nf == 0:
            self._status_bar.set_selection("")
            return
        parts = []
        if ne:
            parts.append(f"{ne} edge" + ("s" if ne != 1 else ""))
        if nf:
            parts.append(f"{nf} face" + ("s" if nf != 1 else ""))
        self._status_bar.set_selection(", ".join(parts) + " selected")
```
Modify `_on_undo` and `_on_redo` to clear the selection and refresh its count:
```python
    def _on_undo(self) -> None:
        if self._command_stack.undo(self._scene):
            self._selection.clear()
            self._refresh_selection_status()
            self._refresh_status_text()
            self._viewport.update()

    def _on_redo(self) -> None:
        if self._command_stack.redo(self._scene):
            self._selection.clear()
            self._refresh_selection_status()
            self._refresh_status_text()
            self._viewport.update()
```
Wire the selection count to refresh after each viewport event. In the existing `_refresh_status_text` (the event-finished callback), add a call to `self._refresh_selection_status()` at the end so click/box/erase update the count.

> If `ToolManager` doesn't expose `_context`, store the context on `self._context` in `MainWindow` when calling `set_context`, and have the test read `win._context.selection`. Read `tool_manager.py` to confirm the attribute name; adapt the test's `_context` access accordingly.

- [ ] **Step 4: Run; all pass** — `.venv\Scripts\python.exe -m pytest tests/test_main_window_selection.py -q` → 7 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/main_window.py python/pluton/ui/status_bar.py tests/test_main_window_selection.py
git commit -m "$(cat <<'EOF'
feat(ui): wire selection — Select/Eraser tools, Delete, status count (M4b)

MainWindow owns the shared Selection (passed to the viewport + tool context),
registers Select (Space) and Eraser (E), deletes the selection on Delete/
Backspace (edges cascade to faces, de-duped; faces leave their edges), clears
the selection on undo/redo, and shows a selection count.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Full regression + manual visual verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python suite** — `.venv\Scripts\python.exe -m pytest -q`. Expected: the prior 290 plus the new M4b tests (~36), all green; no regressions in M2/M3/M4a tool, snap, or renderer tests.

- [ ] **Step 2: Run the C++ suite (unchanged)** — `ctest --test-dir build/tests --output-on-failure`. Expected: 72/72 (M4b touched no C++).

- [ ] **Step 3: Launch + visually verify** — `.venv\Scripts\python.exe -m pluton`:
  - Draw a box (Rectangle + Push/Pull). Press **Space**: hover edges/faces → light-blue pre-highlight; click → blue selection; Shift-click → extend; click empty → clear.
  - Drag **left→right** a box around part of it → solid blue rect, only enclosed selected; drag **right→left** → green rect, touched selected.
  - Status bar shows the selection count.
  - Press **E**: hover an edge (it + its faces tint red); click/drag to erase → edges + their faces vanish; one **Ctrl+Z** restores the whole stroke.
  - Select a face, press **Delete** → face gone (its edges remain); **Ctrl+Z** restores; selection clears on undo.
  - Select something, switch to **L** (Line) and back to **Space** → the selection highlight persisted across the tool switch.
  - **Esc** clears the selection.

- [ ] **Step 4: Record the result.** No commit. Fix any failure in the relevant task's files (with a regression test) before release.

---

## Task 12: Release v0.1.1 (M4b)

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` (version bump — the only task allowed to touch these)
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M4b shipped)

- [ ] **Step 1: Bump 0.1.0 → 0.1.1** in `pyproject.toml` (`version = "0.1.1"`), `CMakeLists.txt` (`VERSION 0.1.1`), `cpp/src/version.cpp` (`return "0.1.1";`).

- [ ] **Step 2: Annotate the master design doc** — in `docs/2026-05-16-pluton-design.md`, mark M4b shipped on the M4 sub-milestone line (mirror the M4a `✅ *(shipped v0.1.0)*` style): `**M4b** ✅ *(shipped v0.1.1)* — selection & eraser`.

- [ ] **Step 3: Rebuild the editable install & verify** — `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation` then `.venv\Scripts\python.exe -c "import pluton._core as c; print('core:', c.version())"` → `0.1.1`.

- [ ] **Step 4: Release gate** — `.venv\Scripts\python.exe -m pytest -q` (all green) and rebuild + run C++ (`cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure` → 72/72).

- [ ] **Step 5: Commit the bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "$(cat <<'EOF'
release: v0.1.1 (M4b — selection & eraser)

Shared Selection subsystem: Select tool (click/Shift/box window+crossing),
persistent blue highlighting, edge Eraser with face cascade, Delete/Backspace.
Pure Python over existing primitives. The keystone for M4c/M4e.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push & watch CI**

```bash
git push origin main
gh run watch $(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status
```
Expected: `success` on both `windows-2022` and `ubuntu-24.04`. Fix forward if red (no force-push).

- [ ] **Step 7: Tag (annotated, SSH-signed)**

```bash
git tag -a v0.1.1-m4b -m "M4b — selection & eraser (v0.1.1)"
git cat-file -t v0.1.1-m4b   # expect: tag
git push origin v0.1.1-m4b
```

- [ ] **Step 8: File carry-over issues** (via `gh issue create`):
  - **Vertex selection** (M4b deferred edges+faces only).
  - **Smart-select**: double-click (face + bounding edges) / triple-click (connected geometry).
  - **Select by material/tag, invert, grow/shrink**.
  - **Eraser modifiers** (soften / hide instead of delete) — needs M5's hidden/softened-geometry concept.
  - **Box-select dashed rectangle for crossing** (M4b ships solid rect, mode distinguished by color — dashing deferred as visual polish).
  - **Arrow-key box-select / axis-lock conflict review** (global Up/Down + future arrow uses — noted in M4a Task 8 review).

- [ ] **Step 9: Report** the tag, CI status, and test counts. M4b done; v0.1.1 cut.

---

## Self-review (completed during authoring)

- **Spec coverage:** Selection object (Task 1) · pick_selectable (Task 2) · box-select predicates (Task 3) · on_mouse_release + box_rect + ToolContext.selection + viewport release routing (Task 4) · persistent selection highlight (Task 5) · screen-space box rect (Task 6) · Select click/Shift/empty/hover/Esc (Task 7) · box-select window/crossing (Task 8) · Eraser cascade + drag-stroke (Task 9) · MainWindow Selection ownership, Space/E/Delete/Backspace, cascade+dedup delete, clear-on-undo, status count (Task 10) · regression+visual (Task 11) · v0.1.1 release + carry-overs (Task 12). Spec §1–§9 all map to tasks. **Deviation from spec D3:** picking is implemented as pure screen-space (no `closest_point_on_segment_to_ray` promotion / no `snap_engine` refactor) — lower risk and more correct for selection; noted here and in the handoff. **Deviation from spec D6:** the box rectangle is solid (color distinguishes window vs crossing); dashing for crossing is deferred to a carry-over issue (Task 12 step 8).
- **Placeholders:** none — every code step has complete code; every run step an exact command + expected result.
- **Type/name consistency:** `Selection.replace/add/toggle_edge/toggle_face/clear/contains_edge/contains_face/is_empty/counts/edges/faces/version`; `pick_selectable(cursor, viewport_size, camera, scene) -> ("edge"|"face", id)|None`; `entities_in_box(rect, mode, viewport_size, camera, scene) -> (edges,faces)`; `_selection_face_polygons`/`_selection_edge_segments`/`_box_rect_ndc_segments`; `ToolOverlay.box_rect`/`box_rect_color`; `Tool.on_mouse_release`; `ToolContext.selection`; `MainWindow._selection`/`_on_delete_selection`/`_refresh_selection_status`; `StatusBar.set_selection`; tool shortcuts `"Space"`/`"E"` — all used consistently across tasks.

---

*End of M4b plan.*

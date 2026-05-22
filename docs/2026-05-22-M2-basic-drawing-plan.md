# M2 — Basic Drawing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add interactive 2D drawing to the M1 viewport — Line tool, Rectangle tool, ground-plane snapping (grid + endpoint + midpoint + axis-lock), a generic Tool framework, a pure-Python `Scene` data model with auto-face on closed planar loop, and a bottom status bar that doubles as the future home of the M4 Measurements Box.

**Architecture:** Python owns the editable `Scene` (Vertex/Edge/Face dicts). A `SnapEngine` evaluates snap candidates per-precedence-class and returns a `SnapResult`. A `Tool` ABC + `ToolManager` lets tools own small state machines and emit a per-frame `ToolOverlay`. The existing `SceneRenderer` gains three new passes (user-face, user-edge, tool-overlay) and drops the M1 hardcoded cube. `ViewportWidget` raycasts the cursor to Z=0, asks the `SnapEngine`, forwards events to the active tool, and triggers repaints. `MainWindow` instantiates the `ToolManager`, hosts the `StatusBar`, and binds keyboard shortcuts (`L`, `R`, `Esc`, `Ctrl+N`). C++ kernel is untouched — first Python-only milestone.

**Tech Stack:** Python 3.13, PySide6 (Qt 6), PyOpenGL, numpy, **mapbox-earcut** (new dep), pytest + pytest-qt.

**Spec:** `docs/2026-05-22-M2-basic-drawing-design.md`

**Prerequisite:** M1 complete (tag `v0.0.2-m1`). Working tree clean on `main`.

---

## Build & Test Commands Reference

Same incantation as M1 — M2 doesn't add or change any C++ deps. The scikit-build-core build directory pattern stays `build/{wheel_tag}/`.

**Git Bash / Linux / macOS:**
```bash
export VCPKG_ROOT=/c/vcpkg
export SKBUILD_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
export VCPKG_BINARY_SOURCES=clear

alias pluton-build='pip install -e . --no-build-isolation'
alias pluton-cpp-tests='ctest --test-dir "$(ls -d build/*/ | head -1)" --output-on-failure'
alias pluton-py-tests='pytest -v'
```

**Windows PowerShell:**
```powershell
$env:VCPKG_ROOT = "C:\vcpkg"
$env:SKBUILD_CMAKE_ARGS = "-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake"
$env:VCPKG_BINARY_SOURCES = "clear"

function pluton-build { pip install -e . --no-build-isolation }
function pluton-cpp-tests {
    $build = (Get-ChildItem build/ -Directory | Select-Object -First 1).FullName
    ctest --test-dir $build --output-on-failure
}
function pluton-py-tests { pytest -v }
```

Each task below uses `pluton-build`, `pluton-py-tests`, `pluton-cpp-tests` as shorthand. Tasks 2–17 are Python-only — they need `pluton-py-tests` only and **do not require a C++ rebuild** unless `python/` symlinks have been clobbered (rare). Task 1 (`pip install -e .`) covers the dependency addition; later Python edits are hot-picked up by the editable install.

---

## File Map

**Python — Scene package (NEW)**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/scene/__init__.py` | NEW | Re-exports `Vertex`, `Edge`, `Face`, `Scene` |
| `python/pluton/scene/vertex.py` | NEW | `Vertex` frozen dataclass |
| `python/pluton/scene/edge.py` | NEW | `Edge` frozen dataclass |
| `python/pluton/scene/face.py` | NEW | `Face` frozen dataclass |
| `python/pluton/scene/scene.py` | NEW | `Scene` class — mutable, dict-backed |

**Python — Tools package (NEW)**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/tools/__init__.py` | NEW | Re-exports `Tool`, `ToolContext`, `ToolOverlay`, `ToolManager`, `LineTool`, `RectangleTool` |
| `python/pluton/tools/tool.py` | NEW | `Tool` ABC, `ToolContext`, `ToolOverlay` |
| `python/pluton/tools/tool_manager.py` | NEW | `ToolManager` (one active tool at a time) |
| `python/pluton/tools/rectangle_tool.py` | NEW | `RectangleTool` state machine |
| `python/pluton/tools/line_tool.py` | NEW | `LineTool` state machine |

**Python — Viewport (MODIFIED + 1 NEW)**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/viewport/snap_engine.py` | NEW | `SnapKind`, `SnapResult`, `SnapEngine` |
| `python/pluton/viewport/camera.py` | MODIFY | Add `ray_from_screen` + `ray_intersect_ground` |
| `python/pluton/viewport/scene_renderer.py` | MODIFY | Drop M1 cube; add user-face / user-edge / tool-overlay passes |
| `python/pluton/viewport/viewport_widget.py` | MODIFY | Delegate events to active tool; raycast cursor; trigger snap evaluation |

**Python — UI (MODIFIED + 1 NEW)**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/ui/status_bar.py` | NEW | `StatusBar` QWidget (two-slot label) |
| `python/pluton/ui/main_window.py` | MODIFY | Instantiates `ToolManager` + `Scene`; binds `L`/`R`/`Esc`/`Ctrl+N`; docks `StatusBar` |

**Tests**

| Path | Status | Responsibility |
|---|---|---|
| `tests/test_scene.py` | NEW | Vertex/Edge/Face + Scene mutators/queries |
| `tests/test_snap_engine.py` | NEW | Each SnapKind + precedence + NONE-above-horizon |
| `tests/test_camera.py` | MODIFY | Add `ray_from_screen` + `ray_intersect_ground` tests |
| `tests/test_tool_manager.py` | NEW | Register / activate / deactivate / shortcut |
| `tests/test_rectangle_tool.py` | NEW | State machine + commit + zero-area + ESC |
| `tests/test_line_tool.py` | NEW | Three-branch logic + ESC + < 3 close attempt |
| `tests/test_status_bar.py` | NEW | Two-slot text updates |
| `tests/test_viewport.py` | MODIFY | Keyboard bindings, status-bar wiring, full gestures via qtbot |

**Versioning / build**

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | MODIFY | Add `mapbox-earcut` dep (Task 1); bump `version = "0.0.3"` (last task) |
| `CMakeLists.txt` (top-level) | MODIFY | Bump `project(... VERSION 0.0.3 ...)` (last task) |
| `cpp/src/version.cpp` | MODIFY | Return `"0.0.3"` (last task) |

---

## Definition of Done for M2

1. `python -m pluton` launches a window showing: grid + colored axes only (no cube), empty status bar at the bottom of the central widget.
2. Pressing `R` then click-drag-click on the ground draws a filled rectangle face.
3. Pressing `L` then clicking out a polyline that ends at the first vertex draws a filled (possibly concave) face.
4. While drawing, grid / endpoint / midpoint / axis-lock snaps fire with correct precedence; rubber-band colours by axis when locked; status bar reads `<tool> · <snap>`.
5. `Esc` cancels mid-gesture; `Ctrl+N` clears the scene; tool stays active.
6. MMB orbit / Shift+MMB pan / wheel zoom from M1 still work and don't trigger tool events.
7. All pytest tests pass locally (~57–62 total).
8. All GoogleTest tests pass locally (14 — unchanged).
9. CI green on Windows + Linux.
10. Tagged `v0.0.3-m2` (annotated, SSH-signed).
11. Tag pushed to GitHub.
12. Carry-over GitHub issues opened for each entry in §5.6 and §6 of the spec.

---

## Task 1: Add `mapbox-earcut` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml`** — add `mapbox-earcut` to `dependencies`

Replace:
```toml
dependencies = [
    "numpy>=2.0",
    "PySide6>=6.7",
    "PyOpenGL>=3.1.7"
]
```
with:
```toml
dependencies = [
    "numpy>=2.0",
    "PySide6>=6.7",
    "PyOpenGL>=3.1.7",
    "mapbox-earcut>=2.0"
]
```

- [ ] **Step 2: Reinstall to pick up the new dep**

Run: `pluton-build`
Expected: build succeeds; pip installs `mapbox-earcut` from PyPI.

- [ ] **Step 3: Verify the import works**

Run: `python -c "import mapbox_earcut; import numpy as np; xy = np.array([[0,0],[1,0],[1,1],[0,1]], dtype=np.float32); print(mapbox_earcut.triangulate_float32(xy, np.array([4], dtype=np.uint32)))"`
Expected: prints a uint32 numpy array of shape `(6,)` containing two triangles' worth of indices (e.g. `[2 3 0 0 1 2]`).

**Note (mapbox-earcut 2.x API):** the function takes a `(N, 2)` shaped float32 array — not the flat `(2*N,)` form from v1. Pass the 2D array directly; do not reshape.

- [ ] **Step 4: Existing tests still pass**

Run: `pluton-py-tests`
Expected: 32 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build(m2): add mapbox-earcut dependency for face triangulation

mapbox-earcut is the standard ear-clipping triangulator. M2's Line tool can
close arbitrary (convex or concave) planar loops; earcut converts those into
GL-ready triangle index buffers. Wheel-only Python dep — no C++ changes."
```

---

## Task 2: Scene dataclasses (Vertex, Edge, Face)

**Files:**
- Create: `python/pluton/scene/__init__.py`
- Create: `python/pluton/scene/vertex.py`
- Create: `python/pluton/scene/edge.py`
- Create: `python/pluton/scene/face.py`
- Create: `tests/test_scene.py`

- [ ] **Step 1: Write the failing test** at `tests/test_scene.py`

```python
"""Unit tests for the Python scene data model (Vertex, Edge, Face, Scene)."""

from __future__ import annotations

import numpy as np
import pytest


def test_vertex_holds_id_and_position():
    from pluton.scene import Vertex

    v = Vertex(id=7, position=np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert v.id == 7
    np.testing.assert_array_equal(v.position, np.array([1.0, 2.0, 3.0], dtype=np.float32))


def test_vertex_is_frozen():
    from pluton.scene import Vertex

    v = Vertex(id=0, position=np.array([0.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(Exception):
        v.id = 1  # type: ignore[misc]


def test_edge_holds_id_and_two_vertex_ids():
    from pluton.scene import Edge

    e = Edge(id=3, v1_id=10, v2_id=20)
    assert e.id == 3
    assert e.v1_id == 10
    assert e.v2_id == 20


def test_face_holds_id_loop_normal_triangles():
    from pluton.scene import Face

    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    f = Face(
        id=5,
        loop_vertex_ids=(0, 1, 2, 3),
        plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        triangles=triangles,
    )
    assert f.id == 5
    assert f.loop_vertex_ids == (0, 1, 2, 3)
    np.testing.assert_array_equal(f.plane_normal, np.array([0.0, 0.0, 1.0], dtype=np.float32))
    np.testing.assert_array_equal(f.triangles, triangles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scene.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.scene'`.

- [ ] **Step 3: Create the package init** at `python/pluton/scene/__init__.py`

```python
"""Python scene data model: Vertex / Edge / Face / Scene.

Pure-Python topology for M2 drawing. Half-edge structure is deferred to M3,
where push/pull is the first consumer that justifies it (per the M1 design
doc rationale).
"""

from __future__ import annotations

from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex

__all__ = ["Edge", "Face", "Vertex"]
```

- [ ] **Step 4: Create `Vertex`** at `python/pluton/scene/vertex.py`

```python
"""A single vertex in the Python scene."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Vertex:
    """A vertex with a stable integer ID and a Z-up world-space position.

    `position` is an (3,) float32 numpy array. Positions are exact — the snap
    engine produces deterministic snapped points, and `Scene.add_vertex` uses
    exact equality (not an epsilon) for idempotent insertion.
    """

    id: int
    position: np.ndarray
```

- [ ] **Step 5: Create `Edge`** at `python/pluton/scene/edge.py`

```python
"""An undirected edge between two vertices."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Edge:
    """An undirected edge with a stable integer ID.

    `v1_id < v2_id` is the canonical ordering — `Scene.add_edge` enforces it
    on insertion so unordered de-duplication is a single dict lookup.
    """

    id: int
    v1_id: int
    v2_id: int
```

- [ ] **Step 6: Create `Face`** at `python/pluton/scene/face.py`

```python
"""A planar face — closed loop of vertices with eager triangulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Face:
    """A planar face bounded by an ordered vertex loop.

    `loop_vertex_ids` is the ordered tuple of vertex IDs walking the boundary
    CCW from +Z (the ground-plane convention in M2). `plane_normal` is a unit
    vector — (0, 0, 1) for all M2 ground-plane faces. `triangles` is an
    (N, 3) int32 array of vertex IDs per triangle, produced by earcut at
    insertion time so the renderer never re-triangulates.
    """

    id: int
    loop_vertex_ids: tuple[int, ...]
    plane_normal: np.ndarray
    triangles: np.ndarray
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_scene.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add python/pluton/scene/ tests/test_scene.py
git commit -m "feat(scene): add Vertex / Edge / Face dataclasses

Frozen, slotted dataclasses with stable integer IDs. Z-up world positions
on Vertex; canonical v1_id < v2_id ordering on Edge; eager earcut
triangulation stored on Face."
```

---

## Task 3: `Scene` with `add_vertex` and `clear`

**Files:**
- Create: `python/pluton/scene/scene.py`
- Modify: `python/pluton/scene/__init__.py`
- Modify: `tests/test_scene.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_scene.py`

```python
def test_scene_starts_empty():
    from pluton.scene import Scene

    s = Scene()
    assert len(list(s.vertices_iter())) == 0
    assert len(list(s.edges_iter())) == 0
    assert len(list(s.faces_iter())) == 0
    assert s.dirty is False


def test_add_vertex_returns_new_id_when_position_is_new():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    assert v0 != v1
    assert s.dirty is True


def test_add_vertex_is_idempotent_on_exact_match():
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([2.0, 3.0, 0.0], dtype=np.float32)
    v0 = s.add_vertex(pos)
    v1 = s.add_vertex(pos.copy())  # different array object, same exact values
    assert v0 == v1


def test_clear_resets_dirty_flag_and_removes_everything():
    from pluton.scene import Scene

    s = Scene()
    s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    s.mark_clean()  # simulate the renderer consuming the buffers
    assert s.dirty is False

    s.clear()
    assert len(list(s.vertices_iter())) == 0
    assert s.dirty is True


def test_vertex_lookup_by_id():
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([5.0, 6.0, 0.0], dtype=np.float32)
    vid = s.add_vertex(pos)
    v = s.vertex(vid)
    assert v.id == vid
    np.testing.assert_array_equal(v.position, pos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene.py -v`
Expected: 5 new tests FAIL with `ImportError: cannot import name 'Scene' from 'pluton.scene'`.

- [ ] **Step 3: Create `Scene`** at `python/pluton/scene/scene.py`

```python
"""The editable polygonal scene.

Pure-Python topology. Stable integer IDs for vertices, edges, and faces.
Idempotent mutators (`add_vertex`, `add_edge`) so tools never have to check
existence before inserting. A single `dirty` flag tracks "has the renderer
seen the current state yet"; the renderer calls `mark_clean()` after
re-uploading buffers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from pluton.scene.vertex import Vertex

if TYPE_CHECKING:
    from pluton.scene.edge import Edge
    from pluton.scene.face import Face


class Scene:
    """Editable polygonal scene with stable integer IDs."""

    def __init__(self) -> None:
        self._vertices: dict[int, Vertex] = {}
        self._edges: dict[int, Edge] = {}
        self._faces: dict[int, Face] = {}
        self._next_vertex_id = 0
        self._next_edge_id = 0
        self._next_face_id = 0
        # Maps tuple(position.tobytes()) -> vertex_id for idempotent add_vertex.
        self._position_index: dict[bytes, int] = {}
        self._dirty: bool = False

    # --- Mutators ---------------------------------------------------------

    def add_vertex(self, position: np.ndarray) -> int:
        """Insert a vertex at `position` (float32 (3,)) and return its ID.

        Idempotent on exact equality: re-adding the same position returns the
        existing vertex's ID. No epsilon — the snap engine produces
        deterministic positions, so float equality is the right contract.
        """
        if position.dtype != np.float32 or position.shape != (3,):
            position = np.asarray(position, dtype=np.float32).reshape(3)
        key = position.tobytes()
        existing = self._position_index.get(key)
        if existing is not None:
            return existing
        vid = self._next_vertex_id
        self._next_vertex_id += 1
        self._vertices[vid] = Vertex(id=vid, position=position.copy())
        self._position_index[key] = vid
        self._dirty = True
        return vid

    def clear(self) -> None:
        """Reset the scene to empty. Renderer will re-upload empty buffers."""
        self._vertices.clear()
        self._edges.clear()
        self._faces.clear()
        self._next_vertex_id = 0
        self._next_edge_id = 0
        self._next_face_id = 0
        self._position_index.clear()
        self._dirty = True

    def mark_clean(self) -> None:
        """Renderer calls this after consuming the current buffers."""
        self._dirty = False

    # --- Queries ----------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    def vertex(self, vid: int) -> Vertex:
        return self._vertices[vid]

    def vertices_iter(self) -> Iterable[Vertex]:
        return self._vertices.values()

    def edges_iter(self) -> Iterable[Edge]:
        return self._edges.values()

    def faces_iter(self) -> Iterable[Face]:
        return self._faces.values()
```

- [ ] **Step 4: Re-export `Scene`** — edit `python/pluton/scene/__init__.py`

Replace:
```python
from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex

__all__ = ["Edge", "Face", "Vertex"]
```
with:
```python
from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.scene import Scene
from pluton.scene.vertex import Vertex

__all__ = ["Edge", "Face", "Scene", "Vertex"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scene.py -v`
Expected: 9 passed (4 from Task 2 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/scene/scene.py python/pluton/scene/__init__.py tests/test_scene.py
git commit -m "feat(scene): add Scene class with add_vertex + clear

Dict-backed Scene with stable integer IDs. add_vertex is idempotent on
exact float32 equality via a position-bytes index. dirty/mark_clean lets
the renderer skip uploads when nothing changed."
```

---

## Task 4: `Scene.add_edge` with dedup and self-loop rejection

**Files:**
- Modify: `python/pluton/scene/scene.py`
- Modify: `tests/test_scene.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_scene.py`

```python
def test_add_edge_returns_new_id():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    e = s.add_edge(v0, v1)
    assert isinstance(e, int)


def test_add_edge_is_idempotent_unordered():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    a = s.add_edge(v0, v1)
    b = s.add_edge(v1, v0)  # swapped order
    assert a == b


def test_add_edge_rejects_self_loop():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    with pytest.raises(ValueError):
        s.add_edge(v0, v0)


def test_add_edge_canonicalises_endpoints():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    eid = s.add_edge(v1, v0)
    e = next(iter(s.edges_iter()))
    assert e.id == eid
    assert e.v1_id == min(v0, v1)
    assert e.v2_id == max(v0, v1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene.py -v`
Expected: 4 new FAIL with `AttributeError: 'Scene' object has no attribute 'add_edge'`.

- [ ] **Step 3: Add `add_edge` to `Scene`** — edit `python/pluton/scene/scene.py`

Add the import at the top (replace the `if TYPE_CHECKING:` block):
```python
from pluton.scene.edge import Edge

if TYPE_CHECKING:
    from pluton.scene.face import Face
```

Add this method to `Scene`, placed immediately after `add_vertex`:
```python
    def add_edge(self, v1_id: int, v2_id: int) -> int:
        """Insert an undirected edge between two existing vertices.

        Idempotent on the unordered pair: ``add_edge(a, b)`` and
        ``add_edge(b, a)`` return the same edge ID. Rejects self-loops with
        ValueError — tools should never request one.
        """
        if v1_id == v2_id:
            raise ValueError(f"self-loop edge requested at vertex {v1_id}")
        a, b = (v1_id, v2_id) if v1_id < v2_id else (v2_id, v1_id)
        key = (a, b)
        existing = self._edge_index.get(key)
        if existing is not None:
            return existing
        eid = self._next_edge_id
        self._next_edge_id += 1
        self._edges[eid] = Edge(id=eid, v1_id=a, v2_id=b)
        self._edge_index[key] = eid
        self._dirty = True
        return eid
```

Add `self._edge_index: dict[tuple[int, int], int] = {}` to `__init__` after `_position_index`. Add `self._edge_index.clear()` to `clear()` after `_position_index.clear()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scene.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene.py
git commit -m "feat(scene): Scene.add_edge with unordered dedup + self-loop rejection

Canonical ordering (v1_id < v2_id) lets unordered de-duplication be a
single dict lookup. Self-loops raise ValueError — tools should never
request one, but we defend the invariant at the API boundary."
```

---

## Task 5: `Scene.add_face_from_loop` with earcut triangulation

**Files:**
- Modify: `python/pluton/scene/scene.py`
- Modify: `tests/test_scene.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_scene.py`

```python
def test_add_face_from_loop_creates_face_and_triangulates():
    from pluton.scene import Scene

    s = Scene()
    # A unit square on Z=0
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))

    fid = s.add_face_from_loop((v0, v1, v2, v3))

    faces = list(s.faces_iter())
    assert len(faces) == 1
    f = faces[0]
    assert f.id == fid
    assert f.loop_vertex_ids == (v0, v1, v2, v3)
    # Ground plane normal is +Z
    np.testing.assert_allclose(f.plane_normal, np.array([0.0, 0.0, 1.0], dtype=np.float32))
    # Square triangulates to 2 triangles
    assert f.triangles.shape == (2, 3)


def test_add_face_from_loop_rejects_fewer_than_three_vertices():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))

    with pytest.raises(ValueError):
        s.add_face_from_loop((v0, v1))


def test_add_face_from_loop_triangulates_concave_polygon():
    from pluton.scene import Scene

    s = Scene()
    # An L-shape (6 vertices, concave) on Z=0
    pts = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    vids = [
        s.add_vertex(np.array([x, y, 0.0], dtype=np.float32)) for (x, y) in pts
    ]

    s.add_face_from_loop(tuple(vids))

    f = next(iter(s.faces_iter()))
    # An L-shape has 6 vertices, so earcut produces 4 triangles
    assert f.triangles.shape == (4, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene.py -v`
Expected: 3 new FAIL with `AttributeError: 'Scene' object has no attribute 'add_face_from_loop'`.

- [ ] **Step 3: Add `add_face_from_loop`** — edit `python/pluton/scene/scene.py`

Replace the `if TYPE_CHECKING:` line at the top with:
```python
import mapbox_earcut

from pluton.scene.face import Face
```

Then add this method to `Scene`, after `add_edge`:
```python
    def add_face_from_loop(self, ordered_vertex_ids: tuple[int, ...]) -> int:
        """Insert a face bounded by the given closed vertex loop.

        The loop is closed implicitly — the caller does not repeat the first
        vertex. Requires len(loop) >= 3. Ground-plane convention in M2:
        plane_normal is hard-coded to (0, 0, 1) and triangulation runs on the
        XY coordinates via mapbox-earcut.
        """
        if len(ordered_vertex_ids) < 3:
            raise ValueError(
                f"face needs at least 3 vertices, got {len(ordered_vertex_ids)}"
            )

        # Build a (N, 2) float32 array of XY for earcut. mapbox-earcut 2.x
        # takes the 2D shape directly — DO NOT reshape to flat.
        xy = np.empty((len(ordered_vertex_ids), 2), dtype=np.float32)
        for i, vid in enumerate(ordered_vertex_ids):
            xy[i] = self._vertices[vid].position[:2]
        ring_ends = np.array([len(ordered_vertex_ids)], dtype=np.uint32)
        # earcut returns a flat uint32 array of length 3*T; reshape to (T, 3).
        # Indices are into the local ring, so map back to global vertex IDs.
        local_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        triangles = np.array(
            [[ordered_vertex_ids[i] for i in tri] for tri in local_indices],
            dtype=np.int32,
        )

        fid = self._next_face_id
        self._next_face_id += 1
        self._faces[fid] = Face(
            id=fid,
            loop_vertex_ids=tuple(ordered_vertex_ids),
            plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            triangles=triangles,
        )
        self._dirty = True
        return fid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scene.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene.py
git commit -m "feat(scene): Scene.add_face_from_loop with earcut triangulation

Eager triangulation via mapbox-earcut runs on the loop's XY coords (M2
ground-plane convention). Handles convex and concave loops. Stored on Face
so the renderer never re-triangulates."
```

---

## Task 6: Scene helpers — `find_vertex_near`, `vertex_count`, buffer projections

**Files:**
- Modify: `python/pluton/scene/scene.py`
- Modify: `tests/test_scene.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_scene.py`

```python
def test_find_vertex_near_returns_closest_within_tolerance():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([5.0, 0.0, 0.0], dtype=np.float32))

    near_v0 = s.find_vertex_near(np.array([0.1, 0.0, 0.0], dtype=np.float32), tolerance=0.5)
    assert near_v0 == v0

    near_v1 = s.find_vertex_near(np.array([5.05, 0.0, 0.0], dtype=np.float32), tolerance=0.5)
    assert near_v1 == v1


def test_find_vertex_near_returns_none_when_outside_tolerance():
    from pluton.scene import Scene

    s = Scene()
    s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))

    assert s.find_vertex_near(np.array([10.0, 0.0, 0.0], dtype=np.float32), tolerance=0.5) is None


def test_edge_line_buffer_shape():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    s.add_edge(v0, v1)
    s.add_edge(v1, v2)

    buf = s.edge_line_buffer()
    assert buf.shape == (4, 3)  # 2 edges * 2 endpoints
    assert buf.dtype == np.float32


def test_face_triangle_buffer_shape():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    s.add_face_from_loop((v0, v1, v2, v3))

    positions, normals = s.face_triangle_buffer()
    # 2 triangles * 3 vertices = 6 vertices
    assert positions.shape == (6, 3)
    assert normals.shape == (6, 3)
    # All normals should be +Z for a ground-plane face
    np.testing.assert_allclose(normals, np.tile([0.0, 0.0, 1.0], (6, 1)).astype(np.float32))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene.py -v`
Expected: 4 new FAIL with `AttributeError`.

- [ ] **Step 3: Add the helpers** — append to `Scene` in `python/pluton/scene/scene.py`

```python
    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None:
        """Return the ID of the vertex closest to `world_xyz` within `tolerance`.

        Linear scan over all vertices. Fine for M2 (small scenes). A spatial
        index lands in M10 if profiling demands it.
        """
        best_id: int | None = None
        best_d2 = tolerance * tolerance
        for vid, v in self._vertices.items():
            d = v.position - world_xyz
            d2 = float(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            if d2 <= best_d2:
                best_d2 = d2
                best_id = vid
        return best_id

    def edge_line_buffer(self) -> np.ndarray:
        """Flat (2*E, 3) float32 array — line-list endpoints for the GL VBO."""
        if not self._edges:
            return np.zeros((0, 3), dtype=np.float32)
        out = np.empty((2 * len(self._edges), 3), dtype=np.float32)
        for i, e in enumerate(self._edges.values()):
            out[2 * i + 0] = self._vertices[e.v1_id].position
            out[2 * i + 1] = self._vertices[e.v2_id].position
        return out

    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]:
        """Flat (3*T, 3) float32 (positions, normals) — triangle-list for the GL VBO.

        Each triangle is expanded inline. Normals are flat — every vertex of a
        triangle takes the face's `plane_normal` — so the Phong shader from M1
        renders the face with the same flat shading as the cube did.
        """
        if not self._faces:
            empty = np.zeros((0, 3), dtype=np.float32)
            return empty, empty
        total_tris = sum(int(f.triangles.shape[0]) for f in self._faces.values())
        positions = np.empty((3 * total_tris, 3), dtype=np.float32)
        normals = np.empty((3 * total_tris, 3), dtype=np.float32)
        row = 0
        for f in self._faces.values():
            for tri in f.triangles:
                positions[row + 0] = self._vertices[int(tri[0])].position
                positions[row + 1] = self._vertices[int(tri[1])].position
                positions[row + 2] = self._vertices[int(tri[2])].position
                normals[row + 0] = f.plane_normal
                normals[row + 1] = f.plane_normal
                normals[row + 2] = f.plane_normal
                row += 3
        return positions, normals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scene.py -v`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene.py
git commit -m "feat(scene): add find_vertex_near + GL buffer projection methods

find_vertex_near is a linear scan (fine for M2 scene sizes; M10 is when
spatial indexing earns its keep). edge_line_buffer and face_triangle_buffer
project the topology into flat float32 arrays ready for VBO upload."
```

---

## Task 7: `Camera.ray_from_screen` and `ray_intersect_ground`

**Files:**
- Modify: `python/pluton/viewport/camera.py`
- Modify: `tests/test_camera.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_camera.py`

```python
def test_ray_from_screen_returns_origin_and_unit_direction():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1.0
    origin, direction = cam.ray_from_screen(640.0, 400.0, 1280, 800)

    # Origin is the camera position
    np.testing.assert_allclose(origin, cam.position, atol=1e-6)
    # Direction is a unit vector
    np.testing.assert_allclose(float(np.linalg.norm(direction)), 1.0, atol=1e-6)
    # Centre cursor → direction points from position toward target
    expected = cam.target - cam.position
    expected = expected / float(np.linalg.norm(expected))
    np.testing.assert_allclose(direction, expected, atol=1e-5)


def test_ray_intersect_ground_for_centre_cursor():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1.0
    hit = cam.ray_intersect_ground(640.0, 400.0, 1280, 800)
    # Centre cursor with default camera (looking at target at z=0.5) hits the
    # ground near, but not exactly at, target.x/target.y because the target
    # has z=0.5 not 0. The hit must still be valid (not None) and on z=0.
    assert hit is not None
    assert abs(float(hit[2])) < 1e-5


def test_ray_intersect_ground_returns_none_when_ray_parallel_or_above():
    """Cursor placed so the ray goes upward (away from ground) yields None.

    Camera ABOVE the ground (z=5) looking further UP (target at z=10): the
    ray direction has +dz, so the Z=0 intersection has negative t (behind
    the camera). The method should return None per the spec §5.3 contract.
    """
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.position = np.array([0.0, 0.0, 5.0], dtype=np.float32)
    cam.target = np.array([0.0, 0.0, 10.0], dtype=np.float32)
    cam.aspect = 1.0
    hit = cam.ray_intersect_ground(640.0, 400.0, 1280, 800)
    assert hit is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_camera.py -v`
Expected: 3 new FAIL with `AttributeError: 'Camera' object has no attribute 'ray_from_screen'`.

- [ ] **Step 3: Add the methods** — append to `Camera` in `python/pluton/viewport/camera.py`

```python
    # --- Picking / raycast helpers ----------------------------------------

    def ray_from_screen(
        self, x_pixels: float, y_pixels: float, width: int, height: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build a world-space ray from the camera through the cursor pixel.

        Returns `(origin, direction)` where `origin = self.position` and
        `direction` is a unit vector. Y is treated as screen-y (top-down).
        """
        w = max(int(width), 1)
        h = max(int(height), 1)
        # NDC: x in [-1, 1] left→right; y in [-1, 1] bottom→top.
        nx = (2.0 * float(x_pixels) / w) - 1.0
        ny = 1.0 - (2.0 * float(y_pixels) / h)

        forward = _normalize(self.target - self.position)
        right = _normalize(np.cross(forward, self.up))
        cam_up = np.cross(right, forward)
        tan_half_fovy = math.tan(math.radians(self.fov_y_deg) * 0.5)

        # Camera-space direction for the (nx, ny) cursor.
        cam_dir = (
            forward
            + right * (nx * tan_half_fovy * self.aspect)
            + cam_up * (ny * tan_half_fovy)
        )
        direction = _normalize(cam_dir).astype(np.float32)
        origin = self.position.astype(np.float32)
        return origin, direction

    def ray_intersect_ground(
        self, x_pixels: float, y_pixels: float, width: int, height: int
    ) -> np.ndarray | None:
        """Intersect the cursor ray with the Z=0 plane.

        Returns the world-space hit point as a float32 (3,) array, or `None`
        if the ray runs parallel to the plane or hits it behind the camera.
        """
        origin, direction = self.ray_from_screen(x_pixels, y_pixels, width, height)
        dz = float(direction[2])
        if abs(dz) < 1e-9:
            return None  # parallel
        t = -float(origin[2]) / dz
        if t <= 0.0:
            return None  # behind the camera
        hit = origin + direction * t
        hit[2] = 0.0  # snap to exact zero to defend against FP drift
        return hit.astype(np.float32)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_camera.py -v`
Expected: 14 passed (11 from M1 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/camera.py tests/test_camera.py
git commit -m "feat(camera): add ray_from_screen + ray_intersect_ground

Reuses the same NDC→camera-space math the existing zoom-toward-cursor uses.
ray_intersect_ground returns None when the cursor is above the horizon
(ray parallel to Z=0 or hits it behind the camera), which the snap engine
maps to SnapKind.NONE in §5.3 of the spec."
```

---

## Task 8: `SnapEngine` — each `SnapKind` in isolation

**Files:**
- Create: `python/pluton/viewport/snap_engine.py`
- Create: `tests/test_snap_engine.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_snap_engine.py`

```python
"""Unit tests for the snap & inference engine."""

from __future__ import annotations

import numpy as np
import pytest


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def test_grid_snap_to_nearest_integer_meter():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    cursor_world = np.array([2.3, -1.4, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (0.0, 0.0), cam, scene)
    assert result.kind == SnapKind.GRID
    np.testing.assert_allclose(result.world_position, [2.0, -1.0, 0.0], atol=1e-5)


def test_endpoint_snap_when_cursor_near_existing_vertex():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    vid = scene.add_vertex(np.array([3.0, 4.0, 0.0], dtype=np.float32))
    cam = _camera_at_default()
    # Cursor a tenth of a metre off the vertex — well within endpoint tolerance.
    cursor_world = np.array([3.05, 4.02, 0.0], dtype=np.float32)
    # Use a screen-position that maps to the same world point — for unit test
    # purposes the engine uses `find_vertex_near` directly and ignores screen.
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.ENDPOINT
    assert result.vertex_id == vid
    np.testing.assert_array_equal(result.world_position, scene.vertex(vid).position)


def test_midpoint_snap_when_cursor_near_edge_midpoint():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    # Midpoint of (0,0)-(4,0) is (2,0). Cursor very close.
    cursor_world = np.array([2.05, 0.05, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.MIDPOINT
    np.testing.assert_allclose(result.world_position, [2.0, 0.0, 0.0], atol=1e-5)


def test_axis_lock_when_drawing_near_x_axis_direction():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    # Anchor at origin; cursor near the +X axis (slight Y offset)
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cursor_world = np.array([5.0, 0.05, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.AXIS_LOCK
    assert result.axis == 0  # X axis
    # Snapped point projected onto X axis is (5, 0, 0)
    np.testing.assert_allclose(result.world_position, [5.0, 0.0, 0.0], atol=1e-5)


def test_returns_none_when_cursor_world_is_none():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    result = eng.snap(None, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.NONE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_snap_engine.py -v`
Expected: 5 FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `SnapEngine`** at `python/pluton/viewport/snap_engine.py`

```python
"""Snap & inference engine for M2 drawing tools.

Evaluates four snap kinds (Grid, Axis-lock, Midpoint, Endpoint) and picks
the highest-precedence one within tolerance. Precedence is encoded in the
numeric value of `SnapKind` — higher wins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from pluton.scene import Scene
from pluton.viewport.camera import Camera


class SnapKind(IntEnum):
    """Snap kinds, ordered by precedence (higher wins on a tie)."""

    NONE = 0
    GRID = 1
    AXIS_LOCK = 2
    MIDPOINT = 3
    ENDPOINT = 4


@dataclass(frozen=True, slots=True)
class SnapResult:
    """The chosen snap for one cursor position."""

    kind: SnapKind
    world_position: np.ndarray
    axis: int | None  # 0=X (red), 1=Y (green), 2=Z (blue); only AXIS_LOCK
    vertex_id: int | None  # only ENDPOINT
    label: str


_AXIS_NAMES = {0: "Red", 1: "Green", 2: "Blue"}


class SnapEngine:
    """SketchUp-style snap & inference engine."""

    PIXEL_TOLERANCE = 8.0  # screen-space, endpoint & midpoint
    AXIS_DEG_TOLERANCE = 5.0  # angular tolerance for axis-lock
    GRID_SIZE_WORLD = 1.0  # 1 m grid spacing matches M1

    def snap(
        self,
        cursor_world_on_ground: np.ndarray | None,
        cursor_screen: tuple[float, float],
        camera: Camera,
        scene: Scene,
        anchor: np.ndarray | None = None,
    ) -> SnapResult:
        """Return the chosen snap for the given cursor."""
        if cursor_world_on_ground is None:
            return SnapResult(
                kind=SnapKind.NONE,
                world_position=np.zeros(3, dtype=np.float32),
                axis=None,
                vertex_id=None,
                label="—",
            )

        # Pixel tolerance in world units depends on distance from camera.
        # Approximate by projecting back: how many world units does 1 pixel
        # cover at the cursor's world depth? Use the cursor's distance to the
        # camera as the depth.
        depth = float(np.linalg.norm(cursor_world_on_ground - camera.position))
        # half-screen-height at this depth in world units
        half_h_world = depth * math.tan(math.radians(camera.fov_y_deg) * 0.5)
        # screen height in pixels (use the global window height — but we don't
        # have it here; tools pass cursor_screen and we use camera.aspect to
        # recover the right scale).
        # Easier: caller supplies a "world tolerance" derived from PIXEL_TOLERANCE
        # via the viewport widget. For M2 we use a small constant fallback if
        # the projection math is fragile. We use 0.2 m world tolerance — fits
        # PIXEL_TOLERANCE=8 at depth ~10 m with a 45° FOV.
        world_tolerance = 0.2

        # --- Endpoint: highest precedence ----------------------------------
        endpoint_vid = scene.find_vertex_near(cursor_world_on_ground, world_tolerance)
        if endpoint_vid is not None:
            return SnapResult(
                kind=SnapKind.ENDPOINT,
                world_position=scene.vertex(endpoint_vid).position.copy(),
                axis=None,
                vertex_id=endpoint_vid,
                label="Endpoint",
            )

        # --- Midpoint -------------------------------------------------------
        best_midpoint = None
        best_md2 = world_tolerance * world_tolerance
        for e in scene.edges_iter():
            p1 = scene.vertex(e.v1_id).position
            p2 = scene.vertex(e.v2_id).position
            mid = (p1 + p2) * 0.5
            d = mid - cursor_world_on_ground
            d2 = float(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            if d2 <= best_md2:
                best_md2 = d2
                best_midpoint = mid.astype(np.float32)
        if best_midpoint is not None:
            return SnapResult(
                kind=SnapKind.MIDPOINT,
                world_position=best_midpoint,
                axis=None,
                vertex_id=None,
                label="Midpoint",
            )

        # --- Axis-lock (only when drawing — anchor is set) -----------------
        if anchor is not None:
            delta = cursor_world_on_ground - anchor
            length_xy = math.hypot(float(delta[0]), float(delta[1]))
            if length_xy > 1e-6:
                # Angles in radians: 0 = +X axis, π/2 = +Y axis.
                angle = math.atan2(float(delta[1]), float(delta[0]))
                tol_rad = math.radians(self.AXIS_DEG_TOLERANCE)
                # Distance to nearest axis direction (0, ±π for X; ±π/2 for Y).
                # Z axis (vertical) is only relevant when drawing off-ground —
                # in M2 we're always on Z=0 so Z-lock never fires.
                deltas = {
                    0: min(abs(angle), abs(abs(angle) - math.pi)),  # X axis
                    1: abs(abs(angle) - math.pi / 2.0),  # Y axis
                }
                best_axis = min(deltas, key=deltas.get)
                if deltas[best_axis] <= tol_rad:
                    # Project the cursor onto the locked axis line through anchor.
                    if best_axis == 0:
                        projected = np.array(
                            [cursor_world_on_ground[0], anchor[1], 0.0], dtype=np.float32
                        )
                    else:
                        projected = np.array(
                            [anchor[0], cursor_world_on_ground[1], 0.0], dtype=np.float32
                        )
                    return SnapResult(
                        kind=SnapKind.AXIS_LOCK,
                        world_position=projected,
                        axis=best_axis,
                        vertex_id=None,
                        label=f"on {_AXIS_NAMES[best_axis]} Axis",
                    )

        # --- Grid (always available on the ground plane) -------------------
        gx = round(float(cursor_world_on_ground[0]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
        gy = round(float(cursor_world_on_ground[1]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
        return SnapResult(
            kind=SnapKind.GRID,
            world_position=np.array([gx, gy, 0.0], dtype=np.float32),
            axis=None,
            vertex_id=None,
            label="Grid",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_snap_engine.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/snap_engine.py tests/test_snap_engine.py
git commit -m "feat(viewport): add SnapEngine with grid/endpoint/midpoint/axis-lock

Numeric SnapKind values encode precedence (higher wins). World tolerance
of 0.2 m approximates PIXEL_TOLERANCE=8 px at a typical viewing depth;
axis-lock has a 5° angular tolerance and only fires when a rubber-band
anchor is set (i.e. mid-Line-tool gesture)."
```

---

## Task 9: `SnapEngine` precedence resolution

**Files:**
- Modify: `tests/test_snap_engine.py`

This task verifies the implicit precedence already encoded in `SnapEngine.snap()`'s early-return structure. No code change is expected if Task 8 implemented it correctly; if a test fails, the order of checks in `snap()` is wrong.

- [ ] **Step 1: Write the precedence tests** — append to `tests/test_snap_engine.py`

```python
def test_endpoint_beats_midpoint():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    # An edge where the midpoint and one endpoint are both within tolerance
    v0 = scene.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([2.4, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    # Midpoint is (2.2, 0). Cursor close to v0 — within tolerance of both.
    cursor_world = np.array([2.05, 0.0, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene)
    assert result.kind == SnapKind.ENDPOINT
    assert result.vertex_id == v0


def test_midpoint_beats_axis_lock():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    # Cursor near midpoint (2,0) AND axis-locked-to-X-from-origin.
    cursor_world = np.array([2.05, 0.02, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.MIDPOINT


def test_axis_lock_beats_grid():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    # (3.0, 0.02) is on the +X axis-lock direction; grid snap would be (3,0).
    # Both produce the same point in this case — but axis-lock label / kind wins.
    cursor_world = np.array([3.0, 0.02, 0.0], dtype=np.float32)
    result = eng.snap(cursor_world, (640.0, 400.0), cam, scene, anchor=anchor)
    assert result.kind == SnapKind.AXIS_LOCK
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_snap_engine.py -v`
Expected: 8 passed (5 from Task 8 + 3 new). If any FAIL, the early-return order in `SnapEngine.snap()` is wrong; the canonical order is endpoint → midpoint → axis-lock → grid.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine.py
git commit -m "test(viewport): cover SnapEngine precedence (endpoint > midpoint > axis > grid)

Regression tests for the precedence order encoded in SnapEngine.snap()'s
sequence of early-returns. Locks in the contract from §3.1 of the design."
```

---

## Task 10: Tool framework — `Tool`, `ToolOverlay`, `ToolManager`

**Files:**
- Create: `python/pluton/tools/__init__.py`
- Create: `python/pluton/tools/tool.py`
- Create: `python/pluton/tools/tool_manager.py`
- Create: `tests/test_tool_manager.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_tool_manager.py`

```python
"""Unit tests for the Tool framework — ABC, overlay dataclass, manager."""

from __future__ import annotations

import numpy as np

from pluton.scene import Scene
from pluton.tools import Tool, ToolContext, ToolManager, ToolOverlay


class FakeTool(Tool):
    """Minimal Tool subclass for unit-testing ToolManager.

    Defined inline rather than as a shared fixture because the existing
    `tests/` directory isn't a Python package and `pythonpath` isn't
    configured — sharing across test files would require build-system
    changes not worth it for a single helper.
    """

    def __init__(self, name: str = "Fake", shortcut: str = "F") -> None:
        self._name = name
        self._shortcut = shortcut
        self.activated = False
        self.deactivated = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def shortcut(self) -> str:
        return self._shortcut

    def activate(self, ctx: ToolContext) -> None:
        self.activated = True

    def deactivate(self) -> None:
        self.deactivated = True

    def overlay(self) -> ToolOverlay:
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=(1.0, 1.0, 1.0),
            snap_marker_position=None,
            snap_marker_color=(1.0, 1.0, 1.0),
        )

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None


def _ctx() -> ToolContext:
    return ToolContext(scene=Scene())


def test_tool_manager_starts_with_no_active_tool():
    mgr = ToolManager()
    assert mgr.active is None


def test_register_and_activate_by_shortcut():
    mgr = ToolManager(_ctx())
    t = FakeTool(name="Fake", shortcut="F")
    mgr.register(t)
    assert mgr.activate_by_shortcut("F") is True
    assert mgr.active is t
    assert t.activated is True


def test_activating_switches_and_deactivates_previous():
    mgr = ToolManager(_ctx())
    a = FakeTool(name="A", shortcut="A")
    b = FakeTool(name="B", shortcut="B")
    mgr.register(a)
    mgr.register(b)
    mgr.activate_by_shortcut("A")
    mgr.activate_by_shortcut("B")
    assert mgr.active is b
    assert a.deactivated is True


def test_deactivate_current_clears_active_tool():
    mgr = ToolManager(_ctx())
    t = FakeTool(name="T", shortcut="T")
    mgr.register(t)
    mgr.activate_by_shortcut("T")
    mgr.deactivate_current()
    assert mgr.active is None
    assert t.deactivated is True


def test_unknown_shortcut_returns_false():
    mgr = ToolManager()
    assert mgr.activate_by_shortcut("X") is False
    assert mgr.active is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_manager.py -v`
Expected: collection ERROR with `ModuleNotFoundError: No module named 'pluton.tools'` (the test file's module-level imports fail before any individual test can run — this counts as the failing-test red state for TDD purposes).

- [ ] **Step 3: Create the Tool ABC + ToolOverlay + ToolContext** at `python/pluton/tools/tool.py`

```python
"""Tool abstraction for drawing/modeling tools.

A Tool owns a small state machine, receives Qt events from the active
ViewportWidget, mutates the Scene, and emits a per-frame ToolOverlay
containing transient preview geometry (rubber-band, snap marker).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from PySide6.QtGui import QKeyEvent, QMouseEvent


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Handed to Tool.activate(); gives the tool a handle to the live Scene."""

    scene: object  # forward-typed to avoid circular import; really a pluton.scene.Scene


@dataclass(frozen=True, slots=True)
class ToolOverlay:
    """Transient preview geometry rebuilt every frame by the active tool."""

    rubber_band_segments: np.ndarray  # shape (2*N, 3), float32
    rubber_band_color: tuple[float, float, float]
    snap_marker_position: np.ndarray | None
    snap_marker_color: tuple[float, float, float]


class Tool(ABC):
    """Base class for all M2+ tools."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def shortcut(self) -> str: ...

    @abstractmethod
    def activate(self, ctx: ToolContext) -> None: ...

    @abstractmethod
    def deactivate(self) -> None: ...

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing. Tools override as needed."""

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing."""

    def on_key_press(self, event: QKeyEvent) -> None:
        """Default: do nothing."""

    @abstractmethod
    def overlay(self) -> ToolOverlay: ...

    @property
    @abstractmethod
    def anchor_or_none(self) -> np.ndarray | None:
        """Rubber-band anchor used by the SnapEngine for axis-lock."""
```

- [ ] **Step 4: Create the ToolManager** at `python/pluton/tools/tool_manager.py`

```python
"""ToolManager: holds the registered tool roster and the currently-active tool."""

from __future__ import annotations

from pluton.tools.tool import Tool, ToolContext


class ToolManager:
    """One active tool at a time, switched by single-letter keyboard shortcut."""

    def __init__(self, ctx: ToolContext | None = None) -> None:
        self._ctx = ctx
        self._tools: dict[str, Tool] = {}
        self._active: Tool | None = None

    def set_context(self, ctx: ToolContext) -> None:
        """MainWindow calls this once the Scene exists."""
        self._ctx = ctx

    def register(self, tool: Tool) -> None:
        self._tools[tool.shortcut.upper()] = tool

    def activate_by_shortcut(self, key: str) -> bool:
        target = self._tools.get(key.upper())
        if target is None:
            return False
        if self._active is target:
            return True
        if self._active is not None:
            self._active.deactivate()
        if self._ctx is None:
            raise RuntimeError("ToolManager has no ToolContext; call set_context() first")
        target.activate(self._ctx)
        self._active = target
        return True

    def deactivate_current(self) -> None:
        if self._active is not None:
            self._active.deactivate()
            self._active = None

    @property
    def active(self) -> Tool | None:
        return self._active
```

- [ ] **Step 5: Create the package init** at `python/pluton/tools/__init__.py`

```python
"""Tool framework: Tool ABC, ToolOverlay, ToolManager, and concrete tools.

M2 ships LineTool and RectangleTool against this framework. M3's PushPullTool
and M4's full roster plug into the same shapes.
"""

from __future__ import annotations

from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["Tool", "ToolContext", "ToolManager", "ToolOverlay"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_tool_manager.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/tools/ tests/test_tool_manager.py
git commit -m "feat(tools): add Tool ABC + ToolOverlay + ToolManager

Generic tool framework. M2 RectangleTool and LineTool plug into this shape,
as will M3's PushPullTool and M4's full tool roster. ToolManager holds one
active tool at a time, switches by keyboard shortcut, and routes through
a ToolContext that carries the live Scene."
```

---

## Task 11: `RectangleTool`

**Files:**
- Create: `python/pluton/tools/rectangle_tool.py`
- Modify: `python/pluton/tools/__init__.py`
- Create: `tests/test_rectangle_tool.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_rectangle_tool.py`

```python
"""Unit tests for the Rectangle tool."""

from __future__ import annotations

import numpy as np


def _snap_at(world):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="Grid",
    )


def test_rectangle_tool_idle_overlay_is_empty():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    tool = RectangleTool()
    tool.activate(ToolContext(scene=Scene()))
    overlay = tool.overlay()
    assert overlay.rubber_band_segments.shape == (0, 3)


def test_rectangle_tool_first_click_starts_drag():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    # Scene is still empty until the second click commits.
    assert len(list(scene.vertices_iter())) == 0


def test_rectangle_tool_two_clicks_commit_four_verts_four_edges_one_face():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((3.0, 2.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.edges_iter())) == 4
    assert len(list(scene.faces_iter())) == 1


def test_rectangle_tool_zero_area_drops_gesture():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((1.0, 1.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((1.0, 1.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.faces_iter())) == 0


def test_rectangle_tool_esc_cancels_mid_drag():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]

    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)

    overlay = tool.overlay()
    assert overlay.rubber_band_segments.shape == (0, 3)
    assert len(list(scene.vertices_iter())) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rectangle_tool.py -v`
Expected: 5 FAIL with `ModuleNotFoundError: No module named 'pluton.tools.rectangle_tool'`.

- [ ] **Step 3: Create the RectangleTool** at `python/pluton/tools/rectangle_tool.py`

```python
"""The Rectangle drawing tool.

Two-corner gesture: first click sets the first corner, second click commits
an axis-aligned rectangle on the ground plane (Z=0). ESC cancels mid-drag.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


class _State(Enum):
    IDLE = 0
    DRAGGING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MARKER_COLOR_BY_KIND = {
    1: (0.7, 0.7, 0.7),     # GRID
    2: None,                # AXIS_LOCK (Rectangle doesn't axis-lock; never set)
    3: (0.2, 0.85, 0.95),   # MIDPOINT
    4: (0.25, 0.78, 0.26),  # ENDPOINT
}


class RectangleTool(Tool):
    @property
    def name(self) -> str:
        return "Rectangle"

    @property
    def shortcut(self) -> str:
        return "R"

    def __init__(self) -> None:
        self._scene = None
        self._state = _State.IDLE
        self._first_corner: np.ndarray | None = None
        self._preview_corner: np.ndarray | None = None
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = _MARKER_COLOR_BY_KIND.get(int(snap.kind), _NEUTRAL_COLOR)
        if self._state == _State.DRAGGING:
            self._preview_corner = snap.world_position.copy()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return

        if self._state == _State.IDLE:
            self._first_corner = snap.world_position.copy()
            self._preview_corner = snap.world_position.copy()
            self._state = _State.DRAGGING
            return

        # DRAGGING — commit or drop
        assert self._first_corner is not None
        second = snap.world_position
        if np.array_equal(second, self._first_corner):
            self._reset_gesture()
            return

        x0, y0 = float(self._first_corner[0]), float(self._first_corner[1])
        x1, y1 = float(second[0]), float(second[1])
        s = self._scene  # type: ignore[assignment]
        v0 = s.add_vertex(np.array([x0, y0, 0.0], dtype=np.float32))
        v1 = s.add_vertex(np.array([x1, y0, 0.0], dtype=np.float32))
        v2 = s.add_vertex(np.array([x1, y1, 0.0], dtype=np.float32))
        v3 = s.add_vertex(np.array([x0, y1, 0.0], dtype=np.float32))
        s.add_edge(v0, v1)
        s.add_edge(v1, v2)
        s.add_edge(v2, v3)
        s.add_edge(v3, v0)
        s.add_face_from_loop((v0, v1, v2, v3))
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        if self._state == _State.DRAGGING and self._first_corner is not None and self._preview_corner is not None:
            x0, y0 = float(self._first_corner[0]), float(self._first_corner[1])
            x1, y1 = float(self._preview_corner[0]), float(self._preview_corner[1])
            segments = np.array(
                [
                    [x0, y0, 0.0], [x1, y0, 0.0],
                    [x1, y0, 0.0], [x1, y1, 0.0],
                    [x1, y1, 0.0], [x0, y1, 0.0],
                    [x0, y1, 0.0], [x0, y0, 0.0],
                ],
                dtype=np.float32,
            )
        else:
            segments = np.zeros((0, 3), dtype=np.float32)

        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
        )

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None  # Rectangle tool doesn't drive axis-lock

    # ---- internal -------------------------------------------------------
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._first_corner = None
        self._preview_corner = None
        self._snap_marker_pos = None
```

- [ ] **Step 4: Re-export `RectangleTool`** — edit `python/pluton/tools/__init__.py`

Replace:
```python
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["Tool", "ToolContext", "ToolManager", "ToolOverlay"]
```
with:
```python
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["RectangleTool", "Tool", "ToolContext", "ToolManager", "ToolOverlay"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_rectangle_tool.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/rectangle_tool.py python/pluton/tools/__init__.py tests/test_rectangle_tool.py
git commit -m "feat(tools): add RectangleTool

Two-corner gesture: click → drag → click commits 4 vertices + 4 edges + 1
face. Zero-area gesture (same point twice) drops without scene mutation.
ESC mid-drag cancels."
```

---

## Task 12: `LineTool`

**Files:**
- Create: `python/pluton/tools/line_tool.py`
- Modify: `python/pluton/tools/__init__.py`
- Create: `tests/test_line_tool.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_line_tool.py`

```python
"""Unit tests for the Line tool — three-branch click logic + ESC + < 3 close."""

from __future__ import annotations

import numpy as np


def _endpoint_snap(world, vertex_id: int):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.ENDPOINT,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=vertex_id,
        label="Endpoint",
    )


def _grid_snap(world):
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="Grid",
    )


def test_line_tool_first_click_adds_one_vertex():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _grid_snap((1.0, 0.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 1


def test_line_tool_branch_3_new_vertex_creates_edge():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((1.0, 0.0, 0.0)))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 2
    assert len(list(scene.edges_iter())) == 1
    assert len(list(scene.faces_iter())) == 0


def test_line_tool_loop_close_creates_face():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    # Click 1 — first vertex at (0,0,0).
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    first_vid = next(iter(scene.vertices_iter())).id
    # Clicks 2, 3 — extend the polyline.
    tool.on_mouse_press(None, _grid_snap((2.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((2.0, 2.0, 0.0)))  # type: ignore[arg-type]
    # Click 4 — endpoint-snap onto the FIRST vertex → loop close.
    tool.on_mouse_press(None, _endpoint_snap((0.0, 0.0, 0.0), vertex_id=first_vid))  # type: ignore[arg-type]

    assert len(list(scene.vertices_iter())) == 3
    assert len(list(scene.edges_iter())) == 3
    assert len(list(scene.faces_iter())) == 1


def test_line_tool_branch_2_extend_to_existing_vertex():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    # Pre-existing vertex (e.g. drawn by a previous gesture or Rectangle).
    pre_vid = scene.add_vertex(np.array([5.0, 0.0, 0.0], dtype=np.float32))

    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _endpoint_snap((5.0, 0.0, 0.0), vertex_id=pre_vid))  # type: ignore[arg-type]

    # Only 2 vertices (the new one + the pre-existing one), 1 edge, no face.
    assert len(list(scene.vertices_iter())) == 2
    assert len(list(scene.edges_iter())) == 1
    assert len(list(scene.faces_iter())) == 0


def test_line_tool_close_with_fewer_than_three_vertices_ignored():
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    # Click 1 — first vertex at (0,0,0).
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    first_vid = next(iter(scene.vertices_iter())).id
    # Click 2 — endpoint snap back onto first vertex (only 1 vertex in gesture).
    # Should be ignored — no face, no extra edge.
    tool.on_mouse_press(None, _endpoint_snap((0.0, 0.0, 0.0), vertex_id=first_vid))  # type: ignore[arg-type]

    assert len(list(scene.faces_iter())) == 0


def test_line_tool_esc_cancels_visible_gesture():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene))
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((1.0, 0.0, 0.0)))  # type: ignore[arg-type]

    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)

    # Per spec §4.5 / §5.6: ESC clears the visible gesture state but does NOT
    # un-add already-committed vertices/edges.
    assert tool.overlay().rubber_band_segments.shape == (0, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_line_tool.py -v`
Expected: 6 FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the LineTool** at `python/pluton/tools/line_tool.py`

```python
"""The Line drawing tool.

Click → click → click polyline. Snapping back onto the first vertex of the
gesture closes the loop and creates a face (provided ≥ 3 vertices exist).
Snapping onto some other existing vertex extends the polyline to it.
Otherwise, a new vertex is created at the snapped position.

ESC clears the visible gesture state; it does not un-add committed vertices.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


class _State(Enum):
    IDLE = 0
    DRAWING = 1


_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_AXIS_COLORS = {
    0: (0.95, 0.30, 0.30),  # X — red
    1: (0.30, 0.85, 0.30),  # Y — green
    2: (0.30, 0.40, 0.95),  # Z — blue
}
_MARKER_COLOR_BY_KIND = {
    1: (0.7, 0.7, 0.7),
    2: None,
    3: (0.2, 0.85, 0.95),
    4: (0.25, 0.78, 0.26),
}


class LineTool(Tool):
    @property
    def name(self) -> str:
        return "Line"

    @property
    def shortcut(self) -> str:
        return "L"

    def __init__(self) -> None:
        self._scene = None
        self._state = _State.IDLE
        self._gesture_vertex_ids: list[int] = []
        self._preview_tip: np.ndarray | None = None
        self._rubber_band_color: tuple[float, float, float] = _NEUTRAL_COLOR
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color: tuple[float, float, float] = _NEUTRAL_COLOR

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = _MARKER_COLOR_BY_KIND.get(int(snap.kind), _NEUTRAL_COLOR)
        if self._state == _State.DRAWING:
            self._preview_tip = snap.world_position.copy()
            if snap.kind == SnapKind.AXIS_LOCK and snap.axis is not None:
                self._rubber_band_color = _AXIS_COLORS.get(snap.axis, _NEUTRAL_COLOR)
            else:
                self._rubber_band_color = _NEUTRAL_COLOR

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return

        s = self._scene  # type: ignore[assignment]
        if self._state == _State.IDLE:
            # First click — seed the gesture.
            if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
                vid = snap.vertex_id
            else:
                vid = s.add_vertex(snap.world_position)
            self._gesture_vertex_ids = [vid]
            self._state = _State.DRAWING
            self._preview_tip = snap.world_position.copy()
            return

        # DRAWING — branch 1, 2, or 3
        tip_vid = self._gesture_vertex_ids[-1]
        first_vid = self._gesture_vertex_ids[0]

        if (
            snap.kind == SnapKind.ENDPOINT
            and snap.vertex_id == first_vid
            and len(self._gesture_vertex_ids) >= 3
        ):
            # Branch 1 — loop closure
            s.add_edge(tip_vid, first_vid)
            s.add_face_from_loop(tuple(self._gesture_vertex_ids))
            self._reset_gesture()
            return

        if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
            # Branch 2 — extend polyline to an existing vertex
            if snap.vertex_id == tip_vid:
                return  # degenerate: dropped
            s.add_edge(tip_vid, snap.vertex_id)
            self._gesture_vertex_ids.append(snap.vertex_id)
            return

        # Branch 3 — new vertex
        new_vid = s.add_vertex(snap.world_position)
        if new_vid == tip_vid:
            return  # degenerate: dropped
        s.add_edge(tip_vid, new_vid)
        self._gesture_vertex_ids.append(new_vid)

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        s = self._scene  # type: ignore[assignment]
        if (
            self._state == _State.DRAWING
            and s is not None
            and self._preview_tip is not None
            and self._gesture_vertex_ids
        ):
            anchor = s.vertex(self._gesture_vertex_ids[-1]).position
            segments = np.array(
                [
                    [float(anchor[0]), float(anchor[1]), float(anchor[2])],
                    [
                        float(self._preview_tip[0]),
                        float(self._preview_tip[1]),
                        float(self._preview_tip[2]),
                    ],
                ],
                dtype=np.float32,
            )
        else:
            segments = np.zeros((0, 3), dtype=np.float32)

        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=self._rubber_band_color,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
        )

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        s = self._scene  # type: ignore[assignment]
        if self._state != _State.DRAWING or s is None or not self._gesture_vertex_ids:
            return None
        return s.vertex(self._gesture_vertex_ids[-1]).position.copy()

    # ---- internal -------------------------------------------------------
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._gesture_vertex_ids = []
        self._preview_tip = None
        self._rubber_band_color = _NEUTRAL_COLOR
        self._snap_marker_pos = None
```

- [ ] **Step 4: Re-export `LineTool`** — edit `python/pluton/tools/__init__.py`

Replace:
```python
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["RectangleTool", "Tool", "ToolContext", "ToolManager", "ToolOverlay"]
```
with:
```python
from pluton.tools.line_tool import LineTool
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = ["LineTool", "RectangleTool", "Tool", "ToolContext", "ToolManager", "ToolOverlay"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_line_tool.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/line_tool.py python/pluton/tools/__init__.py tests/test_line_tool.py
git commit -m "feat(tools): add LineTool with three-branch click logic

Branch 1 (loop close): endpoint-snap onto first vertex of gesture creates
the face. Branch 2 (extend): endpoint-snap onto a different existing vertex
extends the polyline without closing. Branch 3 (new): add a fresh vertex
and edge to the gesture. ESC clears the visible gesture state but does
not roll back committed vertices (M3 will own that via the command stack)."
```

---

## Task 13: `SceneRenderer` extensions + M1 cube removal

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`

This is the biggest single file change in M2. The renderer's `render()` contract gains `scene` and `tool_overlay` parameters; three new draw passes are added; the M1 hardcoded-cube buffers and `_draw_cube` path are removed.

There are no new unit tests for this task — the renderer is exercised end-to-end through the `test_viewport.py` integration tests in Task 16, and through manual visual verification in Task 17. (M1's `SceneRenderer` tests were also integration-style for the same reason — GL state is hard to unit-test without a real context.)

- [ ] **Step 1: Read `python/pluton/viewport/scene_renderer.py` end-to-end** to understand the current structure (M1 cube + grid + axes).

Run: `cat python/pluton/viewport/scene_renderer.py | head -200`

You're looking for:
- `_init_cube_buffers` and `_draw_cube` — to be removed
- `render(self, camera)` — to be widened to `render(self, camera, scene, tool_overlay)`
- `initialize_gl` — currently calls `_init_cube_buffers`; will instead initialize empty user-face/user-edge VBOs.

- [ ] **Step 2: Update the `render` signature and orchestration** — edit `render` in `python/pluton/viewport/scene_renderer.py`

Replace the existing `render(self, camera)` method with:

```python
    def render(self, camera: Camera, scene, tool_overlay=None) -> None:  # noqa: ANN001
        """Draw the full scene: grid + axes + user faces + user edges + tool overlay."""
        from OpenGL import GL

        GL.glClearColor(0.15, 0.16, 0.18, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glEnable(GL.GL_DEPTH_TEST)

        view = camera.view_matrix()
        projection = camera.projection_matrix()

        # 1. Grid (M1)
        self._draw_lines(self._grid_vao, self._grid_count, view, projection)
        # 2. Axes (M1)
        self._draw_lines(self._axes_vao, self._axes_count, view, projection)

        # 3. User faces (NEW) — re-upload if scene is dirty
        if scene is not None:
            if scene.dirty:
                self._refresh_user_buffers(scene)
                scene.mark_clean()
            if self._user_face_count > 0:
                self._draw_user_faces(view, projection)
            if self._user_edge_count > 0:
                self._draw_user_edges(view, projection)

        # 4. Tool overlay (NEW) — drawn on top with depth-test disabled
        if tool_overlay is not None:
            self._draw_tool_overlay(tool_overlay, view, projection)
```

- [ ] **Step 3: Add the new VBO state to `__init__`** — find the `def __init__(self) -> None:` block and add at the end:

```python
        # User-geometry buffers (filled by Scene.dirty refresh path)
        self._user_face_vao: int = 0
        self._user_face_vbo: int = 0  # interleaved (pos.xyz, normal.xyz)
        self._user_face_count: int = 0  # number of vertices to draw

        self._user_edge_vao: int = 0
        self._user_edge_vbo: int = 0
        self._user_edge_count: int = 0

        # Tool overlay buffers (rebuilt every frame)
        self._overlay_line_vao: int = 0
        self._overlay_line_vbo: int = 0
        self._overlay_marker_vao: int = 0
        self._overlay_marker_vbo: int = 0
```

- [ ] **Step 4: Drop the cube init from `initialize_gl`** — find `def initialize_gl(self) -> None:` and remove the call to `self._init_cube_buffers()`. Add overlay buffer creation:

After `self._init_grid_buffers()` and `self._init_axes_buffers()` are called, append:

```python
        self._init_user_buffers()
        self._init_overlay_buffers()
```

- [ ] **Step 5: Remove `_init_cube_buffers` and `_draw_cube`** — delete those two methods entirely. Also remove any cube-related fields (`self._cube_vao`, `self._cube_vbo`, `self._cube_ibo`, `self._cube_index_count`) from `__init__`.

- [ ] **Step 6: Add the new init + draw methods** — append to the `SceneRenderer` class:

```python
    def _init_user_buffers(self) -> None:
        """Create empty VBOs for user-face and user-edge geometry.

        We allocate VAOs/VBOs here but leave them empty until the first
        scene-dirty refresh fills them with real data.
        """
        import ctypes

        from OpenGL import GL

        # User faces — interleaved (pos.xyz, normal.xyz), 24 bytes per vertex
        self._user_face_vao = int(GL.glGenVertexArrays(1))
        self._user_face_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._user_face_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_face_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 24, None)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 24, ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

        # User edges — interleaved (pos.xyz), 12 bytes per vertex
        self._user_edge_vao = int(GL.glGenVertexArrays(1))
        self._user_edge_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._user_edge_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_edge_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12, None)
        GL.glEnableVertexAttribArray(0)
        GL.glBindVertexArray(0)

    def _init_overlay_buffers(self) -> None:
        from OpenGL import GL

        self._overlay_line_vao = int(GL.glGenVertexArrays(1))
        self._overlay_line_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._overlay_line_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12, None)
        GL.glEnableVertexAttribArray(0)
        GL.glBindVertexArray(0)

        # Marker is a unit quad (4 verts) we transform per-frame in CPU.
        self._overlay_marker_vao = int(GL.glGenVertexArrays(1))
        self._overlay_marker_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._overlay_marker_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_marker_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12, None)
        GL.glEnableVertexAttribArray(0)
        GL.glBindVertexArray(0)

    def _refresh_user_buffers(self, scene) -> None:  # noqa: ANN001
        from OpenGL import GL

        # User faces: (3*T, 3) positions + (3*T, 3) normals → interleaved (3*T, 6)
        positions, normals = scene.face_triangle_buffer()
        if positions.shape[0] > 0:
            interleaved = np.concatenate([positions, normals], axis=1).astype(np.float32)
            data = np.ascontiguousarray(interleaved)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_face_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            self._user_face_count = int(positions.shape[0])
        else:
            self._user_face_count = 0

        # User edges: (2*E, 3) positions
        edges = scene.edge_line_buffer()
        if edges.shape[0] > 0:
            data = np.ascontiguousarray(edges)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_edge_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            self._user_edge_count = int(edges.shape[0])
        else:
            self._user_edge_count = 0

    def _draw_user_faces(self, view: np.ndarray, projection: np.ndarray) -> None:
        from OpenGL import GL

        GL.glUseProgram(self._phong_program)
        u = self._phong_uniforms
        _set_mat4(u["u_view"], view)
        _set_mat4(u["u_projection"], projection)
        # Same lighting as the M1 cube — light from above-front, neutral gray material.
        _set_vec3(u["u_light_dir"], (-1.0, 1.0, -2.0))
        _set_vec3(u["u_light_color"], (1.0, 1.0, 1.0))
        _set_vec3(u["u_material_ambient"], (0.18, 0.18, 0.20))
        _set_vec3(u["u_material_diffuse"], (0.72, 0.72, 0.74))
        _set_vec3(u["u_material_specular"], (0.30, 0.30, 0.30))
        _set_float(u["u_material_shininess"], 32.0)

        GL.glBindVertexArray(self._user_face_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, self._user_face_count)
        GL.glBindVertexArray(0)

    def _draw_user_edges(self, view: np.ndarray, projection: np.ndarray) -> None:
        from OpenGL import GL

        # Same line program as grid/axes. We rely on the existing line shader
        # taking a per-draw color via u_color uniform (set per call).
        GL.glUseProgram(self._line_program)
        u = self._line_uniforms
        _set_mat4(u["u_view"], view)
        _set_mat4(u["u_projection"], projection)

        GL.glBindVertexArray(self._user_edge_vao)
        GL.glLineWidth(1.5)
        GL.glDrawArrays(GL.GL_LINES, 0, self._user_edge_count)
        GL.glLineWidth(1.0)
        GL.glBindVertexArray(0)

    def _draw_tool_overlay(self, overlay, view: np.ndarray, projection: np.ndarray) -> None:  # noqa: ANN001
        from OpenGL import GL

        GL.glUseProgram(self._line_program)
        u = self._line_uniforms
        _set_mat4(u["u_view"], view)
        _set_mat4(u["u_projection"], projection)

        # Disable depth test so the overlay always wins.
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            # Rubber-band
            if overlay.rubber_band_segments.shape[0] > 0:
                data = np.ascontiguousarray(overlay.rubber_band_segments.astype(np.float32))
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
                GL.glBindVertexArray(self._overlay_line_vao)
                GL.glLineWidth(2.0)
                GL.glDrawArrays(GL.GL_LINES, 0, int(data.shape[0]))
                GL.glLineWidth(1.0)
                GL.glBindVertexArray(0)

            # Snap marker — small world-aligned quad at the snap point.
            if overlay.snap_marker_position is not None:
                p = overlay.snap_marker_position
                # 0.05 m square on Z=0 — small but visible at default camera distance.
                s = 0.05
                quad = np.array(
                    [
                        [p[0] - s, p[1] - s, p[2]],
                        [p[0] + s, p[1] - s, p[2]],
                        [p[0] + s, p[1] - s, p[2]],
                        [p[0] + s, p[1] + s, p[2]],
                        [p[0] + s, p[1] + s, p[2]],
                        [p[0] - s, p[1] + s, p[2]],
                        [p[0] - s, p[1] + s, p[2]],
                        [p[0] - s, p[1] - s, p[2]],
                    ],
                    dtype=np.float32,
                )
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_marker_vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, quad.nbytes, quad, GL.GL_DYNAMIC_DRAW)
                GL.glBindVertexArray(self._overlay_marker_vao)
                GL.glLineWidth(2.0)
                GL.glDrawArrays(GL.GL_LINES, 0, 8)
                GL.glLineWidth(1.0)
                GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
```

- [ ] **Step 7: Run existing tests to make sure nothing broke**

Run: `pluton-py-tests`
Expected: All existing tests pass. Some `test_viewport.py` tests may need the new render signature — if so, add `scene=None, tool_overlay=None` defaults in those test calls or skip until Task 16.

- [ ] **Step 8: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py
git commit -m "feat(viewport): add user-face/edge/overlay passes; remove M1 cube

SceneRenderer.render(camera, scene, tool_overlay) now drives three new
passes on top of the existing grid + axes: user faces (Phong-shaded, same
shader as M1 cube), user edges (line shader, neutral gray), and tool
overlay (rubber-band + snap marker, depth-test off). The M1 hardcoded cube
has been removed from the default scene per the M2 design — make_cube
survives as a C++ primitive for tests/fixtures."
```

---

## Task 14: `StatusBar` widget

**Files:**
- Create: `python/pluton/ui/status_bar.py`
- Create: `tests/test_status_bar.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_status_bar.py`

```python
"""Unit tests for the bottom status bar widget."""

from __future__ import annotations


def test_status_bar_starts_empty(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    assert bar.text() == ""


def test_status_bar_shows_tool_only_when_no_snap(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("")
    assert bar.text() == "Line · —"


def test_status_bar_shows_tool_and_snap(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("Endpoint")
    assert bar.text() == "Line · Endpoint"


def test_status_bar_clear_tool_blanks_everything(qtbot):
    from pluton.ui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.set_tool("Line")
    bar.set_snap("Grid")
    bar.set_tool("")  # no active tool
    assert bar.text() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_status_bar.py -v`
Expected: 4 FAIL with `ModuleNotFoundError: No module named 'pluton.ui.status_bar'`.

- [ ] **Step 3: Create the StatusBar** at `python/pluton/ui/status_bar.py`

```python
"""Bottom-of-viewport status bar.

Two text slots: tool name and current snap label, joined by `·`. When no
tool is active, the bar shows nothing. When a tool is active but there's
no snap, the bar shows `<tool> · —`. M4 will add a third slot for the
Measurements Box value.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBar(QLabel):
    """Single-label status bar — the tool and snap text rendered together."""

    def __init__(self) -> None:
        super().__init__()
        self._tool: str = ""
        self._snap: str = ""
        self.setText("")
        self.setMinimumHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "QLabel { background-color: rgba(0, 0, 0, 0.5); color: #dddddd;"
            " padding: 4px 10px; font-family: sans-serif; font-size: 11px; }"
        )

    def set_tool(self, name: str) -> None:
        self._tool = name
        self._refresh()

    def set_snap(self, label: str) -> None:
        self._snap = label
        self._refresh()

    def _refresh(self) -> None:
        if not self._tool:
            self.setText("")
            return
        snap = self._snap if self._snap else "—"
        self.setText(f"{self._tool} · {snap}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_status_bar.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/status_bar.py tests/test_status_bar.py
git commit -m "feat(ui): add StatusBar widget — two-slot tool/snap label

Bottom-of-viewport label with format \`<tool> · <snap>\`. Empty when no
tool is active; shows \`—\` when a tool is active but no snap fires.
M4 will add a third slot for the Measurements Box value."
```

---

## Task 15: `MainWindow` integration

**Files:**
- Modify: `python/pluton/ui/main_window.py`

- [ ] **Step 1: Rewrite `MainWindow`** at `python/pluton/ui/main_window.py`

Replace the entire file with:
```python
"""The main application window — hosts the viewport, status bar, and ToolManager."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.scene import Scene
from pluton.tools import LineTool, RectangleTool, ToolContext, ToolManager
from pluton.ui.status_bar import StatusBar
from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Scene + tool manager
        self._scene = Scene()
        self._tool_manager = ToolManager()
        self._tool_manager.set_context(ToolContext(scene=self._scene))
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())

        # Viewport + status bar in a vertical layout
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._status_bar = StatusBar()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewport, stretch=1)
        layout.addWidget(self._status_bar, stretch=0)
        self.setCentralWidget(container)

        # Wire the status bar to ViewportWidget updates
        self._viewport.set_status_bar(self._status_bar)

        # Keyboard shortcuts (work regardless of focus)
        QShortcut(QKeySequence("L"), self, activated=lambda: self._activate("L"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self._activate("R"))
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_clear_scene)

    # --- Slots -----------------------------------------------------------

    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._viewport.update()

    def _on_escape(self) -> None:
        # Forward to active tool's on_key_press; if no tool, no-op.
        active = self._tool_manager.active
        if active is None:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._viewport.update()

    def _on_clear_scene(self) -> None:
        self._scene.clear()
        self._viewport.update()
```

- [ ] **Step 2: Verify the existing main-window test still passes**

Run: `pytest tests/test_viewport.py::test_main_window_constructs -v`
Expected: PASS (we haven't broken construction). If it fails because `ViewportWidget(...)` now takes positional args, Task 16 will update its signature — temporarily skip this test by adding `@pytest.mark.skip("updated in Task 16")` on the M1 test and remove the skip after Task 16.

- [ ] **Step 3: Commit**

```bash
git add python/pluton/ui/main_window.py
git commit -m "feat(ui): wire Scene + ToolManager + StatusBar into MainWindow

MainWindow owns the Scene and ToolManager; instantiates LineTool and
RectangleTool; lays out the viewport above the status bar; binds the
L / R / Esc / Ctrl+N keyboard shortcuts. Ctrl+N clears the scene; Esc
forwards to the active tool's on_key_press."
```

---

## Task 16: `ViewportWidget` rewrite for tool delegation

**Files:**
- Modify: `python/pluton/viewport/viewport_widget.py`
- Modify: `tests/test_viewport.py`

- [ ] **Step 1: Rewrite `ViewportWidget`** at `python/pluton/viewport/viewport_widget.py`

Replace the entire file with:
```python
"""The 3D viewport widget — drives the scene + snap engine + active tool.

Owns a Camera (Python/numpy) and a SceneRenderer (GL resources). Translates
Qt mouse events into:
  * MMB drag         -> camera orbit (unchanged from M1)
  * Shift + MMB drag -> camera pan   (unchanged from M1)
  * Scroll wheel     -> camera zoom  (unchanged from M1)
  * LMB / cursor-move (when a tool is active) -> snap + delegate to tool
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pluton.viewport.camera import Camera
from pluton.viewport.scene_renderer import SceneRenderer
from pluton.viewport.snap_engine import SnapEngine, SnapKind


class ViewportWidget(QOpenGLWidget):
    """The 3D viewport. Renders scene + active tool overlay; routes mouse events."""

    def __init__(self, scene=None, tool_manager=None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.camera = Camera()
        self.scene_renderer = SceneRenderer()
        self.scene = scene
        self.tool_manager = tool_manager
        self.snap_engine = SnapEngine()
        self._status_bar = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._last_mouse_pos: QPoint | None = None
        self._dragging_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._dragging_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    def set_status_bar(self, status_bar) -> None:  # noqa: ANN001
        self._status_bar = status_bar

    # --- GL lifecycle -----------------------------------------------------

    def initializeGL(self) -> None:
        self.scene_renderer.initialize_gl()

    def resizeGL(self, w: int, h: int) -> None:
        self.scene_renderer.resize(w, h)
        self.camera.aspect = float(w) / max(float(h), 1.0)

    def paintGL(self) -> None:
        active = self.tool_manager.active if self.tool_manager is not None else None
        overlay = active.overlay() if active is not None else None
        self.scene_renderer.render(self.camera, self.scene, overlay)

    # --- Mouse handling ---------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.MiddleButton
            self._dragging_modifiers = event.modifiers()
            self._last_mouse_pos = event.position().toPoint()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            active = self.tool_manager.active if self.tool_manager is not None else None
            if active is not None:
                snap = self._snap_for_event(event)
                active.on_mouse_press(event, snap)
                if self._status_bar is not None:
                    self._status_bar.set_snap(snap.label)
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # Camera drag — unchanged from M1.
        if (
            self._dragging_button == Qt.MouseButton.MiddleButton
            and self._last_mouse_pos is not None
        ):
            current = event.position().toPoint()
            dx = float(current.x() - self._last_mouse_pos.x())
            dy = float(current.y() - self._last_mouse_pos.y())
            self._last_mouse_pos = current
            if self._dragging_modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.camera.pan(dx_pixels=dx, dy_pixels=dy)
            else:
                self.camera.orbit(dx_pixels=dx, dy_pixels=-dy)
            self.update()
            event.accept()
            return

        # Tool delegation
        active = self.tool_manager.active if self.tool_manager is not None else None
        if active is not None:
            snap = self._snap_for_event(event)
            active.on_mouse_move(event, snap)
            if self._status_bar is not None:
                self._status_bar.set_snap(snap.label if snap.kind != SnapKind.NONE else "")
            self.update()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.NoButton
            self._last_mouse_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120.0
        if notches == 0:
            super().wheelEvent(event)
            return
        cursor = event.position()
        ndc = self._cursor_to_ndc(cursor.x(), cursor.y())
        self.camera.zoom(scroll_delta=notches, cursor_ndc=ndc)
        self.update()
        event.accept()

    # --- Helpers ----------------------------------------------------------

    def _cursor_to_ndc(self, x: float, y: float) -> np.ndarray:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        nx = (2.0 * x / w) - 1.0
        ny = 1.0 - (2.0 * y / h)
        return np.array([nx, ny], dtype=np.float32)

    def _snap_for_event(self, event: QMouseEvent):
        pos = event.position()
        cursor_world = self.camera.ray_intersect_ground(
            float(pos.x()), float(pos.y()), self.width(), self.height()
        )
        active = self.tool_manager.active if self.tool_manager is not None else None
        anchor = active.anchor_or_none if active is not None else None
        return self.snap_engine.snap(
            cursor_world,
            (float(pos.x()), float(pos.y())),
            self.camera,
            self.scene,
            anchor=anchor,
        )
```

- [ ] **Step 2: Update `test_viewport.py` constructors** — edit `tests/test_viewport.py`

Find the lines that read:
```python
widget = ViewportWidget()
```
and replace with:
```python
from pluton.scene import Scene
from pluton.tools import ToolManager
widget = ViewportWidget(Scene(), ToolManager(), parent=None)
```

(There are several occurrences; update them all. The existing camera/wheel/MMB tests still apply — those code paths are unchanged.)

- [ ] **Step 3: Add full-gesture integration tests** — append to `tests/test_viewport.py`

```python
def test_keyboard_l_activates_line_tool(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.keyClick(window, Qt.Key.Key_L)
    assert window._tool_manager.active is not None
    assert window._tool_manager.active.name == "Line"


def test_keyboard_r_activates_rectangle_tool(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.keyClick(window, Qt.Key.Key_R)
    assert window._tool_manager.active.name == "Rectangle"


def test_ctrl_n_clears_scene(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    # Seed the scene with a vertex.
    window._scene.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))
    assert len(list(window._scene.vertices_iter())) == 1
    qtbot.keyClick(window, Qt.Key.Key_N, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 0
```

- [ ] **Step 4: Run all tests**

Run: `pluton-py-tests`
Expected: ~57–62 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/viewport_widget.py tests/test_viewport.py
git commit -m "feat(viewport): ViewportWidget routes events through SnapEngine + active tool

LMB and cursor-move (when a tool is active) raycast the cursor to Z=0,
ask the SnapEngine, forward the SnapResult to the active tool, and update
the status bar. MMB / Shift+MMB / wheel zoom from M1 are unchanged.
Integration tests cover L/R/Ctrl+N via qtbot."
```

---

## Task 17: Manual visual verification

**Files:**
- (None — this is a manual smoke test by the human at the keyboard.)

- [ ] **Step 1: Rebuild and launch**

```bash
pluton-build
python -m pluton
```

- [ ] **Step 2: Verify the empty scene**

The window opens. You should see:
- Z=0 grid (10×10 m, 1 m spacing)
- Red / green / blue axes through origin
- **No cube**
- Empty status bar at the bottom of the central widget

- [ ] **Step 3: Camera still works**

- MMB drag → orbit
- Shift + MMB drag → pan
- Scroll wheel → zoom toward cursor

These should match M1 exactly. No tool events triggered.

- [ ] **Step 4: Rectangle tool**

- Press **R**. Status bar reads `Rectangle · —`.
- Click on the ground. Drag the cursor. A rectangle preview follows.
- Click again. A filled rectangle face appears, with its 4 edges visible.

- [ ] **Step 5: Line tool**

- Press **L**. Status bar reads `Line · —` (or `Line · Grid` if hovering).
- Click out a 4-click closed quadrilateral that ends at the first vertex. The face fills.
- Verify the rubber-band shows during drawing.
- Verify endpoint-snap fires when hovering near an existing vertex (green marker, status bar `Line · Endpoint`).
- Verify midpoint-snap fires when hovering near the midpoint of an existing edge (cyan marker, status bar `Line · Midpoint`).
- Verify axis-lock fires when drawing roughly along the X/Y axis from the previous vertex — rubber-band turns red/green, status bar reads `Line · on Red Axis` / `Line · on Green Axis`.

- [ ] **Step 6: Cancel + clear**

- Mid-drawing a Line, press **Esc**. The preview clears; the tool stays active.
- Press **Ctrl+N**. The scene clears back to grid + axes.

- [ ] **Step 7: No commit for this task**

Manual verification doesn't produce code; nothing to commit. If anything failed, file a bug as a follow-up task or stop and fix before continuing.

---

## Task 18: Push and verify CI

**Files:**
- (None — just push.)

- [ ] **Step 1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 2: Watch CI**

```bash
gh run watch --exit-status
```

Expected: both Windows and Linux runners green.

- [ ] **Step 3: If CI fails**

Most likely culprits:
1. `mapbox-earcut` wheel not available for the runner's Python version — check the PyPI page and pin a compatible version range.
2. `pytest-qt` flake on the offscreen platform for one of the new integration tests — read the CI log, isolate the test, reproduce locally with `QT_QPA_PLATFORM=offscreen`.
3. A test that uses `qtbot.keyClick` without focus — see if the test calls `window.show()`.

Fix locally, push, re-watch. Confirm green via `gh run view <run_id>` (not just exit-status) per the M1 lesson.

- [ ] **Step 4: No new commit unless a fix landed**

If CI was already green, this task produces no commit.

---

## Task 19: Version bump and release tag

**Files:**
- Modify: `pyproject.toml`
- Modify: `CMakeLists.txt` (top-level)
- Modify: `cpp/src/version.cpp`

- [ ] **Step 1: Bump `pyproject.toml`**

Replace:
```toml
version = "0.0.2"
```
with:
```toml
version = "0.0.3"
```

- [ ] **Step 2: Bump top-level `CMakeLists.txt`**

Find the `project(...)` line and change `VERSION 0.0.2` to `VERSION 0.0.3`.

- [ ] **Step 3: Bump `cpp/src/version.cpp`**

Find:
```cpp
return "0.0.2";
```
and change to:
```cpp
return "0.0.3";
```

- [ ] **Step 4: Rebuild and run all tests**

```bash
pluton-build
pluton-cpp-tests
pluton-py-tests
```

Expected: all green, including the version test that asserts `pluton.version() == "0.0.3"`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp
git commit -m "chore: bump version to 0.0.3 for M2 release"
```

- [ ] **Step 6: Tag the release**

```bash
git tag -a v0.0.3-m2 -m "M2 — Basic Drawing

Line tool, Rectangle tool, snap engine (grid + endpoint + midpoint +
axis-lock with precedence), generic Tool framework, pure-Python Scene
with auto-face on closed planar loop, and bottom status bar.

First Python-only milestone. C++ kernel unchanged."
```

- [ ] **Step 7: Push the commit and the tag**

```bash
git push origin main
git push origin v0.0.3-m2
```

- [ ] **Step 8: Confirm the tag on GitHub**

```bash
gh release view v0.0.3-m2 2>/dev/null || gh api repos/parrow-horrizon-studio/pluton/git/refs/tags/v0.0.3-m2
```

Expected: the tag exists at the M2 final commit.

- [ ] **Step 9: Open carry-over GitHub issues**

For each entry in spec §5.6 (Known M2 limitations) and §6 (Out of scope), open a GitHub issue. Suggested batch:

```bash
gh issue create --title "M4: add on-edge snap + edge-splitting in Line tool" \
  --body "Per M2 spec §5.6 limitation 1. Drawing a Line through the middle of an existing edge should split that edge at the intersection point, creating a new vertex and replacing the original edge with two segments. Lands in M4 with the broader on-edge / intersection snap work."

gh issue create --title "M4: detect self-intersecting Line polylines" \
  --body "Per M2 spec §5.6 limitation 2. A self-crossing closed polyline currently produces a geometrically invalid face. M4 should detect the self-intersection via planar segment-intersection logic and reject the loop close (or auto-split it)."

gh issue create --title "M3: undo/redo via command pattern" \
  --body "Per M2 spec §5.6 limitation 3. M2 has no undo; Ctrl+N clears the entire scene as the only escape hatch. ESC mid-gesture clears visible state but does not roll back committed vertices. M3 owns the command pattern + undo/redo stack."

gh issue create --title "M4: drawing on existing face surfaces" \
  --body "Per M2 spec §5.6 limitation 4. M2 draws strictly on the ground plane. M4 adds drawing on existing faces (ray-mesh intersection, per-face coordinate frames)."

gh issue create --title "M4: Measurements Box + numeric input while drawing" \
  --body "Per M2 spec §5.6 limitation 5. M4 adds the Measurements Box with the units system."

gh issue create --title "M3: Scene.remove_* operations" \
  --body "Per M2 spec §5.6 limitation 6. M3's push/pull will need to remove the source face and substitute the extruded prism. Adds remove_vertex / remove_edge / remove_face with cascading semantics."
```

Optionally also open issues for §6 entries that don't already have a milestone tracker (Circle/Arc/Polygon tools, Eraser/Select/Move/Rotate/Scale, Tape Measure, Groups & Components, Tool palette/toolbar, file I/O, etc.) — only as you see fit.

---

## Self-Review Checklist (for the plan author)

After the plan is written, verify:

- [ ] **Spec §1 (Purpose)** — covered by overall plan goal in the header.
- [ ] **Spec §2 (End State)** — covered by §"Definition of Done for M2".
- [ ] **Spec §3.1 decisions** — each row implemented in a specific task (most in Tasks 2–13).
- [ ] **Spec §3.2 file map** — exactly mirrored in the plan's File Map section.
- [ ] **Spec §3.3 dependency on mapbox-earcut** — Task 1.
- [ ] **Spec §3.4 (render frame data flow)** — Task 13.
- [ ] **Spec §3.5 (mouse-move data flow)** — Task 16.
- [ ] **Spec §4.1 (Scene)** — Tasks 2, 3, 4, 5, 6.
- [ ] **Spec §4.2 (SnapEngine)** — Tasks 8, 9.
- [ ] **Spec §4.3 (Tool framework)** — Tasks 10, 11, 12.
- [ ] **Spec §4.4 (SceneRenderer extensions)** — Task 13.
- [ ] **Spec §4.5 (Tool state machines)** — Tasks 11 (Rectangle), 12 (Line).
- [ ] **Spec §4.6 (StatusBar)** — Task 14.
- [ ] **Spec §5 (edge cases)** — covered by tests in Tasks 4, 5, 11, 12 + integration in Task 16.
- [ ] **Spec §6 (out of scope)** — opened as issues in Task 19 step 9.
- [ ] **Spec §7 (M3 contract)** — no plan task needed; the contract is the API surface produced by Tasks 2–16.
- [ ] **Spec §8 (testing)** — every component-level row in spec §8 maps to one or more tasks above.
- [ ] **Spec §9 (implementation order)** — this plan's task numbering follows the same ordering.

If any row is unticked, the missing coverage was added inline before commit.

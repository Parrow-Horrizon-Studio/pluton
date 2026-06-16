# M4c — Move / Rotate / Scale Transforms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The three SketchUp transform tools — Move (M, point-to-point + snap), Rotate (Q, auto-tilt protractor), Scale (S, full bounding-box handle set) — all operating on the M4b selection, on one new C++ kernel op and a shared generic command.

**Architecture:** One new C++ mutator `HalfEdgeMesh::set_vertex_position` (dedup-index upkeep + cached-normal recompute on incident faces) is the only kernel change. All three tools resolve a `{vertex_id: (old, new)}` dict and hand it to one generic `TransformVerticesCommand`; undo swaps old↔new. Transform numerics live in a pure-Python `geometry/transforms.py`. Gizmos render through generic overlay primitives (`world_polylines`, `screen_markers`, reusing the existing translucent face-fill for the protractor disk), so the renderer stays tool-agnostic. Tools preview via overlay only and commit once at the end — no mid-gesture mesh mutation.

**Tech Stack:** C++20 half-edge kernel (nanobind bindings) · Python 3.13 · numpy · PySide6/PyOpenGL viewport · GoogleTest (ctest) · pytest + pytest-qt. Spec: `docs/2026-06-16-M4c-transforms-design.md`.

---

## Conventions & guardrails (read before every task)

- **Interpreter:** always `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash). The bare `python`/`pytest` resolve to a different, drifting install.
- **Working dir:** run all commands from `F:\dev\00_Parrow-Horrizon-Studio\pluton`. In the Bash tool the cwd resets between calls — prefix with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && …`.
- **C++ rebuild:** Tasks 1–2 change `cpp/`. After **either**, rebuild the extension: `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation`. Tasks 3+ are pure Python but depend on the Task 2 binding being built. Build + run the C++ GoogleTests with: `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure`.
- **Git:** work on `main`. Stage **specific files only** — never `git add -A`/`git add .`. End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay on). Fix hook failures at the cause.
- **Do not touch version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) until the release task (Task 12).
- **TDD:** failing test → watch it fail → minimal code → watch it pass → commit. One commit per task.
- **Qt event construction in tests:** build mouse events with
  `QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)`.
  If your PySide6 build rejects that overload, use the one that also takes a global position: `QMouseEvent(type, QPointF(x,y), QPointF(x,y), button, buttons, modifiers)`. Tool tests need a `qtbot` fixture so a `QApplication` exists.
- **Fake snaps in tool tests:** the tools only read `snap.kind` and `snap.world_position`. Build a stand-in with `types.SimpleNamespace(kind=SnapKind.ON_FACE, world_position=np.array([...], np.float32), axis=None, vertex_id=None, edge_id=None, edge_t=None)` to avoid wiring the full SnapEngine.

---

## File structure

| File | Responsibility |
|------|----------------|
| `cpp/include/pluton/halfedge.h` | + `set_vertex_position` decl; + private `recompute_face_normal` decl. |
| `cpp/src/halfedge.cpp` | + `set_vertex_position` + `recompute_face_normal` impl. |
| `cpp/tests/test_halfedge.cpp` | + GoogleTests for the new op (append). |
| `cpp/bindings/module.cpp` | + `.def("set_vertex_position", …)`. |
| `python/pluton/scene/scene.py` | + `Scene.set_vertex_position` wrapper. |
| `tests/test_halfedge_python.py` | + binding + Scene smoke tests (append). |
| `python/pluton/geometry/transforms.py` | **new** — pure `translate` / `rotate` / `scale`. |
| `python/pluton/tools/transform_support.py` | **new** — `selection_vertices`, `selection_aabb`, grip geometry helpers. |
| `python/pluton/commands/scene_commands.py` | + `TransformVerticesCommand`. |
| `python/pluton/tools/tool.py` | + `ToolOverlay.world_polylines` + `ToolOverlay.screen_markers`. |
| `python/pluton/viewport/scene_renderer.py` | + `_draw_world_polylines`, `_draw_screen_markers`; wire into `render`. |
| `python/pluton/tools/move_tool.py` | **new** — `MoveTool` (M). |
| `python/pluton/tools/rotate_tool.py` | **new** — `RotateTool` (Q). |
| `python/pluton/tools/scale_tool.py` | **new** — `ScaleTool` (S). |
| `python/pluton/tools/__init__.py` | export the three tools. |
| `python/pluton/ui/main_window.py` | register tools; M/Q/S shortcuts; status. |
| `tests/...` | per task. |

---

## Task 1: C++ `set_vertex_position` + GoogleTests

**Files:**
- Modify: `cpp/include/pluton/halfedge.h` (Mutators section + a private helper)
- Modify: `cpp/src/halfedge.cpp`
- Test: `cpp/tests/test_halfedge.cpp` (append)

- [ ] **Step 1: Declare the new op + helper** — in `cpp/include/pluton/halfedge.h`, add to the `// ---- Mutators ----` block (next to `restore_face`):

```cpp
    /// Move an existing live vertex to (x, y, z) in place. Updates the
    /// position dedup index (last-writer-wins on a coincident collision) and
    /// recomputes the cached normal of every incident face. Throws
    /// std::out_of_range if v_id is dead/out of range. No re-triangulation,
    /// no topological merge.
    void set_vertex_position(std::uint32_t v_id, float x, float y, float z);
```

…and in the `private:` section (next to the other helpers near the bottom):

```cpp
    void recompute_face_normal(std::uint32_t f_id);
```

- [ ] **Step 2: Write the failing GoogleTest** — append to `cpp/tests/test_halfedge.cpp` (it already includes `pluton/halfedge.h` and `<gtest/gtest.h>`; add `#include <cmath>` at the top if not present):

```cpp
TEST(HalfEdgeSetVertexPosition, MovesVertexAndUpdatesIndex) {
    pluton::HalfEdgeMesh m;
    auto a = m.add_vertex(0.0f, 0.0f, 0.0f);
    m.set_vertex_position(a, 5.0f, 6.0f, 7.0f);
    auto p = m.vertex_position(a);
    EXPECT_FLOAT_EQ(p[0], 5.0f);
    EXPECT_FLOAT_EQ(p[1], 6.0f);
    EXPECT_FLOAT_EQ(p[2], 7.0f);
    // Old key freed → re-adding the old position allocates a NEW vertex.
    auto a_old = m.add_vertex(0.0f, 0.0f, 0.0f);
    EXPECT_NE(a_old, a);
    // New position is idempotent → returns the moved vertex.
    auto a_new = m.add_vertex(5.0f, 6.0f, 7.0f);
    EXPECT_EQ(a_new, a);
}

TEST(HalfEdgeSetVertexPosition, RecomputesIncidentFaceNormal) {
    pluton::HalfEdgeMesh m;
    auto a = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto b = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto c = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(a, b);
    m.add_halfedge_pair(b, c);
    m.add_halfedge_pair(c, a);
    m.add_face_from_loop({a, b, c},
        {static_cast<std::int32_t>(a), static_cast<std::int32_t>(b), static_cast<std::int32_t>(c)});
    auto buf0 = m.face_triangle_buffer();           // (positions, normals)
    ASSERT_GE(buf0.second.size(), 3u);
    EXPECT_NEAR(std::abs(buf0.second[2]), 1.0f, 1e-4f);   // flat in XY → |nz| ≈ 1
    // Tilt the face: lift c in +Z.
    m.set_vertex_position(c, 0.0f, 1.0f, 1.0f);
    auto buf1 = m.face_triangle_buffer();
    ASSERT_GE(buf1.second.size(), 3u);
    float nx = buf1.second[0], ny = buf1.second[1];
    EXPECT_GT(std::abs(nx) + std::abs(ny), 0.1f);   // normal now has a horizontal component
}

TEST(HalfEdgeSetVertexPosition, ThrowsOnDeadVertex) {
    pluton::HalfEdgeMesh m;
    EXPECT_THROW(m.set_vertex_position(999u, 1.0f, 2.0f, 3.0f), std::out_of_range);
}
```

- [ ] **Step 3: Build & run; confirm FAIL** — `cmake --build build/tests` → link error / undefined `set_vertex_position`.

- [ ] **Step 4: Implement** — in `cpp/src/halfedge.cpp`, **after** the anonymous-namespace block that defines `compute_face_normal_geometric` (i.e. alongside `faces_are_coplanar`, so the helper is in scope):

```cpp
void pluton::HalfEdgeMesh::recompute_face_normal(std::uint32_t f_id) {
    if (!face_is_live(f_id)) return;
    auto n = compute_face_normal_geometric(*this, f_id);  // {0,0,0} if degenerate
    faces_[f_id].normal[0] = n[0];
    faces_[f_id].normal[1] = n[1];
    faces_[f_id].normal[2] = n[2];
}

void pluton::HalfEdgeMesh::set_vertex_position(std::uint32_t v_id, float x, float y, float z) {
    if (v_id >= vertices_.size() || !vertices_[v_id].alive) {
        throw std::out_of_range(
            "HalfEdgeMesh::set_vertex_position: v_id " + std::to_string(v_id) + " is not live");
    }
    // Collapse negative zero so -0.0 and 0.0 hash identically (matches add_vertex).
    if (x == 0.0f) x = 0.0f;
    if (y == 0.0f) y = 0.0f;
    if (z == 0.0f) z = 0.0f;

    Vertex& v = vertices_[v_id];
    // Dedup-index upkeep: drop the old packed key, install the new one.
    position_index_.erase(pack_position(v.pos[0], v.pos[1], v.pos[2]));
    v.pos[0] = x; v.pos[1] = y; v.pos[2] = z;
    position_index_[pack_position(x, y, z)] = v_id;

    // Recompute cached normals on every incident face. Each incident face has
    // exactly one boundary half-edge originating at v_id; recompute is
    // idempotent, so no dedup is needed.
    for (const auto& he : halfedges_) {
        if (he.alive && he.origin == v_id && he.face != INVALID_ID) {
            recompute_face_normal(he.face);
        }
    }
    dirty_ = true;
}
```

- [ ] **Step 5: Build & run; confirm PASS** — `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure -R SetVertexPosition` → 3 PASS. Then full `ctest --test-dir build/tests --output-on-failure` → all green (72 prior + 3).

- [ ] **Step 6: Commit**

```bash
git add cpp/include/pluton/halfedge.h cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(kernel): set_vertex_position with dedup-index + normal recompute

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: nanobind binding + `Scene.set_vertex_position`

**Files:**
- Modify: `cpp/bindings/module.cpp`
- Modify: `python/pluton/scene/scene.py`
- Test: `tests/test_halfedge_python.py` (append)

- [ ] **Step 1: Write the failing test** — append to `tests/test_halfedge_python.py`:

```python
def test_set_vertex_position_binding():
    from pluton._core import HalfEdgeMesh
    m = HalfEdgeMesh()
    a = m.add_vertex(0.0, 0.0, 0.0)
    m.set_vertex_position(a, 2.0, 3.0, 4.0)
    assert tuple(m.vertex_position(a)) == (2.0, 3.0, 4.0)


def test_scene_set_vertex_position():
    import numpy as np
    import pytest
    from pluton.scene.scene import Scene
    s = Scene()
    v = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    s.set_vertex_position(v, np.array([1.0, 1.0, 1.0], dtype=np.float32))
    assert np.allclose(s.vertex(v).position, [1.0, 1.0, 1.0])
    with pytest.raises(KeyError):
        s.set_vertex_position(999, np.array([0.0, 0.0, 0.0], dtype=np.float32))
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_halfedge_python.py -k set_vertex_position -v` → `AttributeError: … 'set_vertex_position'`.

- [ ] **Step 3: Bind it** — in `cpp/bindings/module.cpp`, in the `HalfEdgeMesh` class binding, add after `.def("restore_face", …)`:

```cpp
        .def("set_vertex_position", &HalfEdgeMesh::set_vertex_position)
```

- [ ] **Step 4: Scene wrapper** — in `python/pluton/scene/scene.py`, add after `restore_face` (in the Mutators block):

```python
    def set_vertex_position(self, v_id: int, position: np.ndarray) -> None:
        """Move an existing live vertex to `position` (float32 (3,)) in place.

        Recomputes cached normals on incident faces (delegated to C++).
        Raises KeyError if the vertex is not live.
        """
        position = np.asarray(position, dtype=np.float32).reshape(3)
        try:
            self._mesh.set_vertex_position(
                v_id, float(position[0]), float(position[1]), float(position[2])
            )
        except IndexError as e:
            raise KeyError(str(e)) from None
```

- [ ] **Step 5: Rebuild + run; confirm PASS**

```bash
.venv/Scripts/python.exe -m pip install -e . --no-build-isolation
.venv/Scripts/python.exe -m pytest tests/test_halfedge_python.py -k set_vertex_position -v
```
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add cpp/bindings/module.cpp python/pluton/scene/scene.py tests/test_halfedge_python.py
git commit -m "feat(scene): bind + wrap set_vertex_position

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `geometry/transforms.py` — translate / rotate / scale

**Files:**
- Create: `python/pluton/geometry/transforms.py`
- Test: `tests/test_transforms.py`

- [ ] **Step 1: Write the failing test** — `tests/test_transforms.py`:

```python
"""Unit tests for pure transform math (no Qt/GL/Scene)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pluton.geometry.transforms import rotate, scale, translate


def test_translate_known():
    pts = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
    out = translate(pts, [10, 0, -1])
    assert np.allclose(out, [[11, 2, 2], [14, 5, 5]])
    assert out.dtype == np.float32


def test_translate_zero_is_identity():
    pts = np.array([[1, 2, 3]], dtype=np.float32)
    assert np.allclose(translate(pts, [0, 0, 0]), pts)


def test_rotate_90_about_z_origin():
    pts = np.array([[1, 0, 0]], dtype=np.float32)
    out = rotate(pts, center=[0, 0, 0], axis=[0, 0, 1], angle_rad=math.pi / 2)
    assert np.allclose(out, [[0, 1, 0]], atol=1e-5)


def test_rotate_about_offset_center_keeps_center_fixed():
    c = np.array([5, 5, 0], dtype=np.float32)
    out = rotate(c.reshape(1, 3), center=c, axis=[0, 0, 1], angle_rad=1.2345)
    assert np.allclose(out, c.reshape(1, 3), atol=1e-5)


def test_rotate_zero_angle_is_identity():
    pts = np.array([[2, -3, 4]], dtype=np.float32)
    out = rotate(pts, center=[0, 0, 0], axis=[0, 1, 0], angle_rad=0.0)
    assert np.allclose(out, pts, atol=1e-6)


def test_rotate_degenerate_axis_raises():
    with pytest.raises(ValueError):
        rotate(np.zeros((1, 3), np.float32), center=[0, 0, 0], axis=[0, 0, 0], angle_rad=1.0)


def test_scale_anisotropic_about_anchor():
    pts = np.array([[2, 2, 2]], dtype=np.float32)
    out = scale(pts, anchor=[0, 0, 0], factors=[2, 1, 0.5])
    assert np.allclose(out, [[4, 2, 1]])


def test_scale_keeps_anchor_fixed():
    anchor = np.array([1, 1, 1], dtype=np.float32)
    out = scale(anchor.reshape(1, 3), anchor=anchor, factors=[3, 3, 3])
    assert np.allclose(out, anchor.reshape(1, 3))


def test_scale_factor_one_is_identity():
    pts = np.array([[7, 8, 9]], dtype=np.float32)
    assert np.allclose(scale(pts, anchor=[1, 1, 1], factors=[1, 1, 1]), pts)
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_transforms.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — `python/pluton/geometry/transforms.py`:

```python
"""Pure transform math for Move / Rotate / Scale.

All functions take and return (N, 3) float32 arrays and have no dependency on
Qt, OpenGL, or the Scene. Move/Rotate/Scale tools resolve which vertices to
transform, then call these to get the new positions.
"""

from __future__ import annotations

import numpy as np


def translate(points: np.ndarray, delta) -> np.ndarray:  # noqa: ANN001
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    d = np.asarray(delta, dtype=np.float32).reshape(3)
    return (pts + d).astype(np.float32)


def rotate(points: np.ndarray, center, axis, angle_rad: float) -> np.ndarray:  # noqa: ANN001
    """Rotate points about the line through `center` along `axis` (Rodrigues).

    `axis` need not be unit length. Raises ValueError on a near-zero axis.
    """
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3).astype(np.float64)
    c = np.asarray(center, dtype=np.float64).reshape(3)
    k = np.asarray(axis, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(k))
    if norm < 1e-9:
        raise ValueError("rotate: degenerate (near-zero) axis")
    k = k / norm
    a = float(angle_rad)
    cos_a, sin_a = np.cos(a), np.sin(a)
    rel = pts - c
    cross = np.cross(np.broadcast_to(k, rel.shape), rel)
    dot = rel @ k
    rot = rel * cos_a + cross * sin_a + np.outer(dot, k) * (1.0 - cos_a)
    return (rot + c).astype(np.float32)


def scale(points: np.ndarray, anchor, factors) -> np.ndarray:  # noqa: ANN001
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    a = np.asarray(anchor, dtype=np.float32).reshape(3)
    f = np.asarray(factors, dtype=np.float32).reshape(3)
    return (a + (pts - a) * f).astype(np.float32)
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_transforms.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/geometry/transforms.py tests/test_transforms.py
git commit -m "feat(geometry): pure translate/rotate/scale transform math

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `transform_support.py` — selection → vertex set, AABB, grips

**Files:**
- Create: `python/pluton/tools/transform_support.py`
- Test: `tests/test_transform_support.py`

- [ ] **Step 1: Write the failing test** — `tests/test_transform_support.py`:

```python
"""Selection→vertex-set, AABB, and scale-grip geometry helpers."""

from __future__ import annotations

import numpy as np

from pluton.scene.scene import Scene
from pluton.selection import Selection
from pluton.tools.transform_support import (
    grip_specs,
    selection_aabb,
    selection_vertices,
)


def _square(scene: Scene):
    a = scene.add_vertex(np.array([0, 0, 0], np.float32))
    b = scene.add_vertex(np.array([2, 0, 0], np.float32))
    c = scene.add_vertex(np.array([2, 2, 0], np.float32))
    d = scene.add_vertex(np.array([0, 2, 0], np.float32))
    f = scene.add_face_from_loop([a, b, c, d])
    return a, b, c, d, f


def test_selection_vertices_from_face_is_loop():
    s = Scene()
    a, b, c, d, f = _square(s)
    sel = Selection()
    sel.replace(faces=[f])
    assert sorted(selection_vertices(s, sel)) == sorted([a, b, c, d])


def test_selection_vertices_from_edge_is_two_endpoints():
    s = Scene()
    a, b, c, d, f = _square(s)
    e = s.face_edges(f)[0]  # an edge of the square
    sel = Selection()
    sel.replace(edges=[e])
    verts = selection_vertices(s, sel)
    assert len(verts) == 2
    assert set(verts) <= {a, b, c, d}


def test_selection_vertices_dedups_shared():
    s = Scene()
    a, b, c, d, f = _square(s)
    edges = s.face_edges(f)
    sel = Selection()
    sel.replace(edges=edges, faces=[f])
    # union is still exactly the 4 corners
    assert sorted(selection_vertices(s, sel)) == sorted([a, b, c, d])


def test_selection_aabb():
    s = Scene()
    a, b, c, d, f = _square(s)
    lo, hi = selection_aabb(s, [a, b, c, d])
    assert np.allclose(lo, [0, 0, 0])
    assert np.allclose(hi, [2, 2, 0])


def test_selection_aabb_empty_is_none():
    s = Scene()
    assert selection_aabb(s, []) is None


def test_grip_specs_planar_box_has_eight_grips():
    # A flat (z-extent 0) box collapses the z axis → 8 distinct planar grips
    # (4 corners + 4 edge-mids), no 1-axis face grips that duplicate corners.
    lo = np.array([0, 0, 0], np.float32)
    hi = np.array([2, 2, 0], np.float32)
    grips = grip_specs(lo, hi)
    positions = [tuple(np.round(g.position, 4)) for g in grips]
    assert len(positions) == len(set(positions))   # all distinct
    assert len(grips) == 8


def test_grip_specs_full_box_has_26_grips():
    lo = np.array([0, 0, 0], np.float32)
    hi = np.array([2, 2, 2], np.float32)
    grips = grip_specs(lo, hi)
    assert len(grips) == 26   # 8 corners + 12 edges + 6 faces
    # every grip has a distinct opposite within the set
    by_pos = {tuple(np.round(g.position, 4)): g for g in grips}
    for g in grips:
        opp = tuple(np.round(g.opposite, 4))
        assert opp in by_pos


def test_grip_specs_corner_axes_are_all_three():
    lo = np.array([0, 0, 0], np.float32)
    hi = np.array([2, 2, 2], np.float32)
    grips = grip_specs(lo, hi)
    corners = [g for g in grips if len(g.axes) == 3]
    assert len(corners) == 8
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError: pluton.tools.transform_support`.

- [ ] **Step 3: Implement** — `python/pluton/tools/transform_support.py`:

```python
"""Geometry helpers shared by the transform tools.

`selection_vertices` flattens an M4b Selection into the unique vertex ids it
covers. `selection_aabb` is their world axis-aligned bounding box. `grip_specs`
enumerates the Scale gizmo's handles (corner/edge/face) on that box, each
carrying the axes it drives and its opposite (anchor) position.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def selection_vertices(scene, selection) -> list[int]:  # noqa: ANN001
    """Ordered-unique vertex ids covered by the selection.

    Union of each selected edge's two endpoints and each selected face's loop.
    Ids whose entity is no longer live are skipped. Sorted for determinism.
    """
    seen: dict[int, None] = {}
    for e_id in sorted(selection.edges):
        try:
            e = scene.edge(e_id)
        except KeyError:
            continue
        seen.setdefault(int(e.v1_id), None)
        seen.setdefault(int(e.v2_id), None)
    for f_id in sorted(selection.faces):
        try:
            loop = scene.face_loop(f_id)
        except KeyError:
            continue
        for vid in loop:
            seen.setdefault(int(vid), None)
    return list(seen)


def selection_aabb(scene, vertex_ids):  # noqa: ANN001
    """(min_xyz, max_xyz) float32 over the given vertex ids, or None if empty."""
    if not vertex_ids:
        return None
    pts = np.array([scene.vertex(v).position for v in vertex_ids], dtype=np.float32)
    return pts.min(axis=0).astype(np.float32), pts.max(axis=0).astype(np.float32)


@dataclass(frozen=True)
class GripSpec:
    position: np.ndarray            # world handle position (3,) float32
    opposite: np.ndarray            # the anchor: opposite handle position (3,) float32
    axes: tuple[int, ...]           # which axes this grip drives (subset of {0,1,2})


def grip_specs(lo: np.ndarray, hi: np.ndarray) -> list[GripSpec]:
    """All non-degenerate Scale handles on the AABB [lo, hi].

    A handle sits at one of {lo, mid, hi} per axis. The axes it *drives* are
    those where it is at lo or hi (not mid). Corner = 3 driven axes, edge = 2,
    face = 1. Handles that coincide because an axis has zero extent are
    de-duplicated, so a flat selection yields the planar 8-grip set.
    """
    lo = np.asarray(lo, dtype=np.float32)
    hi = np.asarray(hi, dtype=np.float32)
    mid = (lo + hi) * 0.5
    # Per-axis candidate coordinate index: 0=lo, 1=mid, 2=hi.
    coord = (lo, mid, hi)
    out: dict[tuple, GripSpec] = {}
    for ix in (0, 1, 2):
        for iy in (0, 1, 2):
            for iz in (0, 1, 2):
                if ix == 1 and iy == 1 and iz == 1:
                    continue  # centre is not a handle
                idx = (ix, iy, iz)
                pos = np.array([coord[ix][0], coord[iy][1], coord[iz][2]], dtype=np.float32)
                # Driven axes: those not at mid.
                axes = tuple(ax for ax, i in zip((0, 1, 2), idx) if i != 1)
                if not axes:
                    continue
                # Opposite: reflect each driven axis (0<->2), keep mid axes.
                opp_idx = tuple((2 - i) if i != 1 else 1 for i in idx)
                opp = np.array(
                    [coord[opp_idx[0]][0], coord[opp_idx[1]][1], coord[opp_idx[2]][2]],
                    dtype=np.float32,
                )
                key = tuple(np.round(pos, 5))
                if key not in out:
                    out[key] = GripSpec(position=pos, opposite=opp, axes=axes)
    return list(out.values())
```

> **Note on the planar case:** when an axis has zero extent, `lo == mid == hi` on that axis, so handles differing only in that axis collapse to one `key` and the dict de-dups them — leaving the 8 planar grips. The `axes` of a kept grip still include the degenerate axis index, but `selection_aabb` extent there is 0, so the Scale tool will treat a zero-extent driven axis as factor 1 (Task 9).

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_transform_support.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/transform_support.py tests/test_transform_support.py
git commit -m "feat(tools): selection→vertex-set, AABB, and scale-grip helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `TransformVerticesCommand`

**Files:**
- Modify: `python/pluton/commands/scene_commands.py` (append a class)
- Test: `tests/test_transform_command.py`

- [ ] **Step 1: Write the failing test** — `tests/test_transform_command.py`:

```python
"""TransformVerticesCommand do/undo/redo round-trip."""

from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.scene.scene import Scene


def _two_verts(s: Scene):
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([1, 0, 0], np.float32))
    return a, b


def test_do_moves_and_undo_restores():
    s = Scene()
    a, b = _two_verts(s)
    moves = {
        a: (np.array([0, 0, 0], np.float32), np.array([0, 0, 5], np.float32)),
        b: (np.array([1, 0, 0], np.float32), np.array([1, 0, 5], np.float32)),
    }
    cmd = TransformVerticesCommand(moves)
    cmd.do(s)
    assert np.allclose(s.vertex(a).position, [0, 0, 5])
    assert np.allclose(s.vertex(b).position, [1, 0, 5])
    cmd.undo(s)
    assert np.allclose(s.vertex(a).position, [0, 0, 0])
    assert np.allclose(s.vertex(b).position, [1, 0, 0])


def test_redo_via_stack():
    s = Scene()
    a, _b = _two_verts(s)
    stack = CommandStack()
    cmd = TransformVerticesCommand(
        {a: (np.array([0, 0, 0], np.float32), np.array([9, 0, 0], np.float32))}
    )
    stack.execute(cmd, s)
    assert np.allclose(s.vertex(a).position, [9, 0, 0])
    stack.undo(s)
    assert np.allclose(s.vertex(a).position, [0, 0, 0])
    stack.redo(s)
    assert np.allclose(s.vertex(a).position, [9, 0, 0])


def test_noop_moves_are_dropped():
    a_old = np.array([1, 2, 3], np.float32)
    cmd = TransformVerticesCommand({7: (a_old, a_old.copy())})
    assert cmd.is_empty()
```

- [ ] **Step 2: Run; confirm FAIL** — `ImportError: cannot import name 'TransformVerticesCommand'`.

- [ ] **Step 3: Implement** — append to `python/pluton/commands/scene_commands.py`:

```python
class TransformVerticesCommand(Command):
    """Move a set of vertices to new positions; undo restores the old ones.

    `moves` maps vertex_id -> (old_xyz, new_xyz). No-op entries (old == new)
    are dropped at construction. Topology is unchanged, so do() and undo() are
    both just absolute position writes — id-preserving and re-entrant.
    """

    name = "Transform"

    def __init__(self, moves: dict) -> None:
        self._moves: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for vid, (old, new) in moves.items():
            o = np.asarray(old, dtype=np.float32).reshape(3).copy()
            n = np.asarray(new, dtype=np.float32).reshape(3).copy()
            if not np.array_equal(o, n):
                self._moves[int(vid)] = (o, n)

    def is_empty(self) -> bool:
        return not self._moves

    def do(self, scene) -> None:  # noqa: ANN001
        for vid, (_old, new) in self._moves.items():
            scene.set_vertex_position(vid, new)

    def undo(self, scene) -> None:  # noqa: ANN001
        for vid, (old, _new) in self._moves.items():
            scene.set_vertex_position(vid, old)
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_transform_command.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_transform_command.py
git commit -m "feat(commands): TransformVerticesCommand (id-preserving move/undo)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Generic overlay primitives + renderer draw paths

**Files:**
- Modify: `python/pluton/tools/tool.py` (two `ToolOverlay` fields)
- Modify: `python/pluton/viewport/scene_renderer.py` (two draw methods + `render` wiring)
- Test: `tests/test_overlay_primitives.py`

- [ ] **Step 1: Write the failing test** — `tests/test_overlay_primitives.py` (pure-data test of the dataclass + renderer helpers; no GL context needed because we test the geometry helpers, not the GL calls):

```python
"""ToolOverlay generic-primitive fields + renderer screen projection helper."""

from __future__ import annotations

import numpy as np

from pluton.tools.tool import ToolOverlay
from pluton.viewport.scene_renderer import _screen_marker_ndc_quad


def _empty_overlay(**kw) -> ToolOverlay:
    base = dict(
        rubber_band_segments=np.zeros((0, 3), np.float32),
        rubber_band_color=(1, 1, 1),
        snap_marker_position=None,
        snap_marker_color=(1, 1, 1),
    )
    base.update(kw)
    return ToolOverlay(**base)


def test_overlay_defaults_empty_primitives():
    ov = _empty_overlay()
    assert ov.world_polylines == []
    assert ov.screen_markers == []


def test_overlay_carries_primitives():
    seg = np.zeros((2, 3), np.float32)
    ov = _empty_overlay(
        world_polylines=[(seg, (1, 0, 0), 2.0)],
        screen_markers=[(np.zeros(3, np.float32), 8.0, (0, 1, 0))],
    )
    assert len(ov.world_polylines) == 1
    assert len(ov.screen_markers) == 1


def test_screen_marker_ndc_quad_centers_on_pixel():
    # A 10px square centred at pixel (50, 50) in a 100x100 viewport →
    # NDC centre (0, 0), corners at ±0.1 in x and y.
    quad = _screen_marker_ndc_quad(50.0, 50.0, 10.0, 100, 100)
    assert quad.shape == (4, 2)
    cx = float(quad[:, 0].mean())
    cy = float(quad[:, 1].mean())
    assert abs(cx) < 1e-6 and abs(cy) < 1e-6
    assert np.isclose(quad[:, 0].max() - quad[:, 0].min(), 0.1, atol=1e-6)
```

- [ ] **Step 2: Run; confirm FAIL** — `TypeError: ToolOverlay … unexpected keyword 'world_polylines'` / `ImportError: _screen_marker_ndc_quad`.

- [ ] **Step 3a: Extend `ToolOverlay`** — in `python/pluton/tools/tool.py`, add after the `box_rect`/`box_rect_color` fields:

```python
    # M4c: generic gizmo primitives (transform tools).
    # world_polylines: list of (segments (2*N, 3) float32, rgb, width) drawn in
    # world space via the line shader. screen_markers: list of (world_pos (3,),
    # size_px, rgb) drawn as screen-space outlined squares (scale grips).
    world_polylines: list = field(default_factory=list)
    screen_markers: list = field(default_factory=list)
```

- [ ] **Step 3b: Renderer helper + draw methods** — in `python/pluton/viewport/scene_renderer.py`:

Add a module-level pure helper (near the other geometry helpers, e.g. next to `_box_rect_ndc_segments`):

```python
def _screen_marker_ndc_quad(sx: float, sy: float, size_px: float, width: int, height: int) -> np.ndarray:
    """4 corner NDC points of a `size_px` square centred at pixel (sx, sy)."""
    w = max(int(width), 1)
    h = max(int(height), 1)
    half = size_px * 0.5
    corners_px = [
        (sx - half, sy - half),
        (sx + half, sy - half),
        (sx + half, sy + half),
        (sx - half, sy + half),
    ]
    out = np.empty((4, 2), dtype=np.float32)
    for i, (px, py) in enumerate(corners_px):
        out[i, 0] = (2.0 * px / w) - 1.0
        out[i, 1] = 1.0 - (2.0 * py / h)
    return out
```

Add two methods on the renderer class (next to `_draw_box_rect`). They reuse the existing line shader; **restore GL line width to 1.0 afterwards** (the M4b lesson):

```python
    def _draw_world_polylines(self, polylines, view, projection) -> None:  # noqa: ANN001
        """Draw each (segments, color, width) as world-space line segments."""
        for segs, color, width in polylines:
            arr = np.asarray(segs, dtype=np.float32).reshape(-1, 3)
            if arr.shape[0] >= 2:
                self._draw_world_segments(arr, color, float(width), view, projection)

    def _draw_screen_markers(self, camera, markers, width, height) -> None:  # noqa: ANN001
        """Project each (world_pos, size_px, color) and draw an outlined square
        in screen space (identity matrices), like the box-select rectangle."""
        if not markers:
            return
        identity = np.eye(4, dtype=np.float32)
        glUseProgram(self._line_program)
        glUniformMatrix4fv(self._line_view_loc, 1, GL_FALSE, identity)
        glUniformMatrix4fv(self._line_proj_loc, 1, GL_FALSE, identity)
        glDisable(GL_DEPTH_TEST)
        prev_lw = glGetFloatv(GL_LINE_WIDTH)
        glLineWidth(2.0)
        for world_pos, size_px, color in markers:
            proj = camera.world_to_screen(world_pos, width, height)
            if proj is None:
                continue
            sx, sy, _depth = proj
            quad = _screen_marker_ndc_quad(sx, sy, size_px, width, height)
            # Build a closed line loop (4 edges) as (2*N, 3) at z=0.
            loop = np.zeros((8, 3), dtype=np.float32)
            for i in range(4):
                loop[2 * i, 0:2] = quad[i]
                loop[2 * i + 1, 0:2] = quad[(i + 1) % 4]
            self._upload_and_draw_lines(loop, color)
        glLineWidth(prev_lw)
        glEnable(GL_DEPTH_TEST)
```

> **Implementer note:** match the *exact* line-shader uniform names / VBO upload helper already used by `_draw_box_rect` (e.g. it may already have a private `_upload_and_draw_lines` or it inlines the VBO bind). If `_draw_box_rect` inlines the draw, factor that inline body into `_upload_and_draw_lines(points_2n3, color)` and call it from both — DRY. Do not invent new uniform names; read `_draw_box_rect` and mirror it.

Wire both into `render()` inside the tool-overlay step (after the existing `box_rect` draw), guarded on `tool_overlay is not None`:

```python
            if tool_overlay is not None:
                # … existing rubber-band / snap-marker / face-fill / box_rect …
                if getattr(tool_overlay, "world_polylines", None):
                    self._draw_world_polylines(tool_overlay.world_polylines, view, projection)
                if getattr(tool_overlay, "screen_markers", None):
                    self._draw_screen_markers(camera, tool_overlay.screen_markers,
                                              self._viewport_w, self._viewport_h)
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_overlay_primitives.py -q` → PASS. Then a quick import-smoke of the renderer: `.venv\Scripts\python.exe -c "import pluton.viewport.scene_renderer"` → no error.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tool.py python/pluton/viewport/scene_renderer.py tests/test_overlay_primitives.py
git commit -m "feat(viewport): generic gizmo overlay primitives (world polylines + screen markers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `MoveTool` (M)

Point-to-point translation. Press snaps the grab point + captures the selection's vertices and their original positions; drag computes `delta` (axis-lock comes free from the snap engine, which the viewport calls with `anchor_or_none` = the grab point); release commits one `TransformVerticesCommand`. Preview is overlay-only (ghosted selection + drag vector); nothing mutates the mesh until release, so Esc/deactivate just resets.

**Files:**
- Create: `python/pluton/tools/move_tool.py`
- Test: `tests/test_move_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_move_tool.py`:

```python
"""MoveTool gesture: press → drag → release commits a translate."""

from __future__ import annotations

import types

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.selection import Selection
from pluton.tools.move_tool import MoveTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


def _press(x=0.0, y=0.0):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _release(x=0.0, y=0.0):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(pos, kind=SnapKind.ENDPOINT):
    return types.SimpleNamespace(
        kind=kind, world_position=np.asarray(pos, np.float32),
        axis=None, vertex_id=None, edge_id=None, edge_t=None,
    )


def _square(s: Scene):
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([2, 0, 0], np.float32))
    c = s.add_vertex(np.array([2, 2, 0], np.float32))
    d = s.add_vertex(np.array([0, 2, 0], np.float32))
    f = s.add_face_from_loop([a, b, c, d])
    return a, b, c, d, f


def _ctx(scene, stack, selection):
    return ToolContext(scene=scene, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), selection=selection)


def test_move_translates_selection(qtbot):
    s = Scene()
    a, b, c, d, f = _square(s)
    sel = Selection(); sel.replace(faces=[f])
    stack = CommandStack()
    tool = MoveTool(); tool.activate(_ctx(s, stack, sel))
    # grab at corner a (0,0,0), drop at (0,0,3) → delta (0,0,3)
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))
    tool.on_mouse_move(_press(), _snap([0, 0, 3]))   # button-held move
    tool.on_mouse_release(_release(), _snap([0, 0, 3]))
    for vid, base in ((a, [0, 0, 0]), (b, [2, 0, 0]), (c, [2, 2, 0]), (d, [0, 2, 0])):
        assert np.allclose(s.vertex(vid).position, np.array(base) + [0, 0, 3])
    assert stack.can_undo
    stack.undo(s)
    assert np.allclose(s.vertex(a).position, [0, 0, 0])


def test_move_noop_on_empty_selection(qtbot):
    s = Scene(); _square(s)
    sel = Selection()  # empty
    stack = CommandStack()
    tool = MoveTool(); tool.activate(_ctx(s, stack, sel))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))
    tool.on_mouse_release(_release(), _snap([0, 0, 3]))
    assert not stack.can_undo


def test_move_esc_cancels_without_commit(qtbot):
    s = Scene()
    a, b, c, d, f = _square(s)
    sel = Selection(); sel.replace(faces=[f])
    stack = CommandStack()
    tool = MoveTool(); tool.activate(_ctx(s, stack, sel))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))
    tool.on_mouse_move(_press(), _snap([0, 0, 3]))
    tool.deactivate()  # mid-drag bail
    assert not stack.can_undo
    assert np.allclose(s.vertex(a).position, [0, 0, 0])  # mesh untouched
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError: pluton.tools.move_tool`.

- [ ] **Step 3: Implement** — `python/pluton/tools/move_tool.py`:

```python
"""The Move tool (M) — point-to-point translation of the selection.

Press snaps a grab point and captures the selection's vertices + their
original positions. Drag computes delta = destination − grab (axis-lock is
provided by the SnapEngine, which the viewport calls with anchor_or_none =
the grab point). Release commits one TransformVerticesCommand. The mesh is
never mutated until release, so Esc/deactivate simply resets.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.geometry.transforms import translate
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.transform_support import selection_vertices

_NEUTRAL = (0.85, 0.85, 0.85)
_GHOST = (0.30, 0.65, 1.0)


class MoveTool(Tool):
    @property
    def name(self) -> str:
        return "Move"

    @property
    def shortcut(self) -> str:
        return "M"

    def __init__(self) -> None:
        self._scene = None
        self._stack = None
        self._selection = None
        self._dragging = False
        self._grab: np.ndarray | None = None
        self._delta = np.zeros(3, dtype=np.float32)
        self._vertex_ids: list[int] = []
        self._orig: dict[int, np.ndarray] = {}

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._stack = ctx.command_stack
        self._selection = ctx.selection
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._selection is None or self._selection.is_empty():
            return
        if snap.kind == SnapKind.NONE:
            return
        self._vertex_ids = selection_vertices(self._scene, self._selection)
        if not self._vertex_ids:
            return
        self._orig = {v: self._scene.vertex(v).position.copy() for v in self._vertex_ids}
        self._grab = np.asarray(snap.world_position, np.float32).copy()
        self._delta = np.zeros(3, dtype=np.float32)
        self._dragging = True

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if not self._dragging or self._grab is None or snap.kind == SnapKind.NONE:
            return
        self._delta = (np.asarray(snap.world_position, np.float32) - self._grab).astype(np.float32)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        if snap is not None and getattr(snap, "world_position", None) is not None:
            from pluton.viewport.snap_engine import SnapKind
            if snap.kind != SnapKind.NONE and self._grab is not None:
                self._delta = (np.asarray(snap.world_position, np.float32) - self._grab).astype(np.float32)
        moves = {
            v: (self._orig[v], (self._orig[v] + self._delta).astype(np.float32))
            for v in self._vertex_ids
        }
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        polylines: list = []
        segs = np.zeros((0, 3), dtype=np.float32)
        if self._dragging and self._grab is not None and self._scene is not None:
            # Ghost the selection geometry, translated by the live delta.
            ghost = self._ghost_segments()
            if ghost.shape[0] >= 2:
                polylines.append((ghost, _GHOST, 2.0))
            # Drag vector.
            segs = np.array([self._grab, self._grab + self._delta], dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segs,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=(self._grab + self._delta) if self._dragging and self._grab is not None else None,
            snap_marker_color=_GHOST,
            world_polylines=polylines,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._dragging

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        # Feed the SnapEngine the grab point so axis-lock candidates appear.
        return self._grab.copy() if (self._dragging and self._grab is not None) else None

    @property
    def status_text(self) -> str | None:
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._dragging:
            d = self._delta
            return f"Move Δ ({d[0]:.2f}, {d[1]:.2f}, {d[2]:.2f})"
        return "Move: pick a grab point"

    # ---- internal ----
    def _ghost_segments(self) -> np.ndarray:
        """Selection edges + face loops as world segments, translated by delta."""
        s = self._scene
        sel = self._selection
        pts: list[list[float]] = []

        def seg(p0, p1):
            q0 = (np.asarray(p0, np.float32) + self._delta)
            q1 = (np.asarray(p1, np.float32) + self._delta)
            pts.append([float(q0[0]), float(q0[1]), float(q0[2])])
            pts.append([float(q1[0]), float(q1[1]), float(q1[2])])

        for e_id in sel.edges:
            try:
                e = s.edge(e_id)
            except KeyError:
                continue
            seg(s.vertex(e.v1_id).position, s.vertex(e.v2_id).position)
        for f_id in sel.faces:
            try:
                loop = s.face_loop(f_id)
            except KeyError:
                continue
            n = len(loop)
            for i in range(n):
                seg(s.vertex(loop[i]).position, s.vertex(loop[(i + 1) % n]).position)
        return np.array(pts, dtype=np.float32) if pts else np.zeros((0, 3), np.float32)

    def _reset(self) -> None:
        self._dragging = False
        self._grab = None
        self._delta = np.zeros(3, dtype=np.float32)
        self._vertex_ids = []
        self._orig = {}
```

> **Note:** `translate` is imported for parity with the other tools but `MoveTool` adds `delta` directly; keep the import only if used, else drop it to satisfy ruff (F401). Simplest: build `moves` with `translate(self._orig[v].reshape(1,3), self._delta)[0]` instead of `self._orig[v] + self._delta`, which uses the import and routes through the shared math. Prefer that for DRY.

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_move_tool.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/move_tool.py tests/test_move_tool.py
git commit -m "feat(tools): MoveTool (M) — point-to-point translate of the selection

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `RotateTool` (Q)

Three clicks: center → start direction → angle. The protractor plane comes from the face under the cursor when the center is placed (`scene.ray_pick_face` → `scene.face_normal`), else the ground plane (+Z). Up/Down arrows cycle a forced rotation axis (X→Y→Z→auto) that overrides the inferred plane normal. Angle snaps to 15°. Commit once on the third click.

**Files:**
- Create: `python/pluton/tools/rotate_tool.py`
- Test: `tests/test_rotate_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_rotate_tool.py` (drive the state machine with fake snaps; the plane normal is injected by stubbing `_pick_plane_normal` so the test needs no camera):

```python
"""RotateTool: 3-click flow, 15° snap, plane/axis selection."""

from __future__ import annotations

import math
import types

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.selection import Selection
from pluton.tools.rotate_tool import RotateTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(pos, kind=SnapKind.ENDPOINT):
    return types.SimpleNamespace(
        kind=kind, world_position=np.asarray(pos, np.float32),
        axis=None, vertex_id=None, edge_id=None, edge_t=None,
    )


def _line(s: Scene):
    a = s.add_vertex(np.array([1, 0, 0], np.float32))
    b = s.add_vertex(np.array([2, 0, 0], np.float32))
    e = s.add_edge(a, b)
    return a, b, e


def _ctx(s, stack, sel):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), selection=sel)


def test_rotate_90_about_z(qtbot, monkeypatch):
    s = Scene()
    a, b, e = _line(s)
    sel = Selection(); sel.replace(edges=[e])
    stack = CommandStack()
    tool = RotateTool(); tool.activate(_ctx(s, stack, sel))
    # Force the rotation plane normal to +Z regardless of camera.
    monkeypatch.setattr(tool, "_pick_plane_normal", lambda ev: np.array([0, 0, 1], np.float32))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))      # center at origin
    tool.on_mouse_press(_press(), _snap([1, 0, 0]))      # start dir = +X
    tool.on_mouse_press(_press(), _snap([0, 1, 0]))      # end dir = +Y → +90°
    # a=(1,0,0)→(0,1,0), b=(2,0,0)→(0,2,0)
    assert np.allclose(s.vertex(a).position, [0, 1, 0], atol=1e-4)
    assert np.allclose(s.vertex(b).position, [0, 2, 0], atol=1e-4)
    assert stack.can_undo


def test_rotate_snaps_to_15_degrees(qtbot, monkeypatch):
    s = Scene()
    a, b, e = _line(s)
    sel = Selection(); sel.replace(edges=[e])
    tool = RotateTool(); tool.activate(_ctx(s, CommandStack(), sel))
    monkeypatch.setattr(tool, "_pick_plane_normal", lambda ev: np.array([0, 0, 1], np.float32))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))
    tool.on_mouse_press(_press(), _snap([1, 0, 0]))
    # End direction at ~20° → snaps to 15°.
    ang = math.radians(20)
    tool.on_mouse_press(_press(), _snap([math.cos(ang), math.sin(ang), 0]))
    # a at radius 1 → expected at exactly 15°.
    exp = np.array([math.cos(math.radians(15)), math.sin(math.radians(15)), 0], np.float32)
    assert np.allclose(s.vertex(a).position, exp, atol=1e-4)


def test_rotate_esc_resets(qtbot, monkeypatch):
    s = Scene()
    a, b, e = _line(s)
    sel = Selection(); sel.replace(edges=[e])
    stack = CommandStack()
    tool = RotateTool(); tool.activate(_ctx(s, stack, sel))
    monkeypatch.setattr(tool, "_pick_plane_normal", lambda ev: np.array([0, 0, 1], np.float32))
    tool.on_mouse_press(_press(), _snap([0, 0, 0]))
    tool.on_mouse_press(_press(), _snap([1, 0, 0]))
    from PySide6.QtGui import QKeyEvent
    tool.on_key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not tool.has_active_gesture
    assert not stack.can_undo
    assert np.allclose(s.vertex(a).position, [1, 0, 0])
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — `python/pluton/tools/rotate_tool.py`:

```python
"""The Rotate tool (Q) — auto-tilt protractor.

Three clicks: center → start direction → angle. The protractor plane is the
plane of the face under the cursor when the center is placed (else the ground
plane). Up/Down arrows cycle a forced axis (X/Y/Z/auto) overriding the inferred
normal. The swept angle snaps to 15°. One TransformVerticesCommand on commit.
"""

from __future__ import annotations

import math
from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.geometry.transforms import rotate
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.transform_support import selection_vertices

_ANGLE_SNAP_RAD = math.radians(15.0)
_DISK_COLOR_RGBA = (0.30, 0.55, 0.95, 0.18)
_DISK_OUTLINE = (0.30, 0.55, 0.95)
_RAY_COLOR = (0.95, 0.80, 0.20)
_AXES = (np.array([1, 0, 0], np.float32),
         np.array([0, 1, 0], np.float32),
         np.array([0, 0, 1], np.float32))


class _Stage(Enum):
    IDLE = 0
    HAVE_CENTER = 1
    HAVE_START = 2


class RotateTool(Tool):
    @property
    def name(self) -> str:
        return "Rotate"

    @property
    def shortcut(self) -> str:
        return "Q"

    def __init__(self) -> None:
        self._scene = None
        self._stack = None
        self._selection = None
        self._camera = None
        self._size_provider = None
        self._stage = _Stage.IDLE
        self._center = np.zeros(3, np.float32)
        self._normal = np.array([0, 0, 1], np.float32)
        self._start_dir = np.array([1, 0, 0], np.float32)
        self._cur_dir = np.array([1, 0, 0], np.float32)
        self._forced_axis: int | None = None
        self._vertex_ids: list[int] = []
        self._orig: dict[int, np.ndarray] = {}

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._stack = ctx.command_stack
        self._selection = ctx.selection
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._selection is None or self._selection.is_empty() or snap.kind == SnapKind.NONE:
            return
        p = np.asarray(snap.world_position, np.float32)

        if self._stage == _Stage.IDLE:
            self._vertex_ids = selection_vertices(self._scene, self._selection)
            if not self._vertex_ids:
                return
            self._orig = {v: self._scene.vertex(v).position.copy() for v in self._vertex_ids}
            self._center = p.copy()
            self._normal = self._effective_normal(self._pick_plane_normal(event))
            self._stage = _Stage.HAVE_CENTER
            return

        if self._stage == _Stage.HAVE_CENTER:
            d = self._project_to_plane(p - self._center)
            if float(np.linalg.norm(d)) < 1e-6:
                return
            self._start_dir = d / np.linalg.norm(d)
            self._cur_dir = self._start_dir.copy()
            self._stage = _Stage.HAVE_START
            return

        # HAVE_START → commit.
        angle = self._swept_angle(p)
        moves = self._compute_moves(angle)
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if self._stage != _Stage.HAVE_START or snap.kind == SnapKind.NONE:
            return
        d = self._project_to_plane(np.asarray(snap.world_position, np.float32) - self._center)
        if float(np.linalg.norm(d)) >= 1e-6:
            self._cur_dir = d / np.linalg.norm(d)

    def on_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._reset()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Cycle forced axis: None → X → Y → Z → None.
            order = [None, 0, 1, 2]
            cur = order.index(self._forced_axis)
            self._forced_axis = order[(cur + 1) % len(order)]
            if self._stage != _Stage.IDLE:
                self._normal = self._effective_normal(self._normal)

    def overlay(self) -> ToolOverlay:
        fills: list = []
        polylines: list = []
        if self._stage in (_Stage.HAVE_CENTER, _Stage.HAVE_START):
            disk = self._disk_loop(radius=self._disk_radius())
            fills.append(disk)
            polylines.append((self._loop_to_segments(disk), _DISK_OUTLINE, 1.5))
            if self._stage == _Stage.HAVE_START:
                r = self._disk_radius()
                polylines.append((np.array([self._center, self._center + self._start_dir * r], np.float32), _DISK_OUTLINE, 1.5))
                polylines.append((np.array([self._center, self._center + self._cur_dir * r], np.float32), _RAY_COLOR, 2.0))
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), np.float32),
            rubber_band_color=(1, 1, 1),
            snap_marker_position=None,
            snap_marker_color=(1, 1, 1),
            face_fill_polygons=fills,
            face_fill_color=_DISK_COLOR_RGBA,
            world_polylines=polylines,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._stage != _Stage.IDLE

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return self._center.copy() if self._stage != _Stage.IDLE else None

    @property
    def status_text(self) -> str | None:
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._stage == _Stage.IDLE:
            return "Rotate: click the center"
        if self._stage == _Stage.HAVE_CENTER:
            return "Rotate: click the start direction"
        return f"Rotate: {math.degrees(self._swept_angle_from_cur()):.0f}° (15° snap)"

    # ---- internal ----
    def _pick_plane_normal(self, event) -> np.ndarray:  # noqa: ANN001
        """Normal of the face under the cursor, or +Z (ground) if none/no camera."""
        if self._camera is None or self._size_provider is None or self._scene is None:
            return np.array([0, 0, 1], np.float32)
        w, h = self._size_provider()
        pos = event.position()
        origin, direction = self._camera.ray_from_screen(pos.x(), pos.y(), w, h)
        hit = self._scene.ray_pick_face(origin, direction)
        if hit is None:
            return np.array([0, 0, 1], np.float32)
        try:
            return np.asarray(self._scene.face_normal(hit.face_id), np.float32)
        except (KeyError, ValueError):
            return np.array([0, 0, 1], np.float32)

    def _effective_normal(self, inferred: np.ndarray) -> np.ndarray:
        if self._forced_axis is not None:
            return _AXES[self._forced_axis].copy()
        n = np.asarray(inferred, np.float32)
        ln = float(np.linalg.norm(n))
        return (n / ln).astype(np.float32) if ln > 1e-9 else np.array([0, 0, 1], np.float32)

    def _project_to_plane(self, v: np.ndarray) -> np.ndarray:
        n = self._normal
        return (v - n * float(np.dot(v, n))).astype(np.float32)

    def _swept_angle(self, world_point: np.ndarray) -> float:
        d = self._project_to_plane(np.asarray(world_point, np.float32) - self._center)
        if float(np.linalg.norm(d)) < 1e-9:
            return 0.0
        self._cur_dir = d / np.linalg.norm(d)
        return self._swept_angle_from_cur()

    def _swept_angle_from_cur(self) -> float:
        s, c, n = self._start_dir, self._cur_dir, self._normal
        ang = math.atan2(float(np.dot(np.cross(s, c), n)), float(np.dot(s, c)))
        # Snap to 15°.
        return round(ang / _ANGLE_SNAP_RAD) * _ANGLE_SNAP_RAD

    def _compute_moves(self, angle: float) -> dict:
        ids = self._vertex_ids
        pts = np.array([self._orig[v] for v in ids], np.float32)
        new = rotate(pts, self._center, self._normal, angle)
        return {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}

    def _disk_radius(self) -> float:
        if not self._orig:
            return 1.0
        pts = np.array(list(self._orig.values()), np.float32)
        r = float(np.max(np.linalg.norm(pts - self._center, axis=1)))
        return max(r, 0.5)

    def _disk_loop(self, radius: float, segments: int = 48) -> np.ndarray:
        # Orthonormal basis (u, v) spanning the plane.
        n = self._normal
        ref = np.array([1, 0, 0], np.float32) if abs(n[0]) < 0.9 else np.array([0, 1, 0], np.float32)
        u = np.cross(n, ref); u = u / (np.linalg.norm(u) + 1e-12)
        v = np.cross(n, u)
        loop = np.empty((segments, 3), np.float32)
        for i in range(segments):
            t = 2 * math.pi * i / segments
            loop[i] = self._center + radius * (math.cos(t) * u + math.sin(t) * v)
        return loop

    @staticmethod
    def _loop_to_segments(loop: np.ndarray) -> np.ndarray:
        n = loop.shape[0]
        segs = np.empty((2 * n, 3), np.float32)
        for i in range(n):
            segs[2 * i] = loop[i]
            segs[2 * i + 1] = loop[(i + 1) % n]
        return segs

    def _reset(self) -> None:
        self._stage = _Stage.IDLE
        self._center = np.zeros(3, np.float32)
        self._normal = np.array([0, 0, 1], np.float32)
        self._start_dir = np.array([1, 0, 0], np.float32)
        self._cur_dir = np.array([1, 0, 0], np.float32)
        self._forced_axis = None
        self._vertex_ids = []
        self._orig = {}
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_rotate_tool.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/rotate_tool.py tests/test_rotate_tool.py
git commit -m "feat(tools): RotateTool (Q) — auto-tilt protractor with 15° snap

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `ScaleTool` (S)

Bounding-box gizmo. On activate (with a selection) compute the AABB + grips. Press picks the nearest grip in screen space (anchor = its opposite); drag computes per-axis factors; release commits. Ctrl = scale about the AABB center; Shift = uniform across the grip's driven axes. Zero-extent driven axes stay factor 1. Preview is overlay-only.

**Files:**
- Create: `python/pluton/tools/scale_tool.py`
- Test: `tests/test_scale_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_scale_tool.py` (test the factor math + grip/anchor selection directly; these need no camera. A `_pick_grip` stub drives the gesture test):

```python
"""ScaleTool factor math + grip selection + commit."""

from __future__ import annotations

import numpy as np

from pluton.scene.scene import Scene
from pluton.selection import Selection
from pluton.tools.scale_tool import ScaleTool
from pluton.tools.tool import ToolContext
from pluton.tools.transform_support import GripSpec
from pluton.commands.command_stack import CommandStack


def _square(s: Scene):
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([2, 0, 0], np.float32))
    c = s.add_vertex(np.array([2, 2, 0], np.float32))
    d = s.add_vertex(np.array([0, 2, 0], np.float32))
    f = s.add_face_from_loop([a, b, c, d])
    return a, b, c, d, f


def _ctx(s, stack, sel):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), selection=sel)


def test_face_grip_single_axis_factor():
    tool = ScaleTool()
    # Face grip on +X face of a 2-wide box anchored at x=0; cursor at x=4 → 2x on X only.
    grip = GripSpec(position=np.array([2, 1, 0], np.float32),
                    opposite=np.array([0, 1, 0], np.float32), axes=(0,))
    extent = np.array([2, 2, 0], np.float32)
    f = tool._factors(grip, anchor=grip.opposite, cursor=np.array([4, 1, 0], np.float32),
                      extent=extent, uniform=False)
    assert np.allclose(f, [2, 1, 1])


def test_corner_grip_uniform_factor():
    tool = ScaleTool()
    # Corner at (2,2,0), anchor (0,0,0); cursor at (4,4,0) → diagonal doubled → 2x uniform on X,Y.
    grip = GripSpec(position=np.array([2, 2, 0], np.float32),
                    opposite=np.array([0, 0, 0], np.float32), axes=(0, 1))
    extent = np.array([2, 2, 0], np.float32)
    f = tool._factors(grip, anchor=grip.opposite, cursor=np.array([4, 4, 0], np.float32),
                      extent=extent, uniform=False)
    assert np.allclose(f, [2, 2, 1])


def test_zero_extent_axis_stays_unit():
    tool = ScaleTool()
    grip = GripSpec(position=np.array([2, 2, 0], np.float32),
                    opposite=np.array([0, 0, 0], np.float32), axes=(0, 1, 2))
    extent = np.array([2, 2, 0], np.float32)  # z extent 0
    f = tool._factors(grip, anchor=grip.opposite, cursor=np.array([4, 4, 5], np.float32),
                      extent=extent, uniform=False)
    assert f[2] == 1.0


def test_factor_epsilon_clamp_no_mirror():
    tool = ScaleTool()
    grip = GripSpec(position=np.array([2, 1, 0], np.float32),
                    opposite=np.array([0, 1, 0], np.float32), axes=(0,))
    extent = np.array([2, 2, 0], np.float32)
    # Cursor dragged to the anchor side (x=-1) would be negative → clamped > 0.
    f = tool._factors(grip, anchor=grip.opposite, cursor=np.array([-1, 1, 0], np.float32),
                      extent=extent, uniform=False)
    assert f[0] > 0.0


def test_scale_commit_applies_to_selection(qtbot, monkeypatch):
    s = Scene()
    a, b, c, d, f = _square(s)
    sel = Selection(); sel.replace(faces=[f])
    stack = CommandStack()
    tool = ScaleTool(); tool.activate(_ctx(s, stack, sel))
    # Stub grip picking: the +X/+Y corner, anchored at origin.
    grip = GripSpec(position=np.array([2, 2, 0], np.float32),
                    opposite=np.array([0, 0, 0], np.float32), axes=(0, 1))
    monkeypatch.setattr(tool, "_pick_grip", lambda ev: grip)
    monkeypatch.setattr(tool, "_cursor_world", lambda ev: np.array([4, 4, 0], np.float32))
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    rel = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                      Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                      Qt.KeyboardModifier.NoModifier)
    tool.on_mouse_press(press, None)
    tool.on_mouse_release(rel, None)
    # corner doubled about origin → (2,2,0)→(4,4,0), (2,0,0)→(4,0,0)
    assert np.allclose(s.vertex(c).position, [4, 4, 0])
    assert np.allclose(s.vertex(b).position, [4, 0, 0])
    assert stack.can_undo
```

- [ ] **Step 2: Run; confirm FAIL** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — `python/pluton/tools/scale_tool.py`:

```python
"""The Scale tool (S) — bounding-box gizmo.

On activate the selection's AABB + grips are computed. Press picks the nearest
grip (screen space); its opposite is the anchor (Ctrl → AABB centre). Drag
computes per-axis factors (corner = uniform along the diagonal; edge/face =
per-axis; Shift = uniform across driven axes). Zero-extent driven axes stay 1.
Release commits one TransformVerticesCommand. Preview is overlay-only.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.scene_commands import TransformVerticesCommand
from pluton.geometry.transforms import scale as scale_pts
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.transform_support import (
    GripSpec,
    grip_specs,
    selection_aabb,
    selection_vertices,
)

_GRIP_PX = 9.0
_GRIP_COLOR = (0.20, 0.75, 0.35)
_ACTIVE_COLOR = (1.0, 0.85, 0.10)
_BOX_COLOR = (0.20, 0.55, 0.95)
_EPS = 1e-3


class ScaleTool(Tool):
    @property
    def name(self) -> str:
        return "Scale"

    @property
    def shortcut(self) -> str:
        return "S"

    def __init__(self) -> None:
        self._scene = None
        self._stack = None
        self._selection = None
        self._camera = None
        self._size_provider = None
        self._lo = None
        self._hi = None
        self._grips: list[GripSpec] = []
        self._vertex_ids: list[int] = []
        self._orig: dict[int, np.ndarray] = {}
        self._active: GripSpec | None = None
        self._anchor = np.zeros(3, np.float32)
        self._factors = np.ones(3, np.float32)

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._stack = ctx.command_stack
        self._selection = ctx.selection
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._rebuild_box()

    def deactivate(self) -> None:
        self._reset_drag()
        self._lo = self._hi = None
        self._grips = []

    def _rebuild_box(self) -> None:
        self._reset_drag()
        self._vertex_ids = (
            selection_vertices(self._scene, self._selection)
            if self._selection is not None and not self._selection.is_empty()
            else []
        )
        box = selection_aabb(self._scene, self._vertex_ids)
        if box is None:
            self._lo = self._hi = None
            self._grips = []
            return
        self._lo, self._hi = box
        self._grips = grip_specs(self._lo, self._hi)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or not self._grips:
            return
        grip = self._pick_grip(event)
        if grip is None:
            return
        self._orig = {v: self._scene.vertex(v).position.copy() for v in self._vertex_ids}
        self._active = grip
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._anchor = (
            ((self._lo + self._hi) * 0.5).astype(np.float32) if ctrl else grip.opposite.copy()
        )
        self._factors = np.ones(3, np.float32)

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._active is None:
            return
        cursor = self._cursor_world(event)
        if cursor is None:
            return
        uniform = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        extent = (self._hi - self._lo).astype(np.float32)
        self._factors = self._factors_for(self._active, self._anchor, cursor, extent, uniform)

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton or self._active is None:
            return
        cursor = self._cursor_world(event)
        if cursor is not None:
            uniform = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            extent = (self._hi - self._lo).astype(np.float32)
            self._factors = self._factors_for(self._active, self._anchor, cursor, extent, uniform)
        ids = self._vertex_ids
        pts = np.array([self._orig[v] for v in ids], np.float32)
        new = scale_pts(pts, self._anchor, self._factors)
        moves = {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset_drag()
        self._rebuild_box()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_drag()

    def overlay(self) -> ToolOverlay:
        polylines: list = []
        markers: list = []
        if self._lo is not None and self._hi is not None:
            preview_lo, preview_hi = self._lo, self._hi
            if self._active is not None:
                corners = scale_pts(
                    np.array([self._lo, self._hi], np.float32), self._anchor, self._factors
                )
                preview_lo = np.minimum(corners[0], corners[1]).astype(np.float32)
                preview_hi = np.maximum(corners[0], corners[1]).astype(np.float32)
            polylines.append((self._box_segments(preview_lo, preview_hi), _BOX_COLOR, 1.5))
            for g in self._grips:
                color = _ACTIVE_COLOR if (self._active is not None and np.allclose(g.position, self._active.position)) else _GRIP_COLOR
                markers.append((g.position.copy(), _GRIP_PX, color))
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), np.float32),
            rubber_band_color=(1, 1, 1),
            snap_marker_position=None,
            snap_marker_color=(1, 1, 1),
            world_polylines=polylines,
            screen_markers=markers,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._active is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    @property
    def status_text(self) -> str | None:
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._active is not None:
            f = self._factors
            return f"Scale ({f[0]:.2f}, {f[1]:.2f}, {f[2]:.2f})"
        return "Scale: drag a handle"

    # ---- factor math (pure; unit-tested) ----
    def _factors(self, grip, anchor, cursor, extent, uniform):  # noqa: ANN001
        """Public-ish alias kept for tests; delegates to _factors_for."""
        return self._factors_for(grip, anchor, cursor, extent, uniform)

    def _factors_for(self, grip: GripSpec, anchor, cursor, extent, uniform: bool) -> np.ndarray:
        anchor = np.asarray(anchor, np.float32)
        cursor = np.asarray(cursor, np.float32)
        extent = np.asarray(extent, np.float32)
        out = np.ones(3, np.float32)
        driven = [ax for ax in grip.axes if abs(float(extent[ax])) > 1e-9]
        if len(grip.axes) == 3 and len(driven) >= 2:
            # Corner → uniform along the anchor→grip diagonal.
            diag = grip.position - anchor
            dlen = float(np.linalg.norm(diag))
            if dlen > 1e-9:
                proj = float(np.dot(cursor - anchor, diag)) / dlen
                fac = max(proj / dlen, _EPS)
                for ax in driven:
                    out[ax] = fac
            return out
        for ax in driven:
            denom = float(grip.position[ax] - anchor[ax])
            if abs(denom) < 1e-9:
                continue
            out[ax] = max((float(cursor[ax]) - float(anchor[ax])) / denom, _EPS)
        if uniform and driven:
            f = float(np.max([out[ax] for ax in driven]))
            for ax in driven:
                out[ax] = f
        return out

    # ---- screen picking (camera-dependent; stubbed in unit tests) ----
    def _pick_grip(self, event) -> GripSpec | None:  # noqa: ANN001
        if self._camera is None or self._size_provider is None:
            return None
        w, h = self._size_provider()
        pos = event.position()
        best, best_d = None, _GRIP_PX * 1.6
        for g in self._grips:
            proj = self._camera.world_to_screen(g.position, w, h)
            if proj is None:
                continue
            sx, sy, _d = proj
            dist = ((sx - pos.x()) ** 2 + (sy - pos.y()) ** 2) ** 0.5
            if dist < best_d:
                best, best_d = g, dist
        return best

    def _cursor_world(self, event):  # noqa: ANN001
        """Cursor ray ∩ the plane through the anchor parallel to the AABB faces.

        Falls back to the ground plane if no camera. Returns float32 (3,) or None.
        """
        if self._camera is None or self._size_provider is None:
            return None
        w, h = self._size_provider()
        pos = event.position()
        origin, direction = self._camera.ray_from_screen(pos.x(), pos.y(), w, h)
        # Plane: through the active grip, normal = camera forward's dominant axis
        # is overkill; use the ground plane offset to the grip's z for a stable
        # interactive feel. (M4d refines with axis-aware dragging.)
        n = np.array([0, 0, 1], np.float32)
        p0 = self._active.position if self._active is not None else self._anchor
        denom = float(np.dot(direction, n))
        if abs(denom) < 1e-9:
            return None
        t = float(np.dot(p0 - origin, n)) / denom
        if t <= 0:
            return None
        return (origin + t * direction).astype(np.float32)

    def _box_segments(self, lo, hi) -> np.ndarray:
        lo = np.asarray(lo, np.float32); hi = np.asarray(hi, np.float32)
        c = [
            [lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
            [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]],
        ]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        segs = np.empty((2 * len(edges), 3), np.float32)
        for i, (u, v) in enumerate(edges):
            segs[2 * i] = c[u]
            segs[2 * i + 1] = c[v]
        return segs

    def _reset_drag(self) -> None:
        self._active = None
        self._anchor = np.zeros(3, np.float32)
        self._factors = np.ones(3, np.float32)
        self._orig = {}
```

> **Implementer note:** the tests call `tool._factors(...)` — keep that thin alias. The `_cursor_world` ground-plane projection is a deliberately simple v1 (the spec notes axis-aware dragging is an M4d refinement); do not over-engineer it. If ruff flags the unused `snap` params, keep them (they're part of the Tool signature).

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_scale_tool.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/scale_tool.py tests/test_scale_tool.py
git commit -m "feat(tools): ScaleTool (S) — bounding-box gizmo (corner/edge/face)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Register tools + M/Q/S shortcuts + exports

**Files:**
- Modify: `python/pluton/tools/__init__.py`
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_transform_tools_registered.py`

- [ ] **Step 1: Write the failing test** — `tests/test_transform_tools_registered.py`:

```python
"""Move/Rotate/Scale are registered and bound to M/Q/S."""

from __future__ import annotations

import pytest
from pluton.tools import MoveTool, RotateTool, ScaleTool


def test_tool_shortcuts():
    assert MoveTool().shortcut == "M"
    assert RotateTool().shortcut == "Q"
    assert ScaleTool().shortcut == "S"
    assert MoveTool().name == "Move"
    assert RotateTool().name == "Rotate"
    assert ScaleTool().name == "Scale"


def test_main_window_registers_transform_tools(qtbot):
    from pluton.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    names = {t.name for t in win._tool_manager._tools.values()} \
        if hasattr(win._tool_manager, "_tools") else None
    # Fall back to activation if internal structure differs.
    assert win._tool_manager.activate_by_shortcut("M")
    assert win._tool_manager.activate_by_shortcut("Q")
    assert win._tool_manager.activate_by_shortcut("S")
```

> If `_tool_manager._tools` isn't a dict, delete the `names` block — the `activate_by_shortcut` assertions are the real check. Read `tool_manager.py` and keep whichever introspection matches.

- [ ] **Step 2: Run; confirm FAIL** — `ImportError: cannot import name 'MoveTool'` (exports missing) and/or shortcut activation returns False.

- [ ] **Step 3a: Export** — in `python/pluton/tools/__init__.py`, add imports + `__all__` entries:

```python
from pluton.tools.move_tool import MoveTool
from pluton.tools.rotate_tool import RotateTool
from pluton.tools.scale_tool import ScaleTool
```
(append `"MoveTool"`, `"RotateTool"`, `"ScaleTool"` to `__all__` if present.)

- [ ] **Step 3b: Register + shortcuts** — in `python/pluton/ui/main_window.py`:

Imports: add `MoveTool, RotateTool, ScaleTool` to the existing tools import.

In the registration block (after `EraserTool()`):
```python
        self._tool_manager.register(MoveTool())
        self._tool_manager.register(RotateTool())
        self._tool_manager.register(ScaleTool())
```

In the shortcuts block (after the `E` shortcut):
```python
        QShortcut(QKeySequence("M"), self, activated=lambda: self._activate("M"))
        QShortcut(QKeySequence("Q"), self, activated=lambda: self._activate("Q"))
        QShortcut(QKeySequence("S"), self, activated=lambda: self._activate("S"))
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_transform_tools_registered.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/__init__.py python/pluton/ui/main_window.py tests/test_transform_tools_registered.py
git commit -m "feat(ui): register Move/Rotate/Scale tools on M/Q/S

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Full regression + manual visual verification

**Files:** none (verification only) — except a short notes file if useful.

- [ ] **Step 1: C++ suite** — `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure` → all green (72 prior + 3 new = 75).

- [ ] **Step 2: Python suite** — `.venv\Scripts\python.exe -m pytest -q` → all green (336 prior + the new transform tests). Note the new total.

- [ ] **Step 3: Lint** — `.venv\Scripts\python.exe -m ruff check python/pluton tests` → clean (fix any F401/unused-arg the new modules introduce).

- [ ] **Step 4: Manual visual verification** — `.venv\Scripts\python.exe -m pluton`. Confirm by eye and report back to the user with what was observed:
  - Draw a rectangle; push/pull to a box; **Select** the top face.
  - **M** → grab a corner, drag along an axis (cursor near the axis line shows axis-lock color); release → box translates; **Ctrl+Z** restores.
  - **Q** → click center on the top face (protractor lies *on* that face), click a start edge, sweep → snaps every 15°; release → selection rotates; undo restores. Press Up to force an axis and confirm the disk reorients.
  - **S** → the green grip box appears around the selection; drag a **corner** (uniform), an **edge** (2-axis), a **face** (1-axis); Ctrl while dragging scales about the center; release → undo restores.
  - Switch tools mid-gesture / press **Esc** mid-gesture → no stray geometry, undo stack clean.
  - The M4b selection highlight, box-select, and Eraser still behave; no flicker / line-width leak in the grid or axes.

- [ ] **Step 5: Commit** (only if a notes file was added; otherwise skip). No code changes expected here.

---

## Task 12: Release v0.1.2 (M4c)

> Only now touch the version files. Follow the M4b release sequence exactly.

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M4c shipped)

- [ ] **Step 1: Bump version to 0.1.2** in all three files:
  - `pyproject.toml`: `version = "0.1.2"`
  - `CMakeLists.txt`: `VERSION 0.1.2`
  - `cpp/src/version.cpp`: `return "0.1.2";`

- [ ] **Step 2: Annotate the master design doc** — in `docs/2026-05-16-pluton-design.md`, the M4 line, change the `**M4c** Move/Rotate/Scale transforms` fragment to:
  `**M4c** ✅ *(shipped v0.1.2)* — Move/Rotate/Scale transforms (set_vertex_position kernel op; point-to-point Move, auto-tilt Rotate protractor, full corner/edge/face Scale gizmo)`

- [ ] **Step 3: Rebuild + verify version** — `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation` then `.venv\Scripts\python.exe -c "import pluton._core as c; print(c.version())"` → `0.1.2`.

- [ ] **Step 4: Full suite once more** — `ctest --test-dir build/tests --output-on-failure` and `.venv\Scripts\python.exe -m pytest -q` → all green.

- [ ] **Step 5: Commit the release**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "release: v0.1.2 (M4c — Move/Rotate/Scale transforms)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + watch the RIGHT CI run** — `git push`. Then identify the **Build & Test** workflow run on `main` (not Dependency Graph / Dependabot) and wait for it specifically:

```bash
gh run list --branch main --workflow "Build & Test" --limit 1
gh run watch <that-run-id> --exit-status
```
Confirm both `windows-2022` and `ubuntu-24.04` jobs = success via `gh run view <id> --json status,conclusion,jobs`.

- [ ] **Step 7: Tag (annotated, SSH-signed) + push the tag**

```bash
git tag -a v0.1.2-m4c -m "M4c — Move/Rotate/Scale transforms"
git cat-file -t v0.1.2-m4c        # → tag (annotated)
git cat-file tag v0.1.2-m4c | grep -c "BEGIN SSH SIGNATURE"   # → 1
git push origin v0.1.2-m4c
```

- [ ] **Step 8: File carry-over issues** (use `gh issue create`), one each:
  - Copy-move (Ctrl-drag duplicate) — needs geometry cloning; revisit with M4e.
  - Auto-fold of non-planar faces on partial-vertex moves.
  - Scale mirror (negative factor past the anchor).
  - Auto-grab transform of the hovered entity when nothing is selected.
  - Preserve selection across transform undo/redo (vs. the M4b clear-on-undo default).
  - Axis-aware Scale dragging + Rotate free-angle/typed entry (folds into M4d's VCB).

---

## Self-review (filled in by the plan author)

**Spec coverage:** kernel op (T1/T2 ↔ spec §4.1/§4.2); transform math (T3 ↔ §4.3); selection→vertex-set + AABB + grips (T4 ↔ §4.4/§4.6 Scale); command (T5 ↔ §4.5); overlay primitives + renderer (T6 ↔ §4.7); Move/Rotate/Scale tools (T7/T8/T9 ↔ §4.6); registration + shortcuts (T10 ↔ §4.6); regression + visual (T11 ↔ §7); release + carry-overs (T12 ↔ §8/§9). Modifiers Ctrl-center / Shift-uniform (T9 ↔ §4.6); 15° angle snap (T8 ↔ §4.6); non-planar handling is inherent to set_vertex_position (T1, no extra task needed). All spec sections map to a task.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; every test step shows the assertions.

**Type consistency:** `set_vertex_position(v_id, x, y, z)` (kernel) / `Scene.set_vertex_position(v_id, position)` consistent T1↔T2↔T5/T7/T8/T9. `TransformVerticesCommand(moves: dict[id, (old, new)])` + `.is_empty()` consistent T5↔T7/T8/T9. `GripSpec(position, opposite, axes)` consistent T4↔T9. `ToolOverlay.world_polylines` (list of (segs, color, width)) + `screen_markers` (list of (world_pos, size_px, color)) consistent T6↔T7/T8/T9↔renderer. `CommandStack.execute(cmd, scene)` matches the real signature.

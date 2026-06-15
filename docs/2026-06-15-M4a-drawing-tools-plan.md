# M4a — Drawing Tools (Circle, Polygon, 2-Point Arc) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three SketchUp-style drawing tools — Circle (`C`), Polygon (`G`), 2-Point Arc (`A`) — that draw on the ground / ground-parallel / existing-face planes, snapped via the M3d engine, committing atomically undoable geometry.

**Architecture:** A new pure, Qt-free `pluton.geometry` package holds the shared math: `DrawingPlane` (plane resolution + 2D↔3D basis) and `curves` (circle / polygon / arc point generators). A thin `tools/shape_support.py` turns world-point rings into `CompositeCommand`s over the existing `AddVertex`/`AddEdge`/`AddFace` commands (with vertex reuse for snapped-to-existing points). Three thin `Tool` subclasses drive the gestures. **No C++/kernel changes** — pure Python over existing primitives.

**Tech Stack:** Python 3.13, numpy, PySide6 (Qt), pytest + pytest-qt. Spec: `docs/2026-06-15-M4a-drawing-tools-design.md`.

---

## Conventions & guardrails (read before every task)

- **Interpreter:** always use the venv explicitly — `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash). The bare `python`/`pytest` resolve to a different, drifting install.
- **Working dir:** run all commands from `F:\dev\00_Parrow-Horrizon-Studio\pluton`. In the Bash tool, the cwd resets between calls — prefix with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && …`.
- **No C++ rebuild needed** — M4a touches no kernel/binding/`CMakeLists` code. The existing editable install (built at v0.0.7) is sufficient. **Exception:** when a *new Python package directory* (`pluton/geometry`) is first added, the scikit-build-core editable install may not expose it until refreshed — Task 1 handles this once.
- **Git:** work on `main`. Stage **specific files only** — never `git add -A` / `git add .`. End every commit message with the trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay on).
- **Do not touch version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) until the release task (Task 10).
- **TDD:** write the failing test, watch it fail, write minimal code, watch it pass, commit. One commit per task (test + impl together), matching repo history.

---

## File structure

| File | Responsibility |
|------|----------------|
| `python/pluton/geometry/__init__.py` | Package init; re-export `DrawingPlane` and curve functions. |
| `python/pluton/geometry/plane.py` | `DrawingPlane` — origin + orthonormal `u`/`v`/`normal`, `horizontal`/`from_normal`/`from_face`, `to_world`/`project`. Pure. |
| `python/pluton/geometry/curves.py` | `circle`, `polygon`, `arc_2pt`, `semicircle_snap` — 2D point generators in plane coords. Pure. |
| `python/pluton/tools/shape_support.py` | `resolve_drawing_plane`, `build_closed_face`, `build_open_polyline`, `polyline_segments`. Bridges snap→plane and world-points→`CompositeCommand`. |
| `python/pluton/tools/circle_tool.py` | `CircleTool` (`C`) — center→radius gesture. |
| `python/pluton/tools/polygon_tool.py` | `PolygonTool` (`G`) — center→radius, `↑`/`↓` sides. |
| `python/pluton/tools/arc_tool.py` | `ArcTool` (`A`) — start→end→bulge, half-circle snap. |
| `python/pluton/tools/__init__.py` | Export the three new tools. |
| `python/pluton/ui/main_window.py` | Register tools; `C`/`G`/`A` + `↑`/`↓` shortcuts. |
| `tests/test_geometry_plane.py` | `DrawingPlane` unit tests. |
| `tests/test_geometry_curves.py` | curve generator unit tests. |
| `tests/test_shape_support.py` | shape-support helper tests (with a real `Scene`). |
| `tests/test_circle_tool.py` / `test_polygon_tool.py` / `test_arc_tool.py` | gesture tests (pytest-qt harness). |

---

## Task 1: `geometry` package + `DrawingPlane`

**Files:**
- Create: `python/pluton/geometry/__init__.py`
- Create: `python/pluton/geometry/plane.py`
- Test: `tests/test_geometry_plane.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geometry_plane.py`:

```python
"""Unit tests for DrawingPlane (pure geometry, no Qt)."""

from __future__ import annotations

import numpy as np

from pluton.geometry import DrawingPlane


def _orthonormal(plane: DrawingPlane) -> None:
    for a in (plane.u, plane.v, plane.normal):
        assert abs(float(np.linalg.norm(a)) - 1.0) < 1e-9
    assert abs(float(plane.u @ plane.v)) < 1e-9
    assert abs(float(plane.u @ plane.normal)) < 1e-9
    assert abs(float(plane.v @ plane.normal)) < 1e-9
    assert np.allclose(np.cross(plane.u, plane.v), plane.normal, atol=1e-9)


def test_horizontal_plane_is_world_aligned():
    p = DrawingPlane.horizontal(np.array([2.0, 3.0, 5.0]))
    _orthonormal(p)
    assert np.allclose(p.u, [1.0, 0.0, 0.0])
    assert np.allclose(p.v, [0.0, 1.0, 0.0])
    assert np.allclose(p.normal, [0.0, 0.0, 1.0])


def test_to_world_project_round_trip():
    p = DrawingPlane.horizontal(np.array([1.0, 1.0, 4.0]))
    uv = np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 3.0], [-1.5, 2.5]])
    world = p.to_world(uv)
    # uv (0,0) maps to the origin; world points lie on the plane (z == origin z).
    assert np.allclose(world[0], [1.0, 1.0, 4.0])
    assert np.allclose(world[:, 2], 4.0)
    back = p.project(world)
    assert np.allclose(back, uv, atol=1e-9)


def test_from_normal_builds_orthonormal_basis():
    p = DrawingPlane.from_normal(np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 5.0]))
    _orthonormal(p)
    assert np.allclose(p.normal, [0.0, 0.0, 1.0])
    # A vertical (Y-facing) plane.
    q = DrawingPlane.from_normal(np.array([0.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]))
    _orthonormal(q)
    assert np.allclose(q.normal, [0.0, 1.0, 0.0])


def test_from_normal_rejects_degenerate():
    import pytest

    with pytest.raises(ValueError):
        DrawingPlane.from_normal(np.zeros(3), np.zeros(3))


def test_from_face_uses_scene_face_normal():
    from pluton.scene import Scene

    scene = Scene()
    # A unit square on the ground → +Z normal.
    a = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    d = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    fid = scene.add_face_from_loop((a, b, c, d))

    p = DrawingPlane.from_face(scene, fid, np.array([0.5, 0.5, 0.0]))
    _orthonormal(p)
    assert np.allclose(p.normal, scene.face_normal(fid), atol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_geometry_plane.py -q`
Expected: collection/`ModuleNotFoundError: No module named 'pluton.geometry'`.

- [ ] **Step 3: Create the package init**

Create `python/pluton/geometry/__init__.py`:

```python
"""Pure, Qt-free geometry helpers (plane math + curve generation)."""

from __future__ import annotations

from pluton.geometry.curves import arc_2pt, circle, polygon, semicircle_snap
from pluton.geometry.plane import DrawingPlane

__all__ = ["DrawingPlane", "circle", "polygon", "arc_2pt", "semicircle_snap"]
```

- [ ] **Step 4: Implement `DrawingPlane`**

Create `python/pluton/geometry/plane.py`:

```python
"""DrawingPlane — an immutable orthonormal frame for 2D-on-3D construction.

A plane carries an `origin` (a world point on the plane), a unit `normal`, and
an in-plane orthonormal basis `u`, `v` with `u x v == normal`. Tools generate
shape vertices in 2D plane coords and lift them to world via `to_world`.
"""

from __future__ import annotations

import numpy as np

_DEGENERATE = 1e-9


class DrawingPlane:
    __slots__ = ("origin", "u", "v", "normal")

    def __init__(
        self,
        origin: np.ndarray,
        u: np.ndarray,
        v: np.ndarray,
        normal: np.ndarray,
    ) -> None:
        self.origin = np.asarray(origin, dtype=np.float64).reshape(3)
        self.u = np.asarray(u, dtype=np.float64).reshape(3)
        self.v = np.asarray(v, dtype=np.float64).reshape(3)
        self.normal = np.asarray(normal, dtype=np.float64).reshape(3)

    @classmethod
    def horizontal(cls, origin: np.ndarray) -> "DrawingPlane":
        """Ground-parallel plane (normal +Z, u=+X, v=+Y) through `origin`."""
        return cls(
            origin,
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )

    @classmethod
    def from_normal(cls, origin: np.ndarray, normal: np.ndarray) -> "DrawingPlane":
        """Build a stable orthonormal in-plane basis from an arbitrary normal."""
        n = np.asarray(normal, dtype=np.float64).reshape(3)
        ln = float(np.linalg.norm(n))
        if ln < _DEGENERATE:
            raise ValueError("DrawingPlane.from_normal: degenerate (zero) normal")
        n = n / ln
        ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) <= 0.9 else np.array([1.0, 0.0, 0.0])
        u = np.cross(ref, n)
        u = u / float(np.linalg.norm(u))
        v = np.cross(n, u)
        return cls(origin, u, v, n)

    @classmethod
    def from_face(cls, scene, face_id: int, origin: np.ndarray) -> "DrawingPlane":  # noqa: ANN001
        """Plane coplanar with an existing face (normal from scene.face_normal)."""
        n = np.asarray(scene.face_normal(face_id), dtype=np.float64).reshape(3)
        return cls.from_normal(origin, n)

    def to_world(self, uv: np.ndarray) -> np.ndarray:
        """Map plane coords (..., 2) to world coords (..., 3)."""
        uv = np.asarray(uv, dtype=np.float64)
        return self.origin + uv[..., 0:1] * self.u + uv[..., 1:2] * self.v

    def project(self, world: np.ndarray) -> np.ndarray:
        """Drop world coords (..., 3) onto the plane → coords (..., 2)."""
        d = np.asarray(world, dtype=np.float64) - self.origin
        return np.stack([d @ self.u, d @ self.v], axis=-1)
```

- [ ] **Step 5: Refresh the editable install so the new package is importable**

The new `pluton/geometry` package directory may not be exposed by the existing editable install. Run:
`.venv\Scripts\python.exe -c "import pluton.geometry"` — if it raises `ModuleNotFoundError`, refresh (no build isolation, reuses the cached C++ build — fast):
`.venv\Scripts\python.exe -m pip install -e . --no-build-isolation`
Then re-run the import check; it must succeed.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_geometry_plane.py -q`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add python/pluton/geometry/__init__.py python/pluton/geometry/plane.py tests/test_geometry_plane.py
git commit -m "$(cat <<'EOF'
feat(geometry): DrawingPlane for 2D-on-3D construction (M4a)

New pure geometry package. DrawingPlane resolves a horizontal/ground-parallel
or face-coplanar frame with a stable orthonormal basis, and maps between plane
(2D) and world (3D) coords. Foundation for the Circle/Polygon/Arc tools.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Circle & Polygon point generators

**Files:**
- Create: `python/pluton/geometry/curves.py`
- Test: `tests/test_geometry_curves.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geometry_curves.py`:

```python
"""Unit tests for curve generators (pure 2D, no Qt)."""

from __future__ import annotations

import numpy as np

from pluton.geometry import circle, polygon


def test_circle_has_segment_count_points_on_radius():
    pts = circle(radius=2.0, segments=24)
    assert pts.shape == (24, 2)
    dists = np.linalg.norm(pts, axis=1)
    assert np.allclose(dists, 2.0, atol=1e-9)


def test_circle_first_vertex_follows_start_angle():
    pts = circle(radius=1.0, segments=24, start_angle=np.pi / 2)
    # start_angle = 90° → first vertex points along +v (0, 1).
    assert np.allclose(pts[0], [0.0, 1.0], atol=1e-9)


def test_polygon_is_inscribed_and_regular():
    pts = polygon(radius=3.0, sides=6)
    assert pts.shape == (6, 2)
    # Inscribed: every vertex is exactly `radius` from the center.
    assert np.allclose(np.linalg.norm(pts, axis=1), 3.0, atol=1e-9)
    # Regular: equal edge lengths.
    edges = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
    assert np.allclose(edges, edges[0], atol=1e-9)


def test_ring_winding_is_ccw():
    # Shoelace signed area > 0 → counter-clockwise → face normal aligns with +normal.
    pts = polygon(radius=1.0, sides=5)
    x, y = pts[:, 0], pts[:, 1]
    area2 = float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    assert area2 > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_geometry_curves.py -q`
Expected: FAIL — `ImportError: cannot import name 'circle'` (curves.py doesn't exist).

- [ ] **Step 3: Implement circle & polygon (and the arc stubs imported by `__init__`)**

Create `python/pluton/geometry/curves.py`:

```python
"""Curve point generators in 2D plane coordinates.

All functions return (N, 2) float64 arrays of plane coords centered on the
plane origin (0, 0). Tools lift them to world via DrawingPlane.to_world.
Rings are wound counter-clockwise so the resulting face normal aligns with the
plane normal.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-7


def _ring(radius: float, count: int, start_angle: float) -> np.ndarray:
    angles = start_angle + np.arange(count, dtype=np.float64) * (2.0 * np.pi / count)
    return np.stack([radius * np.cos(angles), radius * np.sin(angles)], axis=-1)


def circle(radius: float, segments: int = 24, start_angle: float = 0.0) -> np.ndarray:
    """A `segments`-gon approximating a circle of `radius`, centered at (0, 0)."""
    return _ring(float(radius), int(segments), float(start_angle))


def polygon(radius: float, sides: int, start_angle: float = 0.0) -> np.ndarray:
    """A regular inscribed `sides`-gon of circumradius `radius`, centered at (0, 0)."""
    return _ring(float(radius), int(sides), float(start_angle))


def arc_2pt(
    start_uv: np.ndarray,
    end_uv: np.ndarray,
    bulge_uv: np.ndarray,
    segments: int = 12,
) -> np.ndarray:
    """Sample a circular arc through `start_uv` and `end_uv` whose bow is set by
    the perpendicular offset of `bulge_uv` from the chord.

    Returns (segments + 1, 2) inclusive of both endpoints. Degenerate cases:
    near-zero chord → single point; near-zero sagitta → the straight chord
    (2 points).
    """
    start = np.asarray(start_uv, dtype=np.float64).reshape(2)
    end = np.asarray(end_uv, dtype=np.float64).reshape(2)
    bulge = np.asarray(bulge_uv, dtype=np.float64).reshape(2)

    chord = end - start
    chord_len = float(np.linalg.norm(chord))
    if chord_len < _EPS:
        return start.reshape(1, 2).copy()

    chord_dir = chord / chord_len
    normal_dir = np.array([-chord_dir[1], chord_dir[0]])
    mid = 0.5 * (start + end)
    half = 0.5 * chord_len
    sagitta = float((bulge - mid) @ normal_dir)
    if abs(sagitta) < _EPS:
        return np.stack([start, end])

    # Circle through start/end with the given sagitta. Center lies on the
    # normal line through mid at signed offset yc.
    yc = (sagitta * sagitta - half * half) / (2.0 * sagitta)
    center = mid + normal_dir * yc
    radius = float(np.linalg.norm(start - center))

    def _ang(p: np.ndarray) -> float:
        d = p - center
        return float(np.arctan2(d @ normal_dir, d @ chord_dir))

    apex = mid + normal_dir * sagitta  # on the circle, on the bulge side
    ts = _ang(start)
    te_rel = (_ang(end) - ts) % (2.0 * np.pi)
    ta_rel = (_ang(apex) - ts) % (2.0 * np.pi)
    end_rel = te_rel if ta_rel <= te_rel else te_rel - 2.0 * np.pi

    thetas = ts + np.linspace(0.0, end_rel, int(segments) + 1)
    return center + radius * (
        np.outer(np.cos(thetas), chord_dir) + np.outer(np.sin(thetas), normal_dir)
    )


def semicircle_snap(
    start_uv: np.ndarray,
    end_uv: np.ndarray,
    bulge_uv: np.ndarray,
    rel_tol: float = 0.08,
) -> np.ndarray:
    """Snap `bulge_uv` to an exact semicircle (sagitta == half-chord) when it is
    within `rel_tol` of one; otherwise return `bulge_uv` unchanged."""
    start = np.asarray(start_uv, dtype=np.float64).reshape(2)
    end = np.asarray(end_uv, dtype=np.float64).reshape(2)
    bulge = np.asarray(bulge_uv, dtype=np.float64).reshape(2)

    chord = end - start
    chord_len = float(np.linalg.norm(chord))
    if chord_len < _EPS:
        return bulge.copy()
    normal_dir = np.array([-chord[1], chord[0]]) / chord_len
    mid = 0.5 * (start + end)
    half = 0.5 * chord_len
    sagitta = float((bulge - mid) @ normal_dir)
    if abs(abs(sagitta) - half) <= rel_tol * half:
        snapped = half if sagitta >= 0.0 else -half
        return mid + normal_dir * snapped
    return bulge.copy()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_geometry_curves.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/geometry/curves.py tests/test_geometry_curves.py
git commit -m "$(cat <<'EOF'
feat(geometry): circle & inscribed-polygon point generators (M4a)

CCW-wound 2D rings centered at the plane origin (so the lifted face normal
aligns with the plane normal). Includes arc_2pt/semicircle_snap stubs exercised
by Task 3.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 2-Point Arc generator

**Files:**
- Modify: `python/pluton/geometry/curves.py` (already authored in Task 2 — this task adds its tests)
- Test: `tests/test_geometry_curves.py` (append)

> Note: `arc_2pt` and `semicircle_snap` were written in Task 2 (they are imported by `__init__`). This task adds their failing-first tests and verifies them. If executing strictly TDD per-function, the implementer may instead author the arc tests *before* the Task 2 implementation; the grouping here keeps the file edits cohesive.

- [ ] **Step 1: Append the failing arc tests**

Append to `tests/test_geometry_curves.py`:

```python
def test_arc_semicircle_lies_on_circle():
    from pluton.geometry import arc_2pt

    # start (-1,0), end (1,0), bulge (0,1) → unit semicircle centered at origin.
    pts = arc_2pt(np.array([-1.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0]), segments=12)
    assert pts.shape == (13, 2)
    assert np.allclose(pts[0], [-1.0, 0.0], atol=1e-9)
    assert np.allclose(pts[-1], [1.0, 0.0], atol=1e-9)
    # Every sample is on the unit circle, and the bow goes through (0, 1).
    assert np.allclose(np.linalg.norm(pts, axis=1), 1.0, atol=1e-9)
    assert np.any(np.all(np.isclose(pts, [0.0, 1.0], atol=1e-9), axis=1))


def test_arc_general_samples_on_common_circle():
    from pluton.geometry import arc_2pt

    start, end, bulge = np.array([0.0, 0.0]), np.array([2.0, 0.0]), np.array([1.0, 0.5])
    pts = arc_2pt(start, end, bulge, segments=16)
    # Expected circle: center (1, -0.75), radius 1.25.
    center = np.array([1.0, -0.75])
    assert np.allclose(np.linalg.norm(pts - center, axis=1), 1.25, atol=1e-9)
    assert np.allclose(pts[0], start, atol=1e-9)
    assert np.allclose(pts[-1], end, atol=1e-9)


def test_arc_flat_bulge_returns_straight_chord():
    from pluton.geometry import arc_2pt

    pts = arc_2pt(np.array([0.0, 0.0]), np.array([2.0, 0.0]), np.array([1.0, 0.0]))
    assert pts.shape == (2, 2)
    assert np.allclose(pts, [[0.0, 0.0], [2.0, 0.0]])


def test_arc_degenerate_chord_returns_single_point():
    from pluton.geometry import arc_2pt

    pts = arc_2pt(np.array([1.0, 1.0]), np.array([1.0, 1.0]), np.array([2.0, 2.0]))
    assert pts.shape == (1, 2)


def test_semicircle_snap_pulls_near_semicircle_exact():
    from pluton.geometry import semicircle_snap

    start, end = np.array([-1.0, 0.0]), np.array([1.0, 0.0])
    snapped = semicircle_snap(start, end, np.array([0.0, 0.97]))  # near half-chord (1.0)
    assert np.allclose(snapped, [0.0, 1.0], atol=1e-9)
    # Far from a semicircle → unchanged.
    far = semicircle_snap(start, end, np.array([0.0, 0.4]))
    assert np.allclose(far, [0.0, 0.4])
```

- [ ] **Step 2: Run the arc tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_geometry_curves.py -q`
Expected: PASS (9 tests total). If the arc tests fail, fix `arc_2pt`/`semicircle_snap` in `curves.py` until green (the implementation in Task 2 is the reference).

- [ ] **Step 3: Commit**

```bash
git add tests/test_geometry_curves.py
git commit -m "$(cat <<'EOF'
test(geometry): arc_2pt + semicircle_snap coverage (M4a)

Semicircle/general-arc on-circle checks, straight-chord and degenerate-chord
fallbacks, and the half-circle snap threshold.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Shape-support helpers (snap→plane, world-points→command)

**Files:**
- Create: `python/pluton/tools/shape_support.py`
- Test: `tests/test_shape_support.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_shape_support.py`:

```python
"""Tests for shape_support: plane resolution + world-points → CompositeCommand."""

from __future__ import annotations

import numpy as np


def _snap(kind, world, *, face_id=None, vertex_id=None):  # noqa: ANN001
    from pluton.viewport.snap_engine import SnapResult

    return SnapResult(
        kind=kind,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=vertex_id,
        label="t",
        face_id=face_id,
    )


def test_resolve_plane_defaults_to_horizontal_through_point():
    from pluton.scene import Scene
    from pluton.tools.shape_support import resolve_drawing_plane
    from pluton.viewport.snap_engine import SnapKind

    plane = resolve_drawing_plane(_snap(SnapKind.ENDPOINT, (1.0, 2.0, 5.0)), Scene())
    assert np.allclose(plane.normal, [0.0, 0.0, 1.0])
    assert np.allclose(plane.origin, [1.0, 2.0, 5.0])


def test_resolve_plane_uses_face_for_on_face_snap():
    from pluton.scene import Scene
    from pluton.tools.shape_support import resolve_drawing_plane
    from pluton.viewport.snap_engine import SnapKind

    scene = Scene()
    # A vertical face in the X=0 plane → normal points along ±X.
    a = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([0.0, 2.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([0.0, 2.0, 2.0], dtype=np.float32))
    d = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    fid = scene.add_face_from_loop((a, b, c, d))

    plane = resolve_drawing_plane(
        _snap(SnapKind.ON_FACE, (0.0, 1.0, 1.0), face_id=fid), scene
    )
    assert abs(abs(float(plane.normal[0])) - 1.0) < 1e-6  # ±X


def test_build_closed_face_creates_ring_face_and_undoes_atomically():
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools.shape_support import build_closed_face

    scene = Scene()
    stack = CommandStack()
    # A square ring (4 distinct world points on the ground).
    pts = np.array(
        [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], dtype=np.float32
    )
    composite = build_closed_face(scene, pts, name="X")
    assert composite is not None
    stack.push_executed(composite)

    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.edges_iter())) == 4
    assert len(list(scene.faces_iter())) == 1

    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.faces_iter())) == 0

    stack.redo(scene)
    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.faces_iter())) == 1


def test_build_closed_face_reuses_coincident_existing_vertex():
    from pluton.scene import Scene
    from pluton.tools.shape_support import build_closed_face

    scene = Scene()
    existing = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    pts = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], dtype=np.float32)
    build_closed_face(scene, pts, name="X")
    # The (0,0,0) corner reuses `existing` rather than adding a 5th vertex.
    assert len(list(scene.vertices_iter())) == 4
    assert any(v.id == existing for v in scene.vertices_iter())


def test_build_open_polyline_creates_edges_no_face():
    from pluton.scene import Scene
    from pluton.tools.shape_support import build_open_polyline

    scene = Scene()
    pts = np.array([[0, 0, 0], [1, 1, 0], [2, 0, 0]], dtype=np.float32)
    composite = build_open_polyline(scene, pts, name="A")
    assert composite is not None
    composite_children = composite.children
    assert composite_children  # non-empty
    assert len(list(scene.vertices_iter())) == 3
    assert len(list(scene.edges_iter())) == 2
    assert len(list(scene.faces_iter())) == 0


def test_polyline_segments_closed_and_open():
    from pluton.tools.shape_support import polyline_segments

    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0]], dtype=np.float32)
    closed = polyline_segments(pts, closed=True)
    assert closed.shape == (6, 3)  # 3 segments × 2 endpoints
    opened = polyline_segments(pts, closed=False)
    assert opened.shape == (4, 3)  # 2 segments × 2 endpoints
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shape_support.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.tools.shape_support'`.

- [ ] **Step 3: Implement the helpers**

Create `python/pluton/tools/shape_support.py`:

```python
"""Bridges between snaps/world geometry and the command layer for drawing tools.

- resolve_drawing_plane: pick the construction plane from the first click's snap.
- build_closed_face / build_open_polyline: turn a ring/polyline of world points
  into one CompositeCommand over AddVertex/AddEdge(/AddFace), reusing existing
  vertices that coincide with a generated point (so undo stays correct).
- polyline_segments: world points -> (2N, 3) GL_LINES pairs for overlay preview.
"""

from __future__ import annotations

import numpy as np

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import AddEdgeCommand, AddFaceCommand, AddVertexCommand
from pluton.geometry import DrawingPlane

# Reuse an existing vertex when a generated point lands within this distance of
# it (world units / meters). Tight enough not to merge genuinely-distinct CAD
# vertices; loose enough to absorb float round-trip error from a snapped point.
_COINCIDENT_EPS = 1e-5


def resolve_drawing_plane(snap, scene) -> DrawingPlane:  # noqa: ANN001
    """ON_FACE snap → that face's plane; otherwise a ground-parallel plane
    through the snapped point's height."""
    from pluton.viewport.snap_engine import SnapKind

    origin = np.asarray(snap.world_position, dtype=np.float64).reshape(3)
    if snap.kind == SnapKind.ON_FACE and snap.face_id is not None:
        try:
            return DrawingPlane.from_face(scene, snap.face_id, origin)
        except (ValueError, KeyError):
            return DrawingPlane.horizontal(origin)
    return DrawingPlane.horizontal(origin)


def _resolve_vertex(scene, composite: CompositeCommand, point: np.ndarray) -> int:  # noqa: ANN001
    """Reuse an existing coincident vertex, else add one (recorded in composite)."""
    p = np.asarray(point, dtype=np.float32).reshape(3)
    existing = scene.find_vertex_near(p, _COINCIDENT_EPS)
    if existing is not None:
        return existing
    cmd = AddVertexCommand(p)
    cmd.do(scene)
    composite.children.append(cmd)
    return cmd._vertex_id  # type: ignore[attr-defined]


def _resolve_ring(scene, composite, world_points):  # noqa: ANN001
    """Resolve each point to a vertex id, dropping consecutive duplicates."""
    vids: list[int] = []
    for p in np.asarray(world_points, dtype=np.float32):
        vid = _resolve_vertex(scene, composite, p)
        if not vids or vids[-1] != vid:
            vids.append(vid)
    return vids


def build_closed_face(scene, world_points, name: str = "Draw Shape"):  # noqa: ANN001
    """Closed ring of world points → vertices + boundary edges + one face.
    Returns the CompositeCommand (already executed), or None if degenerate
    (fewer than 3 distinct vertices)."""
    composite = CompositeCommand(name=name)
    vids = _resolve_ring(scene, composite, world_points)
    if len(vids) >= 2 and vids[0] == vids[-1]:
        vids.pop()
    if len(vids) < 3:
        composite.undo(scene)
        return None
    n = len(vids)
    for i in range(n):
        e = AddEdgeCommand(vids[i], vids[(i + 1) % n])
        e.do(scene)
        composite.children.append(e)
    f = AddFaceCommand(tuple(vids))
    f.do(scene)
    composite.children.append(f)
    return composite


def build_open_polyline(scene, world_points, name: str = "Draw Curve"):  # noqa: ANN001
    """Open polyline of world points → vertices + connecting edges (no face).
    Returns the CompositeCommand (already executed), or None if degenerate
    (fewer than 2 distinct vertices)."""
    composite = CompositeCommand(name=name)
    vids = _resolve_ring(scene, composite, world_points)
    if len(vids) < 2:
        composite.undo(scene)
        return None
    for i in range(len(vids) - 1):
        e = AddEdgeCommand(vids[i], vids[i + 1])
        e.do(scene)
        composite.children.append(e)
    return composite


def polyline_segments(points: np.ndarray, closed: bool) -> np.ndarray:
    """World points → (2N, 3) float32 GL_LINES endpoint pairs for overlay."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    n = len(pts)
    if n < 2:
        return np.zeros((0, 3), dtype=np.float32)
    if closed:
        seg = np.empty((2 * n, 3), dtype=np.float32)
        seg[0::2] = pts
        seg[1::2] = np.roll(pts, -1, axis=0)
    else:
        seg = np.empty((2 * (n - 1), 3), dtype=np.float32)
        seg[0::2] = pts[:-1]
        seg[1::2] = pts[1:]
    return seg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_shape_support.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/shape_support.py tests/test_shape_support.py
git commit -m "$(cat <<'EOF'
feat(tools): shape_support — plane resolution + ring/polyline commands (M4a)

resolve_drawing_plane picks ground-parallel vs face-coplanar from the first
snap; build_closed_face/build_open_polyline compose AddVertex/AddEdge/AddFace
into one undoable gesture, reusing coincident existing vertices; polyline_segments
feeds the overlay rubber-band.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: CircleTool

**Files:**
- Create: `python/pluton/tools/circle_tool.py`
- Modify: `python/pluton/tools/__init__.py` (export `CircleTool`)
- Test: `tests/test_circle_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_circle_tool.py`:

```python
"""Gesture tests for the Circle tool."""

from __future__ import annotations

import numpy as np


def _snap(world, *, kind=None, face_id=None):  # noqa: ANN001
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=kind if kind is not None else SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="t",
        face_id=face_id,
    )


def _make_tool(scene, stack=None):  # noqa: ANN001
    from pluton.tools import ToolContext
    from pluton.tools.circle_tool import CircleTool

    tool = CircleTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))
    return tool


def test_circle_idle_overlay_empty():
    from pluton.scene import Scene

    tool = _make_tool(Scene())
    assert tool.overlay().rubber_band_segments.shape == (0, 3)


def test_circle_two_clicks_make_24_segments_and_a_face():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))  # center
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))  # radius
    assert len(list(scene.vertices_iter())) == 24
    assert len(list(scene.edges_iter())) == 24
    assert len(list(scene.faces_iter())) == 1
    # All ring vertices lie at radius 2 from center on the ground plane.
    for v in scene.vertices_iter():
        assert abs(float(np.hypot(v.position[0], v.position[1])) - 2.0) < 1e-3
        assert abs(float(v.position[2])) < 1e-6


def test_circle_face_normal_points_up_on_ground():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((3.0, 0.0, 0.0)))
    face = next(iter(scene.faces_iter()))
    assert float(scene.face_normal(face.id)[2]) > 0.99


def test_circle_zero_radius_does_not_commit():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((1.0, 1.0, 0.0)))
    tool.on_mouse_press(None, _snap((1.0, 1.0, 0.0)))  # same point → radius 0
    assert len(list(scene.vertices_iter())) == 0


def test_circle_commit_is_atomically_undoable():
    from pluton.commands import CommandStack
    from pluton.scene import Scene

    scene = Scene()
    stack = CommandStack()
    tool = _make_tool(scene, stack)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))
    assert stack.can_undo
    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    stack.redo(scene)
    assert len(list(scene.faces_iter())) == 1


def test_circle_draws_on_a_vertical_face():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapKind

    scene = Scene()
    a = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([0.0, 4.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([0.0, 4.0, 4.0], dtype=np.float32))
    d = scene.add_vertex(np.array([0.0, 0.0, 4.0], dtype=np.float32))
    fid = scene.add_face_from_loop((a, b, c, d))
    base_verts = len(list(scene.vertices_iter()))

    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 2.0, 2.0), kind=SnapKind.ON_FACE, face_id=fid))
    tool.on_mouse_press(None, _snap((0.0, 3.0, 2.0), kind=SnapKind.ON_FACE, face_id=fid))
    # New ring vertices all lie on the face's plane (x == 0).
    new = [v for v in scene.vertices_iter() if v.id >= base_verts]
    assert len(new) == 24
    for v in new:
        assert abs(float(v.position[0])) < 1e-4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_circle_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.tools.circle_tool'`.

- [ ] **Step 3: Implement `CircleTool`**

Create `python/pluton/tools/circle_tool.py`:

```python
"""The Circle drawing tool.

Two-click gesture: first click sets the center (and resolves the drawing plane
from the snap), second click sets the radius. Commits a 24-segment polygonal
circle (N vertices + N edges + 1 face). ESC cancels.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.geometry import circle
from pluton.tools.shape_support import (
    build_closed_face,
    polyline_segments,
    resolve_drawing_plane,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MIN_RADIUS = 1e-4
_SEGMENTS = 24


class _State(Enum):
    IDLE = 0
    DRAWING = 1


class CircleTool(Tool):
    @property
    def name(self) -> str:
        return "Circle"

    @property
    def shortcut(self) -> str:
        return "C"

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._state = _State.IDLE
        self._plane = None
        self._center: np.ndarray | None = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color = _NEUTRAL_COLOR
        self._snap_marker_kind = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._state == _State.DRAWING and self._plane is not None:
            uv = self._plane.project(snap.world_position)
            self._radius = float(np.linalg.norm(uv))
            self._start_angle = float(np.arctan2(uv[1], uv[0]))

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return
        s = self._scene  # type: ignore[assignment]

        if self._state == _State.IDLE:
            self._plane = resolve_drawing_plane(snap, s)
            self._center = snap.world_position.copy()
            self._state = _State.DRAWING
            return

        if self._plane is None:
            self._reset_gesture()
            return
        uv = self._plane.project(snap.world_position)
        radius = float(np.linalg.norm(uv))
        if radius < _MIN_RADIUS:
            return  # ignore a zero-radius second click; keep drawing
        start_angle = float(np.arctan2(uv[1], uv[0]))
        ring_uv = circle(radius, _SEGMENTS, start_angle)
        world = self._plane.to_world(ring_uv).astype(np.float32)
        composite = build_closed_face(s, world, name="Draw Circle")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        if (
            self._state == _State.DRAWING
            and self._plane is not None
            and self._radius >= _MIN_RADIUS
        ):
            ring_uv = circle(self._radius, _SEGMENTS, self._start_angle)
            world = self._plane.to_world(ring_uv).astype(np.float32)
            segments = polyline_segments(world, closed=True)
        else:
            segments = np.zeros((0, 3), dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAWING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        if self._state == _State.DRAWING and self._center is not None:
            return self._center.copy()
        return None

    @property
    def status_text(self) -> str | None:
        if self._state == _State.DRAWING:
            return f"Radius: {self._radius:.3f}"
        return None

    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._plane = None
        self._center = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
```

- [ ] **Step 4: Export the tool**

In `python/pluton/tools/__init__.py`, add `CircleTool` to the imports and `__all__`. Check the existing file first (`Read`), then add a line mirroring the existing tool exports, e.g.:

```python
from pluton.tools.circle_tool import CircleTool
```
and add `"CircleTool"` to `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_circle_tool.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/circle_tool.py python/pluton/tools/__init__.py tests/test_circle_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): Circle tool — center+radius on ground/face planes (M4a)

Two-click 24-segment circle. Resolves the drawing plane from the first snap,
snaps the radius, commits one atomically undoable face. ESC cancels.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: PolygonTool

**Files:**
- Create: `python/pluton/tools/polygon_tool.py`
- Modify: `python/pluton/tools/__init__.py` (export `PolygonTool`)
- Test: `tests/test_polygon_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_polygon_tool.py`:

```python
"""Gesture tests for the Polygon tool."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


def _snap(world):  # noqa: ANN001
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="t",
    )


def _key(qt_key):  # noqa: ANN001
    return QKeyEvent(QKeyEvent.Type.KeyPress, qt_key, Qt.KeyboardModifier.NoModifier)


def _make_tool(scene):  # noqa: ANN001
    from pluton.tools import ToolContext
    from pluton.tools.polygon_tool import PolygonTool

    tool = PolygonTool()
    tool.activate(ToolContext(scene=scene))
    return tool


def test_polygon_default_six_sides():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))
    assert len(list(scene.vertices_iter())) == 6
    assert len(list(scene.edges_iter())) == 6
    assert len(list(scene.faces_iter())) == 1


def test_polygon_up_down_adjusts_side_count():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))  # start gesture (anchor)
    tool.on_key_press(_key(Qt.Key.Key_Up))   # 6 -> 7
    tool.on_key_press(_key(Qt.Key.Key_Up))   # 7 -> 8
    tool.on_key_press(_key(Qt.Key.Key_Down))  # 8 -> 7
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))
    assert len(list(scene.vertices_iter())) == 7


def test_polygon_sides_clamped_to_min_three():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    for _ in range(10):
        tool.on_key_press(_key(Qt.Key.Key_Down))  # try to go below 3
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))
    assert len(list(scene.vertices_iter())) == 3


def test_polygon_side_count_remembered_across_gestures():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_key_press(_key(Qt.Key.Key_Up))  # 6 -> 7
    tool.on_mouse_press(None, _snap((2.0, 0.0, 0.0)))  # commit a heptagon
    # Second gesture should start at 7, not reset to 6.
    tool.on_mouse_press(None, _snap((10.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((12.0, 0.0, 0.0)))
    counts = [len(scene.face_loop(f.id)) for f in scene.faces_iter()]
    assert sorted(counts) == [7, 7]


def test_polygon_vertices_inscribed_at_radius():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((3.0, 0.0, 0.0)))
    for v in scene.vertices_iter():
        assert abs(float(np.hypot(v.position[0], v.position[1])) - 3.0) < 1e-3
```

> Note: `scene.face_loop(f_id)` returns the ordered boundary vertex ids (per the Scene API). If unavailable, substitute `len(list(scene.vertices_iter()))` accounting per-face; the `face_loop` helper exists in `scene.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_polygon_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.tools.polygon_tool'`.

- [ ] **Step 3: Implement `PolygonTool`**

Create `python/pluton/tools/polygon_tool.py`:

```python
"""The Polygon drawing tool.

Two-click gesture identical to Circle, but commits a regular inscribed N-gon.
The side count (default 6, remembered for the session) is nudged with Up/Down
during the gesture. ESC cancels.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.geometry import polygon
from pluton.tools.shape_support import (
    build_closed_face,
    polyline_segments,
    resolve_drawing_plane,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MIN_RADIUS = 1e-4
_MIN_SIDES = 3
_MAX_SIDES = 64


class _State(Enum):
    IDLE = 0
    DRAWING = 1


class PolygonTool(Tool):
    @property
    def name(self) -> str:
        return "Polygon"

    @property
    def shortcut(self) -> str:
        return "G"

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._state = _State.IDLE
        self._plane = None
        self._center: np.ndarray | None = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._sides = 6  # remembered across gestures (instance lives for the session)
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color = _NEUTRAL_COLOR
        self._snap_marker_kind = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._state == _State.DRAWING and self._plane is not None:
            uv = self._plane.project(snap.world_position)
            self._radius = float(np.linalg.norm(uv))
            self._start_angle = float(np.arctan2(uv[1], uv[0]))

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return
        s = self._scene  # type: ignore[assignment]

        if self._state == _State.IDLE:
            self._plane = resolve_drawing_plane(snap, s)
            self._center = snap.world_position.copy()
            self._state = _State.DRAWING
            return

        if self._plane is None:
            self._reset_gesture()
            return
        uv = self._plane.project(snap.world_position)
        radius = float(np.linalg.norm(uv))
        if radius < _MIN_RADIUS:
            return
        start_angle = float(np.arctan2(uv[1], uv[0]))
        ring_uv = polygon(radius, self._sides, start_angle)
        world = self._plane.to_world(ring_uv).astype(np.float32)
        composite = build_closed_face(s, world, name="Draw Polygon")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._reset_gesture()
        elif key == Qt.Key.Key_Up:
            self._sides = min(_MAX_SIDES, self._sides + 1)
        elif key == Qt.Key.Key_Down:
            self._sides = max(_MIN_SIDES, self._sides - 1)

    def overlay(self) -> ToolOverlay:
        if (
            self._state == _State.DRAWING
            and self._plane is not None
            and self._radius >= _MIN_RADIUS
        ):
            ring_uv = polygon(self._radius, self._sides, self._start_angle)
            world = self._plane.to_world(ring_uv).astype(np.float32)
            segments = polyline_segments(world, closed=True)
        else:
            segments = np.zeros((0, 3), dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAWING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        if self._state == _State.DRAWING and self._center is not None:
            return self._center.copy()
        return None

    @property
    def status_text(self) -> str | None:
        if self._state == _State.DRAWING:
            return f"Radius: {self._radius:.3f}   Sides: {self._sides}"
        return None

    def _reset_gesture(self) -> None:
        # NOTE: _sides is intentionally NOT reset — it persists across gestures.
        self._state = _State.IDLE
        self._plane = None
        self._center = None
        self._radius = 0.0
        self._start_angle = 0.0
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
```

- [ ] **Step 4: Export the tool**

Add `PolygonTool` to `python/pluton/tools/__init__.py` imports and `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_polygon_tool.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/polygon_tool.py python/pluton/tools/__init__.py tests/test_polygon_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): Polygon tool — inscribed N-gon, Up/Down sides (M4a)

Center+radius like Circle, committing a regular inscribed polygon. Side count
(default 6) is nudged with Up/Down during the gesture and remembered for the
session. ESC cancels.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: ArcTool (2-Point, free bulge + half-circle snap)

**Files:**
- Create: `python/pluton/tools/arc_tool.py`
- Modify: `python/pluton/tools/__init__.py` (export `ArcTool`)
- Test: `tests/test_arc_tool.py`

> **Scope note (D8):** edge-tangency is intentionally **deferred** to a fast-follow (issue filed in Task 10). This task ships the free-bulge 2-Point Arc with semicircle snapping.

- [ ] **Step 1: Write the failing test**

Create `tests/test_arc_tool.py`:

```python
"""Gesture tests for the 2-Point Arc tool."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent


def _snap(world):  # noqa: ANN001
    from pluton.viewport.snap_engine import SnapKind, SnapResult

    return SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array(world, dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="t",
    )


def _make_tool(scene, stack=None):  # noqa: ANN001
    from pluton.tools import ToolContext
    from pluton.tools.arc_tool import ArcTool

    tool = ArcTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))
    return tool


def test_arc_three_clicks_make_open_curve_no_face():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((-1.0, 0.0, 0.0)))  # start
    tool.on_mouse_press(None, _snap((1.0, 0.0, 0.0)))   # end
    tool.on_mouse_press(None, _snap((0.0, 1.0, 0.0)))   # bulge (semicircle)
    # 12 segments → 13 vertices, 12 edges, no face.
    assert len(list(scene.vertices_iter())) == 13
    assert len(list(scene.edges_iter())) == 12
    assert len(list(scene.faces_iter())) == 0


def test_arc_points_lie_on_expected_circle():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((-1.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((1.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((0.0, 1.0, 0.0)))
    for v in scene.vertices_iter():
        assert abs(float(np.hypot(v.position[0], v.position[1])) - 1.0) < 1e-3
        assert abs(float(v.position[2])) < 1e-6


def test_arc_commit_is_atomically_undoable():
    from pluton.commands import CommandStack
    from pluton.scene import Scene

    scene = Scene()
    stack = CommandStack()
    tool = _make_tool(scene, stack)
    tool.on_mouse_press(None, _snap((-1.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((1.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((0.0, 1.0, 0.0)))
    assert stack.can_undo
    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    stack.redo(scene)
    assert len(list(scene.edges_iter())) == 12


def test_arc_esc_after_two_clicks_cancels_cleanly():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((-1.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((1.0, 0.0, 0.0)))
    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)
    assert tool.has_active_gesture is False
    assert len(list(scene.vertices_iter())) == 0


def test_arc_degenerate_end_ignored():
    from pluton.scene import Scene

    scene = Scene()
    tool = _make_tool(scene)
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))
    tool.on_mouse_press(None, _snap((0.0, 0.0, 0.0)))  # end == start → ignored
    # Still awaiting a real end point; nothing committed.
    assert len(list(scene.vertices_iter())) == 0
    assert tool.has_active_gesture is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_arc_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.tools.arc_tool'`.

- [ ] **Step 3: Implement `ArcTool`**

Create `python/pluton/tools/arc_tool.py`:

```python
"""The 2-Point Arc drawing tool.

Three clicks: start, end (defines the chord and the drawing plane via the first
snap), then a bulge point setting the bow. Commits an open 12-segment polyline
(no face). A near-semicircle bulge snaps to an exact half-circle. ESC cancels.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.geometry import arc_2pt, semicircle_snap
from pluton.tools.shape_support import (
    build_open_polyline,
    polyline_segments,
    resolve_drawing_plane,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_NEUTRAL_COLOR = (0.85, 0.85, 0.85)
_MIN_CHORD = 1e-4
_SEGMENTS = 12
_ORIGIN_UV = np.zeros(2)


class _State(Enum):
    IDLE = 0
    PLACING_END = 1
    PLACING_BULGE = 2


class ArcTool(Tool):
    @property
    def name(self) -> str:
        return "Arc"

    @property
    def shortcut(self) -> str:
        return "A"

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._state = _State.IDLE
        self._plane = None
        self._start: np.ndarray | None = None  # world
        self._end_uv: np.ndarray | None = None
        self._cursor_uv: np.ndarray | None = None  # live projected cursor (preview)
        self._snap_marker_pos: np.ndarray | None = None
        self._snap_marker_color = _NEUTRAL_COLOR
        self._snap_marker_kind = 0

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._reset_gesture()

    def deactivate(self) -> None:
        self._reset_gesture()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            self._snap_marker_pos = None
            self._snap_marker_kind = 0
            return
        self._snap_marker_pos = snap.world_position.copy()
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
        self._snap_marker_kind = int(snap.kind)
        if self._plane is not None and self._state != _State.IDLE:
            self._cursor_uv = self._plane.project(snap.world_position)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return
        s = self._scene  # type: ignore[assignment]

        if self._state == _State.IDLE:
            self._plane = resolve_drawing_plane(snap, s)
            self._start = snap.world_position.copy()
            self._cursor_uv = _ORIGIN_UV.copy()
            self._state = _State.PLACING_END
            return

        if self._plane is None:
            self._reset_gesture()
            return

        if self._state == _State.PLACING_END:
            end_uv = self._plane.project(snap.world_position)
            if float(np.linalg.norm(end_uv)) < _MIN_CHORD:
                return  # end coincides with start — keep waiting
            self._end_uv = end_uv
            self._cursor_uv = end_uv.copy()
            self._state = _State.PLACING_BULGE
            return

        # PLACING_BULGE → commit
        assert self._end_uv is not None
        bulge_uv = semicircle_snap(_ORIGIN_UV, self._end_uv, self._plane.project(snap.world_position))
        pts_uv = arc_2pt(_ORIGIN_UV, self._end_uv, bulge_uv, _SEGMENTS)
        if len(pts_uv) < 2:
            return
        world = self._plane.to_world(pts_uv).astype(np.float32)
        composite = build_open_polyline(s, world, name="Draw Arc")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_gesture()

    def overlay(self) -> ToolOverlay:
        segments = np.zeros((0, 3), dtype=np.float32)
        if self._plane is not None and self._cursor_uv is not None:
            if self._state == _State.PLACING_END:
                world = self._plane.to_world(
                    np.stack([_ORIGIN_UV, self._cursor_uv])
                ).astype(np.float32)
                segments = polyline_segments(world, closed=False)
            elif self._state == _State.PLACING_BULGE and self._end_uv is not None:
                bulge_uv = semicircle_snap(_ORIGIN_UV, self._end_uv, self._cursor_uv)
                pts_uv = arc_2pt(_ORIGIN_UV, self._end_uv, bulge_uv, _SEGMENTS)
                world = self._plane.to_world(pts_uv).astype(np.float32)
                segments = polyline_segments(world, closed=False)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=self._snap_marker_pos.copy() if self._snap_marker_pos is not None else None,
            snap_marker_color=self._snap_marker_color,
            snap_marker_kind=self._snap_marker_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._state != _State.IDLE

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        if self._state != _State.IDLE and self._start is not None:
            return self._start.copy()
        return None

    @property
    def status_text(self) -> str | None:
        if self._state == _State.PLACING_END:
            return "Pick arc end"
        if self._state == _State.PLACING_BULGE:
            return "Drag the bulge"
        return None

    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._plane = None
        self._start = None
        self._end_uv = None
        self._cursor_uv = None
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
```

- [ ] **Step 4: Export the tool**

Add `ArcTool` to `python/pluton/tools/__init__.py` imports and `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_arc_tool.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/arc_tool.py python/pluton/tools/__init__.py tests/test_arc_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): 2-Point Arc tool — start/end/bulge, semicircle snap (M4a)

Three-click open arc (12 segments, no face) on the resolved drawing plane, with
a near-semicircle bulge snapping to an exact half-circle. Edge-tangency deferred
to a fast-follow. ESC cancels.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Register tools + shortcuts in the main window

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_window_tools.py`:

```python
"""Smoke tests: the new tools are registered and key-activatable."""

from __future__ import annotations

import pytest


@pytest.fixture
def main_window(qtbot):  # noqa: ANN001
    from pluton.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_new_tools_registered(main_window):  # noqa: ANN001
    mgr = main_window._tool_manager
    assert mgr.activate_by_shortcut("C")
    assert mgr.active.name == "Circle"
    assert mgr.activate_by_shortcut("G")
    assert mgr.active.name == "Polygon"
    assert mgr.activate_by_shortcut("A")
    assert mgr.active.name == "Arc"


def test_arrow_keys_forward_to_active_polygon_gesture(main_window):  # noqa: ANN001
    import numpy as np

    from pluton.viewport.snap_engine import SnapKind, SnapResult

    mgr = main_window._tool_manager
    mgr.activate_by_shortcut("G")
    tool = mgr.active
    snap = SnapResult(
        kind=SnapKind.GRID,
        world_position=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        axis=None,
        vertex_id=None,
        label="t",
    )
    tool.on_mouse_press(None, snap)  # begin gesture
    main_window._on_tool_key(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Up)
    assert tool._sides == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main_window_tools.py -q`
Expected: FAIL — `activate_by_shortcut("C")` returns False (tool not registered) / `_on_tool_key` missing.

- [ ] **Step 3: Register tools, add shortcuts, add the arrow-forwarding slot**

In `python/pluton/ui/main_window.py`:

1. Extend the tools import:
```python
from pluton.tools import (
    ArcTool,
    CircleTool,
    LineTool,
    PolygonTool,
    PushPullTool,
    RectangleTool,
    ToolContext,
    ToolManager,
)
```

2. Register the three tools (after the existing `register(...)` calls):
```python
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(PushPullTool())
        self._tool_manager.register(CircleTool())
        self._tool_manager.register(PolygonTool())
        self._tool_manager.register(ArcTool())
```

3. Add the activation shortcuts (next to the existing `L`/`R`/`P` ones):
```python
        QShortcut(QKeySequence("C"), self, activated=lambda: self._activate("C"))
        QShortcut(QKeySequence("G"), self, activated=lambda: self._activate("G"))
        QShortcut(QKeySequence("A"), self, activated=lambda: self._activate("A"))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self._on_tool_key(Qt.Key.Key_Up))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=lambda: self._on_tool_key(Qt.Key.Key_Down))
```

4. Add the forwarding slot (next to `_on_finish_gesture`):
```python
    def _on_tool_key(self, qt_key) -> None:  # noqa: ANN001
        """Forward a non-text key (e.g. Up/Down for polygon sides) to the active
        tool, but only while it has a live gesture (so arrows are inert otherwise)."""
        active = self._tool_manager.active
        if active is None or not active.has_active_gesture:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, qt_key, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._refresh_status_text()
        self._viewport.update()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main_window_tools.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/main_window.py tests/test_main_window_tools.py
git commit -m "$(cat <<'EOF'
feat(ui): register Circle/Polygon/Arc tools + C/G/A and Up/Down keys (M4a)

Wires the three drawing tools into the ToolManager with C/G/A shortcuts, and
forwards Up/Down to the active tool's gesture (polygon side count) only while a
gesture is live.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Full regression + manual visual verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire Python suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green — the prior 244 tests plus the new M4a tests (≈ 31 new). No regressions in M2/M3 tool or snap tests.

- [ ] **Step 2: Run the C++ suite (unchanged — must still pass)**

Run: `ctest --test-dir build/tests --output-on-failure` (or the project's standard GoogleTest invocation).
Expected: 72/72 pass (M4a touched no C++).

- [ ] **Step 3: Launch the app and manually verify**

Run: `.venv\Scripts\python.exe -m pluton`

Verify each, on screen:
- Press `C`; click a center on the ground, move out, click — a 24-gon circle with a filled face appears; the rubber-band ring previews while dragging; status bar shows the live radius.
- Press `G`; before the second click, press `↑`/`↓` — the previewed polygon gains/loses sides; status shows `Sides: N`; commit. Draw another — side count persisted.
- Press `A`; click start, click end, move — the arc bows with the cursor; near a half-circle it snaps; click to commit (open curve, no fill).
- Push/Pull a box (`P`), then press `C` and hover the box's **top face** — the circle draws **on that face's plane** (faceted, facing the right way). Confirm it does NOT cut the face (expected per #27).
- `Ctrl+Z` / `Ctrl+Y` each shape — single-step atomic undo/redo.
- `Esc` mid-gesture for each tool — preview clears, scene unchanged.

- [ ] **Step 4: Record the result**

No commit. If any check fails, fix in the relevant task's files (with a regression test) before proceeding to release.

---

## Task 10: Release v0.1.0 (M4a)

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` (version bump — the one task allowed to touch these)
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M4a shipped)

- [ ] **Step 1: Bump version 0.0.7 → 0.1.0**

- `pyproject.toml`: `version = "0.1.0"`
- `CMakeLists.txt`: `VERSION 0.1.0`
- `cpp/src/version.cpp`: `return "0.1.0";`

- [ ] **Step 2: Annotate the master design doc**

In `docs/2026-05-16-pluton-design.md`, mark M4a shipped under the M4 bullet (mirror the M3d `✅ *(shipped v0.0.7)*` style), e.g. append to the M4 line a sub-note: *M4a (Circle/Polygon/2-Point Arc) ✅ shipped v0.1.0; M4b–M4e pending.*

- [ ] **Step 3: Rebuild the editable install at the new version & verify**

Run:
`.venv\Scripts\python.exe -m pip install -e . --no-build-isolation`
`.venv\Scripts\python.exe -c "import pluton; print('core version:', pluton.__version__ if hasattr(pluton,'__version__') else pluton._core.version())"`
Expected: prints `0.1.0`.

- [ ] **Step 4: Full suite once more (release gate)**

Run: `.venv\Scripts\python.exe -m pytest -q` → all green.
Run the C++ suite → 72/72.

- [ ] **Step 5: Commit the version bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "$(cat <<'EOF'
release: v0.1.0 (M4a — Circle/Polygon/2-Point Arc drawing tools)

First Phase 2 increment. Pure-Python drawing tools on ground/face planes with
snap-driven precision (VCB deferred to M4d). Enters the v0.1 minor band.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push and watch CI**

```bash
git push origin main
```
Watch the run to completion (both `windows-2022` and `ubuntu-24.04`):
`gh run watch $(gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status`
Expected: `completed / success` on both jobs. If red, fix forward (no force-push).

- [ ] **Step 7: Tag the release (annotated, SSH-signed)**

```bash
git tag -a v0.1.0-m4a -m "M4a — Circle/Polygon/2-Point Arc drawing tools (v0.1.0)"
git cat-file -t v0.1.0-m4a   # expect: tag
git push origin v0.1.0-m4a
```

- [ ] **Step 8: File carry-over issues**

Using `gh issue create`, file:
- **3-Point Arc + Pie gestures** (fast-follow; reference the M4a design §2 non-goals).
- **2-Point Arc edge-tangency** (deferred D8 stretch).
- **Curve-as-logical-entity** (grouped circle/arc segments; depends on M4e grouping).

Already-tracked elsewhere (do **not** re-file): VCB/typed entry + inscribed-circumscribed toggle (M4d), smooth/softened shading (M5), face-split-on-draw ([#27]).

- [ ] **Step 9: Mark the milestone complete**

Report the tag, CI status, and test counts. M4a done; v0.1.0 cut.

---

## Self-review (completed during authoring)

- **Spec coverage:** Circle (Tasks 2,5), Polygon incl. inscribed + side adjust (Tasks 2,6), 2-Point Arc incl. free-bulge + semicircle snap (Tasks 3,7), draw-on-ground/face plane resolution (Tasks 1,4), mouse+snap precision/no-VCB (all tool tasks), atomic undo via CompositeCommand (Task 4 + each tool test), faceted output / no face-cut #27 (Task 9 manual check + Task 10 issues), C/G/A + Up/Down wiring (Task 8), v0.1.0 release (Task 10). Tangency (D8) explicitly deferred with an issue — noted in Task 7 and Task 10.
- **Placeholders:** none — every code step carries complete code; every run step an exact command + expected result.
- **Type/name consistency:** `DrawingPlane.horizontal/from_normal/from_face/to_world/project`; `circle(radius,segments,start_angle)`, `polygon(radius,sides,start_angle)`, `arc_2pt(start_uv,end_uv,bulge_uv,segments)`, `semicircle_snap(...)`; `resolve_drawing_plane`, `build_closed_face`, `build_open_polyline`, `polyline_segments`; `_on_tool_key` — all used consistently across tasks. Tool API matches `Tool` ABC (`overlay()` method; `anchor_or_none`/`status_text` properties; `has_active_gesture`).

---

*End of M4a plan.*

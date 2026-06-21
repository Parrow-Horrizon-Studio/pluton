# M5b — Materials (solid color + paint tool) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named solid-color materials, a dockable Materials palette, and a Paint tool (B) that assigns the active material to single faces — with no shader change and no C++ kernel change.

**Architecture:** Material data is a Python-side sidecar (`face_id → material_id`) on each Definition's `Scene`, plus a per-`Model` `MaterialLibrary`. Per-face color is rendered by **batching a definition's triangles by material** (a pure `plan_face_batches` function) and drawing one batch per material through M5a's existing `resolve_face_pass`. A zero-painted model collapses to a single Default batch, byte-identical to v0.1.5.

**Tech Stack:** Python 3.13, numpy, PySide6 (Qt), PyOpenGL, pytest + pytest-qt. C++/nanobind kernel is **untouched**.

**Spec:** `docs/2026-06-22-M5b-materials-design.md`

## Global Constraints

- **Python interpreter / tests:** use `.venv/Scripts/python` explicitly (bash) — a bare `python`/`pytest` resolves to a drifting editable install. Run tests as `.venv/Scripts/python -m pytest …`.
- **Ruff:** the repo selects `["E","F","W","I","N","UP","B","C4","RUF"]`. **Never run `ruff --fix` broadly** — it strips intentional `# noqa: ANN001` comments (issue #48) the project deliberately keeps. Fix lint by hand; only run `ruff --fix` on a brand-new file with no intentional `noqa`.
- **Git:** work on `main` (no feature branches). Stage **specific files only** — never `git add -A` / `git add .`. **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay on). End every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **No C++ kernel changes.** No edits under `cpp/`. No version-file edits (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) except in Task 10 (release).
- **Regression invariant:** a model with zero painted faces must render **byte-identical to v0.1.5** (one Default batch → `_DEFAULT_MATERIAL`, no shader change). Full suite (593 pytest + 76/76 ctest) stays green; new tests add on top.
- **DEFAULT sentinel:** material id `0` means "unpainted / Default" everywhere. It is never stored in a face map.

---

### Task 1: `Material` + `MaterialLibrary`

**Files:**
- Create: `python/pluton/model/material.py`
- Test: `tests/test_material_library.py`

**Interfaces:**
- Produces:
  - `Material(id: int, name: str, color: tuple[float,float,float])` — frozen dataclass.
  - `MaterialLibrary` with `DEFAULT_ID = 0`, `materials() -> list[Material]` (Default first), `get(mid: int) -> Material` (falls back to Default for unknown ids), `add_custom(name: str, color) -> Material` (fresh monotonic id).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_material_library.py
from __future__ import annotations

import pytest
from pluton.model.material import Material, MaterialLibrary


def test_default_material_is_first_with_default_id():
    lib = MaterialLibrary()
    mats = lib.materials()
    assert MaterialLibrary.DEFAULT_ID == 0
    assert mats[0].id == 0
    assert mats[0].name == "Default"


def test_builtin_palette_seeded_with_contiguous_monotonic_ids():
    lib = MaterialLibrary()
    ids = [m.id for m in lib.materials()]
    assert len(ids) >= 9                      # Default + >= 8 builtins
    assert ids == list(range(len(ids)))       # 0..N contiguous & ascending


def test_get_returns_material_by_id():
    lib = MaterialLibrary()
    brick = next(m for m in lib.materials() if m.name == "Brick Red")
    assert lib.get(brick.id) is brick


def test_get_unknown_id_falls_back_to_default():
    lib = MaterialLibrary()
    assert lib.get(9999).id == MaterialLibrary.DEFAULT_ID


def test_add_custom_appends_with_fresh_id_and_keeps_default_first():
    lib = MaterialLibrary()
    before = len(lib.materials())
    mat = lib.add_custom("#A1B2C3", (0.63, 0.70, 0.76))
    assert mat.id == before                   # next id == old count
    assert lib.get(mat.id) is mat
    assert lib.materials()[-1] is mat
    assert lib.materials()[0].id == MaterialLibrary.DEFAULT_ID


def test_material_is_frozen():
    m = Material(1, "X", (0.1, 0.2, 0.3))
    with pytest.raises(Exception):
        m.color = (0.0, 0.0, 0.0)  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_material_library.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.model.material'`

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/model/material.py
"""Solid-color materials + the per-Model material library (M5b).

Pure Python — no GL, no Qt — so it is fully unit-testable headlessly. A
Material is a named base RGB color; faces reference materials by id (see
Scene._face_materials). The library owns the canonical colors and is
serialization-ready for M6 file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Material:
    """A named solid-color material. `color` is base RGB in 0..1 (opaque)."""

    id: int
    name: str
    color: tuple[float, float, float]


# The Default swatch color mirrors the renderer's default diffuse
# (scene_renderer._MATERIAL_DIFFUSE). Duplicated as a literal to avoid a
# viewport -> model import; used only for the dock swatch / hover preview,
# never for face shading (the renderer shades the Default batch with
# _DEFAULT_MATERIAL directly).
_DEFAULT_SWATCH_COLOR = (0.65, 0.65, 0.70)

# Built-in palette seeded into every MaterialLibrary (stable ids 1..N).
_BUILTIN_PALETTE: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("White", (0.92, 0.92, 0.92)),
    ("Warm Gray", (0.66, 0.63, 0.60)),
    ("Concrete", (0.74, 0.73, 0.71)),
    ("Brick Red", (0.70, 0.27, 0.22)),
    ("Wood Tan", (0.78, 0.62, 0.40)),
    ("Slate Blue", (0.36, 0.45, 0.60)),
    ("Forest Green", (0.27, 0.50, 0.31)),
    ("Charcoal", (0.22, 0.22, 0.24)),
)


class MaterialLibrary:
    """Owns the model's Material objects: Default first, then builtins, then customs."""

    DEFAULT_ID = 0

    def __init__(self) -> None:
        self._default = Material(self.DEFAULT_ID, "Default", _DEFAULT_SWATCH_COLOR)
        self._materials: dict[int, Material] = {self.DEFAULT_ID: self._default}
        self._order: list[int] = [self.DEFAULT_ID]
        self._next_id = 1
        for name, color in _BUILTIN_PALETTE:
            self._add(name, color)

    def _add(self, name: str, color: tuple[float, float, float]) -> Material:
        mat = Material(self._next_id, name, (float(color[0]), float(color[1]), float(color[2])))
        self._materials[mat.id] = mat
        self._order.append(mat.id)
        self._next_id += 1
        return mat

    def add_custom(self, name: str, color: tuple[float, float, float]) -> Material:
        """Append a new material with a fresh monotonic id and return it."""
        return self._add(name, color)

    def get(self, mid: int) -> Material:
        """Return the material for `mid`, or the Default material if unknown."""
        return self._materials.get(mid, self._default)

    def materials(self) -> list[Material]:
        """All materials in display order (Default first)."""
        return [self._materials[i] for i in self._order]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_material_library.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Lint the new files**

Run: `.venv/Scripts/python -m ruff check python/pluton/model/material.py tests/test_material_library.py`
Expected: no errors. (Safe to `ruff --fix` these two NEW files only if I001 import-sort flags.)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/model/material.py tests/test_material_library.py
git commit -m "$(printf 'feat(m5b): Material value object + MaterialLibrary palette\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: Rename `render_style.Material → PhongMaterial` + add `phong_material_for`

**Files:**
- Modify: `python/pluton/viewport/render_style.py` (rename class; add converter + constants)
- Modify: `python/pluton/viewport/scene_renderer.py:22` (import) and `:109` (`_DEFAULT_MATERIAL`)
- Test: `tests/test_phong_material_for.py`

**Interfaces:**
- Consumes: `render_style.PhongMaterial` (renamed from `Material`).
- Produces:
  - `PhongMaterial(ambient, diffuse, specular, shininess)` (renamed class; identical fields).
  - `phong_material_for(color: tuple[float,float,float]) -> PhongMaterial`.
  - module constants `_AMBIENT_FACTOR`, `_DEFAULT_SPECULAR`, `_DEFAULT_SHININESS`.

This is a **purely nominal** rename plus a new pure function. No behavior changes; all existing M5a tests must stay green.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_phong_material_for.py
from __future__ import annotations

from pluton.viewport.render_style import (
    PhongMaterial,
    _AMBIENT_FACTOR,
    _DEFAULT_SHININESS,
    _DEFAULT_SPECULAR,
    phong_material_for,
)


def test_phong_material_for_maps_color_to_uniforms():
    pm = phong_material_for((0.70, 0.27, 0.22))
    assert isinstance(pm, PhongMaterial)
    assert pm.diffuse == (0.70, 0.27, 0.22)
    assert pm.ambient == (0.70 * _AMBIENT_FACTOR, 0.27 * _AMBIENT_FACTOR, 0.22 * _AMBIENT_FACTOR)
    assert pm.specular == _DEFAULT_SPECULAR
    assert pm.shininess == _DEFAULT_SHININESS


def test_defaults_mirror_scene_renderer_constants():
    # Guard against drift between the painted-face look and the default look.
    from pluton.viewport.scene_renderer import _MATERIAL_SHININESS, _MATERIAL_SPECULAR
    assert _DEFAULT_SPECULAR == _MATERIAL_SPECULAR
    assert _DEFAULT_SHININESS == _MATERIAL_SHININESS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_phong_material_for.py -v`
Expected: FAIL with `ImportError: cannot import name 'phong_material_for'`

- [ ] **Step 3: Rename the class and add the converter in `render_style.py`**

Rename the class `Material` → `PhongMaterial` (the dataclass currently at lines 57–64) and update the two type hints that reference it:

```python
@dataclass(frozen=True)
class PhongMaterial:
    """A phong material's color terms (ambient/diffuse/specular/shininess)."""

    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float
```

In `face_uniforms(...)` change the parameter type `material: Material` → `material: PhongMaterial`. In `resolve_face_pass(...)` change `material: Material` → `material: PhongMaterial`.

Then append the converter + constants at the end of the module:

```python
# --- M5b: painted-material -> phong uniforms -------------------------------
# These mirror scene_renderer._MATERIAL_SPECULAR / _MATERIAL_SHININESS so a
# painted face gets the same highlight character as the default look; only the
# hue varies. Duplicated here (not imported) to keep render_style import-free
# of the GL renderer. A guard test asserts they stay in sync.
_AMBIENT_FACTOR = 0.55
_DEFAULT_SPECULAR = (0.10, 0.10, 0.10)
_DEFAULT_SHININESS = 16.0


def phong_material_for(color: tuple[float, float, float]) -> PhongMaterial:
    """Map a painted base RGB to phong uniforms.

    diffuse = color; ambient = color * _AMBIENT_FACTOR; specular/shininess are
    the shared defaults. Does NOT reproduce _DEFAULT_MATERIAL (whose terms are
    hand-tuned); unpainted faces keep using _DEFAULT_MATERIAL directly.
    """
    r, g, b = float(color[0]), float(color[1]), float(color[2])
    return PhongMaterial(
        ambient=(r * _AMBIENT_FACTOR, g * _AMBIENT_FACTOR, b * _AMBIENT_FACTOR),
        diffuse=(r, g, b),
        specular=_DEFAULT_SPECULAR,
        shininess=_DEFAULT_SHININESS,
    )
```

- [ ] **Step 4: Update `scene_renderer.py` for the rename**

At the import block (lines 21–26) change `Material,` → `PhongMaterial,`:

```python
from pluton.viewport.render_style import (
    PhongMaterial,
    RenderStyle,
    ResolvedFacePass,
    resolve_face_pass,
)
```

At `_DEFAULT_MATERIAL` (line 109) change the constructor name:

```python
_DEFAULT_MATERIAL = PhongMaterial(
    ambient=_MATERIAL_AMBIENT,
    diffuse=_MATERIAL_DIFFUSE,
    specular=_MATERIAL_SPECULAR,
    shininess=_MATERIAL_SHININESS,
)
```

Verify no other reference to the old name remains:

Run: `.venv/Scripts/python -m ruff check python/pluton/viewport/render_style.py python/pluton/viewport/scene_renderer.py`
Also grep: `git grep -n "render_style import" -- python | grep -w Material` should return nothing.

- [ ] **Step 5: Run the new tests + the full M5a regression**

Run: `.venv/Scripts/python -m pytest tests/test_phong_material_for.py tests/test_render_style.py tests/test_scene_renderer_style.py tests/test_phong_alpha_uniform.py tests/test_view_menu.py -v`
Expected: PASS (all M5a style tests still green + 2 new tests pass)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/render_style.py python/pluton/viewport/scene_renderer.py tests/test_phong_material_for.py
git commit -m "$(printf 'refactor(m5b): rename render_style.Material -> PhongMaterial; add phong_material_for\n\nNominal rename + a pure painted-color->phong-uniforms converter. No\nbehavior change; M5a style tests unchanged.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: `Scene` materials sidecar + `_render_dirty` + `face_triangle_materials`

**Files:**
- Modify: `python/pluton/scene/scene.py` (`__init__`, `mark_clean`, `dirty`; add 4 methods + a module constant)
- Test: `tests/test_scene_materials.py`

**Interfaces:**
- Produces (on `Scene`):
  - `set_face_material(f_id: int, material_id: int) -> None` (material_id 0 clears)
  - `clear_face_material(f_id: int) -> None`
  - `face_material(f_id: int) -> int` (returns 0 when unpainted)
  - `face_triangle_materials() -> np.ndarray` (int64, length T, aligned 1:1 with `face_triangle_buffer()`)
  - `dirty` now returns `mesh.is_dirty() or _render_dirty`; `mark_clean()` clears both.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scene_materials.py
from __future__ import annotations

import numpy as np
from pluton.scene.scene import Scene


def _two_face_scene():
    """Two triangular faces sharing an edge: fa (lower id) then fb."""
    s = Scene()
    a = [
        s.add_vertex(np.array([0.0, 0.0, 0.0])),
        s.add_vertex(np.array([1.0, 0.0, 0.0])),
        s.add_vertex(np.array([0.0, 1.0, 0.0])),
    ]
    fa = s.add_face_from_loop(a)
    b = [a[1], s.add_vertex(np.array([1.0, 1.0, 0.0])), a[2]]
    fb = s.add_face_from_loop(b)
    return s, fa, fb


def test_face_material_defaults_to_zero():
    s, fa, fb = _two_face_scene()
    assert s.face_material(fa) == 0
    assert s.face_material(fb) == 0


def test_set_and_get_face_material():
    s, fa, fb = _two_face_scene()
    s.set_face_material(fa, 3)
    assert s.face_material(fa) == 3
    assert s.face_material(fb) == 0


def test_set_default_id_clears():
    s, fa, _ = _two_face_scene()
    s.set_face_material(fa, 3)
    s.set_face_material(fa, 0)
    assert s.face_material(fa) == 0


def test_clear_face_material():
    s, fa, _ = _two_face_scene()
    s.set_face_material(fa, 5)
    s.clear_face_material(fa)
    assert s.face_material(fa) == 0


def test_paint_marks_render_dirty_and_mark_clean_clears():
    s, fa, _ = _two_face_scene()
    s.mark_clean()
    assert s.dirty is False
    s.set_face_material(fa, 2)
    assert s.dirty is True
    s.mark_clean()
    assert s.dirty is False


def test_face_triangle_materials_aligns_one_to_one_with_buffer():
    s, fa, fb = _two_face_scene()
    s.set_face_material(fb, 7)
    positions, _ = s.face_triangle_buffer()
    tri_mats = s.face_triangle_materials()
    assert tri_mats.shape[0] * 3 == positions.shape[0]
    assert tri_mats.tolist() == [0, 7]   # fa(default) then fb(7), ascending id order
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_scene_materials.py -v`
Expected: FAIL with `AttributeError: 'Scene' object has no attribute 'set_face_material'`

- [ ] **Step 3: Add a module constant + sidecar state in `Scene.__init__`**

Near the top of `scene.py` (module level, after imports) add:

```python
# Material id 0 == MaterialLibrary.DEFAULT_ID: the "unpainted / standard look"
# sentinel. Kept as a literal to avoid a scene -> model import.
_DEFAULT_MATERIAL_ID = 0
```

In `Scene.__init__` (currently sets `self._mesh = HalfEdgeMesh()`), add:

```python
        self._face_materials: dict[int, int] = {}
        self._render_dirty = False
```

- [ ] **Step 4: Add the four methods + update `dirty` / `mark_clean`**

Add these methods to `Scene` (place them near the render-buffer section):

```python
    def set_face_material(self, f_id: int, material_id: int) -> None:
        """Paint a face. material_id 0 (Default) clears any existing paint."""
        if material_id == _DEFAULT_MATERIAL_ID:
            self.clear_face_material(f_id)
            return
        self._face_materials[f_id] = material_id
        self._render_dirty = True

    def clear_face_material(self, f_id: int) -> None:
        """Remove any material from a face (return it to the default look)."""
        if self._face_materials.pop(f_id, None) is not None:
            self._render_dirty = True

    def face_material(self, f_id: int) -> int:
        """Return the material id painted on a face, or 0 (Default) if unpainted."""
        return self._face_materials.get(f_id, _DEFAULT_MATERIAL_ID)

    def face_triangle_materials(self) -> np.ndarray:
        """Per-triangle material id, aligned 1:1 with face_triangle_buffer().

        Walks live faces in next_live_face ascending order (the exact order the
        C++ face_triangle_buffer uses) and repeats each face's material id by
        its triangle count.
        """
        mats: list[int] = []
        f = self._mesh.next_live_face(0)
        while f != HalfEdgeMesh.INVALID_ID:
            n_tris = len(self._mesh.face_triangles(f)) // 3
            mats.extend([self._face_materials.get(f, _DEFAULT_MATERIAL_ID)] * n_tris)
            f = self._mesh.next_live_face(f + 1)
        return np.asarray(mats, dtype=np.int64)
```

Update `mark_clean` (currently `self._mesh.mark_clean()`):

```python
    def mark_clean(self) -> None:
        self._mesh.mark_clean()
        self._render_dirty = False
```

Update the `dirty` property body (currently `return self._mesh.is_dirty()`):

```python
        return self._mesh.is_dirty() or self._render_dirty
```

- [ ] **Step 5: Run tests + scene regression**

Run: `.venv/Scripts/python -m pytest tests/test_scene_materials.py -v`
Expected: PASS (6 passed)

Run: `.venv/Scripts/python -m pytest tests/ -k "scene" -q`
Expected: PASS (existing scene tests still green)

- [ ] **Step 6: Lint (hand-fix only — do NOT broad `ruff --fix`, scene.py carries intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/scene/scene.py tests/test_scene_materials.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene_materials.py
git commit -m "$(printf 'feat(m5b): per-face material sidecar on Scene + render-dirty + face_triangle_materials\n\nMaterial map keyed by face id (ids never reused, so erase/undo restores\npaint for free). _render_dirty composes with the C++ dirty flag so a\npaint triggers a buffer rebuild. No C++ change.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: `plan_face_batches` (pure batching seam)

**Files:**
- Create: `python/pluton/viewport/face_batches.py`
- Test: `tests/test_face_batches.py`

**Interfaces:**
- Produces:
  - `FaceBatch(material_id: int, first: int, count: int)` — frozen dataclass; `first`/`count` are vertex indices/counts (multiples of 3).
  - `plan_face_batches(triangle_material_ids: Sequence[int]) -> tuple[np.ndarray, list[FaceBatch]]` — returns `(vertex_order, batches)`. `vertex_order` is an int64 permutation of `0..3T-1`; `batches` are in ascending material-id order; both empty when `T == 0`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_face_batches.py
from __future__ import annotations

from pluton.viewport.face_batches import FaceBatch, plan_face_batches


def test_empty_returns_no_batches():
    order, batches = plan_face_batches([])
    assert order.tolist() == []
    assert batches == []


def test_single_material_one_batch_identity_order():
    order, batches = plan_face_batches([0, 0, 0])      # 3 triangles, all Default
    assert order.tolist() == list(range(9))            # identity over 9 vertices
    assert batches == [FaceBatch(material_id=0, first=0, count=9)]


def test_default_only_collapses_to_one_default_batch():
    order, batches = plan_face_batches([0, 0, 0, 0])
    assert batches == [FaceBatch(material_id=0, first=0, count=12)]
    assert order.tolist() == list(range(12))           # identity → byte-identical path


def test_interleaved_materials_grouped_and_contiguous():
    # triangles: mat 2, mat 0, mat 2, mat 0  -> grouped 0,0 then 2,2
    order, batches = plan_face_batches([2, 0, 2, 0])
    assert batches == [
        FaceBatch(material_id=0, first=0, count=6),
        FaceBatch(material_id=2, first=6, count=6),
    ]
    # mat-0 tris are originals 1 and 3 (verts 3,4,5 and 9,10,11), then mat-2.
    assert order.tolist() == [3, 4, 5, 9, 10, 11, 0, 1, 2, 6, 7, 8]


def test_vertex_order_is_a_valid_permutation():
    order, _ = plan_face_batches([5, 1, 5, 1, 9])
    assert sorted(order.tolist()) == list(range(15))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_face_batches.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.viewport.face_batches'`

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/viewport/face_batches.py
"""Group a definition's triangles by material into contiguous draw batches (M5b).

Pure Python + numpy — no GL — so it is fully unit-testable headlessly. The
renderer reorders its interleaved face VBO by `vertex_order` so each material's
triangles are contiguous, then issues one glDrawArrays per FaceBatch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class FaceBatch:
    """A contiguous run of same-material vertices in the (reordered) face VBO."""

    material_id: int
    first: int   # first vertex index
    count: int   # vertex count (a multiple of 3)


def plan_face_batches(
    triangle_material_ids: Sequence[int],
) -> tuple[np.ndarray, list[FaceBatch]]:
    """Stable-sort triangles by material id into contiguous batches.

    Args:
        triangle_material_ids: material id of each triangle, length T, in
            face-VBO order (e.g. Scene.face_triangle_materials()).

    Returns:
        vertex_order: int64 permutation of 0..3T-1 to apply to the (3T, .)
            vertex arrays so each material's triangles are contiguous. Identity
            when triangles are already grouped (e.g. all one material).
        batches: one FaceBatch per distinct material, ascending by material id.
            Empty when T == 0.
    """
    tri_mats = np.asarray(triangle_material_ids, dtype=np.int64)
    t = int(tri_mats.shape[0])
    if t == 0:
        return np.zeros(0, dtype=np.int64), []

    tri_order = np.argsort(tri_mats, kind="stable")          # stable: keeps in-group order
    sorted_mats = tri_mats[tri_order]
    vertex_order = (tri_order[:, None] * 3 + np.arange(3)).reshape(-1).astype(np.int64)

    batches: list[FaceBatch] = []
    uniq, starts = np.unique(sorted_mats, return_index=True)  # ascending mat id, group starts
    for k, mid in enumerate(uniq):
        tri_start = int(starts[k])
        tri_end = int(starts[k + 1]) if k + 1 < len(starts) else t
        n_tris = tri_end - tri_start
        batches.append(FaceBatch(material_id=int(mid), first=tri_start * 3, count=n_tris * 3))
    return vertex_order, batches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_face_batches.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Lint**

Run: `.venv/Scripts/python -m ruff check python/pluton/viewport/face_batches.py tests/test_face_batches.py`
Expected: no errors. (Safe to `ruff --fix` these two NEW files only if I001 flags.)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/face_batches.py tests/test_face_batches.py
git commit -m "$(printf 'feat(m5b): plan_face_batches pure batching seam (group triangles by material)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: Renderer applies material batches

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py` (`_DefBuffers`; imports; `_upload_definition`; `render()` per-definition loop; `_draw_definition_faces`)
- Test: `tests/test_scene_renderer_batches.py`

**Interfaces:**
- Consumes: `face_batches.FaceBatch`, `face_batches.plan_face_batches`, `render_style.phong_material_for`, `model.materials` (Task 8 adds `Model.materials`; until then the loop guards on `getattr`), `Scene.face_triangle_materials`.
- Produces: `_DefBuffers.batches: list[FaceBatch]`; `_draw_definition_faces(..., *, resolved, first, count)`.

This is a large-file, regression-critical GL edit. The byte-identical invariant (zero paint → one Default batch) is the acceptance bar.

- [ ] **Step 1: Write the failing test (buffer-level, no GL context needed)**

This test drives `plan_face_batches` through a `Scene` exactly as `_upload_definition` will, asserting the batch plan the renderer will consume. It does not open a GL context.

```python
# tests/test_scene_renderer_batches.py
from __future__ import annotations

import numpy as np
from pluton.scene.scene import Scene
from pluton.viewport.face_batches import plan_face_batches


def _two_face_scene():
    s = Scene()
    a = [
        s.add_vertex(np.array([0.0, 0.0, 0.0])),
        s.add_vertex(np.array([1.0, 0.0, 0.0])),
        s.add_vertex(np.array([0.0, 1.0, 0.0])),
    ]
    fa = s.add_face_from_loop(a)
    b = [a[1], s.add_vertex(np.array([1.0, 1.0, 0.0])), a[2]]
    fb = s.add_face_from_loop(b)
    return s, fa, fb


def test_unpainted_scene_yields_single_default_batch():
    s, _, _ = _two_face_scene()
    order, batches = plan_face_batches(s.face_triangle_materials())
    assert len(batches) == 1
    assert batches[0].material_id == 0
    assert batches[0].first == 0
    # identity reorder => byte-identical draw path
    assert order.tolist() == list(range(order.shape[0]))


def test_painted_scene_splits_into_per_material_batches():
    s, fa, fb = _two_face_scene()
    s.set_face_material(fb, 7)
    order, batches = plan_face_batches(s.face_triangle_materials())
    assert [b.material_id for b in batches] == [0, 7]
    assert sum(b.count for b in batches) * 1 == order.shape[0]
```

- [ ] **Step 2: Run to verify it passes already (it exercises Tasks 3+4)**

Run: `.venv/Scripts/python -m pytest tests/test_scene_renderer_batches.py -v`
Expected: PASS (this pins the contract the renderer edit must honor). If it fails, Tasks 3/4 are wrong — fix before editing the renderer.

- [ ] **Step 3: Add `batches` to `_DefBuffers` and update imports**

In `scene_renderer.py`, extend the import from `face_batches` and `render_style`:

```python
from pluton.viewport.face_batches import FaceBatch, plan_face_batches
from pluton.viewport.render_style import (
    PhongMaterial,
    RenderStyle,
    ResolvedFacePass,
    phong_material_for,
    resolve_face_pass,
)
```

Extend `_DefBuffers` (add a field; keep `face_count`):

```python
@dataclass
class _DefBuffers:
    """Per-definition GL buffer handles and vertex counts."""
    face_vao: int = 0
    face_vbo: int = 0
    face_count: int = 0  # number of triangle vertices
    edge_vao: int = 0
    edge_vbo: int = 0
    edge_count: int = 0  # number of line-segment vertices
    batches: list = field(default_factory=list)  # list[FaceBatch], one per material
```

(`field` is already imported on line 13.)

- [ ] **Step 4: Reorder triangles by material in `_upload_definition`**

In `_upload_definition`, the face block currently builds `interleaved` (3T,6) and uploads it. Replace that block so it reorders by material and records batches:

```python
        # Faces: (3*T, 3) positions + (3*T, 3) normals -> interleaved (3*T, 6)
        positions, normals = scene.face_triangle_buffer()
        if positions.shape[0] > 0:
            interleaved = np.concatenate([positions, normals], axis=1).astype(np.float32)
            # Group triangles by material so each material draws as one contiguous batch.
            tri_mats = scene.face_triangle_materials()
            vertex_order, batches = plan_face_batches(tri_mats)
            interleaved = interleaved[vertex_order]
            data = np.ascontiguousarray(interleaved)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.face_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            buf.face_count = int(positions.shape[0])
            buf.batches = batches
        else:
            buf.face_count = 0
            buf.batches = []
```

- [ ] **Step 5: Replace the per-definition face draw in `render()` with a per-batch loop**

In `render()`, replace the single `resolve_face_pass(...)` + `_draw_definition_faces(...)` block (currently the `resolved = resolve_face_pass(...)` assignment and the `if resolved.draw_faces and buf.face_count > 0:` call) with:

```python
                materials = getattr(model, "materials", None)
                for batch in buf.batches:
                    if batch.material_id != 0 and materials is not None:
                        mat = phong_material_for(materials.get(batch.material_id).color)
                    else:
                        mat = _DEFAULT_MATERIAL
                    resolved = resolve_face_pass(
                        self._render_style,
                        dimmed=dimmed,
                        bg=_BG_COLOR[:3],
                        material=mat,
                        dim_ambient=_DIM_AMBIENT,
                        dim_diffuse=_DIM_DIFFUSE,
                        dim_alpha=_DIM_ALPHA_BLEND,
                    )
                    if resolved.draw_faces and batch.count > 0:
                        self._draw_definition_faces(
                            buf, view, projection, camera.position, model_mat,
                            resolved=resolved, first=batch.first, count=batch.count,
                        )
```

(`dimmed = definition_is_dimmed(definition, model)` stays where it is, just above this block. The edge pass below is unchanged.)

- [ ] **Step 6: Give `_draw_definition_faces` a `first`/`count` range**

Change its signature and the draw call. Currently it takes `*, resolved: ResolvedFacePass` and calls `glDrawArrays(GL_TRIANGLES, 0, buf.face_count)`. Make it:

```python
    def _draw_definition_faces(
        self,
        buf: _DefBuffers,
        view: np.ndarray,
        projection: np.ndarray,
        camera_pos: np.ndarray,
        model_mat: np.ndarray,
        *,
        resolved: ResolvedFacePass,
        first: int = 0,
        count: int | None = None,
    ) -> None:
```

and the draw call:

```python
        GL.glBindVertexArray(buf.face_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, first, buf.face_count if count is None else count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
```

(Everything else in the method — uniforms, blend/depth-mask enable+restore — is unchanged.)

- [ ] **Step 7: Run the full suite (renderer regression)**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (full suite green, including the new batch test and all M5a renderer tests).

- [ ] **Step 8: Verify the byte-identical net diff by inspection**

Run: `git diff -- python/pluton/viewport/scene_renderer.py`
Confirm: (a) the default branch uses `_DEFAULT_MATERIAL`; (b) `vertex_order` is identity for unpainted scenes (guaranteed by Task 4); (c) no `# noqa: ANN001` comments were deleted; (d) blend/depth-mask restore is untouched.

- [ ] **Step 9: Lint (hand-fix only — scene_renderer.py carries intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/viewport/scene_renderer.py tests/test_scene_renderer_batches.py`
Expected: no errors. If `ruff --fix` is tempting, DON'T — restore any stripped `# noqa: ANN001` by hand (issue #48).

- [ ] **Step 10: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py tests/test_scene_renderer_batches.py
git commit -m "$(printf 'feat(m5b): renderer draws per-material face batches via resolve_face_pass\n\nOne glDrawArrays per material per definition; unpainted scenes collapse\nto a single Default batch with identity reorder -> byte-identical to\nv0.1.5. No shader change.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 6: `PaintFaceCommand`

**Files:**
- Create: `python/pluton/commands/material_commands.py`
- Test: `tests/test_paint_face_command.py`

**Interfaces:**
- Consumes: `Command` base (`pluton.commands.command.Command`); `Scene.face_material/set_face_material/clear_face_material` (Task 3).
- Produces: `PaintFaceCommand(face_id: int, new_material_id: int)` with `do(scene)` / `undo(scene)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_paint_face_command.py
from __future__ import annotations

import numpy as np
from pluton.commands.material_commands import PaintFaceCommand
from pluton.scene.scene import Scene


def _one_face_scene():
    s = Scene()
    v = [
        s.add_vertex(np.array([0.0, 0.0, 0.0])),
        s.add_vertex(np.array([1.0, 0.0, 0.0])),
        s.add_vertex(np.array([0.0, 1.0, 0.0])),
    ]
    return s, s.add_face_from_loop(v)


def test_do_paints_and_undo_restores_default():
    s, f = _one_face_scene()
    cmd = PaintFaceCommand(f, 4)
    cmd.do(s)
    assert s.face_material(f) == 4
    cmd.undo(s)
    assert s.face_material(f) == 0


def test_overpaint_undo_restores_previous_material():
    s, f = _one_face_scene()
    s.set_face_material(f, 2)
    cmd = PaintFaceCommand(f, 9)
    cmd.do(s)
    assert s.face_material(f) == 9
    cmd.undo(s)
    assert s.face_material(f) == 2


def test_paint_default_clears_and_undo_restores():
    s, f = _one_face_scene()
    s.set_face_material(f, 6)
    cmd = PaintFaceCommand(f, 0)        # paint Default -> clear
    cmd.do(s)
    assert s.face_material(f) == 0
    cmd.undo(s)
    assert s.face_material(f) == 6


def test_redo_after_undo_is_idempotent():
    s, f = _one_face_scene()
    cmd = PaintFaceCommand(f, 5)
    cmd.do(s)
    cmd.undo(s)
    cmd.do(s)
    assert s.face_material(f) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_paint_face_command.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.commands.material_commands'`

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/commands/material_commands.py
"""Material commands (M5b): PaintFaceCommand."""

from __future__ import annotations

from pluton.commands.command import Command

_DEFAULT_MATERIAL_ID = 0  # == MaterialLibrary.DEFAULT_ID (the unpainted sentinel)


def _apply(scene, f_id: int, material_id: int) -> None:  # noqa: ANN001
    if material_id == _DEFAULT_MATERIAL_ID:
        scene.clear_face_material(f_id)
    else:
        scene.set_face_material(f_id, material_id)


class PaintFaceCommand(Command):
    """Assign a material to one face; undo restores the prior material.

    Captures the previous material at do() time (id-preserving undo). Painting
    the Default material (id 0) clears any paint; undo restores it exactly.
    """

    name = "Paint Face"

    def __init__(self, face_id: int, new_material_id: int) -> None:
        self._fid = face_id
        self._new = new_material_id
        self._old: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._old = scene.face_material(self._fid)
        _apply(scene, self._fid, self._new)

    def undo(self, scene) -> None:  # noqa: ANN001
        _apply(scene, self._fid, self._old if self._old is not None else _DEFAULT_MATERIAL_ID)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_paint_face_command.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint**

Run: `.venv/Scripts/python -m ruff check python/pluton/commands/material_commands.py tests/test_paint_face_command.py`
Expected: no errors. (Note the intentional `# noqa: ANN001` on `_apply` / `do` / `undo` — keep them; scene params are untyped by repo convention.)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/material_commands.py tests/test_paint_face_command.py
git commit -m "$(printf 'feat(m5b): PaintFaceCommand (id-preserving undo for face paint)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 7: `ToolContext` hooks + `PaintTool` (B)

**Files:**
- Modify: `python/pluton/tools/tool.py` (add two `ToolContext` fields)
- Create: `python/pluton/tools/paint_tool.py`
- Test: `tests/test_paint_tool.py`

**Interfaces:**
- Consumes: `PaintFaceCommand` (Task 6); `pick_selectable`; `Material` (for the provider's return type); `CommandStack.push_executed`.
- Produces:
  - `ToolContext.active_material_provider: object = None` (callable `() -> Material`).
  - `ToolContext.set_active_material: object = None` (callable `(int) -> None`).
  - `PaintTool` (shortcut `"B"`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_paint_tool.py
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from pluton.model.material import Material
from pluton.tools import paint_tool as paint_tool_mod
from pluton.tools.paint_tool import PaintTool
from pluton.tools.tool import ToolContext


class _FakeScene:
    def __init__(self):
        self._mats: dict[int, int] = {}

    def face_material(self, fid):
        return self._mats.get(fid, 0)

    def set_face_material(self, fid, mid):
        if mid == 0:
            self._mats.pop(fid, None)
        else:
            self._mats[fid] = mid

    def clear_face_material(self, fid):
        self._mats.pop(fid, None)


class _FakeStack:
    def __init__(self):
        self.pushed: list = []

    def push_executed(self, cmd, target):
        self.pushed.append((cmd, target))


class _Event:
    def __init__(self, alt=False):
        self._alt = alt

    def position(self):
        return QPointF(10.0, 10.0)

    def modifiers(self):
        return Qt.KeyboardModifier.AltModifier if self._alt else Qt.KeyboardModifier.NoModifier


def _tool(monkeypatch, scene, stack, active_mat, pick=7):
    monkeypatch.setattr(
        paint_tool_mod, "pick_selectable",
        lambda *a, **k: ("face", pick) if pick is not None else None,
    )
    captured: dict = {}
    ctx = ToolContext(
        scene=scene,
        command_stack=stack,
        camera=object(),
        widget_size_provider=lambda: (100, 100),
        model=None,
        active_material_provider=lambda: active_mat,
        set_active_material=lambda mid: captured.__setitem__("sampled", mid),
    )
    t = PaintTool()
    t.activate(ctx)
    return t, captured


RED = Material(3, "Brick Red", (0.70, 0.27, 0.22))


def test_paint_pushes_command_and_applies(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(), snap=None)
    assert scene.face_material(7) == 3
    assert len(stack.pushed) == 1


def test_alt_click_samples_without_command(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 5)
    t, captured = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(alt=True), snap=None)
    assert captured["sampled"] == 5
    assert stack.pushed == []
    assert scene.face_material(7) == 5


def test_no_op_when_material_unchanged(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    scene.set_face_material(7, 3)
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=7)
    t.on_mouse_press(_Event(), snap=None)
    assert stack.pushed == []


def test_miss_does_nothing(monkeypatch):
    scene, stack = _FakeScene(), _FakeStack()
    t, _ = _tool(monkeypatch, scene, stack, RED, pick=None)
    t.on_mouse_press(_Event(), snap=None)
    assert stack.pushed == []


def test_shortcut_is_b():
    assert PaintTool().shortcut == "B"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_paint_tool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.tools.paint_tool'` (or a `ToolContext` TypeError for the new kwargs).

- [ ] **Step 3: Add the two fields to `ToolContext`**

In `tool.py`, add to the `ToolContext` dataclass (after `request_context_rebuild`):

```python
    active_material_provider: object = None  # M5b — callable () -> Material (active material)
    set_active_material: object = None       # M5b — callable (int) -> None (eyedropper -> dock)
```

- [ ] **Step 4: Write `PaintTool`**

```python
# python/pluton/tools/paint_tool.py
"""The Paint tool (B).

Click a face to apply the active material; Alt-click to sample (eyedropper)
the clicked face's material as the new active material. Painting the Default
material removes paint. Each paint is one undoable PaintFaceCommand.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.material_commands import PaintFaceCommand
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import pick_selectable

_HOVER_ALPHA = 0.45
_NEUTRAL_COLOR = (0.85, 0.85, 0.85)


class PaintTool(Tool):
    @property
    def name(self) -> str:
        return "Paint"

    @property
    def shortcut(self) -> str:
        return "B"

    def __init__(self) -> None:
        self._scene = None
        self._camera = None
        self._size_provider = None
        self._command_stack = None
        self._model = None
        self._active_material_provider = None
        self._set_active_material = None
        self._hovered_face: int | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._active_material_provider = ctx.active_material_provider
        self._set_active_material = ctx.set_active_material
        self._hovered_face = None

    def deactivate(self) -> None:
        self._hovered_face = None

    def _world_transform(self):  # noqa: ANN202
        return self._model.active_world_transform if self._model is not None else None

    def _viewport_size(self) -> tuple[int, int]:
        return self._size_provider() if self._size_provider is not None else (1, 1)

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return (float(pos.x()), float(pos.y()))

    def _pick_face(self, event: QMouseEvent) -> int | None:
        hit = pick_selectable(
            self._cursor(event), self._viewport_size(), self._camera, self._scene,
            world_transform=self._world_transform(),
        )
        return hit[1] if hit is not None and hit[0] == "face" else None

    def _active_material(self):  # noqa: ANN202
        if self._active_material_provider is None:
            return None
        return self._active_material_provider()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        self._hovered_face = self._pick_face(event)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        f_id = self._pick_face(event)
        if f_id is None or self._scene is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Eyedropper: sample the face's material. Not a mutation.
            if self._set_active_material is not None:
                self._set_active_material(self._scene.face_material(f_id))
            return
        mat = self._active_material()
        if mat is None or mat.id == self._scene.face_material(f_id):
            return  # no-op guard avoids empty undo entries
        if self._command_stack is not None:
            cmd = PaintFaceCommand(f_id, mat.id)
            cmd.do(self._scene)
            self._command_stack.push_executed(cmd, self._scene)

    def overlay(self) -> ToolOverlay:
        fills: list[np.ndarray] = []
        mat = self._active_material()
        tint = mat.color if mat is not None else _NEUTRAL_COLOR
        if self._hovered_face is not None and self._scene is not None:
            try:
                from pluton.geometry.transforms import apply_mat, is_identity_transform
                wt = self._world_transform()
                use_wt = not is_identity_transform(wt)
                wt_arr = np.asarray(wt, dtype=np.float64) if use_wt else None

                def _to_world(local_pos: np.ndarray) -> np.ndarray:
                    if not use_wt:
                        return local_pos
                    return apply_mat(local_pos.reshape(1, 3), wt_arr)[0]

                loop = self._scene.face_loop(self._hovered_face)
                fills.append(np.array(
                    [_to_world(np.asarray(self._scene.vertex(v).position, dtype=np.float32))
                     for v in loop],
                    dtype=np.float32,
                ))
            except KeyError:
                pass
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=_NEUTRAL_COLOR,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL_COLOR,
            snap_marker_kind=0,
            face_fill_polygons=fills,
            face_fill_color=(tint[0], tint[1], tint[2], _HOVER_ALPHA),
        )

    @property
    def has_active_gesture(self) -> bool:
        return False

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None

    def status_text(self) -> str | None:
        mat = self._active_material()
        name = mat.name if mat is not None else "Default"
        return f"Paint: {name} · Alt-click to sample"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_paint_tool.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Lint (hand-fix only — tool.py / paint_tool.py carry intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/tools/tool.py python/pluton/tools/paint_tool.py tests/test_paint_tool.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/tools/tool.py python/pluton/tools/paint_tool.py tests/test_paint_tool.py
git commit -m "$(printf 'feat(m5b): PaintTool (B) with click-paint, Alt-sample, hover preview\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 8: Materials dock + MainWindow wiring

**Files:**
- Create: `python/pluton/ui/materials_dock.py`
- Modify: `python/pluton/model/model.py` (add `self.materials = MaterialLibrary()`)
- Modify: `python/pluton/ui/main_window.py` (register `PaintTool`; build dock; wire `ToolContext` hooks + active id)
- Test: `tests/test_materials_dock.py`, `tests/test_main_window_materials.py`

**Interfaces:**
- Consumes: `MaterialLibrary`, `Material` (Task 1); `PaintTool` (Task 7); `ToolContext.active_material_provider/set_active_material` (Task 7).
- Produces: `MaterialsDock(library, parent=None)` with signal `active_material_changed(Material)`, `set_active(material_id)`, `active_material_id` property, `_buttons` dict (id→QPushButton), `_rebuild_swatches()`, `_on_pick(mid)`.

- [ ] **Step 1: Write the failing dock tests**

```python
# tests/test_materials_dock.py
from __future__ import annotations

import pytest
from pluton.model.material import MaterialLibrary
from pluton.ui.materials_dock import MaterialsDock


@pytest.fixture
def lib():
    return MaterialLibrary()


def test_dock_builds_a_swatch_per_material(qtbot, lib):
    dock = MaterialsDock(lib)
    qtbot.addWidget(dock)
    assert len(dock._buttons) == len(lib.materials())


def test_pick_changes_active_and_emits(qtbot, lib):
    dock = MaterialsDock(lib)
    qtbot.addWidget(dock)
    brick = next(m for m in lib.materials() if m.name == "Brick Red")
    with qtbot.waitSignal(dock.active_material_changed, timeout=500) as blocker:
        dock._on_pick(brick.id)
    assert dock.active_material_id == brick.id
    assert blocker.args[0].id == brick.id


def test_set_active_highlights(qtbot, lib):
    dock = MaterialsDock(lib)
    qtbot.addWidget(dock)
    forest = next(m for m in lib.materials() if m.name == "Forest Green")
    dock.set_active(forest.id)
    assert dock.active_material_id == forest.id


def test_add_custom_then_rebuild_grows_grid(qtbot, lib):
    dock = MaterialsDock(lib)
    qtbot.addWidget(dock)
    n = len(dock._buttons)
    mat = lib.add_custom("#abcdef", (0.67, 0.80, 0.94))
    dock._rebuild_swatches()
    assert len(dock._buttons) == n + 1
    assert mat.id in dock._buttons
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_materials_dock.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.ui.materials_dock'`

- [ ] **Step 3: Write `MaterialsDock`**

```python
# python/pluton/ui/materials_dock.py
"""The Materials dock (M5b): a swatch grid for choosing the active material."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QColorDialog,
    QDockWidget,
    QGridLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pluton.model.material import MaterialLibrary

_COLUMNS = 4


def _swatch_style(color: tuple[float, float, float], active: bool) -> str:
    r, g, b = (int(round(c * 255)) for c in color)
    border = "3px solid #2f8fff" if active else "1px solid #555"
    return (
        f"background-color: rgb({r},{g},{b}); border: {border}; "
        f"min-width: 36px; min-height: 28px;"
    )


class MaterialsDock(QDockWidget):
    """Swatch grid + custom-color button. Emits active_material_changed(Material)."""

    active_material_changed = Signal(object)  # emits a Material

    def __init__(self, library: MaterialLibrary, parent=None) -> None:  # noqa: ANN001
        super().__init__("Materials", parent)
        self._library = library
        self._active_id = MaterialLibrary.DEFAULT_ID
        self._buttons: dict[int, QPushButton] = {}

        container = QWidget(self)
        outer = QVBoxLayout(container)
        self._grid = QGridLayout()
        outer.addLayout(self._grid)
        custom = QPushButton("Custom color…", container)
        custom.clicked.connect(self._on_custom)
        outer.addWidget(custom)
        outer.addStretch(1)
        self.setWidget(container)

        self._rebuild_swatches()

    def _rebuild_swatches(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._buttons.clear()
        for idx, mat in enumerate(self._library.materials()):
            btn = QPushButton(self)
            btn.setToolTip(mat.name)
            btn.setStyleSheet(_swatch_style(mat.color, mat.id == self._active_id))
            btn.clicked.connect(lambda _checked=False, mid=mat.id: self._on_pick(mid))
            self._grid.addWidget(btn, idx // _COLUMNS, idx % _COLUMNS)
            self._buttons[mat.id] = btn

    def _restyle(self) -> None:
        for mid, btn in self._buttons.items():
            mat = self._library.get(mid)
            btn.setStyleSheet(_swatch_style(mat.color, mid == self._active_id))

    def _on_pick(self, material_id: int) -> None:
        self._active_id = material_id
        self._restyle()
        self.active_material_changed.emit(self._library.get(material_id))

    def _on_custom(self) -> None:
        qc = QColorDialog.getColor(parent=self)
        if not qc.isValid():
            return
        color = (qc.redF(), qc.greenF(), qc.blueF())
        mat = self._library.add_custom(qc.name(), color)  # name == hex "#rrggbb"
        self._rebuild_swatches()
        self._on_pick(mat.id)

    def set_active(self, material_id: int) -> None:
        """Update the highlighted swatch (used by the Paint tool's eyedropper)."""
        self._active_id = material_id
        self._restyle()
        self.active_material_changed.emit(self._library.get(material_id))

    @property
    def active_material_id(self) -> int:
        return self._active_id
```

- [ ] **Step 4: Run the dock tests**

Run: `.venv/Scripts/python -m pytest tests/test_materials_dock.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Add `materials` to `Model`**

In `model/model.py`, add the import and seed the library in `__init__`:

```python
from pluton.model.material import MaterialLibrary
```

In `Model.__init__` (after `self.active_path = []`):

```python
        self.materials = MaterialLibrary()
```

- [ ] **Step 6: Write the failing MainWindow wiring test**

```python
# tests/test_main_window_materials.py
from __future__ import annotations

import pytest
from pluton.ui.main_window import MainWindow
from pluton.ui.materials_dock import MaterialsDock


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_main_window_has_materials_dock(win):
    assert isinstance(win._materials_dock, MaterialsDock)


def test_paint_tool_registered_under_b(win):
    assert win._tool_manager.activate_by_shortcut("B")
    assert win._tool_manager.active.name == "Paint"


def test_tool_context_exposes_material_hooks(win):
    ctx = win._tool_manager._ctx  # installed ToolContext (ToolManager stores it as _ctx)
    assert ctx.active_material_provider is not None
    assert ctx.set_active_material is not None
    # provider returns the model's active material (Default at startup)
    assert ctx.active_material_provider().id == win._model.materials.DEFAULT_ID


def test_dock_selection_updates_active_material_id(win):
    brick = next(m for m in win._model.materials.materials() if m.name == "Brick Red")
    win._materials_dock._on_pick(brick.id)
    assert win._active_material_id == brick.id
```

- [ ] **Step 7: Wire MainWindow**

In `main_window.py`:

1. Imports (extend the tools import and add the dock + Qt dock area):

```python
from pluton.tools.paint_tool import PaintTool
from pluton.ui.materials_dock import MaterialsDock
from PySide6.QtCore import Qt   # if not already imported
```

2. Register the tool alongside the others (after `EraserTool()`):

```python
        self._tool_manager.register(PaintTool())
```

3. After the viewport + model exist (near where `_render_style` is set), initialize the active material and build the dock:

```python
        self._active_material_id = self._model.materials.DEFAULT_ID
        self._materials_dock = MaterialsDock(self._model.materials, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._materials_dock)
        self._materials_dock.active_material_changed.connect(self._on_active_material_changed)
```

4. Add the handler:

```python
    def _on_active_material_changed(self, material) -> None:  # noqa: ANN001
        self._active_material_id = material.id
```

5. In `_rebuild_tool_context()`, add the two hooks to the `ToolContext(...)` call:

```python
            active_material_provider=lambda: self._model.materials.get(self._active_material_id),
            set_active_material=self._materials_dock.set_active,
```

(Build the dock BEFORE the first `_rebuild_tool_context()` call so `self._materials_dock` exists when the lambda is created.)

- [ ] **Step 8: Run the wiring test + full suite**

Run: `.venv/Scripts/python -m pytest tests/test_main_window_materials.py tests/test_materials_dock.py -v`
Expected: PASS

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (full suite green)

- [ ] **Step 9: Lint (hand-fix only — main_window.py / model.py carry intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/ui/materials_dock.py python/pluton/model/model.py python/pluton/ui/main_window.py tests/test_materials_dock.py tests/test_main_window_materials.py`
Expected: no errors. (Safe to `ruff --fix` ONLY the two new test files / materials_dock.py if I001 flags; never the edited model.py/main_window.py.)

- [ ] **Step 10: Commit**

```bash
git add python/pluton/ui/materials_dock.py python/pluton/model/model.py python/pluton/ui/main_window.py tests/test_materials_dock.py tests/test_main_window_materials.py
git commit -m "$(printf 'feat(m5b): Materials dock + MainWindow wiring (library on Model, PaintTool, context hooks)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 9: Full regression + manual visual pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS — 593 (v0.1.5) + the M5b additions, all green.

- [ ] **Step 2: Run the C++ tests (unchanged kernel)**

Run: `ctest --test-dir build/<wheel_tag> --output-on-failure` (use the existing build dir; kernel is untouched).
Expected: 76/76 passed.

- [ ] **Step 3: Rebuild the editable install (so the app runs the new Python)**

Run: `.venv/Scripts/python -m pip install -e . --no-build-isolation`
Expected: builds and installs (pure-Python is editable-redirected; no kernel change).

- [ ] **Step 4: Ruff over the whole tree (report only — do NOT `--fix`)**

Run: `.venv/Scripts/python -m ruff check python/ tests/`
Expected: only pre-existing `# noqa: ANN001` debt on edited files (issue #48) — no NEW errors. Hand-fix anything new.

- [ ] **Step 5: Manual visual pass — launch the app**

Run: `.venv/Scripts/python -m pluton`

Verify (this is the GL-output gate the unit tests cannot cover):
- Materials dock appears (right side) with Default + built-in swatches.
- Press **B**; paint several faces with different palette colors — Shaded view shows the colors.
- Paint a face with **Default** → it returns to the standard gray look.
- **Alt-click** a painted face → the dock highlights that material (eyedropper).
- Hover preview tints the hovered face with the active color.
- **Ctrl+Z / Ctrl+Y** undo/redo a paint correctly.
- Make a component, instance it twice, paint a face inside → **all instances** show the paint.
- Paint a face, **erase** it, **undo** → the paint returns.
- Cycle **View ▸ Face Style** over a painted model: Shaded = colors; Monochrome = uniform gray (ignores paint); Hidden Line = bg fill; Wireframe = unaffected. Toggle **X-Ray** in each — faces go translucent, edges stay opaque.
- A brand-new empty scene / unpainted model looks identical to v0.1.5 (no regression).

- [ ] **Step 6: Report results to the user and STOP for confirmation**

Do not proceed to release until the user confirms the visual pass looks right.

---

### Task 10: Release v0.1.6-m5b

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` (0.1.5 → 0.1.6)
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M5b shipped)

This task requires explicit user authorization for each outward-facing step (push, tag). Do NOT push/tag without it.

- [ ] **Step 1: Bump the version in all three files**

- `pyproject.toml`: `version = "0.1.5"` → `version = "0.1.6"`
- `CMakeLists.txt`: `VERSION 0.1.5` → `VERSION 0.1.6`
- `cpp/src/version.cpp`: `return "0.1.5";` → `return "0.1.6";`

- [ ] **Step 2: Rebuild so `_core.version()` reports 0.1.6**

Run: `.venv/Scripts/python -m pip install -e . --no-build-isolation`
Then: `.venv/Scripts/python -c "import pluton; print(pluton.__version__)"`
Expected: `0.1.6`

- [ ] **Step 3: Annotate the master roadmap**

In `docs/2026-05-16-pluton-design.md`, update the M5 line: mark **M5b ✅ *(shipped v0.1.6)*** — solid-color materials + paint tool; note textures remain deferred (their own later milestone).

- [ ] **Step 4: Final full suite + commit the release**

Run: `.venv/Scripts/python -m pytest tests/ -q` → green.

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "$(printf 'release: v0.1.6 (M5b — solid-color materials + paint tool)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

- [ ] **Step 5: (AUTH REQUIRED) Push, tag, watch CI**

After the user authorizes:

```bash
git push origin main
git tag -a v0.1.6-m5b -m "M5b — solid-color materials + paint tool"
git push origin v0.1.6-m5b
gh run watch
```
Expected: CI SUCCESS on ubuntu-24.04 + windows-2022.

- [ ] **Step 6: File deferred-feature follow-up issues**

After release, file issues for: textures/UV mapping; drag-to-paint strokes; material editing/rename/delete with re-propagation; per-side (front/back) face materials; translucent materials. (Persistence is already covered by M6.)

---

## Notes for the executor

- **Suggested models (subagent-driven):** Tasks 1, 4, 6 = haiku (pure, complete code = transcription). Tasks 2, 3, 5, 7, 8 = sonnet (cross-file edits / regression-critical renderer / Qt UI integration). Reviewers = sonnet floor. Task 9/10 = controller-coordinated.
- **Task 5 is the regression-critical one.** The acceptance bar is the byte-identical unpainted path: identity `vertex_order` + `_DEFAULT_MATERIAL` for the single Default batch. Inspect the net diff (Step 8) before approving.
- **Never run broad `ruff --fix`** on edited files that carry intentional `# noqa: ANN001` (issue #48): `scene.py`, `scene_renderer.py`, `tool.py`, `paint_tool.py`, `material_commands.py`, `model.py`, `main_window.py`. Hand-fix lint. New-file-only `--fix` (for I001) is acceptable.
- **Layering:** `render_style.py` and `material.py` stay import-free of the GL renderer; constants are duplicated (with guard test / comment) rather than imported upward.
- **No C++ changes** anywhere in Tasks 1–9. Version files only in Task 10.
```

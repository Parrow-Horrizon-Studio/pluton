# M4e — Groups & Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SketchUp-style Groups and Components — bundles of geometry that move/transform as a unit, are isolated from surrounding geometry, can be entered for editing, and (for components) share one definition so editing any instance updates all.

**Architecture:** A **Python scene graph** over the existing per-definition C++ `HalfEdgeMesh`. A `Definition` owns one `Scene` (geometry) plus child `Instance`s; an `Instance` is a 4×4 transform + a reference to a `Definition`. A `Model` owns the root definition and the active editing path. The kernel is reused untouched; the root context with an identity transform is behaviorally identical to today's single mesh.

**Tech Stack:** Python 3.13, numpy, PySide6/Qt, PyOpenGL, the existing C++/nanobind `HalfEdgeMesh`, pytest (+ pytest-qt).

**Spec:** `docs/2026-06-19-M4e-groups-components-design.md`

## Global Constraints

- **Interpreter:** run Python/pytest **only** via `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash). Bare `python`/`pytest` hit a drifting editable install. Example: `.venv/Scripts/python.exe -m pytest tests/test_model.py -v`.
- **Git:** work on `main` directly. Stage **specific files only** — never `git add -A` / `git add .`. Never `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing stays on). End every commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) are touched **only** in the release task (Task 20).
- **No C++ changes.** The kernel is reused as-is; all M4e code is Python.
- **Base unit:** 1 model unit = 1 meter (unchanged). Mesh vertex positions are `float32`; instance transforms are `float64` `(4,4)` numpy matrices.
- **Bash cwd resets between turns** — prefix git/python with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.
- **Regression bar:** the full suite (currently **417 pytest + 76 ctest**) must stay green after every integration task. CI does **not** run ruff; keep new code ruff-clean locally anyway (`.venv/Scripts/python.exe -m ruff check python/pluton`).

---

# Phase 1 — Model core (headless, fully tested)

### Task 1: `Instance` and `Definition`

**Files:**
- Create: `python/pluton/model/__init__.py`
- Create: `python/pluton/model/instance.py`
- Create: `python/pluton/model/definition.py`
- Test: `tests/test_model_definition.py`

**Interfaces:**
- Consumes: `pluton.scene.scene.Scene` (existing — one mesh wrapper).
- Produces:
  - `Instance(instance_id: int, definition: Definition, transform: np.ndarray | None = None)` with attrs `.id:int`, `.definition:Definition`, `.transform:np.ndarray (4,4) float64`.
  - `Definition(definition_id: int, name: str, is_group: bool, mesh: Scene | None = None)` with attrs `.id:int`, `.name:str`, `.is_group:bool`, `.mesh:Scene`, `.children:list[Instance]`, `.instances:list[Instance]`; method `local_aabb() -> tuple[np.ndarray, np.ndarray] | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_definition.py
import numpy as np
from pluton.model.definition import Definition
from pluton.model.instance import Instance


def test_definition_defaults_to_empty_scene():
    d = Definition(0, "Model", is_group=False)
    assert d.id == 0
    assert d.name == "Model"
    assert d.is_group is False
    assert d.children == []
    assert d.instances == []
    assert d.local_aabb() is None  # empty mesh → no bbox


def test_instance_defaults_to_identity_transform():
    d = Definition(1, "Group #1", is_group=True)
    inst = Instance(7, d)
    assert inst.id == 7
    assert inst.definition is d
    assert np.allclose(inst.transform, np.eye(4))


def test_local_aabb_spans_mesh_vertices():
    d = Definition(2, "Box", is_group=True)
    d.mesh.add_vertex(np.array([-1, -2, 0], np.float32))
    d.mesh.add_vertex(np.array([3, 4, 5], np.float32))
    lo, hi = d.local_aabb()
    assert np.allclose(lo, [-1, -2, 0])
    assert np.allclose(hi, [3, 4, 5])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model_definition.py -v`
Expected: FAIL — `ModuleNotFoundError: pluton.model`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/model/__init__.py
"""The scene-graph layer: Definitions (geometry owners) + Instances (placements)."""
from pluton.model.definition import Definition
from pluton.model.instance import Instance
from pluton.model.model import Model

__all__ = ["Definition", "Instance", "Model"]
```
*(Note: `model.py` is created in Task 2; if running Task 1 alone, temporarily drop the `Model` import + entry, then restore in Task 2.)*

```python
# python/pluton/model/instance.py
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pluton.model.definition import Definition


class Instance:
    """A placement: a 4x4 transform + a reference to a Definition. Non-destructive."""

    __slots__ = ("id", "definition", "transform")

    def __init__(
        self, instance_id: int, definition: "Definition", transform: np.ndarray | None = None
    ) -> None:
        self.id = int(instance_id)
        self.definition = definition
        if transform is None:
            self.transform = np.eye(4, dtype=np.float64)
        else:
            self.transform = np.asarray(transform, dtype=np.float64).reshape(4, 4).copy()
```

```python
# python/pluton/model/definition.py
from __future__ import annotations

import numpy as np

from pluton.model.instance import Instance
from pluton.scene.scene import Scene


class Definition:
    """Owns geometry (one Scene/HalfEdgeMesh) plus nested child instances."""

    def __init__(
        self, definition_id: int, name: str, is_group: bool, mesh: Scene | None = None
    ) -> None:
        self.id = int(definition_id)
        self.name = str(name)
        self.is_group = bool(is_group)
        self.mesh = mesh if mesh is not None else Scene()
        self.children: list[Instance] = []
        self.instances: list[Instance] = []

    def local_aabb(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Axis-aligned bounds over this definition's live vertices, or None if empty."""
        pts = [v.position for v in self.mesh.vertices_iter()]
        if not pts:
            return None
        arr = np.asarray(pts, dtype=np.float32).reshape(-1, 3)
        return arr.min(axis=0), arr.max(axis=0)
```

For Step 3, drop the `Model` import from `__init__.py` for now:
```python
# python/pluton/model/__init__.py  (Task 1 version)
"""The scene-graph layer: Definitions (geometry owners) + Instances (placements)."""
from pluton.model.definition import Definition
from pluton.model.instance import Instance

__all__ = ["Definition", "Instance"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model_definition.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/__init__.py python/pluton/model/instance.py python/pluton/model/definition.py tests/test_model_definition.py && git commit -m "feat(m4e): Instance + Definition scene-graph nodes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `Model` — root, active path, enter/exit

**Files:**
- Create: `python/pluton/model/model.py`
- Modify: `python/pluton/model/__init__.py` (restore `Model` import/entry from Task 1 note)
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: `Definition`, `Instance` (Task 1); `geometry.transforms` matrix helpers are NOT yet needed (active_world_transform uses raw numpy `@`).
- Produces:
  - `Model()` with `.root:Definition` (name `"Model"`, `is_group=False`), `.active_path:list[Instance]`.
  - `Model.new_definition(name: str, is_group: bool) -> Definition`
  - `Model.new_instance(definition: Definition, transform=None) -> Instance` (registers the back-ref in `definition.instances`).
  - Properties `active_context -> Definition`, `active_scene -> Scene`, `active_world_transform -> np.ndarray (4,4) float64`.
  - `enter(instance: Instance) -> None`, `exit_one() -> None`, `revalidate_active_path() -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model.py
import numpy as np
from pluton.model.model import Model


def test_fresh_model_is_at_root_identity():
    m = Model()
    assert m.root.name == "Model"
    assert m.active_path == []
    assert m.active_context is m.root
    assert m.active_scene is m.root.mesh
    assert np.allclose(m.active_world_transform, np.eye(4))


def test_enter_exit_changes_active_context():
    m = Model()
    d = m.new_definition("Group #1", is_group=True)
    t = np.eye(4); t[:3, 3] = [2, 0, 0]
    inst = m.new_instance(d, t)
    m.root.children.append(inst)

    m.enter(inst)
    assert m.active_context is d
    assert m.active_scene is d.mesh
    assert np.allclose(m.active_world_transform[:3, 3], [2, 0, 0])

    m.exit_one()
    assert m.active_context is m.root
    assert np.allclose(m.active_world_transform, np.eye(4))


def test_new_instance_registers_backref():
    m = Model()
    d = m.new_definition("Chair", is_group=False)
    a = m.new_instance(d)
    b = m.new_instance(d)
    assert d.instances == [a, b]
    assert a.id != b.id


def test_revalidate_pops_destroyed_context():
    m = Model()
    d = m.new_definition("Group #1", is_group=True)
    inst = m.new_instance(d)
    m.root.children.append(inst)
    m.enter(inst)
    # Simulate undo destroying the instance:
    m.root.children.remove(inst)
    m.revalidate_active_path()
    assert m.active_path == []
    assert m.active_context is m.root
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: pluton.model.model`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/model/model.py
from __future__ import annotations

import numpy as np

from pluton.model.definition import Definition
from pluton.model.instance import Instance


class Model:
    """The scene graph: a root Definition + the active editing path."""

    def __init__(self) -> None:
        self._next_def_id = 0
        self._next_inst_id = 0
        self.root = self.new_definition("Model", is_group=False)
        self.active_path: list[Instance] = []

    # --- construction ---
    def new_definition(self, name: str, is_group: bool) -> Definition:
        d = Definition(self._next_def_id, name, is_group)
        self._next_def_id += 1
        return d

    def new_instance(self, definition: Definition, transform=None) -> Instance:
        inst = Instance(self._next_inst_id, definition, transform)
        self._next_inst_id += 1
        definition.instances.append(inst)
        return inst

    # --- active context ---
    @property
    def active_context(self) -> Definition:
        return self.active_path[-1].definition if self.active_path else self.root

    @property
    def active_scene(self):  # noqa: ANN201  (Scene)
        return self.active_context.mesh

    @property
    def active_world_transform(self) -> np.ndarray:
        m = np.eye(4, dtype=np.float64)
        for inst in self.active_path:
            m = m @ inst.transform
        return m

    def enter(self, instance: Instance) -> None:
        self.active_path.append(instance)

    def exit_one(self) -> None:
        if self.active_path:
            self.active_path.pop()

    def revalidate_active_path(self) -> None:
        """Pop the active path to the nearest still-reachable instance.

        After an undo/redo destroys a group, the entered instance may no longer
        be a child of its parent context. Walk the path from the root; truncate
        at the first instance that isn't in its parent's children list.
        """
        valid: list[Instance] = []
        parent = self.root
        for inst in self.active_path:
            if inst in parent.children:
                valid.append(inst)
                parent = inst.definition
            else:
                break
        self.active_path = valid
```

Restore `python/pluton/model/__init__.py` to import `Model` (the Task 1 `__all__` note).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model.py tests/test_model_definition.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py python/pluton/model/__init__.py tests/test_model.py && git commit -m "feat(m4e): Model root + active editing path (enter/exit/revalidate)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `Model.traverse()` — depth-first with accumulated transforms

**Files:**
- Modify: `python/pluton/model/model.py`
- Test: `tests/test_model_traverse.py`

**Interfaces:**
- Produces: `Model.traverse() -> Iterator[tuple[Definition, np.ndarray]]` — yields every reachable definition paired with its accumulated world transform `(4,4) float64`, depth-first from root. The root is yielded first with identity. A definition reached via two instances is yielded twice (drives instancing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_model_traverse.py
import numpy as np
from pluton.model.model import Model


def test_traverse_root_only():
    m = Model()
    out = list(m.traverse())
    assert len(out) == 1
    d, t = out[0]
    assert d is m.root
    assert np.allclose(t, np.eye(4))


def test_traverse_accumulates_transforms():
    m = Model()
    g = m.new_definition("G", is_group=True)
    t = np.eye(4); t[:3, 3] = [5, 0, 0]
    inst = m.new_instance(g, t)
    m.root.children.append(inst)
    out = list(m.traverse())
    defs = [d for d, _ in out]
    assert defs == [m.root, g]
    assert np.allclose(out[1][1][:3, 3], [5, 0, 0])


def test_traverse_yields_shared_definition_twice():
    m = Model()
    chair = m.new_definition("Chair", is_group=False)
    a = m.new_instance(chair, _xlate(1, 0, 0))
    b = m.new_instance(chair, _xlate(9, 0, 0))
    m.root.children += [a, b]
    out = [(d.id, tuple(t[:3, 3])) for d, t in m.traverse()]
    # root + chair@1 + chair@9
    assert (chair.id, (1.0, 0.0, 0.0)) in out
    assert (chair.id, (9.0, 0.0, 0.0)) in out


def _xlate(x, y, z):
    t = np.eye(4); t[:3, 3] = [x, y, z]; return t
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model_traverse.py -v`
Expected: FAIL — `AttributeError: 'Model' object has no attribute 'traverse'`.

- [ ] **Step 3: Write minimal implementation**

Add to `python/pluton/model/model.py`:
```python
    def traverse(self):
        """Yield (definition, world_transform) depth-first from the root."""
        yield from self._traverse(self.root, np.eye(4, dtype=np.float64))

    def _traverse(self, definition, world):
        yield definition, world
        for inst in definition.children:
            yield from self._traverse(inst.definition, world @ inst.transform)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_model_traverse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py tests/test_model_traverse.py && git commit -m "feat(m4e): Model.traverse() with accumulated world transforms

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 2 — Coordinate helpers

### Task 4: 4×4 matrix builders + apply/compose/invert

**Files:**
- Modify: `python/pluton/geometry/transforms.py`
- Test: `tests/test_transforms_matrix.py`

**Interfaces:**
- Produces (all in `pluton.geometry.transforms`):
  - `mat_translate(delta) -> np.ndarray (4,4) float64`
  - `mat_scale(anchor, factors) -> np.ndarray (4,4) float64` (scale about `anchor`)
  - `mat_rotate(center, axis, angle_rad) -> np.ndarray (4,4) float64` (rotate about line through `center` along `axis`)
  - `mat_compose(*mats) -> np.ndarray (4,4)` (left-to-right: `mat_compose(A, B)` applies A then B → `B @ A`)
  - `mat_invert(m) -> np.ndarray (4,4)`
  - `apply_mat(points, m) -> np.ndarray (N,3) float32` (homogeneous transform of `(N,3)` points)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transforms_matrix.py
import numpy as np
from pluton.geometry.transforms import (
    apply_mat, mat_compose, mat_invert, mat_rotate, mat_scale, mat_translate,
)


def test_translate_moves_points():
    M = mat_translate([1, 2, 3])
    out = apply_mat(np.array([[0, 0, 0], [1, 1, 1]], np.float32), M)
    assert np.allclose(out, [[1, 2, 3], [2, 3, 4]])


def test_scale_about_anchor():
    M = mat_scale([1, 0, 0], [2, 2, 2])
    out = apply_mat(np.array([[2, 0, 0]], np.float32), M)
    assert np.allclose(out, [[3, 0, 0]])  # (2-1)*2 + 1 = 3


def test_rotate_90_about_z_through_origin():
    M = mat_rotate([0, 0, 0], [0, 0, 1], np.pi / 2)
    out = apply_mat(np.array([[1, 0, 0]], np.float32), M)
    assert np.allclose(out, [[0, 1, 0]], atol=1e-6)


def test_invert_roundtrip():
    M = mat_compose(mat_translate([3, -1, 2]), mat_rotate([0, 0, 0], [0, 1, 0], 0.7))
    Minv = mat_invert(M)
    p = np.array([[4, 5, 6]], np.float32)
    back = apply_mat(apply_mat(p, M), Minv)
    assert np.allclose(back, p, atol=1e-5)


def test_compose_order_is_left_then_right():
    # translate by (1,0,0) THEN scale x2 about origin → (1,0,0) maps to (2,0,0)+... check a point at origin
    M = mat_compose(mat_translate([1, 0, 0]), mat_scale([0, 0, 0], [2, 2, 2]))
    out = apply_mat(np.array([[0, 0, 0]], np.float32), M)
    assert np.allclose(out, [[2, 0, 0]])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_transforms_matrix.py -v`
Expected: FAIL — `ImportError: cannot import name 'mat_translate'`.

- [ ] **Step 3: Write minimal implementation**

Append to `python/pluton/geometry/transforms.py`:
```python
def mat_translate(delta) -> np.ndarray:
    m = np.eye(4, dtype=np.float64)
    m[:3, 3] = np.asarray(delta, dtype=np.float64).reshape(3)
    return m


def mat_scale(anchor, factors) -> np.ndarray:
    a = np.asarray(anchor, dtype=np.float64).reshape(3)
    f = np.asarray(factors, dtype=np.float64).reshape(3)
    m = np.eye(4, dtype=np.float64)
    m[0, 0], m[1, 1], m[2, 2] = f
    m[:3, 3] = a - f * a  # p' = a + (p-a)*f
    return m


def mat_rotate(center, axis, angle_rad: float) -> np.ndarray:
    c = np.asarray(center, dtype=np.float64).reshape(3)
    k = np.asarray(axis, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(k))
    if norm < 1e-9:
        raise ValueError("mat_rotate: degenerate (near-zero) axis")
    k = k / norm
    x, y, z = k
    ca, sa = np.cos(angle_rad), np.sin(angle_rad)
    r = np.array([
        [ca + x * x * (1 - ca), x * y * (1 - ca) - z * sa, x * z * (1 - ca) + y * sa],
        [y * x * (1 - ca) + z * sa, ca + y * y * (1 - ca), y * z * (1 - ca) - x * sa],
        [z * x * (1 - ca) - y * sa, z * y * (1 - ca) + x * sa, ca + z * z * (1 - ca)],
    ], dtype=np.float64)
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = r
    m[:3, 3] = c - r @ c  # rotate about the line through center
    return m


def mat_compose(*mats) -> np.ndarray:
    """Compose transforms applied left-to-right: mat_compose(A, B) == B @ A."""
    out = np.eye(4, dtype=np.float64)
    for m in mats:
        out = np.asarray(m, dtype=np.float64) @ out
    return out


def mat_invert(m) -> np.ndarray:
    return np.linalg.inv(np.asarray(m, dtype=np.float64))


def apply_mat(points, m) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    m = np.asarray(m, dtype=np.float64)
    h = np.hstack([pts, np.ones((pts.shape[0], 1))])
    out = (h @ m.T)[:, :3]
    return out.astype(np.float32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_transforms_matrix.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/transforms.py tests/test_transforms_matrix.py && git commit -m "feat(m4e): 4x4 matrix builders (translate/scale/rotate/compose/invert/apply)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 3 — Commands (headless, tested)

### Task 5: CommandStack target-threading refactor

The stack must remember which **target** (a `Scene` for geometry commands, or the `Model` for structural commands) each command ran against, so undo/redo apply to the right object regardless of the active context. Existing geometry commands keep their `do(self, target)` / `undo(self, target)` signatures unchanged — they just receive the stored target.

**Files:**
- Modify: `python/pluton/commands/command_stack.py`
- Modify (call sites, add the target arg to `push_executed`): `python/pluton/tools/arc_tool.py:121,201`, `python/pluton/tools/circle_tool.py:106,120`, `python/pluton/tools/erase_tool.py:108`, `python/pluton/tools/line_tool.py:123,181`, `python/pluton/tools/polygon_tool.py:108,130`, `python/pluton/tools/push_pull_tool.py:380`, `python/pluton/tools/rectangle_tool.py:193`, `python/pluton/ui/main_window.py:294`
- Test: `tests/test_command_stack.py` (extend if it exists, else create)

**Interfaces:**
- Produces:
  - `CommandStack.execute(cmd, target) -> None` (unchanged signature; now stores `(cmd, target)`).
  - `CommandStack.push_executed(cmd, target) -> None` (**target added** — required).
  - `CommandStack.undo() -> bool` and `redo() -> bool` (**scene arg dropped**; uses the stored target).
  - `can_undo`, `can_redo`, `add_undo_listener`, `add_redo_listener` unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_command_stack.py  (add these; keep existing tests)
from pluton.commands.command import Command
from pluton.commands.command_stack import CommandStack


class _Recorder(Command):
    name = "Rec"
    def __init__(self, log, tag):
        self._log, self._tag = log, tag
    def do(self, target):
        self._log.append(("do", self._tag, target))
    def undo(self, target):
        self._log.append(("undo", self._tag, target))


def test_stack_threads_per_command_target():
    log = []
    s = CommandStack()
    s.execute(_Recorder(log, "a"), "SCENE_A")
    s.execute(_Recorder(log, "b"), "SCENE_B")
    assert s.undo() is True          # undoes b against SCENE_B
    assert s.undo() is True          # undoes a against SCENE_A
    assert s.undo() is False
    assert ("undo", "b", "SCENE_B") in log
    assert ("undo", "a", "SCENE_A") in log


def test_push_executed_remembers_target():
    log = []
    s = CommandStack()
    s.push_executed(_Recorder(log, "x"), "TARGET_X")
    assert s.undo() is True
    assert ("undo", "x", "TARGET_X") in log
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_command_stack.py -v`
Expected: FAIL — `undo()` takes a required positional `scene`, or `push_executed()` takes 1 positional.

- [ ] **Step 3: Write minimal implementation**

Rewrite `python/pluton/commands/command_stack.py` bodies (keep the docstrings/listeners):
```python
    def execute(self, cmd, target) -> None:  # noqa: ANN001
        cmd.do(target)
        self._undo.append((cmd, target))
        self._redo.clear()

    def push_executed(self, cmd, target) -> None:  # noqa: ANN001
        self._undo.append((cmd, target))
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd, target = self._undo.pop()
        cmd.undo(target)
        self._redo.append((cmd, target))
        for fn in self._on_after_undo:
            fn()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd, target = self._redo.pop()
        cmd.do(target)
        self._undo.append((cmd, target))
        for fn in self._on_after_redo:
            fn()
        return True
```

Update each `push_executed(...)` call site to pass the active scene as the target. In every tool the active scene is `self._scene` (set in `activate`); in `main_window.py:294` it is `self._scene`. Examples:
- `python/pluton/tools/line_tool.py:123` → `self._command_stack.push_executed(self._composite, self._scene)`
- `python/pluton/tools/erase_tool.py:108` → `self._command_stack.push_executed(self._stroke, self._scene)`
- `python/pluton/ui/main_window.py:294` → `self._command_stack.push_executed(composite, self._scene)`
- (apply the same `, self._scene` to all 12 listed sites)

Update the two undo/redo call sites in `main_window.py`:
- `:317` `if self._command_stack.undo(self._scene):` → `if self._command_stack.undo():`
- `:322` `if self._command_stack.redo(self._scene):` → `if self._command_stack.redo():`

*(Note: `execute(cmd, self._scene)` call sites are unchanged — they already pass the target.)*

- [ ] **Step 4: Run the full suite (regression-critical)**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Expected: all pass (the 417 existing + the 2 new). If any test calls `undo(scene)`/`push_executed(cmd)` directly, update it to the new signatures.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/command_stack.py tests/test_command_stack.py python/pluton/tools/arc_tool.py python/pluton/tools/circle_tool.py python/pluton/tools/erase_tool.py python/pluton/tools/line_tool.py python/pluton/tools/polygon_tool.py python/pluton/tools/push_pull_tool.py python/pluton/tools/rectangle_tool.py python/pluton/ui/main_window.py && git commit -m "refactor(m4e): CommandStack threads a per-command target (Scene or Model)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `MakeGroupCommand` / `MakeComponentCommand`

Lift the current entity selection out of a parent Scene into a new Definition + Instance. Target = the **Model**. Undo restores the lifted geometry (original IDs) into the parent and removes the new definition/instance.

**Files:**
- Create: `python/pluton/commands/group_commands.py`
- Test: `tests/test_group_commands.py`

**Interfaces:**
- Consumes: `Model`, `Definition`, `Instance`; `Scene.restore_vertex/edge/face`, `Scene.vertex/edge/face`, `Scene.remove_*`, `Scene.add_vertex/add_edge/add_face_from_loop`, `selection_vertices` (from `pluton.tools.transform_support`).
- Produces:
  - `MakeGroupCommand(parent_definition, vertex_ids, edge_ids, face_ids, *, is_group=True, name=None)` with `.created_instance: Instance | None` (set after do).
  - `MakeComponentCommand(...)` — same, `is_group=False`, requires `name`.
  - `do(self, model)` / `undo(self, model)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_group_commands.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.group_commands import MakeGroupCommand


def _triangle(scene):
    a = scene.add_vertex(np.array([0, 0, 0], np.float32))
    b = scene.add_vertex(np.array([1, 0, 0], np.float32))
    c = scene.add_vertex(np.array([0, 1, 0], np.float32))
    f = scene.add_face_from_loop([a, b, c])
    return [a, b, c], f


def test_make_group_moves_geometry_into_new_definition():
    m = Model()
    verts, face = _triangle(m.root.mesh)
    cmd = MakeGroupCommand(m.root, verts, [], [face])
    cmd.do(m)

    # Parent mesh is now empty; a child instance exists.
    assert list(m.root.mesh.faces_iter()) == []
    assert len(m.root.children) == 1
    inst = m.root.children[0]
    assert inst is cmd.created_instance
    # The new definition holds the triangle.
    assert len(list(inst.definition.mesh.faces_iter())) == 1
    assert inst.definition.is_group is True


def test_make_group_undo_restores_parent_geometry():
    m = Model()
    verts, face = _triangle(m.root.mesh)
    before_face_ids = {f.id for f in m.root.mesh.faces_iter()}
    cmd = MakeGroupCommand(m.root, verts, [], [face])
    cmd.do(m)
    cmd.undo(m)
    assert {f.id for f in m.root.mesh.faces_iter()} == before_face_ids
    assert m.root.children == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_group_commands.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/commands/group_commands.py
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command


class MakeGroupCommand(Command):
    """Lift selected entities from a parent definition into a new Definition+Instance."""

    name = "Make Group"

    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids,
                 *, is_group: bool = True, name: str | None = None) -> None:
        self._parent = parent_definition
        self._vids = list(vertex_ids)
        self._eids = list(edge_ids)
        self._fids = list(face_ids)
        self._is_group = is_group
        self._name = name
        self.created_instance = None
        self._captured = None  # (verts, edges, faces) descriptors for undo

    def do(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        # 1. Capture lifted geometry descriptors (original ids) for undo restore.
        verts = [(v, parent_scene.vertex(v).position.copy()) for v in self._vids]
        edges = [(e, parent_scene.edge(e).v1_id, parent_scene.edge(e).v2_id) for e in self._eids]
        faces = [(f, tuple(parent_scene.face(f).loop_vertex_ids)) for f in self._fids]
        self._captured = (verts, edges, faces)

        # 2. Create the definition + copy geometry into it (fresh ids in child mesh).
        defn = model.new_definition(
            self._name or (f"Group #{model._next_def_id}" if self._is_group
                           else f"Component #{model._next_def_id}"),
            is_group=self._is_group,
        )
        idmap = {}
        for v, pos in verts:
            idmap[v] = defn.mesh.add_vertex(pos)
        for _e, v1, v2 in edges:
            defn.mesh.add_edge(idmap[v1], idmap[v2])
        for _f, loop in faces:
            defn.mesh.add_face_from_loop([idmap[v] for v in loop])

        # 3. Remove lifted geometry from the parent (faces, then edges, then verts).
        for f, _loop in faces:
            parent_scene.remove_face(f)
        for e, _v1, _v2 in edges:
            try:
                parent_scene.remove_edge(e)
            except Exception:
                pass  # edge may have been auto-removed with its faces
        for v, _pos in verts:
            try:
                parent_scene.remove_vertex(v)
            except Exception:
                pass

        # 4. Create one instance in the parent.
        inst = model.new_instance(defn)
        self._parent.children.append(inst)
        self.created_instance = inst

    def undo(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        verts, edges, faces = self._captured
        # Remove the instance + definition.
        if self.created_instance in self._parent.children:
            self._parent.children.remove(self.created_instance)
        # Restore parent geometry by original ids (verts, edges, faces in order).
        for v, pos in verts:
            parent_scene.restore_vertex(v, pos)
        for e, v1, v2 in edges:
            parent_scene.restore_edge(e, v1, v2)
        for f, loop in faces:
            parent_scene.restore_face(f, loop)


class MakeComponentCommand(MakeGroupCommand):
    name = "Make Component"

    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids, *, name: str) -> None:
        super().__init__(parent_definition, vertex_ids, edge_ids, face_ids,
                         is_group=False, name=name)
```

*(Clean up the dead `edges = [...mro...]` experimental line; keep only the single correct `edges = [(e, v1, v2) ...]` comprehension.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_group_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/group_commands.py tests/test_group_commands.py && git commit -m "feat(m4e): MakeGroup/MakeComponent commands (lift geometry into a definition)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `TransformInstanceCommand` + `CreateInstanceCommand`

**Files:**
- Create: `python/pluton/commands/instance_commands.py`
- Test: `tests/test_instance_commands.py`

**Interfaces:**
- Produces:
  - `TransformInstanceCommand(instance, new_transform)` — stores old + new `(4,4)`; `do` sets new, `undo` restores old.
  - `CreateInstanceCommand(parent_definition, definition, transform)` with `.created_instance`; `do` adds a new instance of `definition` to `parent_definition.children`, `undo` removes it.
  - Both `do(self, model)` / `undo(self, model)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instance_commands.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.instance_commands import CreateInstanceCommand, TransformInstanceCommand


def _xlate(x):
    t = np.eye(4); t[0, 3] = x; return t


def test_transform_instance_sets_and_restores():
    m = Model()
    d = m.new_definition("G", is_group=True)
    inst = m.new_instance(d)
    m.root.children.append(inst)
    cmd = TransformInstanceCommand(inst, _xlate(5))
    cmd.do(m)
    assert np.allclose(inst.transform[:3, 3], [5, 0, 0])
    cmd.undo(m)
    assert np.allclose(inst.transform, np.eye(4))


def test_create_instance_adds_and_removes():
    m = Model()
    d = m.new_definition("Chair", is_group=False)
    base = m.new_instance(d)
    m.root.children.append(base)
    cmd = CreateInstanceCommand(m.root, d, _xlate(9))
    cmd.do(m)
    assert cmd.created_instance in m.root.children
    assert len(d.instances) == 2
    cmd.undo(m)
    assert cmd.created_instance not in m.root.children
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_instance_commands.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/commands/instance_commands.py
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command


class TransformInstanceCommand(Command):
    name = "Transform"

    def __init__(self, instance, new_transform) -> None:
        self._inst = instance
        self._old = np.asarray(instance.transform, np.float64).copy()
        self._new = np.asarray(new_transform, np.float64).reshape(4, 4).copy()

    def do(self, model) -> None:  # noqa: ANN001
        self._inst.transform = self._new.copy()

    def undo(self, model) -> None:  # noqa: ANN001
        self._inst.transform = self._old.copy()


class CreateInstanceCommand(Command):
    name = "Create Instance"

    def __init__(self, parent_definition, definition, transform) -> None:
        self._parent = parent_definition
        self._definition = definition
        self._transform = np.asarray(transform, np.float64).reshape(4, 4).copy()
        self.created_instance = None

    def do(self, model) -> None:  # noqa: ANN001
        if self.created_instance is None:
            self.created_instance = model.new_instance(self._definition, self._transform)
        else:
            # redo: re-register the same instance object + back-ref
            if self.created_instance not in self._definition.instances:
                self._definition.instances.append(self.created_instance)
        self._parent.children.append(self.created_instance)

    def undo(self, model) -> None:  # noqa: ANN001
        if self.created_instance in self._parent.children:
            self._parent.children.remove(self.created_instance)
        if self.created_instance in self._definition.instances:
            self._definition.instances.remove(self.created_instance)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_instance_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/instance_commands.py tests/test_instance_commands.py && git commit -m "feat(m4e): TransformInstance + CreateInstance commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `ExplodeInstanceCommand`

Bake a selected instance's geometry into the parent mesh (apply the instance transform), reparent its child instances up one level (composing transforms), and remove the instance. Undo reverses.

**Files:**
- Create: `python/pluton/commands/explode_command.py`
- Test: `tests/test_explode_command.py`

**Interfaces:**
- Consumes: `apply_mat`, `mat_compose` (Task 4); `Scene` iter/add/remove/restore.
- Produces: `ExplodeInstanceCommand(parent_definition, instance)` with `do(self, model)`/`undo(self, model)`. After `do`, the instance's geometry exists in the parent at world (relative-to-parent) coordinates and `instance` is removed from `parent.children`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explode_command.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.explode_command import ExplodeInstanceCommand


def test_explode_bakes_geometry_into_parent_at_transformed_positions():
    m = Model()
    d = m.new_definition("G", is_group=True)
    d.mesh.add_vertex(np.array([0, 0, 0], np.float32))
    d.mesh.add_vertex(np.array([1, 0, 0], np.float32))
    t = np.eye(4); t[:3, 3] = [10, 0, 0]
    inst = m.new_instance(d, t)
    m.root.children.append(inst)

    cmd = ExplodeInstanceCommand(m.root, inst)
    cmd.do(m)

    assert inst not in m.root.children
    xs = sorted(float(v.position[0]) for v in m.root.mesh.vertices_iter())
    assert np.allclose(xs, [10.0, 11.0])  # baked by the +10 translation


def test_explode_undo_restores_instance_and_clears_parent():
    m = Model()
    d = m.new_definition("G", is_group=True)
    d.mesh.add_vertex(np.array([0, 0, 0], np.float32))
    inst = m.new_instance(d, np.eye(4))
    m.root.children.append(inst)
    cmd = ExplodeInstanceCommand(m.root, inst)
    cmd.do(m)
    cmd.undo(m)
    assert inst in m.root.children
    assert list(m.root.mesh.vertices_iter()) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_explode_command.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/commands/explode_command.py
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command
from pluton.geometry.transforms import apply_mat


class ExplodeInstanceCommand(Command):
    name = "Explode"

    def __init__(self, parent_definition, instance) -> None:
        self._parent = parent_definition
        self._inst = instance
        self._baked = None       # list of (new_vid_in_parent) for undo removal
        self._child_records = None  # reparented child instances (for undo)

    def do(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        defn = self._inst.definition
        t = self._inst.transform

        # Bake geometry: copy verts/edges/faces with transformed positions.
        idmap = {}
        new_vids = []
        for v in defn.mesh.vertices_iter():
            world_pos = apply_mat(v.position.reshape(1, 3), t)[0]
            nv = parent_scene.add_vertex(world_pos)
            idmap[v.id] = nv
            new_vids.append(nv)
        for e in defn.mesh.edges_iter():
            parent_scene.add_edge(idmap[e.v1_id], idmap[e.v2_id])
        new_faces = []
        for f in defn.mesh.faces_iter():
            nf = parent_scene.add_face_from_loop([idmap[v] for v in f.loop_vertex_ids])
            new_faces.append(nf)
        self._baked = (new_vids, new_faces)

        # Reparent the instance's children into the parent, composing transforms.
        self._child_records = list(defn.children)
        for child in defn.children:
            child.transform = t @ child.transform
            self._parent.children.append(child)

        # Remove the exploded instance.
        if self._inst in self._parent.children:
            self._parent.children.remove(self._inst)

    def undo(self, model) -> None:  # noqa: ANN001
        parent_scene = self._parent.mesh
        new_vids, new_faces = self._baked
        for nf in new_faces:
            parent_scene.remove_face(nf)
        # Edges auto-handled with verts where possible; remove leftover verts.
        for nv in new_vids:
            try:
                parent_scene.remove_vertex(nv)
            except Exception:
                pass
        # Un-reparent children + undo their transform compose.
        t = self._inst.transform
        tinv = np.linalg.inv(np.asarray(t, np.float64))
        for child in self._child_records:
            if child in self._parent.children:
                self._parent.children.remove(child)
            child.transform = tinv @ child.transform
        self._parent.children.append(self._inst)
```

*(Note for the implementer: removing baked edges explicitly is omitted because `remove_vertex` of both endpoints removes incident edges; if `remove_vertex` raises on still-referenced verts, remove edges first. Add an edge-id capture if a test surfaces leftover edges.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_explode_command.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/explode_command.py tests/test_explode_command.py && git commit -m "feat(m4e): ExplodeInstance command (bake geometry + reparent children)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `MakeUniqueCommand` + `DeleteInstanceCommand`

**Files:**
- Create: `python/pluton/commands/instance_lifecycle_commands.py`
- Test: `tests/test_instance_lifecycle_commands.py`

**Interfaces:**
- Produces:
  - `MakeUniqueCommand(instance)` — `do` clones the instance's definition (deep-copies mesh geometry + child instances) and repoints `instance.definition` at the clone; `undo` repoints back. No-op if the instance is already the sole user.
  - `DeleteInstanceCommand(parent_definition, instance)` — `do` removes the instance from parent + its def back-ref; `undo` re-adds.
  - `Model.clone_definition(definition) -> Definition` helper (add to `model.py`) — deep-copies geometry into a fresh definition.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instance_lifecycle_commands.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.instance_lifecycle_commands import (
    DeleteInstanceCommand, MakeUniqueCommand,
)


def test_make_unique_detaches_shared_definition():
    m = Model()
    d = m.new_definition("Chair", is_group=False)
    d.mesh.add_vertex(np.array([0, 0, 0], np.float32))
    a = m.new_instance(d); b = m.new_instance(d)
    m.root.children += [a, b]

    cmd = MakeUniqueCommand(b)
    cmd.do(m)
    assert b.definition is not d         # b now has its own clone
    assert a.definition is d
    assert len(list(b.definition.mesh.vertices_iter())) == 1  # geometry copied
    cmd.undo(m)
    assert b.definition is d


def test_delete_instance_removes_and_restores():
    m = Model()
    d = m.new_definition("G", is_group=True)
    inst = m.new_instance(d)
    m.root.children.append(inst)
    cmd = DeleteInstanceCommand(m.root, inst)
    cmd.do(m)
    assert inst not in m.root.children
    cmd.undo(m)
    assert inst in m.root.children
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_instance_lifecycle_commands.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

Add to `python/pluton/model/model.py`:
```python
    def clone_definition(self, definition):
        """Deep-copy a definition's geometry + child instances into a fresh def."""
        clone = self.new_definition(definition.name, definition.is_group)
        idmap = {}
        for v in definition.mesh.vertices_iter():
            idmap[v.id] = clone.mesh.add_vertex(v.position)
        for e in definition.mesh.edges_iter():
            clone.mesh.add_edge(idmap[e.v1_id], idmap[e.v2_id])
        for f in definition.mesh.faces_iter():
            clone.mesh.add_face_from_loop([idmap[v] for v in f.loop_vertex_ids])
        for child in definition.children:
            clone.children.append(self.new_instance(child.definition, child.transform))
        return clone
```

```python
# python/pluton/commands/instance_lifecycle_commands.py
from __future__ import annotations

from pluton.commands.command import Command


class MakeUniqueCommand(Command):
    name = "Make Unique"

    def __init__(self, instance) -> None:
        self._inst = instance
        self._old_def = instance.definition
        self._clone = None

    def do(self, model) -> None:  # noqa: ANN001
        if len(self._old_def.instances) <= 1:
            return  # already unique — no-op
        if self._clone is None:
            self._clone = model.clone_definition(self._old_def)
        self._old_def.instances.remove(self._inst)
        self._inst.definition = self._clone
        if self._inst not in self._clone.instances:
            self._clone.instances.append(self._inst)

    def undo(self, model) -> None:  # noqa: ANN001
        if self._clone is None:
            return
        if self._inst in self._clone.instances:
            self._clone.instances.remove(self._inst)
        self._inst.definition = self._old_def
        if self._inst not in self._old_def.instances:
            self._old_def.instances.append(self._inst)


class DeleteInstanceCommand(Command):
    name = "Delete"

    def __init__(self, parent_definition, instance) -> None:
        self._parent = parent_definition
        self._inst = instance

    def do(self, model) -> None:  # noqa: ANN001
        if self._inst in self._parent.children:
            self._parent.children.remove(self._inst)
        if self._inst in self._inst.definition.instances:
            self._inst.definition.instances.remove(self._inst)

    def undo(self, model) -> None:  # noqa: ANN001
        self._parent.children.append(self._inst)
        if self._inst not in self._inst.definition.instances:
            self._inst.definition.instances.append(self._inst)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_instance_lifecycle_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py python/pluton/commands/instance_lifecycle_commands.py tests/test_instance_lifecycle_commands.py && git commit -m "feat(m4e): MakeUnique + DeleteInstance commands; Model.clone_definition

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 4 — Integration (regression-critical: root/identity == today)

### Task 10: MainWindow owns a `Model`; ToolContext routes to the active scene

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Modify: `python/pluton/viewport/viewport_widget.py`
- Test: `tests/test_main_window_model.py` (pytest-qt)

**Interfaces:**
- `MainWindow._model: Model` replaces `MainWindow._scene`. A read-only property `MainWindow.scene` returns `self._model.active_scene` for back-compat with any internal reference.
- `ToolContext.scene` is set to `self._model.active_scene` and the context is rebuilt + the active tool re-activated whenever the active context changes (`_rebuild_tool_context()`).
- ViewportWidget holds `self.model` and exposes `self.scene` as `self.model.active_scene` (property) so the renderer/snap calls keep working.

**Key edits (precise):**
- `main_window.py:50` `self._scene = Scene()` → `self._model = Model()`.
- Add: `@property def scene(self): return self._model.active_scene`.
- Everywhere `self._scene` is referenced (lines ~69, 76, 254, 294, 317-322 etc.) → `self._model.active_scene` (or `self.scene`). For `ClearSceneCommand` (line 254) and delete composite (line 294), `self._model.active_scene` is correct (clear/delete operate on the active context).
- The two undo/redo handlers already drop the scene arg (Task 5); after undo/redo also call `self._model.revalidate_active_path()` and rebuild the tool context. Add to `_on_after_undo_redo` (main_window.py:311-314): `self._model.revalidate_active_path(); self._rebuild_tool_context()`.
- Extract the `ToolContext(...)` construction (lines 74-82) into `def _rebuild_tool_context(self): self._tool_manager.set_context(ToolContext(scene=self._model.active_scene, ..., units_provider=lambda: self._doc.units)); active = self._tool_manager.active; (active.activate(...) re-run if not None)`. Verify `ToolManager.set_context` re-activates or call the active tool's `activate` with the new context.
- `viewport_widget.py`: constructor takes `model` (or keep `scene` param but pass `self._model.active_scene`); add `@property def scene(self): return self.model.active_scene`. Pass `self.model` from `main_window.py:69`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_window_model.py
import numpy as np
import pytest
from pluton.ui.main_window import MainWindow


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_mainwindow_has_model_with_root_scene(win):
    assert win._model is not None
    assert win.scene is win._model.active_scene
    assert win.scene is win._model.root.mesh


def test_active_scene_follows_entered_context(win):
    d = win._model.new_definition("G", is_group=True)
    inst = win._model.new_instance(d)
    win._model.root.children.append(inst)
    win._model.enter(inst)
    win._rebuild_tool_context()
    assert win.scene is d.mesh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_main_window_model.py -v`
Expected: FAIL — `AttributeError: _model`.

- [ ] **Step 3: Implement the edits above.** Replace `_scene` with `_model`, add the `scene` property, extract `_rebuild_tool_context`, route ViewportWidget to the model.

- [ ] **Step 4: Run the FULL suite (regression-critical)**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Expected: all pass. The app at the root context with identity transform is behaviorally identical to before.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py python/pluton/viewport/viewport_widget.py tests/test_main_window_model.py && git commit -m "feat(m4e): MainWindow owns a Model; ToolContext routes to the active scene

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Renderer draws the whole graph (per-definition model matrix)

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`
- Modify: `python/pluton/viewport/viewport_widget.py` (pass `model` to `render`)
- Test: manual + existing renderer regression tests.

**Interfaces:**
- `SceneRenderer.render(camera, model=None, tool_overlay=None, selection=None)` — iterates `model.traverse()`, drawing each definition's buffers with its `world_transform` as `u_model`. Per-definition GL buffers are cached in a dict keyed by `id(definition)`, re-uploaded only when that definition's `mesh.dirty` is set; `mesh.mark_clean()` per definition after upload.

**Approach (precise):**
- Replace the single `_user_face_vbo`/`_user_edge_vbo` usage in `_refresh_user_buffers` (lines 505-531) + `_draw_user_faces`/`_draw_user_edges` with a per-definition cache: `self._def_buffers: dict[int, _DefBuffers]`. `_DefBuffers` holds the face VBO, edge VBO, and vertex counts.
- In `render` (line 331): after grid/axes, do:
  ```python
  for definition, world in model.traverse():
      buf = self._def_buffers.get(id(definition))
      if buf is None or definition.mesh.dirty:
          buf = self._upload_definition(definition)   # builds/updates _DefBuffers
          definition.mesh.mark_clean()
          self._def_buffers[id(definition)] = buf
      model_mat = world.astype(np.float32)
      self._draw_definition_faces(buf, view, projection, camera_pos, model_mat, dimmed=...)
      self._draw_definition_edges(buf, view, projection, model_mat, dimmed=...)
  ```
- `u_model` (currently hardcoded `np.eye(4)` at line 544) becomes `model_mat`.
- Keep selection highlight + tool overlay drawing AFTER the loop (they operate on the active context only — see Task 15 for the dim flag + bbox).
- For this task, pass `dimmed=False` for all; the dim pass lands in Task 15. The goal here is multi-definition drawing with correct transforms while the single-root case stays pixel-identical.

- [ ] **Step 1: Write the failing test (headless buffer build)**

```python
# tests/test_renderer_traverse_buffers.py
# A light test that the renderer can build per-definition buffers from a Model
# without a GL context is impractical (GL calls). Instead assert the data path:
import numpy as np
from pluton.model.model import Model


def test_model_traverse_provides_drawable_pairs():
    m = Model()
    m.root.mesh.add_vertex(np.array([0, 0, 0], np.float32))
    g = m.new_definition("G", is_group=True)
    g.mesh.add_vertex(np.array([0, 0, 0], np.float32))
    t = np.eye(4); t[:3, 3] = [4, 0, 0]
    inst = m.new_instance(g, t); m.root.children.append(inst)
    pairs = list(m.traverse())
    assert len(pairs) == 2
    # The renderer will draw g's buffer with this model matrix:
    assert np.allclose(pairs[1][1][:3, 3], [4, 0, 0])
```

- [ ] **Step 2: Run it (passes already — it exercises Model)**; then implement the renderer changes and verify no regression visually.

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_renderer_traverse_buffers.py -v`

- [ ] **Step 3: Implement the per-definition buffer cache + traverse draw loop** as described.

- [ ] **Step 4: Regression + manual visual check**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Then launch the app (`.venv/Scripts/python.exe -m pluton`) and confirm a single drawn box looks identical to before. Build a box, verify edges/faces render.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/scene_renderer.py python/pluton/viewport/viewport_widget.py tests/test_renderer_traverse_buffers.py && git commit -m "feat(m4e): renderer draws the scene graph with per-definition model matrices

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Picking + snap honor the active world transform

**Files:**
- Modify: `python/pluton/viewport/picking.py`
- Modify: `python/pluton/viewport/snap_engine.py`
- Modify: `python/pluton/viewport/viewport_widget.py` (pass the active transform)
- Test: `tests/test_picking_transform.py`

**Interfaces:**
- `pick_selectable(cursor, size, camera, scene, world_transform=None)` and `entities_in_box(rect, mode, size, camera, scene, world_transform=None)` gain an optional `world_transform` (`(4,4)`, default identity). When non-identity, project local vertices to screen via `world_transform` and transform the camera ray into local space for the face ray-test.
- `SnapEngine.snap(..., world_transform=None)` similarly converts.
- `viewport_widget` passes `self.model.active_world_transform` (or identity when at root).

**Approach (precise):**
- In `pick_selectable`, where edge endpoints are projected to screen: transform each endpoint through `world_transform` first (use `apply_mat`). Where the face ray test is done (`scene.ray_pick_face(origin, direction)`): if `world_transform` non-identity, transform `(origin, direction)` by `mat_invert(world_transform)` before the call (point-transform origin; vector-transform direction with the 3×3 block).
- Default `world_transform=None` ⇒ skip all conversion ⇒ identical to today (regression-safe).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_picking_transform.py
import numpy as np
from pluton.viewport.picking import pick_selectable
# This test verifies the signature accepts world_transform and that identity
# matches the no-arg behavior. (Full screen-space asserts need a camera fixture;
# reuse the camera fixture pattern from the existing tests/test_picking*.py.)


def test_pick_selectable_accepts_world_transform_kwarg():
    import inspect
    sig = inspect.signature(pick_selectable)
    assert "world_transform" in sig.parameters
```

*(Augment with a real pick assertion mirroring the existing `tests/test_picking*.py` camera fixture: build geometry inside a translated definition, pass `world_transform=translate(+10x)`, and assert the entity is hit at the translated screen location.)*

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_picking_transform.py -v`
Expected: FAIL — no `world_transform` parameter.

- [ ] **Step 3: Implement the optional `world_transform` conversion** in picking + snap, threaded from viewport_widget.

- [ ] **Step 4: Full regression**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Expected: all pass (identity default unchanged).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/picking.py python/pluton/viewport/snap_engine.py python/pluton/viewport/viewport_widget.py tests/test_picking_transform.py && git commit -m "feat(m4e): picking + snap honor the active world transform (identity default)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 5 — Editing context & selection

### Task 13: `Selection.instances` + object picking

**Files:**
- Modify: `python/pluton/selection.py`
- Modify: `python/pluton/viewport/picking.py` (add `pick_instance`)
- Modify: `python/pluton/model/model.py` (add `pick_instance` walk)
- Test: `tests/test_selection_instances.py`, `tests/test_model_pick_instance.py`

**Interfaces:**
- `Selection` gains: `instances: set[int]` property; `replace(..., instances=())`, `add(..., instances=())`, `toggle_instance(i_id)`, `contains_instance(i_id)`; `clear()` clears instances too; `is_empty()` includes instances; `counts()` returns `(edges, faces, instances)`.
- `Model.pick_instance(origin, direction) -> Instance | None` — among the **active context's** direct children, returns the instance whose definition mesh the ray hits nearest (ray transformed into each instance's local frame via `mat_invert(world_transform)`; reuse `scene.ray_pick_face`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_selection_instances.py
from pluton.selection import Selection


def test_selection_tracks_instances():
    s = Selection()
    s.replace(instances=[3, 5])
    assert s.instances == {3, 5}
    assert not s.is_empty()
    s.toggle_instance(3)
    assert s.instances == {5}
    s.clear()
    assert s.is_empty()
    assert s.counts() == (0, 0, 0)
```

```python
# tests/test_model_pick_instance.py
import numpy as np
from pluton.model.model import Model


def _unit_quad(scene):
    a = scene.add_vertex(np.array([-1, -1, 0], np.float32))
    b = scene.add_vertex(np.array([1, -1, 0], np.float32))
    c = scene.add_vertex(np.array([1, 1, 0], np.float32))
    d = scene.add_vertex(np.array([-1, 1, 0], np.float32))
    scene.add_face_from_loop([a, b, c, d])


def test_pick_instance_hits_translated_child():
    m = Model()
    g = m.new_definition("G", is_group=True)
    _unit_quad(g.mesh)
    t = np.eye(4); t[:3, 3] = [10, 0, 0]
    inst = m.new_instance(g, t); m.root.children.append(inst)
    # Ray from above the translated quad pointing down (-z):
    hit = m.pick_instance(np.array([10, 0, 5], np.float32), np.array([0, 0, -1], np.float32))
    assert hit is inst
    # A ray over the origin (where nothing is) misses:
    miss = m.pick_instance(np.array([0, 0, 5], np.float32), np.array([0, 0, -1], np.float32))
    assert miss is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_selection_instances.py tests/test_model_pick_instance.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** the `Selection.instances` bucket (mirror edges/faces) and:
```python
    # python/pluton/model/model.py
    def pick_instance(self, origin, direction):
        from pluton.geometry.transforms import mat_invert
        best, best_t = None, float("inf")
        world0 = self.active_world_transform
        for inst in self.active_context.children:
            world = world0 @ inst.transform
            inv = mat_invert(world)
            o = (inv @ np.append(origin, 1.0))[:3]
            d = inv[:3, :3] @ np.asarray(direction, np.float64)
            hit = inst.definition.mesh.ray_pick_face(o, d)
            if hit is not None and hit.t < best_t:
                best, best_t = inst, hit.t
        return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest tests/test_selection_instances.py tests/test_model_pick_instance.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/selection.py python/pluton/model/model.py python/pluton/viewport/picking.py tests/test_selection_instances.py tests/test_model_pick_instance.py && git commit -m "feat(m4e): Selection.instances + Model.pick_instance (ray into local frame)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: SelectTool — object pick, enter/exit, hover

**Files:**
- Modify: `python/pluton/tools/select_tool.py`
- Modify: `python/pluton/ui/main_window.py` (enter/exit plumbing: a `_model`/context handle on the tool context; breadcrumb refresh)
- Test: `tests/test_select_tool_objects.py` (pytest-qt or headless with a fake ctx)

**Interfaces:**
- SelectTool reads `ctx` for the `Model` (add `model` to `ToolContext`, default None) to call `pick_instance`, `enter`, `exit_one`, and to read `active_context`.
- Single left-click: if `pick_instance` hits an instance → select it (`selection.replace(instances=[hit.id])` or shift→toggle); else fall through to existing entity pick; if nothing and inside a group → `model.exit_one()` + rebuild context.
- Double-click an instance → `model.enter(inst)`, clear selection, rebuild context, refresh breadcrumb.
- Hover: `pick_instance` for object silhouette (store hovered instance id) in addition to entity hover.

**Interfaces produced for later tasks:** `ToolContext.model: object = None` (the `Model`) — add the field to the dataclass in `tool.py` and pass `model=self._model` from `MainWindow._rebuild_tool_context()` (Task 10); `MainWindow._enter_instance(inst)` / `_exit_context()` helpers that call into the model + `_rebuild_tool_context()` + breadcrumb update.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_select_tool_objects.py
import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent
from pluton.model.model import Model
from pluton.selection import Selection
from pluton.tools.select_tool import SelectTool
from pluton.tools.tool import ToolContext
# Reuse the camera/size fixtures from existing tests/test_select_tool*.py.


def test_double_click_enters_instance(qtbot, monkeypatch):
    m = Model()
    g = m.new_definition("G", is_group=True)
    inst = m.new_instance(g); m.root.children.append(inst)
    sel = Selection()
    # Force pick_instance to return our instance regardless of ray:
    monkeypatch.setattr(m, "pick_instance", lambda o, d: inst)
    tool = SelectTool()
    ctx = ToolContext(scene=m.active_scene, selection=sel, model=m)  # camera/size from fixtures
    tool.activate(ctx)
    evt = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick, QPointF(100, 100),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    tool.on_mouse_double_click(evt, None)
    assert m.active_context is g          # double-click entered the instance
```

*(Reuse the camera/`widget_size_provider` fixtures from the existing `tests/test_select_tool*.py` when constructing `ctx`; the assertion is the contract: a double-click on an instance enters it.)*

- [ ] **Step 2: Run it to verify it fails**, then implement the object-pick + enter/exit branches in SelectTool and the MainWindow plumbing (`ToolContext.model`, `_enter_instance`, `_exit_context`, double-click forwarding from the viewport — add `mouseDoubleClickEvent` to `viewport_widget.py` that calls the active tool's `on_mouse_double_click` if present).

- [ ] **Step 3: Implement.** Add `on_mouse_double_click(self, event, snap)` to the `Tool` ABC (default no-op) and to `SelectTool`. Wire `viewport_widget.mouseDoubleClickEvent`.

- [ ] **Step 4: Regression + manual**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Manual: create geometry, group it (after Task 16), double-click to enter, Esc to exit.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/select_tool.py python/pluton/tools/tool.py python/pluton/viewport/viewport_widget.py python/pluton/ui/main_window.py tests/test_select_tool_objects.py && git commit -m "feat(m4e): SelectTool object pick + double-click enter / click-out exit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Dim pass, object bbox, hover silhouette, breadcrumb

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`
- Modify: `python/pluton/ui/status_bar.py` + `python/pluton/ui/main_window.py` (breadcrumb)
- Test: manual visual + a headless bbox-corners test.

**Interfaces:**
- `render(...)` receives the active path (e.g. `model.active_path`) to decide, per traversed definition, whether it's on the active path → full color, else → dimmed (desaturate + alpha). Pass a `dimmed` flag to the per-definition draw calls (Task 11 hook).
- Object selection overlay: for each `inst.id in selection.instances`, draw the world-space bbox from `inst.definition.local_aabb()` transformed by its world transform (12 edges + corner ticks), selection-blue.
- Hover overlay: silhouette for the hovered instance.
- Breadcrumb: `StatusBar` shows `Model ▸ <name> ▸ …` from `model.active_path`.

**Interfaces produced:** `def aabb_world_edges(lo, hi, world_transform) -> np.ndarray (24,3)` helper in `scene_renderer.py` (12 segments) — unit-testable.

- [ ] **Step 1: Write the failing test (bbox edges)**

```python
# tests/test_bbox_edges.py
import numpy as np
from pluton.viewport.scene_renderer import aabb_world_edges


def test_aabb_world_edges_count_and_translation():
    lo = np.array([0, 0, 0], np.float32); hi = np.array([1, 1, 1], np.float32)
    t = np.eye(4); t[:3, 3] = [10, 0, 0]
    segs = aabb_world_edges(lo, hi, t)
    assert segs.shape == (24, 3)            # 12 edges * 2 endpoints
    assert segs[:, 0].min() >= 10.0 - 1e-6  # translated +10 in x
```

- [ ] **Step 2: Run it to verify it fails**, then implement `aabb_world_edges` + the dim flag + bbox/hover overlays + breadcrumb.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Regression + manual**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Manual: enter a group → rest of model dims; select an instance → blue bbox; hover → silhouette; breadcrumb updates.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/scene_renderer.py python/pluton/ui/status_bar.py python/pluton/ui/main_window.py tests/test_bbox_edges.py && git commit -m "feat(m4e): dim pass + object bbox + hover silhouette + active-path breadcrumb

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 6 — Operations & UI

### Task 16: Edit menu + Make Group / Make Component / Explode / Make Unique

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Create: `python/pluton/ui/name_dialog.py` (minimal component-name prompt)
- Test: `tests/test_make_group_action.py` (pytest-qt)

**Interfaces:**
- New **Edit** menu (added before/after the Units menu) with actions: "Make Group" (`Ctrl+G`), "Make Component…" (`Ctrl+Shift+G`), "Explode" (`Ctrl+Shift+E`), "Make Unique". Each enabled/disabled by selection contents.
- Handlers build the corresponding command with `self._model.active_context` as the parent and the current selection, then `self._command_stack.execute(cmd, self._model)`. After Make Group/Component, set `selection.replace(instances=[cmd.created_instance.id])`.
- `QShortcut("Ctrl+G")`, `QShortcut("Ctrl+Shift+G")`, `QShortcut("Ctrl+Shift+E")` added to the shortcut block (lines ~100-123).
- **Instance Delete (spec §7.7):** extend `_on_delete_selection` (main_window.py:258-297) so that when `self._selection.instances` is non-empty, it builds a `DeleteInstanceCommand` per selected instance (resolved from `self._model.active_context.children` by id), wraps them in a `CompositeCommand` if >1, and runs `self._command_stack.execute(cmd, self._model)`. The existing entity-delete path runs when only edges/faces are selected.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_make_group_action.py
import numpy as np
import pytest
from pluton.ui.main_window import MainWindow


@pytest.fixture
def win(qtbot):
    w = MainWindow(); qtbot.addWidget(w); return w


def test_make_group_action_creates_instance_from_selection(win):
    s = win._model.root.mesh
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([1, 0, 0], np.float32))
    c = s.add_vertex(np.array([0, 1, 0], np.float32))
    f = s.add_face_from_loop([a, b, c])
    win._selection.replace(faces=[f])
    win._on_make_group()            # the menu/shortcut handler
    assert len(win._model.root.children) == 1
    assert win._model.root.children[0].definition.is_group is True
    # Undo restores loose geometry:
    win._command_stack.undo()
    assert len(win._model.root.children) == 0
    assert len(list(win._model.root.mesh.faces_iter())) == 1
```

- [ ] **Step 2: Run it to verify it fails**, then implement the Edit menu, the four handlers (`_on_make_group`, `_on_make_component`, `_on_explode`, `_on_make_unique`), the name dialog, and the shortcuts. For the handlers, derive `vertex_ids/edge_ids/face_ids` from the selection using `selection_vertices` (verts) + `selection.edges` + `selection.faces`.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Regression + manual**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Manual: select a face → Ctrl+G groups it; Ctrl+Shift+G prompts a name and makes a component; Explode/Make Unique via the Edit menu.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py python/pluton/ui/name_dialog.py tests/test_make_group_action.py && git commit -m "feat(m4e): Edit menu — Make Group/Component/Explode/Make Unique + shortcuts

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Move / Rotate / Scale operate on a selected instance

**Files:**
- Modify: `python/pluton/tools/move_tool.py`, `rotate_tool.py`, `scale_tool.py`
- Modify: `python/pluton/tools/tool.py` (ToolContext already gained `model` in Task 14)
- Test: `tests/test_transform_instance_mode.py`

**Interfaces:**
- Each transform tool, on gesture start, checks `ctx.selection.instances`. **Precedence:** if non-empty, the tool is in **instance-mode** — it computes the gesture's 4×4 delta matrix and emits a `TransformInstanceCommand(instance, new_transform = delta @ instance.transform)` via `self._stack.execute(cmd, self._model)` (one command per selected instance, wrapped in a `CompositeCommand` if >1). Otherwise existing entity-vertex behavior runs unchanged.
- Move delta = `mat_translate(self._delta)`. Rotate delta = `mat_rotate(center, normal, angle)`. Scale delta = `mat_scale(anchor, factor_vec)`.
- **VCB / typed values in instance-mode (spec §12):** each tool's `apply_typed_value(text, units)` must also branch on `ctx.selection.instances`. When in instance-mode, the typed distance/angle/factor produces the same delta matrix and emits the `TransformInstanceCommand` (instead of `TransformVerticesCommand`). Add a unit test mirroring the entity-mode `apply_typed_value` tests but asserting the instance transform changed.
- The tool needs the `Model` (for `execute(cmd, self._model)`) — read it from `ctx.model` (added in Task 14) at `activate`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transform_instance_mode.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.instance_commands import TransformInstanceCommand
from pluton.geometry.transforms import mat_translate


def test_move_in_instance_mode_emits_transform_instance(monkeypatch):
    # Unit-level: a translated delta applied to an instance transform composes left.
    m = Model()
    d = m.new_definition("G", is_group=True)
    inst = m.new_instance(d); m.root.children.append(inst)
    delta = mat_translate([3, 0, 0])
    cmd = TransformInstanceCommand(inst, delta @ inst.transform)
    cmd.do(m)
    assert np.allclose(inst.transform[:3, 3], [3, 0, 0])
```

*(The tool-level assertion — driving Move with a fake snap in instance-mode and checking the instance moved — should mirror the existing `tests/test_move_tool*.py` fixtures.)*

- [ ] **Step 2: Run it to verify it fails / passes the unit part**, then implement the instance-mode branch in each tool.

- [ ] **Step 3: Implement** the `ctx.selection.instances` precedence branch in Move/Rotate/Scale.

- [ ] **Step 4: Regression + manual**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Manual: select a group, Move/Rotate/Scale it as a unit; undo/redo.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/move_tool.py python/pluton/tools/rotate_tool.py python/pluton/tools/scale_tool.py tests/test_transform_instance_mode.py && git commit -m "feat(m4e): Move/Rotate/Scale operate on selected instances (transform matrix)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: Move-copy (Ctrl during Move → new instance)

**Files:**
- Modify: `python/pluton/tools/move_tool.py`
- Test: `tests/test_move_copy.py`

**Interfaces:**
- In instance-mode Move, if `Ctrl` is held at release, instead of `TransformInstanceCommand`, emit `CreateInstanceCommand(parent=active_context, definition=inst.definition, transform=delta @ inst.transform)` — the original stays put, a new instance appears at the moved transform. Multiple selected instances → a `CompositeCommand` of `CreateInstanceCommand`s.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_move_copy.py
import numpy as np
from pluton.model.model import Model
from pluton.commands.instance_commands import CreateInstanceCommand
from pluton.geometry.transforms import mat_translate


def test_move_copy_adds_instance_of_same_definition():
    m = Model()
    d = m.new_definition("Chair", is_group=False)
    base = m.new_instance(d); m.root.children.append(base)
    cmd = CreateInstanceCommand(m.root, d, mat_translate([5, 0, 0]) @ base.transform)
    cmd.do(m)
    assert len(m.root.children) == 2
    assert all(child.definition is d for child in m.root.children)
    assert np.allclose(m.root.children[1].transform[:3, 3], [5, 0, 0])
```

*(Tool-level: drive Move with Ctrl held using the existing move-tool test fixtures and assert a second instance exists.)*

- [ ] **Step 2: Run it to verify it fails / passes the unit part**, then implement the Ctrl-at-release branch in MoveTool.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Regression + manual**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Manual: select a component, Move with Ctrl → a second instance is left behind; edit one instance's geometry (enter it, push/pull) → both update.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/move_tool.py tests/test_move_copy.py && git commit -m "feat(m4e): Move-copy (Ctrl during Move) creates a new instance

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

# Phase 7 — Verification & release

### Task 19: Full regression + manual visual verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire suite**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pytest -q`
Expected: all pass (the ~417 prior + all M4e tests).

- [ ] **Step 2: Run the C++ tests (must be untouched-green)**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && ctest --test-dir build/<wheel_tag> --output-on-failure` (or the project's standard ctest invocation). Expected: 76/76.

- [ ] **Step 3: Ruff**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m ruff check python/pluton`
Fix any findings (CI doesn't gate ruff, but keep clean).

- [ ] **Step 4: Manual visual pass** (launch `.venv/Scripts/python.exe -m pluton`):
  1. Draw a box; select all its faces; **Ctrl+G** → it becomes a group (blue bbox on select).
  2. **Double-click** to enter → rest dims, breadcrumb shows `Model ▸ Group #N`; edit a face (push/pull); **Esc** to exit.
  3. Select the group; **Move** it as a unit; **Rotate**; **Scale**; undo/redo each.
  4. **Make Component** (Ctrl+Shift+G), name it; **Move with Ctrl** to drop a 2nd instance.
  5. Enter one instance, push/pull a face → **both instances update**.
  6. **Make Unique** on one → edits no longer propagate.
  7. **Explode** a group → geometry returns to loose; undo restores the group.
  8. Nested: group inside a group; enter twice; breadcrumb depth correct.

- [ ] **Step 5:** No commit (verification only). Record results in the progress ledger.

---

### Task 20: Release v0.1.4 (M4e)

**Files:**
- Modify: `pyproject.toml` (version `0.1.4`), `CMakeLists.txt` (VERSION `0.1.4`), `cpp/src/version.cpp` (return `"0.1.4"`), `docs/2026-05-16-pluton-design.md` (annotate M4e shipped).

- [ ] **Step 1:** Bump all three version files to `0.1.4`.

- [ ] **Step 2:** Rebuild + verify the embedded version:

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python.exe -m pip install -e . --no-build-isolation` then `.venv/Scripts/python.exe -c "import pluton._core as c; print(c.version())"` → `0.1.4`.

- [ ] **Step 3:** Full ctest (76) + pytest (all green).

- [ ] **Step 4:** Annotate the master design doc M4e line: append `✅ *(shipped v0.1.4)* — Groups & Components: unified Definition+Instance scene graph; create/enter-edit/move-as-unit/Move-copy/Explode/Make Unique; full-isolation editing context; edit-propagation across component instances`.

- [ ] **Step 5:** Commit the release:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md && git commit -m "release: v0.1.4 (M4e — Groups & Components)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6 (requires explicit user authorization):** push `main`; watch CI (Build & Test) to green on windows-2022 + ubuntu-24.04; create the annotated SSH-signed tag `v0.1.4-m4e` at the release commit; verify `BEGIN SSH SIGNATURE` count = 1; file carry-over issues (component browser, Outliner, on-disk persistence, clipboard copy/paste + loose-geometry copy, unused-definition GC, glue/cut/insertion-axes/dynamic components, VBO instancing, rename/Entity-Info panel — see spec §15).

---

## Notes for the executor

- **Phase 4 is the regression cliff.** After Tasks 10–12 the app must behave exactly as today at the root context. If any of the 417 existing tests fail, stop and fix before proceeding — the identity-transform path is the safety net.
- **Coordinate sign/compose conventions:** `apply_mat(p, world)` takes local→world; the inverse (`mat_invert(world)`) takes world→local. `instance.transform` is world-from-local. `mat_compose(A, B) == B @ A` (A applied first).
- **`CompositeCommand`** (existing) wraps multiple sub-commands for multi-instance operations; its `do/undo` already pass the threaded target through to children — so a composite of `TransformInstanceCommand`s executed with `target=model` works.
- **Naming counters:** group/component default names use `model._next_def_id`; if you prefer human-friendly sequential numbers, add a dedicated counter to `Model`.
- **Edge cleanup in MakeGroup/Explode undo:** the kernel may auto-remove edges when their vertices/faces go; the `try/except` guards tolerate that. If a test surfaces a leftover-edge assertion, capture edge ids explicitly and restore them first (mirror `DissolveEdgeCommand`'s restore order: edges before faces).

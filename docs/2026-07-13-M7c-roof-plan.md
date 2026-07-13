# M7c — Roof Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Roof tool (`O`) that bakes parametric **Gable / Hip / Shed** closed-solid roofs into the active context over a drawn rectangle footprint, ridge auto-aligned to the longer edge (arrow-key flip), form + slope from an options row. Ship as **v0.2.3**.

**Architecture:** Pure `roof_solid` generator → `CreateRoofCommand` (baked `"Roof"` group, clean reuse-on-redo undo) → `RoofTool` (draw rectangle footprint on the drawing plane, world→active-local placement transform, ridge flip) → `RoofOptionsBar` → MainWindow. Mirrors the M7a/M7b layering; **no C++/kernel change**.

**Tech Stack:** Python 3.13 + numpy; PySide6 (tool + options widget); pytest (+ pytest-qt for tool/UI).

**Spec:** `docs/2026-07-13-M7c-roof-design.md` (decisions D1–D10).

## Global Constraints

- **Layering:** `geometry/roof.py` is PURE (numpy only — no Model/Scene/Qt/GL). Only the command + tool touch Model/Scene. The generator works in a canonical footprint frame (centred at origin; `+X` = across-ridge, `+Y` = along-ridge, `+Z` = up; base at `z=0`). The roof is ONE closed solid with a shared vertex list.
- **No kernel change (D4/D10):** roofs are pure polygon generation → `ctest` stays **79/79**.
- **Baked group (D5):** each placement is a new `"Roof"` `Definition` (`is_group=True`) — no dedup registry. The command uses the clean reuse-on-redo lifecycle (cache Definition+Instance; redo re-attaches the *same* objects; undo detaches from both `children` and `defn.instances`), mirroring `CreateInstanceCommand`.
- **`# noqa` RULE (repo ruff `select=["E","F","W","I","N","UP","B","C4","RUF"]` — ANN NOT enabled):** do **NOT** write any `# noqa` in new code (an unused `noqa` for a non-enabled rule is itself `RUF100`). New files must be genuinely `ruff check`-clean. The M7a/M7b tools (`wall_tool.py`, `opening_tool.py`) prove the untyped `snap` parameter needs no `# noqa: ANN001` — follow them, not the older `rectangle_tool.py`.
- **Units:** slope stored in **degrees** on the tool; the options row parses/formats via `pluton.units.parse_angle` / `format_angle`. Lengths (thickness-like) are meters.
- **Tests:** `.venv/Scripts/python` explicitly; full suite under a timeout: `timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Baseline (v0.2.2): **826 pytest + 79/79 ctest**. New Python files ruff-clean. **NEVER** broad `ruff --fix` on `main_window.py` (issue #48 — exactly 9 deliberate pre-existing findings: 5 RUF100 + 3 E501 + 1 I001; additive-only, keep the count at 9).
- **Git:** stage specific files only (no `git add -A`). SSH-signed commits; never `--no-verify`/`--amend`/`--no-gpg-sign`. Trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. On `main`. Verify sig via `git cat-file -p <sha> | grep -c "BEGIN SSH SIGNATURE"` (==1); `git log --show-signature` "No signature" is a KNOWN local gap, not a failure.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) edited ONLY in the release task. `0.2.2` → `0.2.3`.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.

---

## File Structure

- Create `python/pluton/geometry/roof.py` — pure `roof_solid` + `_rot_z` (Task 1 shed/gable, Task 2 hip).
- Create `python/pluton/commands/roof_commands.py` — `CreateRoofCommand` (Task 3).
- Create `python/pluton/tools/roof_tool.py` — `RoofTool` (Task 4).
- Create `python/pluton/ui/roof_options_bar.py` — `RoofOptionsBar` (Task 5).
- Modify `python/pluton/ui/main_window.py` — register the tool, host the options row, `O` shortcut + menu (Task 6; additive; issue #48).
- Tests: `tests/test_roof_geometry.py`, `tests/test_roof_commands.py`, `tests/test_roof_tool.py`, `tests/test_roof_options_bar.py`, `tests/test_main_window_roof.py`.

---

### Task 1: `roof_solid` — module + Shed + Gable

**Files:**
- Create: `python/pluton/geometry/roof.py`
- Test: `tests/test_roof_geometry.py`

**Interfaces:**
- Produces: `roof_solid(kind, width, depth, angle) -> (vertices, faces)` — a closed solid in the canonical frame, or `([], [])` if degenerate. `kind` is `"shed"`, `"gable"`, or `"hip"` (hip added in Task 2). `angle` is in **degrees**. `vertices` is a list of `(x,y,z)` float tuples; `faces` a list of index tuples (outward-wound). Consumed by `CreateRoofCommand` (Task 3) and `RoofTool` preview (Task 4).

- [ ] **Step 1: Write the failing test**

`tests/test_roof_geometry.py`:

```python
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from pluton.geometry.roof import roof_solid


def _edge_counts(faces):
    edges = Counter()
    for f in faces:
        n = len(f)
        for i in range(n):
            edges[frozenset((f[i], f[(i + 1) % n]))] += 1
    return edges


def _closed(faces):
    return all(c == 2 for c in _edge_counts(faces).values())


def _bbox(verts):
    a = np.array(verts, dtype=np.float64)
    return a.min(axis=0), a.max(axis=0)


def test_shed_counts_and_closed():
    verts, faces = roof_solid("shed", width=4.0, depth=6.0, angle=30.0)
    assert len(verts) == 6
    assert len(faces) == 5
    assert _closed(faces)


def test_gable_counts_and_closed():
    verts, faces = roof_solid("gable", width=4.0, depth=6.0, angle=30.0)
    assert len(verts) == 6
    assert len(faces) == 5
    assert _closed(faces)


def test_gable_ridge_height_and_extent():
    w, d, ang = 4.0, 6.0, 30.0
    verts, _ = roof_solid("gable", w, d, ang)
    lo, hi = _bbox(verts)
    # footprint centred; base at z=0; ridge height = (w/2)*tan(angle)
    assert np.allclose(lo, [-w / 2, -d / 2, 0.0])
    assert np.isclose(hi[2], (w / 2) * math.tan(math.radians(ang)))
    assert np.allclose([hi[0], hi[1]], [w / 2, d / 2])


def test_shed_high_edge_height():
    w, d, ang = 4.0, 6.0, 30.0
    verts, _ = roof_solid("shed", w, d, ang)
    _, hi = _bbox(verts)
    # shed rises across the full width: H = w*tan(angle)
    assert np.isclose(hi[2], w * math.tan(math.radians(ang)))


def test_identical_params_identical_geometry():
    a = roof_solid("gable", 4.0, 6.0, 30.0)
    b = roof_solid("gable", 4.0, 6.0, 30.0)
    assert a[0] == b[0] and a[1] == b[1]


def test_degenerate_returns_empty():
    assert roof_solid("gable", 0.0, 6.0, 30.0) == ([], [])
    assert roof_solid("gable", 4.0, 0.0, 30.0) == ([], [])
    assert roof_solid("gable", 4.0, 6.0, 0.0) == ([], [])
    assert roof_solid("gable", 4.0, 6.0, 90.0) == ([], [])
    assert roof_solid("shed", 4.0, 6.0, -5.0) == ([], [])
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_geometry.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.geometry.roof`).

- [ ] **Step 3: Implement the module + shed + gable**

`python/pluton/geometry/roof.py`:

```python
"""Pure geometry for the Roof tool (M7c).

roof_solid builds a parametric Gable / Hip / Shed roof as ONE closed solid
(shared vertex list, outward-wound faces) in a canonical footprint frame:
origin at the footprint centre; +X = across-ridge span, +Y = along-ridge span,
+Z = up; base at z=0. No Model/Scene/Qt/GL deps.

_rot_z is a small 4x4 Z-rotation helper the tool uses to orient the canonical
roof onto the drawn footprint (kept here so the geometry frame conventions live
in one place).
"""
from __future__ import annotations

import numpy as np

_MAX_SLOPE_DEG = 85.0


def _rot_z(theta: float) -> np.ndarray:
    """4x4 rotation about +Z by theta radians."""
    c, s = float(np.cos(theta)), float(np.sin(theta))
    return np.array(
        [[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _finish(verts):
    return [(float(x), float(y), float(z)) for (x, y, z) in verts]


def roof_solid(kind, width, depth, angle):
    """Return (vertices, faces) for a Gable/Hip/Shed roof, or ([], []) if degenerate.

    kind: "shed" (mono-pitch), "gable" (full-depth ridge), or "hip" (ridge set
    back from both ends; pyramidal when depth <= width). angle is in degrees.
    """
    w = float(width)
    d = float(depth)
    a = float(angle)
    if w <= 0.0 or d <= 0.0 or a <= 0.0 or a > _MAX_SLOPE_DEG:
        return [], []
    t = float(np.tan(np.radians(a)))
    hw, hd = w / 2.0, d / 2.0

    if kind == "shed":
        big_h = w * t
        verts = [
            (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
            (hw, -hd, big_h), (hw, hd, big_h),                              # high edge 4,5
        ]
        faces = [
            (0, 3, 2, 1),      # base (-Z)
            (0, 4, 5, 3),      # sloped top
            (1, 2, 5, 4),      # high wall (+X)
            (0, 1, 4),         # -Y side
            (2, 3, 5),         # +Y side
        ]
        return _finish(verts), faces

    if kind == "gable":
        h = hw * t
        verts = [
            (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
            (0.0, -hd, h), (0.0, hd, h),                                    # ridge 4,5
        ]
        faces = [
            (0, 3, 2, 1),      # base
            (1, 2, 5, 4),      # +X slope
            (3, 0, 4, 5),      # -X slope
            (0, 1, 4),         # -Y gable end
            (2, 3, 5),         # +Y gable end
        ]
        return _finish(verts), faces

    # "hip" is added in Task 2; until then any unrecognised kind -> empty.
    return [], []
```

*(Task 1 deliberately does NOT reference `_hip` — a forward reference to an undefined name would be an `F821` at lint time. Task 2 replaces this final `return [], []` branch with the `"hip"` dispatch.)*

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_geometry.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/geometry/roof.py tests/test_roof_geometry.py
```
Expected: 6 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/roof.py tests/test_roof_geometry.py && git commit -m "$(cat <<'EOF'
feat(m7c): roof_solid generator — Shed + Gable closed solids

Pure numpy generator building a mono-pitch Shed or full-depth-ridge Gable roof
as one closed outward-wound solid in a canonical footprint frame (origin at
footprint centre, +Z up, base z=0). Degenerate/steep -> empty. Hip added next.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `roof_solid` — Hip (ridge + pyramidal cases)

**Files:**
- Modify: `python/pluton/geometry/roof.py` (add `_hip`, wire the `"hip"` branch)
- Test: `tests/test_roof_geometry.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `roof_solid("hip", ...)` — equal-pitch hip: when `depth > width` a ridge set back by the hip run (6 verts / 5 faces); when `depth <= width` a pyramidal (tented) apex (5 verts / 5 faces).

- [ ] **Step 1: Write the failing test** (append to `tests/test_roof_geometry.py`)

```python
def test_hip_ridge_case_counts_and_closed():
    # depth > width -> a ridge set back from both ends
    verts, faces = roof_solid("hip", width=4.0, depth=6.0, angle=30.0)
    assert len(verts) == 6
    assert len(faces) == 5
    assert _closed(faces)


def test_hip_pyramid_case_counts_and_closed():
    # depth <= width -> pyramidal apex (single point)
    verts, faces = roof_solid("hip", width=6.0, depth=4.0, angle=30.0)
    assert len(verts) == 5
    assert len(faces) == 5
    assert _closed(faces)


def test_hip_apex_height_equal_pitch():
    # apex height = min(w, d)/2 * tan(angle)
    for w, d in [(4.0, 6.0), (6.0, 4.0), (5.0, 5.0)]:
        verts, _ = roof_solid("hip", w, d, 35.0)
        _, hi = _bbox(verts)
        assert np.isclose(hi[2], min(w, d) / 2.0 * math.tan(math.radians(35.0)))


def test_hip_ridge_setback_length():
    # for d > w, ridge length along Y == d - w (hip run = w/2 each end)
    w, d = 4.0, 10.0
    verts, _ = roof_solid("hip", w, d, 30.0)
    a = np.array(verts)
    apex_z = (w / 2.0) * math.tan(math.radians(30.0))
    ridge = a[np.isclose(a[:, 2], apex_z)]
    assert len(ridge) == 2
    assert np.isclose(abs(ridge[:, 1].max() - ridge[:, 1].min()), d - w)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_geometry.py -q -p no:cacheprovider
```
Expected: FAIL (hip returns `([], [])` → count assertions fail).

- [ ] **Step 3: Implement `_hip`** (append to `roof.py`, and change the final `roof_solid` branch to call it)

Change the final branch of `roof_solid` from `return [], []` to:

```python
    if kind == "hip":
        return _hip(hw, hd, w, d, t)
    return [], []
```

Then append:

```python
def _hip(hw, hd, w, d, t):
    """Equal-pitch hip. depth>width -> ridge set back by w/2 each end;
    depth<=width -> pyramidal apex. hw/hd are half width/depth; t = tan(angle)."""
    h = min(w, d) / 2.0 * t
    if d > w:
        ry = (d - w) / 2.0                       # half ridge length
        verts = [
            (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
            (0.0, -ry, h), (0.0, ry, h),                                    # ridge 4,5
        ]
        faces = [
            (0, 3, 2, 1),      # base
            (1, 2, 5, 4),      # +X eave trapezoid
            (3, 0, 4, 5),      # -X eave trapezoid
            (0, 1, 4),         # -Y hip triangle
            (2, 3, 5),         # +Y hip triangle
        ]
        return _finish(verts), faces
    # pyramidal (tented) hip
    verts = [
        (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),  # base 0..3
        (0.0, 0.0, h),                                                   # apex 4
    ]
    faces = [
        (0, 3, 2, 1),      # base
        (0, 1, 4),         # -Y
        (1, 2, 4),         # +X
        (2, 3, 4),         # +Y
        (3, 0, 4),         # -X
    ]
    return _finish(verts), faces
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_geometry.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/geometry/roof.py tests/test_roof_geometry.py
```
Expected: 10 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/roof.py tests/test_roof_geometry.py && git commit -m "$(cat <<'EOF'
feat(m7c): roof_solid Hip (ridge setback + pyramidal cases)

Equal-pitch hip: depth>width gives a ridge set back by w/2 at each end (6 verts,
2 eave trapezoids + 2 hip triangles); depth<=width collapses to a pyramidal apex
(5 verts, 4 triangles). apex height = min(w,d)/2 * tan(angle).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `CreateRoofCommand`

**Files:**
- Create: `python/pluton/commands/roof_commands.py`
- Test: `tests/test_roof_commands.py`

**Interfaces:**
- Consumes: `roof_solid` (Task 1/2); `model.new_definition/new_instance`, `defn.mesh.add_vertex/add_face_from_loop`, `target_context.children`, `model.revalidate_active_path`; the `Command` ABC (`pluton.commands.command`).
- Produces: `CreateRoofCommand(kind, width, depth, angle, transform, target_context)` — bake a `"Roof"` group and instance it with `transform`; undoable with the clean reuse-on-redo lifecycle.

- [ ] **Step 1: Write the failing test**

`tests/test_roof_commands.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.roof_commands import CreateRoofCommand
from pluton.model.model import Model


def _cmd(model, kind="gable"):
    return CreateRoofCommand(kind, 4.0, 6.0, 30.0, np.eye(4), model.active_context)


def test_creates_one_roof_group():
    model = Model()
    target = model.active_context
    _cmd(model).do(model)
    assert len(target.children) == 1
    defn = target.children[0].definition
    assert defn.is_group is True
    assert defn.name == "Roof"
    assert len(defn.mesh.faces()) == 5


def test_each_placement_is_its_own_definition():
    model = Model()
    target = model.active_context
    _cmd(model).do(model)
    _cmd(model).do(model)
    assert target.children[0].definition is not target.children[1].definition


def test_undo_detaches_and_redo_reuses_same_instance():
    model = Model()
    target = model.active_context
    cmd = _cmd(model)
    cmd.do(model)
    inst = target.children[0]
    defn = inst.definition
    assert len(defn.instances) == 1
    cmd.undo(model)
    assert len(target.children) == 0
    assert len(defn.instances) == 0          # detached from both
    cmd.do(model)                            # redo
    assert len(target.children) == 1
    assert target.children[0] is inst        # SAME object reused
    assert len(defn.instances) == 1


def test_transform_is_applied():
    model = Model()
    t = np.eye(4)
    t[:3, 3] = [5.0, 6.0, 2.4]
    CreateRoofCommand("gable", 4.0, 6.0, 30.0, t, model.active_context).do(model)
    inst = model.active_context.children[-1]
    assert np.allclose(inst.transform[:3, 3], [5.0, 6.0, 2.4])


def test_degenerate_adds_nothing():
    model = Model()
    CreateRoofCommand("gable", 0.0, 6.0, 30.0, np.eye(4), model.active_context).do(model)
    assert len(model.active_context.children) == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_commands.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.commands.roof_commands`).

- [ ] **Step 3: Implement**

`python/pluton/commands/roof_commands.py`:

```python
"""CreateRoofCommand (M7c): bake a parametric roof as a "Roof" group."""
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command
from pluton.geometry.roof import roof_solid


class CreateRoofCommand(Command):
    """Bake a Gable/Hip/Shed roof solid into a new "Roof" group in the target
    context, instanced with `transform`. Undo detaches the instance (from both
    children and defn.instances); redo re-attaches the SAME Definition/Instance
    (mirrors CreateInstanceCommand — no fresh Definition, no leak)."""

    name = "Create Roof"

    def __init__(self, kind, width, depth, angle, transform, target_context) -> None:
        self._kind = kind
        self._width = width
        self._depth = depth
        self._angle = angle
        self._transform = np.asarray(transform, dtype=np.float64).reshape(4, 4)
        self._target = target_context
        self._definition = None
        self._instance = None

    def do(self, model) -> None:
        if self._definition is None:
            vertices, faces = roof_solid(self._kind, self._width, self._depth, self._angle)
            if not vertices:
                self._instance = None
                return
            defn = model.new_definition("Roof", is_group=True)
            ids = [defn.mesh.add_vertex(np.array(v, dtype=np.float32)) for v in vertices]
            for loop in faces:
                defn.mesh.add_face_from_loop([ids[i] for i in loop])
            self._definition = defn
            self._instance = model.new_instance(defn, self._transform)
        elif self._instance not in self._definition.instances:
            self._definition.instances.append(self._instance)   # redo: re-register
        if self._instance is not None:
            self._target.children.append(self._instance)

    def undo(self, model) -> None:
        if self._instance is None:
            return
        if self._instance in self._target.children:
            self._target.children.remove(self._instance)
        if self._instance in self._instance.definition.instances:
            self._instance.definition.instances.remove(self._instance)
        model.revalidate_active_path()
```

*(Note the redo path: `do()` after `undo()` finds `self._definition` set, so it re-appends the cached instance to `defn.instances` (if absent) and to `children` — the same object, no new Definition. `new_instance` already appended to `defn.instances` on the first `do()`.)*

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_commands.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/commands/roof_commands.py tests/test_roof_commands.py
```
Expected: 5 passed; ruff clean. (If `defn.mesh.faces()` is not the accessor name, ground it against `Scene`/mesh — adjust the test's face-count assertion to the real accessor; do not change the command.)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/roof_commands.py tests/test_roof_commands.py && git commit -m "$(cat <<'EOF'
feat(m7c): CreateRoofCommand (baked Roof group, clean redo)

Bakes a roof_solid into a new "Roof" group and instances it with the placement
transform. Undo detaches from both children and defn.instances; redo re-attaches
the SAME Definition/Instance (CreateInstanceCommand pattern, no leak). Degenerate
adds nothing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `RoofTool` (footprint gesture + placement + flip)

**Files:**
- Create: `python/pluton/tools/roof_tool.py`
- Test: `tests/test_roof_tool.py`

**Interfaces:**
- Consumes: the `Tool` ABC / `ToolContext` / `ToolOverlay` (`tools/tool.py`); `snap` results (`snap.kind`, `snap.world_position`, `SnapKind`, `MARKER_COLOR_BY_KIND` from `pluton.viewport.snap_engine`); `world_to_local_point` (`pluton.viewport.picking`); `mat_invert` (`pluton.geometry.transforms`); `roof_solid` + `_rot_z` (Task 1/2); `CreateRoofCommand` (Task 3); `model.active_world_transform` / `active_context`; `command_stack.execute`.
- Produces: `RoofTool` with public `kind` / `slope` (degrees) the options bar binds to; `shortcut = "O"`.

**Interaction (mirror `rectangle_tool.py` gesture + `wall_tool.py` world→local):** first click sets a footprint corner (its snapped world Z is the base plane `z0`); second click commits. During the drag, the roof is previewed as its wireframe (world-space). Up/Down arrows rotate the ridge orientation 90° (default = ridge along the longer edge). Params (type/slope) come from the options row. Esc cancels.

- [ ] **Step 1: Write the failing test** (headless: fake snap objects + a real `Model`)

`tests/test_roof_tool.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.model.model import Model
from pluton.tools.roof_tool import RoofTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


class _Snap:
    def __init__(self, x, y, z=0.0, kind=SnapKind.ON_FACE):
        self.kind = kind
        self.world_position = np.array([x, y, z], dtype=np.float64)


def _ctx(model, stack):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model,
        camera=None, widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def _place(tool, ax, ay, bx, by):
    tool.on_mouse_press(None, _Snap(ax, ay))
    tool.on_mouse_move(None, _Snap(bx, by))
    tool.on_mouse_press(None, _Snap(bx, by))


def test_footprint_drag_places_one_roof():
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.activate(_ctx(model, stack))
    _place(tool, 0.0, 0.0, 4.0, 6.0)
    assert len(model.active_context.children) == 1
    defn = model.active_context.children[-1].definition
    assert defn.is_group is True and defn.name == "Roof"


def test_ridge_runs_along_longer_edge_by_default():
    # footprint 4 (x) x 8 (y): ridge should run along Y (the longer edge), so the
    # roof's apex line spans ~8 in Y and the cross-section spans ~4 in X.
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.kind = "gable"
    tool.activate(_ctx(model, stack))
    _place(tool, 0.0, 0.0, 4.0, 8.0)
    inst = model.active_context.children[-1]
    m = inst.transform
    verts = [(m @ np.append(np.array(v), 1.0))[:3]
             for v in _defn_local_verts(inst.definition)]
    a = np.array(verts)
    # X extent ~4 (across ridge), Y extent ~8 (along ridge)
    assert np.isclose(a[:, 0].max() - a[:, 0].min(), 4.0, atol=1e-6)
    assert np.isclose(a[:, 1].max() - a[:, 1].min(), 8.0, atol=1e-6)


def test_no_footprint_no_placement_on_degenerate():
    model = Model()
    stack = CommandStack()
    tool = RoofTool()
    tool.activate(_ctx(model, stack))
    _place(tool, 1.0, 1.0, 1.0, 1.0)   # zero-area footprint
    assert len(model.active_context.children) == 0


def _defn_local_verts(defn):
    mesh = defn.mesh
    return [mesh.vertex_position(vid) for vid in mesh.vertices()]
```

*(If `mesh.vertices()` / `mesh.vertex_position(vid)` are not the real accessors, ground them against `Scene` and adjust `_defn_local_verts` only — the tool code is the unit under test.)*

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_tool.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.tools.roof_tool`).

- [ ] **Step 3: Implement `RoofTool`**

`python/pluton/tools/roof_tool.py` — confirm the snap/gesture shape against `rectangle_tool.py` and the world→local + execute against `wall_tool.py`:

```python
"""The Roof placement tool (M7c).

Draw a rectangle footprint on the active drawing plane; a parametric
Gable/Hip/Shed roof (from the options row) is baked as a "Roof" group over it,
ridge auto-aligned to the longer edge. Up/Down arrows rotate the ridge 90°.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.roof_commands import CreateRoofCommand
from pluton.geometry.roof import _rot_z, roof_solid
from pluton.geometry.transforms import mat_invert
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import world_to_local_point
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND, SnapKind

_NEUTRAL = (0.85, 0.85, 0.85)


class RoofTool(Tool):
    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._first: np.ndarray | None = None      # world, incl. base z0
        self._preview: np.ndarray | None = None     # world, x/y at z0
        self._flip_quarters = 0
        self._snap_pos: np.ndarray | None = None
        self._snap_color: tuple[float, float, float] = _NEUTRAL
        self._snap_kind = 0
        self.kind = "gable"
        self.slope = 30.0                            # degrees

    @property
    def name(self) -> str:
        return "Roof"

    @property
    def shortcut(self) -> str:
        return "O"

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    # ---- geometry of the placement -------------------------------------
    def _dims_and_transform(self, second_world):
        """Return (w, d, transform_local) for the current footprint, or None if
        the footprint is degenerate (zero area)."""
        z0 = float(self._first[2])
        x0, y0 = float(self._first[0]), float(self._first[1])
        x1, y1 = float(second_world[0]), float(second_world[1])
        width_x = abs(x1 - x0)
        width_y = abs(y1 - y0)
        if width_x < 1e-9 or width_y < 1e-9:
            return None
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        base_q = 0 if width_y >= width_x else 1       # ridge along the longer edge
        q = (base_q + self._flip_quarters) % 4
        if q % 2 == 0:
            w, d = width_x, width_y
        else:
            w, d = width_y, width_x
        m_world = _rot_z(np.pi / 2.0 * q)
        m_world[:3, 3] = [cx, cy, z0]
        wt = self._model.active_world_transform if self._model is not None else None
        if wt is None:
            transform_local = m_world
        else:
            transform_local = mat_invert(wt) @ m_world
        return w, d, transform_local

    def _commit(self, second_world) -> None:
        dims = self._dims_and_transform(second_world)
        if dims is None:
            self._reset()
            return
        w, d, transform_local = dims
        cmd = CreateRoofCommand(
            self.kind, w, d, self.slope, transform_local, self._model.active_context
        )
        self._command_stack.execute(cmd, self._model)
        self._reset()

    # ---- events ---------------------------------------------------------
    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            self._snap_pos = None
            self._snap_kind = 0
            return
        self._snap_pos = np.asarray(snap.world_position, np.float64).copy()
        self._snap_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL)
        self._snap_kind = int(snap.kind)
        if self._first is not None:
            z0 = float(self._first[2])
            self._preview = np.array(
                [float(snap.world_position[0]), float(snap.world_position[1]), z0],
                dtype=np.float64,
            )

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            return
        pt = np.asarray(snap.world_position, np.float64)
        if self._first is None:
            self._first = pt.copy()
            self._preview = pt.copy()
            return
        second = np.array([float(pt[0]), float(pt[1]), float(self._first[2])], np.float64)
        self._commit(second)

    def on_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._reset()
        elif key == Qt.Key.Key_Up:
            self._flip_quarters = (self._flip_quarters + 1) % 4
        elif key == Qt.Key.Key_Down:
            self._flip_quarters = (self._flip_quarters - 1) % 4

    def apply_typed_value(self, text, units) -> bool:
        from pluton.units import parse_angle

        value = parse_angle(text)
        if value is None or value <= 0.0 or value > 85.0:
            return False
        self.slope = value
        return True

    def overlay(self) -> ToolOverlay:
        segments = np.zeros((0, 3), dtype=np.float32)
        if self._first is not None and self._preview is not None:
            dims = self._dims_and_transform(self._preview)
            if dims is not None:
                w, d, _ = dims
                verts, faces = roof_solid(self.kind, w, d, self.slope)
                if verts:
                    z0 = float(self._first[2])
                    cx = (float(self._first[0]) + float(self._preview[0])) / 2.0
                    cy = (float(self._first[1]) + float(self._preview[1])) / 2.0
                    q = (0 if d >= w else 1)
                    m = _rot_z(np.pi / 2.0 * ((q + self._flip_quarters) % 4))
                    m[:3, 3] = [cx, cy, z0]
                    world = [(m @ np.append(np.array(v), 1.0))[:3] for v in verts]
                    segs = []
                    for f in faces:
                        n = len(f)
                        for i in range(n):
                            segs.append(world[f[i]])
                            segs.append(world[f[(i + 1) % n]])
                    segments = np.array(segs, dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=self._snap_pos.copy() if self._snap_pos is not None else None,
            snap_marker_color=self._snap_color,
            snap_marker_kind=self._snap_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._first is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return self._first.copy() if self._first is not None else None

    @property
    def status_text(self) -> str | None:
        return None

    def _reset(self) -> None:
        self._first = None
        self._preview = None
        self._snap_pos = None
        self._snap_kind = 0
```

*(The overlay recomputes `w, d` via `_dims_and_transform` then rebuilds the same `m` used for placement so the wireframe preview lands exactly where the roof will. `m` here mirrors `_dims_and_transform`'s world matrix — the overlay is world-space, matching the placed roof at `active_world @ transform_local = m_world`.)*

Note the overlay's local `q` recompute uses `d >= w` (post-assignment dims), which flips the base logic; to keep the preview identical to placement, instead compute the world matrix ONCE inside `_dims_and_transform` and return it. Refactor `_dims_and_transform` to also return `m_world`, and have both `_commit` and `overlay` use that returned `m_world` for the preview — do NOT re-derive `q` in `overlay`. Concretely, change `_dims_and_transform` to `return w, d, transform_local, m_world` and update both call sites (the `overlay` builds its wireframe from the returned `m_world`; `_commit` ignores it). This removes the duplicated orientation logic.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/roof_tool.py tests/test_roof_tool.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/roof_tool.py tests/test_roof_tool.py && git commit -m "$(cat <<'EOF'
feat(m7c): RoofTool (draw footprint -> baked parametric roof)

Two-click rectangle footprint on the active drawing plane -> world->active-local
placement transform -> one CreateRoofCommand. Ridge auto-runs along the longer
edge; Up/Down rotate it 90°. Type/slope from the options row; live wireframe
preview (world-space); Esc cancels.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `RoofOptionsBar` (Gable|Hip|Shed toggle + slope)

**Files:**
- Create: `python/pluton/ui/roof_options_bar.py`
- Test: `tests/test_roof_options_bar.py`

**Interfaces:**
- Consumes: `pluton.units.parse_angle`/`format_angle`; a `RoofTool` (reads/writes `.kind`/`.slope`); a `units_provider` callable (unused for angles but kept for signature parity with the other options bars).
- Produces: `RoofOptionsBar(tool, units_provider)` — a `QWidget` with a Gable|Hip|Shed toggle + a slope-degrees field; `refresh()` reloads from the tool; `set_kind()` sets the tool kind.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_roof_options_bar.py`:

```python
from __future__ import annotations

from pluton.tools.roof_tool import RoofTool
from pluton.ui.roof_options_bar import RoofOptionsBar


def test_slope_field_updates_tool(qtbot):
    tool = RoofTool()
    bar = RoofOptionsBar(tool, units_provider=lambda: None)
    qtbot.addWidget(bar)
    bar._slope_edit.setText("45")
    bar._on_slope_committed()
    assert abs(tool.slope - 45.0) < 1e-6


def test_toggle_sets_kind(qtbot):
    tool = RoofTool()
    bar = RoofOptionsBar(tool, units_provider=lambda: None)
    qtbot.addWidget(bar)
    bar.set_kind("hip")
    assert tool.kind == "hip"
    bar.set_kind("shed")
    assert tool.kind == "shed"
    bar.set_kind("gable")
    assert tool.kind == "gable"


def test_bad_slope_ignored(qtbot):
    tool = RoofTool()
    bar = RoofOptionsBar(tool, units_provider=lambda: None)
    qtbot.addWidget(bar)
    bar._slope_edit.setText("bogus")
    bar._on_slope_committed()
    assert tool.slope == 30.0
    bar._slope_edit.setText("90")   # out of (0, 85]
    bar._on_slope_committed()
    assert tool.slope == 30.0
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_options_bar.py -q -p no:cacheprovider
```
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`python/pluton/ui/roof_options_bar.py`:

```python
"""RoofOptionsBar (M7c): Gable|Hip|Shed toggle + slope field for the tool."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QWidget,
)

from pluton.units import format_angle, parse_angle

_KINDS = ("gable", "hip", "shed")


class RoofOptionsBar(QWidget):
    """A compact row: Gable|Hip|Shed radio toggle + a slope-degrees field bound
    to a RoofTool. MainWindow shows it only while the tool is active."""

    def __init__(self, tool, units_provider) -> None:
        super().__init__()
        self._tool = tool
        self._units = units_provider
        self._buttons = {}
        self._group = QButtonGroup(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        for kind in _KINDS:
            btn = QRadioButton(kind.capitalize())
            self._buttons[kind] = btn
            self._group.addButton(btn)
            layout.addWidget(btn)
            btn.clicked.connect(lambda _checked=False, k=kind: self.set_kind(k))
        layout.addWidget(QLabel("Slope:"))
        self._slope_edit = QLineEdit()
        layout.addWidget(self._slope_edit)
        layout.addStretch(1)

        self._slope_edit.editingFinished.connect(self._on_slope_committed)
        self.refresh()

    def set_kind(self, kind) -> None:
        self._tool.kind = kind
        self._buttons[kind].setChecked(True)

    def refresh(self) -> None:
        self._buttons[self._tool.kind].setChecked(True)
        self._slope_edit.setText(format_angle(self._tool.slope))

    def _on_slope_committed(self) -> None:
        value = parse_angle(self._slope_edit.text())
        if value is not None and 0.0 < value <= 85.0:
            self._tool.slope = value
        self.refresh()
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_roof_options_bar.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/ui/roof_options_bar.py tests/test_roof_options_bar.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/roof_options_bar.py tests/test_roof_options_bar.py && git commit -m "$(cat <<'EOF'
feat(m7c): RoofOptionsBar (Gable|Hip|Shed toggle + slope field)

A compact row bound to the RoofTool: three-way roof-type radio toggle plus a
slope-degrees field (parse_angle/format_angle, clamped to (0, 85]); bad input
ignored + field resynced.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: MainWindow integration (register `O` + host options bar)

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_roof.py`

**Interfaces:**
- Consumes: `ToolManager.register`; the `_activate` shortcut dispatch; the layout holding `_status_bar`; the existing `_refresh_tool_options` hook.
- Produces: `RoofTool` registered (shortcut `O`); a `RoofOptionsBar` created + hosted, shown only when the tool is active; a `Tools ▸ Roof` entry.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_main_window_roof.py`:

```python
from __future__ import annotations

from pluton.tools.roof_tool import RoofTool
from pluton.ui.main_window import MainWindow


def test_roof_tool_registered_with_o(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("O")
    assert isinstance(w._tool_manager.active, RoofTool)


def test_o_key_shortcut_registered(qtbot):
    from PySide6.QtGui import QShortcut

    w = MainWindow()
    qtbot.addWidget(w)
    keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
    assert "O" in keys


def test_roof_options_bar_visible_only_for_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("O")
    w._refresh_tool_options()
    assert w._roof_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")   # line tool
    w._refresh_tool_options()
    assert not w._roof_options_bar.isVisibleTo(w)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_roof.py -q -p no:cacheprovider
```
Expected: FAIL (no `O` tool / no `_roof_options_bar`).

- [ ] **Step 3: Wire MainWindow** (additive — do NOT reflow/`ruff --fix`; issue #48; keep the finding count at exactly 9)

1. Import `RoofTool` and `RoofOptionsBar` with the other tool/ui imports, in correct alphabetical position (`roof_tool` sorts before `select_tool`/`wall_tool`; `roof_options_bar` before `status_bar`/`wall_options_bar`) — no new I001.
2. Register the tool alongside the other tool registrations (keep a reference):
   ```python
   self._roof_tool = RoofTool()
   self._tool_manager.register(self._roof_tool)
   ```
3. Add the bare-key shortcut next to the other single-key tool `QShortcut`s (after the `"W"` / `"D"` line):
   ```python
   QShortcut(QKeySequence("O"), self, activated=lambda: self._activate("O"))
   ```
4. Create + host the options bar next to the wall/opening options bars (start hidden; add to the layout above the status bar):
   ```python
   self._roof_options_bar = RoofOptionsBar(self._roof_tool, units_provider=lambda: self._doc.units)
   self._roof_options_bar.hide()
   layout.addWidget(self._roof_options_bar, stretch=0)   # above the status bar
   ```
5. Extend `_refresh_tool_options()` additively — append (do NOT rewrite the wall/opening blocks):
   ```python
   is_roof = isinstance(self._tool_manager.active, RoofTool)
   if is_roof:
       self._roof_options_bar.refresh()
   self._roof_options_bar.setVisible(is_roof)
   ```
6. Add a `Tools ▸ Roof (O)` action matching the existing `"Wall\tW"` / `"Door/Window\tD"` idiom (calls `self._activate("O")` + `_refresh_tool_options()`, or matches exactly how the Wall/Door entries are wired).

Audit shortcuts to confirm `O` is unused before finalizing.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_roof.py -q -p no:cacheprovider
```
Expected: 3 passed, no hang. Then confirm issue #48: `.venv/Scripts/python -m ruff check python/pluton/ui/main_window.py` still reports **exactly 9** findings (same 5 RUF100 + 3 E501 + 1 I001). If your additions added one, fix only your own new line (do NOT autofix the file).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_roof.py && git commit -m "$(cat <<'EOF'
feat(m7c): register RoofTool (O) + host RoofOptionsBar in MainWindow

Register the Roof tool with the O shortcut (QShortcut + Tools entry) and show
the RoofOptionsBar only while the tool is active (extends _refresh_tool_options).
Additive-only (issue #48).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Full regression + master design-doc annotation

**Files:**
- Modify: `docs/2026-05-16-pluton-design.md` (annotate the M7 line)

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass, above the 826 baseline (M7c adds ~24 tests).

- [ ] **Step 2: C++ regression (unchanged, confirm still green)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure | tail -3)
```
Expected: 79/79 (M7c is Python-only).

- [ ] **Step 3: Annotate the master design doc**

`docs/2026-05-16-pluton-design.md` — on the **M7** line, after the M7b note, add an **M7c** ✅ *(shipped v0.2.3)* sub-milestone note: the Roof tool (`O`) bakes parametric Gable/Hip/Shed closed-solid roofs over a drawn rectangle footprint, ridge auto-aligned to the longer edge (arrow-key flip), form + slope from an options row, on the active drawing plane. Update the "Remaining sub-milestones" list to just **M7d** Dimensions & annotations, **M7e** Scenes. Confirm the M8 line is untouched (`grep -c "M8:"` stays 1).

- [ ] **Step 4: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
docs(m7c): annotate master design M7 line — Roof tool shipped

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Release v0.2.3

*(Outward-facing steps — push, tag, issues — require explicit per-turn user authorization, as with prior releases. Do the local bump/build/commit first, then ask.)*

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`

- [ ] **Step 1: Bump the version to 0.2.3**

- `pyproject.toml` → `version = "0.2.3"`
- `CMakeLists.txt` → `VERSION 0.2.3`
- `cpp/src/version.cpp` → `return "0.2.3";`

- [ ] **Step 2: Rebuild and verify the reported version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake" .venv/Scripts/python -m pip install -e . --no-build-isolation && .venv/Scripts/python -c "import pluton._core as c; assert c.version()=='0.2.3', c.version(); print('version OK', c.version())"
```
Expected: `version OK 0.2.3`. (Only `version.cpp` recompiles; Assimp is cached.)

- [ ] **Step 3: Final full suite at the new version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass.

- [ ] **Step 4: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -m "$(cat <<'EOF'
release: v0.2.3 — Roof tool (M7c)

Bump 0.2.2 -> 0.2.3. Third M7 sub-milestone: a Roof tool baking parametric
Gable/Hip/Shed closed-solid roofs over a drawn rectangle footprint, ridge
auto-aligned to the longer edge, form + slope from an options row.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify signatures on the branch**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && for s in $(git log --format=%H cdd784f..HEAD); do echo "$s $(git cat-file -p $s | grep -c 'BEGIN SSH SIGNATURE')"; done
```
Expected: every listed commit shows `1`.

- [ ] **Step 6: Push, tag, issues — AFTER explicit user authorization**

Ask the user to authorize the release. Once authorized:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main && git tag -s v0.2.3 -m "Pluton v0.2.3 — Roof tool (M7c)" && git push origin v0.2.3
```
Then watch CI to green on both platforms (`gh run watch`). File carry-over issues (eave overhang with fascia; arbitrary/polygon footprints + straight-skeleton hips/valleys; gambrel/mansard/dutch-gable/dormers; roof-to-wall trimming + host-wall attachment; roof thickness/rafters/ridge caps; footprint-from-face/wall-loop) + any review roll-ups.

- [ ] **Step 7: Manual visual pass (user)**

Launch the app; draw walls, press `O`, pick Gable/Hip/Shed + a slope, hover a wall-top face and drag a footprint rectangle (live wireframe preview), press Up/Down to flip the ridge, place; confirm the roof lands on the walls, undo/redo works, and the roof paints/moves like a normal group.

---

## Self-Review

**1. Spec coverage.** D1 three forms → `roof_solid` shed/gable (Task 1) + hip (Task 2) + a `RoofOptionsBar` toggle (Task 5). D2 drawn rectangle footprint → `RoofTool` gesture (Task 4). D3 slope in degrees → `parse_angle`/`format_angle` (Tasks 4/5). D4 flush closed solid → the generators (Tasks 1/2). D5 baked `"Roof"` group + clean redo → `CreateRoofCommand` (Task 3). D6 ridge along longer edge + flip → `_dims_and_transform` base-quarter + Up/Down (Task 4). D7 canonical frame → Task 1. D8 slope clamp / degenerate → Tasks 1/4/5. D9 shortcut `O` (QShortcut + menu) + defaults gable/30° → Tasks 4/6. D10 v0.2.3 → Task 8. **All decisions covered.**

**2. Placeholder scan.** No TBD/"add error handling". The "ground the mesh accessor names against `Scene`" notes in Tasks 3/4 are concrete confirm-against-code steps for real accessor names (`defn.mesh.faces()`, `mesh.vertices()`, `mesh.vertex_position()`), not hand-waving — the implementer verifies the exact accessor and adjusts only the test helper. No `# noqa` anywhere.

**3. Type/interface consistency.** `roof_solid(kind, width, depth, angle) -> (vertices, faces)` used identically in Tasks 1/2/3/4. `_rot_z(theta) -> 4x4` produced in Task 1, consumed in Task 4. `CreateRoofCommand(kind, width, depth, angle, transform, target_context)` consistent in Tasks 3/4 (the 3rd positional is the depth/along-ridge span — the tool passes `d`). `RoofTool.kind/slope` produced in Task 4, consumed in Task 5. `RoofOptionsBar(tool, units_provider)` consistent in Tasks 5/6. `_refresh_tool_options` extended in Task 6.

**4. Ordering.** Pure generator shed/gable (1) → hip (2) → command (3) → tool composing generator+command (4) → options bar binding the tool (5) → MainWindow hosting both (6) → regression/doc (7) → release (8). Each task independently testable; no forward dependency (Task 1 deliberately does not reference `_hip`).

**5. Known grounding actions for the implementer** (not placeholders — explicit verifications):
- Task 3/4 tests reference mesh accessors (`defn.mesh.faces()`, `mesh.vertices()`, `mesh.vertex_position(vid)`). Confirm the real names against `Scene`/the bound mesh and adjust ONLY the test helper if they differ.
- Task 4: confirm `ToolContext` accepts the kwargs used (it did for M7b: `scene` required, the rest default), and that `snap` objects in the real flow expose `.kind` + `.world_position` (they do — see `wall_tool.py`).
- Task 4: the `overlay`/`_dims_and_transform` refactor note (return `m_world`, use it in both places) must be applied so the preview matches placement exactly — do not ship the duplicated `q` recompute.

Plan complete.

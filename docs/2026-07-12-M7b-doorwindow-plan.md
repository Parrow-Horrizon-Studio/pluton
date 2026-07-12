# M7b — Door/Window Placement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place parametric framed door/window **Components** onto a picked wall face (no cut — wall stays solid), auto-oriented and floor-anchored, with identical openings sharing one Component definition (instancing). Ship as **v0.2.2**.

**Architecture:** Pure `opening_frame` generator → pure `opening_placement_transform` → a hierarchical `Model.pick_face_local` (new) → `PlaceOpeningCommand` (dedup Component via a `Model` registry) → `DoorWindowTool` (pick face, preview, place) → `OpeningOptionsBar` → MainWindow. Mirrors the M7a layering; **no C++/kernel change**.

**Tech Stack:** Python 3.13 + numpy; PySide6 (tool + options widget); pytest (+ pytest-qt for tool/UI).

**Spec:** `docs/2026-07-12-M7b-doorwindow-design.md` (decisions D1–D10).

## Global Constraints

- **Layering:** `geometry/opening.py` is PURE (numpy only — no Model/Scene/Qt/GL). Only the command + tool touch Model/Scene. The generator works in a canonical local frame (origin at the opening's bottom-center; `+X`=width, `+Y`=depth-into-wall, `+Z`=up).
- **No cut (D1):** the wall stays solid; the opening is a framed **Component** placed on the wall (overlap with the solid wall is expected). No boolean, no re-tessellation, **no C++/kernel change** → `ctest` stays **79/79**.
- **Instancing (D5):** identical `(kind, width, height, depth)` reuse ONE Component `Definition` (`is_group=False`) via a runtime dedup registry dict on `Model`. Each placement is an `Instance` carrying its transform, appended to the active context.
- **Placement (D3/D6/D8):** place on a picked wall face; the opening stands upright (`up` = the active context's local +Z), faces the viewer (`out` = the horizontalized, viewer-facing wall normal), horizontal follows the cursor, bottom sits at floor (`z=0`) + `sill`, outer face flush with the wall. Near-horizontal faces (degenerate `out`) → no placement.
- **`# noqa` RULE (repo ruff `select=["E","F","W","I","N","UP","B","C4","RUF"]` — ANN NOT enabled):** do **NOT** write any `# noqa: ANN0xx` in new code — an unused `noqa` for a non-enabled rule is itself `RUF100`. New files must be genuinely `ruff check`-clean. (This is why the code blocks below carry no `# noqa`.)
- **Units:** thickness-like sizes stored in **meters** on the tool; the options row parses/formats via `pluton.units.parse_length` / `format_length` with the document's `Units`. `apply_typed_value` sets `width`.
- **Tests:** `.venv/Scripts/python` explicitly; full suite under a timeout: `timeout 200 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Baseline (v0.2.1): **797 pytest + 79/79 ctest**. New Python files ruff-clean. **NEVER** broad `ruff --fix` on `main_window.py` (issue #48 — exactly 9 deliberate pre-existing findings: 5 RUF100 + 3 E501 + 1 I001; additive-only, keep the count at 9).
- **Git:** stage specific files only (no `git add -A`). SSH-signed commits; never `--no-verify`/`--amend`/`--no-gpg-sign`. Trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. On `main`. Verify sig via `git cat-file -p <sha> | grep -c "BEGIN SSH SIGNATURE"` (==1); `git log --show-signature` "No signature" is a KNOWN local gap, not a failure.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) edited ONLY in the release task. `0.2.1` → `0.2.2`.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.

---

## File Structure

- Create `python/pluton/geometry/opening.py` — pure `opening_frame` + `opening_placement_transform` + `_box` helper.
- Create `python/pluton/commands/opening_commands.py` — `PlaceOpeningCommand`.
- Modify `python/pluton/model/model.py` — add `pick_face_local` + the `opening_definitions` registry dict (additive).
- Create `python/pluton/tools/opening_tool.py` — `DoorWindowTool`.
- Create `python/pluton/ui/opening_options_bar.py` — `OpeningOptionsBar`.
- Modify `python/pluton/ui/main_window.py` — register the tool, host the options row, show/hide on tool switch (additive; issue #48).
- Tests: `tests/test_opening_geometry.py`, `tests/test_opening_placement.py`, `tests/test_pick_face_local.py`, `tests/test_opening_commands.py`, `tests/test_opening_tool.py`, `tests/test_opening_options_bar.py`, `tests/test_main_window_opening.py`.

---

### Task 1: `opening_frame` pure geometry generator

**Files:**
- Create: `python/pluton/geometry/opening.py`
- Test: `tests/test_opening_geometry.py`

**Interfaces:**
- Produces: `opening_frame(kind, width, height, depth) -> (vertices, faces)` — a framed door/window built from closed solid sub-boxes in the canonical local frame, or `([], [])` if degenerate. `kind` is `"door"` or `"window"`. Also a private `_box(x0, x1, y0, y1, z0, z1)` helper. Consumed by `PlaceOpeningCommand` (Task 4).

- [ ] **Step 1: Write the failing test**

`tests/test_opening_geometry.py`:

```python
from __future__ import annotations

from collections import Counter

import numpy as np

from pluton.geometry.opening import opening_frame


def _closed(faces):
    edges = Counter()
    for f in faces:
        n = len(f)
        for i in range(n):
            edges[frozenset((f[i], f[(i + 1) % n]))] += 1
    return edges


def _bbox(verts):
    a = np.array(verts, dtype=np.float64)
    return a.min(axis=0), a.max(axis=0)


def test_door_has_three_frame_members_plus_panel():
    verts, faces = opening_frame("door", width=0.9, height=2.1, depth=0.1)
    # 4 boxes (L jamb, R jamb, head, panel) -> 32 verts, 24 quad faces
    assert len(verts) == 32
    assert len(faces) == 24
    # every box is closed: each edge shared by exactly two faces of its own box
    assert all(c == 2 for c in _closed(faces).values())


def test_window_has_four_frame_members_plus_glazing():
    verts, faces = opening_frame("window", width=1.2, height=1.2, depth=0.1)
    # 5 boxes (L, R, head, sill, glazing) -> 40 verts, 30 quad faces
    assert len(verts) == 40
    assert len(faces) == 30
    assert all(c == 2 for c in _closed(faces).values())


def test_canonical_extents_and_origin():
    verts, _ = opening_frame("window", width=1.2, height=1.5, depth=0.1)
    lo, hi = _bbox(verts)
    assert np.allclose(lo, [-0.6, 0.0, 0.0])   # X centered, Y from 0, Z from 0 (bottom-center origin)
    assert np.allclose(hi, [0.6, 0.1, 1.5])


def test_door_panel_vs_window_sill_at_the_floor():
    # At the floor (z==0), a door's solid panel is thin in depth, adding two
    # interior depth values (iy0, iy1) on top of the jambs' (0, d) -> 4 distinct
    # depths. A window's sill spans the full depth like the jambs -> only (0, d),
    # 2 distinct depths (its glazing starts above the sill, at z=profile).
    dv, _ = opening_frame("door", 0.9, 2.1, 0.1)
    wv, _ = opening_frame("window", 1.2, 1.2, 0.1)
    d = np.array(dv)
    w = np.array(wv)
    d_floor_y = np.unique(np.round(d[d[:, 2] < 1e-9][:, 1], 6))
    w_floor_y = np.unique(np.round(w[w[:, 2] < 1e-9][:, 1], 6))
    assert len(d_floor_y) == 4     # door: jambs (0, d) + panel (iy0, iy1)
    assert len(w_floor_y) == 2     # window: jambs + sill both span the full depth


def test_identical_params_identical_geometry():
    a = opening_frame("door", 0.9, 2.1, 0.1)
    b = opening_frame("door", 0.9, 2.1, 0.1)
    assert a[0] == b[0] and a[1] == b[1]


def test_degenerate_returns_empty():
    assert opening_frame("door", 0.0, 2.1, 0.1) == ([], [])
    assert opening_frame("door", 0.9, 2.1, 0.0) == ([], [])
    assert opening_frame("door", 0.1, 2.1, 0.1) == ([], [])   # width <= 2*profile
    assert opening_frame("window", 1.2, 0.1, 0.1) == ([], []) # height <= 2*profile
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_geometry.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.geometry.opening`).

- [ ] **Step 3: Implement `opening_frame`**

`python/pluton/geometry/opening.py`:

```python
"""Pure geometry for the Door/Window tool (M7b).

opening_frame builds a framed door/window from closed solid sub-boxes in a
canonical local frame (origin at the opening's bottom-center; +X = width,
+Y = depth-into-wall, +Z = up). No Model/Scene/Qt/GL deps.

opening_placement_transform builds the 4x4 that places a canonical opening onto
a picked wall face (see Task 2).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9
_PROFILE = 0.06        # frame member width (m), fixed (not a user knob)
_PANEL_T = 0.04        # door panel thickness (m)
_GLAZING_T = 0.006     # window glazing thickness (m)

# Outward-wound quad faces for an axis-aligned box with corners
# 0:(x0,y0,z0) 1:(x1,y0,z0) 2:(x1,y1,z0) 3:(x0,y1,z0) and 4..7 = same at z1.
_BOX_FACES = (
    (0, 3, 2, 1),   # bottom -Z
    (4, 5, 6, 7),   # top    +Z
    (0, 1, 5, 4),   # front  -Y
    (1, 2, 6, 5),   # right  +X
    (2, 3, 7, 6),   # back   +Y
    (3, 0, 4, 7),   # left   -X
)


def _box(x0, x1, y0, y1, z0, z1):
    """Return (8 vertex tuples, 6 outward-wound quad loops) for a box."""
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    return verts, [tuple(loop) for loop in _BOX_FACES]


def opening_frame(kind, width, height, depth):
    """Return (vertices, faces) for a framed door/window, or ([], []) if degenerate.

    kind: "door" (open threshold + solid panel) or "window" (sill + glazing).
    """
    w = float(width)
    h = float(height)
    d = float(depth)
    p = _PROFILE
    if w <= 2.0 * p + _EPS or h <= 2.0 * p + _EPS or d <= _EPS:
        return [], []

    hx = w / 2.0
    is_window = kind == "window"
    infill_t = _GLAZING_T if is_window else _PANEL_T
    iy0 = (d - infill_t) / 2.0
    iy1 = (d + infill_t) / 2.0

    boxes = [
        (-hx, -hx + p, 0.0, d, 0.0, h),          # left jamb
        (hx - p, hx, 0.0, d, 0.0, h),            # right jamb
        (-hx + p, hx - p, 0.0, d, h - p, h),     # head
    ]
    if is_window:
        boxes.append((-hx + p, hx - p, 0.0, d, 0.0, p))          # sill
        boxes.append((-hx + p, hx - p, iy0, iy1, p, h - p))      # glazing
    else:
        boxes.append((-hx + p, hx - p, iy0, iy1, 0.0, h - p))    # door panel (to floor)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for (x0, x1, y0, y1, z0, z1) in boxes:
        bverts, bfaces = _box(x0, x1, y0, y1, z0, z1)
        off = len(vertices)
        vertices.extend((float(a), float(b), float(c)) for (a, b, c) in bverts)
        faces.extend(tuple(i + off for i in loop) for loop in bfaces)
    return vertices, faces
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_geometry.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/geometry/opening.py tests/test_opening_geometry.py
```
Expected: 6 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/opening.py tests/test_opening_geometry.py && git commit -m "$(cat <<'EOF'
feat(m7b): opening_frame generator (framed door/window)

Pure numpy generator building a framed door (open threshold + solid panel) or
window (sill + glazing) from closed outward-wound solid sub-boxes in a canonical
local frame (origin at bottom-center). Degenerate -> empty.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `opening_placement_transform` pure helper

**Files:**
- Modify: `python/pluton/geometry/opening.py`
- Test: `tests/test_opening_placement.py`

**Interfaces:**
- Consumes: nothing new (numpy only).
- Produces: `opening_placement_transform(point, normal, sill) -> np.ndarray(4,4) | None` — the transform mapping the canonical opening frame onto a picked wall face, or `None` for a near-horizontal face. `point`/`normal` are in the target (active-context-local) frame; `normal` faces the viewer. Consumed by `DoorWindowTool` (Task 5).

- [ ] **Step 1: Write the failing test**

`tests/test_opening_placement.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.geometry.opening import opening_placement_transform


def _apply(m, pt):
    return (m @ np.array([pt[0], pt[1], pt[2], 1.0]))[:3]


def test_wall_facing_plus_x():
    # A wall face at x=3 whose outward (viewer-facing) normal is +X.
    m = opening_placement_transform(point=(3.0, 1.0, 1.2), normal=(1.0, 0.0, 0.0), sill=0.9)
    assert m is not None
    # canonical origin (bottom-center, outer face) -> cursor x,y at height=sill
    assert np.allclose(_apply(m, (0.0, 0.0, 0.0)), [3.0, 1.0, 0.9])
    # canonical +Z (up) stays up
    assert np.allclose((m[:3, :3] @ np.array([0.0, 0.0, 1.0])), [0.0, 0.0, 1.0])
    # canonical +Y (depth) points INTO the wall (-X here)
    assert np.allclose((m[:3, :3] @ np.array([0.0, 1.0, 0.0])), [-1.0, 0.0, 0.0])
    # proper rotation (no mirroring)
    assert np.isclose(np.linalg.det(m[:3, :3]), 1.0)


def test_horizontalizes_a_tilted_normal():
    # a normal with a small +Z tilt still yields an upright opening
    m = opening_placement_transform((0.0, 0.0, 0.0), (1.0, 0.0, 0.2), sill=0.0)
    assert m is not None
    assert np.allclose((m[:3, :3] @ np.array([0.0, 0.0, 1.0])), [0.0, 0.0, 1.0])
    out_into_wall = m[:3, :3] @ np.array([0.0, 1.0, 0.0])
    assert np.isclose(out_into_wall[2], 0.0)        # depth axis horizontal


def test_horizontal_face_returns_none():
    assert opening_placement_transform((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.0) is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_placement.py -q -p no:cacheprovider
```
Expected: FAIL (`ImportError: cannot import name 'opening_placement_transform'`).

- [ ] **Step 3: Implement `opening_placement_transform`** (append to `python/pluton/geometry/opening.py`)

```python
def opening_placement_transform(point, normal, sill):
    """Return the 4x4 placing a canonical opening onto a wall face, or None.

    point/normal are in the active-context-local frame; normal faces the viewer.
    The opening stands upright (up = local +Z); its outer face is flush with the
    wall face; its bottom-center sits at the cursor's horizontal position, at
    height `sill`. Returns None for a near-horizontal face (no valid upright).
    """
    up = np.array([0.0, 0.0, 1.0])
    n = np.asarray(normal, dtype=np.float64).reshape(3)
    out = n - np.dot(n, up) * up          # horizontalize
    mag = float(np.linalg.norm(out))
    if mag < _EPS:
        return None                        # near-horizontal face
    out /= mag
    along = np.cross(up, out)              # unit (up, out orthonormal)
    p = np.asarray(point, dtype=np.float64).reshape(3)
    m = np.eye(4, dtype=np.float64)
    m[:3, 0] = along                       # canonical +X -> along-wall
    m[:3, 1] = -out                        # canonical +Y -> into the wall
    m[:3, 2] = up                          # canonical +Z -> up
    m[:3, 3] = np.array([p[0], p[1], float(sill)])
    return m
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_placement.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/geometry/opening.py tests/test_opening_placement.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/opening.py tests/test_opening_placement.py && git commit -m "$(cat <<'EOF'
feat(m7b): opening_placement_transform (place canonical opening on a wall face)

Builds the 4x4 mapping the canonical opening frame onto a picked wall face:
upright (up=local +Z), outer face flush, bottom-center at the cursor's
horizontal position at sill height; horizontalizes the normal; None for a
near-horizontal face.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `Model.pick_face_local` (hierarchical wall-face pick)

**Files:**
- Modify: `python/pluton/model/model.py`
- Test: `tests/test_pick_face_local.py`

**Interfaces:**
- Consumes: `mat_invert` (`pluton.geometry.transforms`); `active_world_transform`, `active_context.children`, `tags.is_visible`; `inst.definition.mesh.ray_pick_face` / `.face_normal` (Scene).
- Produces: `Model.pick_face_local(origin, direction) -> (point, normal) | None` — casts a WORLD ray, returns the nearest child-instance face hit as **(point, viewer-facing normal)** in the **active-context-local** frame. Consumed by `DoorWindowTool` (Task 5).

**Interaction:** mirrors the existing `Model.pick_instance` loop, but returns the face point + normal (mapped to active-local) instead of the instance, and orients the normal toward the ray origin.

- [ ] **Step 1: Write the failing test**

`tests/test_pick_face_local.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.geometry.wall import wall_box
from pluton.model.model import Model


def _add_wall(model):
    # a wall along +X, thickness 0.2 (faces at y = +/-0.1), height 2.4
    verts, faces = wall_box((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.2, 2.4)
    defn = model.new_definition("Wall", is_group=True)
    ids = [defn.mesh.add_vertex(np.array(v, dtype=np.float32)) for v in verts]
    for loop in faces:
        defn.mesh.add_face_from_loop([ids[i] for i in loop])
    inst = model.new_instance(defn)
    model.active_context.children.append(inst)
    return inst


def test_picks_wall_face_point_and_viewer_facing_normal():
    model = Model()
    _add_wall(model)
    # ray from +Y toward -Y at (1, 5, 1.2): hits the y=+0.1 face
    hit = model.pick_face_local(origin=(1.0, 5.0, 1.2), direction=(0.0, -1.0, 0.0))
    assert hit is not None
    point, normal = hit
    assert np.allclose(point, [1.0, 0.1, 1.2], atol=1e-5)
    # normal faces the viewer (+Y), i.e. opposite the ray direction
    assert np.allclose(normal / np.linalg.norm(normal), [0.0, 1.0, 0.0], atol=1e-5)


def test_miss_returns_none():
    model = Model()
    _add_wall(model)
    hit = model.pick_face_local(origin=(50.0, 50.0, 50.0), direction=(0.0, 0.0, 1.0))
    assert hit is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_pick_face_local.py -q -p no:cacheprovider
```
Expected: FAIL (`AttributeError: 'Model' object has no attribute 'pick_face_local'`).

- [ ] **Step 3: Implement `pick_face_local`** (add as a method on `Model`, next to `pick_instance` in `python/pluton/model/model.py`)

```python
    def pick_face_local(self, origin, direction):
        """Nearest child-instance face hit for a WORLD ray, as (point, normal)
        in the active-context-local frame. `normal` faces the ray origin
        (viewer-facing). None if nothing is hit."""
        from pluton.geometry.transforms import mat_invert

        w = self.active_world_transform
        w_inv = mat_invert(w)
        o_a = (w_inv @ np.append(np.asarray(origin, np.float64), 1.0))[:3]
        d_a = w_inv[:3, :3] @ np.asarray(direction, np.float64)

        best = None
        best_t = float("inf")
        for inst in self.active_context.children:
            if not self.tags.is_visible(inst.tag_id):
                continue
            t_inv = mat_invert(inst.transform)
            o_c = (t_inv @ np.append(o_a, 1.0))[:3]
            d_c = t_inv[:3, :3] @ d_a
            hit = inst.definition.mesh.ray_pick_face(o_c, d_c)
            if hit is None or hit.t >= best_t:
                continue
            n_c = np.asarray(inst.definition.mesh.face_normal(hit.face_id), np.float64)
            p_c = np.asarray(hit.point, np.float64)
            p_a = (inst.transform @ np.append(p_c, 1.0))[:3]
            n_a = inst.transform[:3, :3] @ n_c
            if np.dot(n_a, d_a) > 0.0:      # orient toward the viewer (against the ray)
                n_a = -n_a
            best = (p_a, n_a)
            best_t = hit.t
        return best
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_pick_face_local.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/model/model.py tests/test_pick_face_local.py
```
Expected: 2 passed; ruff clean on the test (and no NEW ruff finding in `model.py` — run `ruff check python/pluton/model/model.py` and confirm the count did not grow versus before this task; do NOT autofix).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py tests/test_pick_face_local.py && git commit -m "$(cat <<'EOF'
feat(m7b): Model.pick_face_local (hierarchical wall-face pick)

Casts a world ray, returns the nearest child-instance face hit as
(point, viewer-facing normal) in the active-context-local frame. Mirrors
pick_instance's per-child ray transform but keeps the face + normal.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `Model` registry + `PlaceOpeningCommand`

**Files:**
- Modify: `python/pluton/model/model.py` (add `self.opening_definitions = {}` in `__init__`)
- Create: `python/pluton/commands/opening_commands.py`
- Test: `tests/test_opening_commands.py`

**Interfaces:**
- Consumes: `opening_frame` (Task 1); `model.opening_definitions`, `model.new_definition/new_instance`, `defn.mesh.add_vertex/add_face_from_loop`, `target_context.children`, `model.revalidate_active_path`; the `Command` ABC.
- Produces: `PlaceOpeningCommand(kind, width, height, depth, transform, target_context)` — dedup-or-create a Component `Definition` keyed by `(kind, width, height, depth)`, instance it with `transform`; undoable.

- [ ] **Step 1: Write the failing test**

`tests/test_opening_commands.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.opening_commands import PlaceOpeningCommand
from pluton.model.model import Model


def _cmd(model, kind="door"):
    return PlaceOpeningCommand(kind, 0.9, 2.1, 0.1, np.eye(4), model.active_context)


def test_identical_placements_share_one_component_two_instances():
    model = Model()
    target = model.active_context
    _cmd(model).do(model)
    _cmd(model).do(model)
    assert len(target.children) == 2
    d0 = target.children[0].definition
    d1 = target.children[1].definition
    assert d0 is d1                       # shared Component
    assert d0.is_group is False           # a Component, not a group
    assert d0.name == "Door"


def test_different_params_distinct_definitions():
    model = Model()
    target = model.active_context
    PlaceOpeningCommand("door", 0.9, 2.1, 0.1, np.eye(4), target).do(model)
    PlaceOpeningCommand("window", 1.2, 1.2, 0.1, np.eye(4), target).do(model)
    assert target.children[0].definition is not target.children[1].definition


def test_undo_detaches_instance_but_keeps_definition_registered():
    model = Model()
    target = model.active_context
    cmd = _cmd(model)
    cmd.do(model)
    assert len(target.children) == 1
    cmd.undo(model)
    assert len(target.children) == 0
    # the Definition stays registered so a later placement reuses it
    assert ("door", 0.9, 2.1, 0.1) in model.opening_definitions
    cmd.do(model)                          # redo reuses the registered Definition
    assert len(target.children) == 1


def test_transform_is_applied_to_the_instance():
    model = Model()
    t = np.eye(4)
    t[:3, 3] = [5.0, 6.0, 0.9]
    PlaceOpeningCommand("door", 0.9, 2.1, 0.1, t, model.active_context).do(model)
    inst = model.active_context.children[-1]
    assert np.allclose(inst.transform[:3, 3], [5.0, 6.0, 0.9])


def test_degenerate_opening_adds_nothing():
    model = Model()
    PlaceOpeningCommand("door", 0.05, 2.1, 0.1, np.eye(4), model.active_context).do(model)
    assert len(model.active_context.children) == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_commands.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.commands.opening_commands`).

- [ ] **Step 3: Implement the registry + command**

First, in `python/pluton/model/model.py`'s `Model.__init__`, add (additive — next to the other instance-state fields):

```python
        self.opening_definitions = {}   # M7b: (kind, w, h, depth) -> shared Component Definition
```

Then `python/pluton/commands/opening_commands.py`:

```python
"""PlaceOpeningCommand (M7b): place a framed door/window Component on a wall."""
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command
from pluton.geometry.opening import opening_frame


def _sig(kind, width, height, depth):
    return (kind, round(float(width), 6), round(float(height), 6), round(float(depth), 6))


class PlaceOpeningCommand(Command):
    """Place a door/window as an Instance of a shared Component Definition.

    Identical (kind, width, height, depth) reuse one Definition via
    model.opening_definitions. Undo detaches the single created instance
    (leaving the Definition + registry entry for reuse); redo re-runs do()."""

    name = "Place Opening"

    def __init__(self, kind, width, height, depth, transform, target_context) -> None:
        self._kind = kind
        self._width = width
        self._height = height
        self._depth = depth
        self._transform = np.asarray(transform, dtype=np.float64).reshape(4, 4)
        self._target = target_context
        self._instance = None

    def _definition_for(self, model):
        sig = _sig(self._kind, self._width, self._height, self._depth)
        defn = model.opening_definitions.get(sig)
        if defn is not None:
            return defn
        vertices, faces = opening_frame(self._kind, self._width, self._height, self._depth)
        if not vertices:
            return None
        defn = model.new_definition(self._kind.capitalize(), is_group=False)
        ids = {}
        for i, (x, y, z) in enumerate(vertices):
            ids[i] = defn.mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
        for loop in faces:
            defn.mesh.add_face_from_loop([ids[i] for i in loop])
        model.opening_definitions[sig] = defn
        return defn

    def do(self, model) -> None:
        defn = self._definition_for(model)
        if defn is None:
            self._instance = None
            return
        inst = model.new_instance(defn, self._transform)
        self._target.children.append(inst)
        self._instance = inst

    def undo(self, model) -> None:
        if self._instance is None:
            return
        if self._instance in self._target.children:
            self._target.children.remove(self._instance)
        model.revalidate_active_path()
        self._instance = None
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_commands.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/commands/opening_commands.py tests/test_opening_commands.py
```
Expected: 5 passed; ruff clean (and no new ruff finding in `model.py`).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py python/pluton/commands/opening_commands.py tests/test_opening_commands.py && git commit -m "$(cat <<'EOF'
feat(m7b): PlaceOpeningCommand + Model opening registry (dedup instancing)

Identical (kind,w,h,depth) reuse one shared Component Definition via a runtime
registry on Model; each placement is an Instance carrying its transform. Undo
detaches the instance (keeps the Definition registered for reuse); redo re-runs
do(); degenerate opening adds nothing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `DoorWindowTool` (pick face, preview, place)

**Files:**
- Create: `python/pluton/tools/opening_tool.py`
- Test: `tests/test_opening_tool.py`

**Interfaces:**
- Consumes: the `Tool` ABC / `ToolContext` / `ToolOverlay` (`tools/tool.py`); `ctx.camera.ray_from_screen(cx, cy, w, h)`, `ctx.widget_size_provider`; `model.pick_face_local` (Task 3); `opening_placement_transform` (Task 2); `PlaceOpeningCommand` (Task 4); `parse_length` (`pluton.units`).
- Produces: `DoorWindowTool` with public `kind` / `width` / `height` / `sill` / `depth` (meters) the options bar binds to; `shortcut = "D"`.

**Interaction (mirror `select_tool.py` for cursor+ray, `wall_tool.py` for overlay/units):** `on_mouse_move` builds a world ray from the cursor + `pick_face_local`; if a face is hit, computes the placement transform and stores a preview (outer-frame outline). `on_mouse_press` places one `PlaceOpeningCommand` at the previewed transform (tool stays active). `apply_typed_value` sets `width`. Esc clears the preview. No valid wall face → no preview, no placement.

- [ ] **Step 1: Write the failing test** (headless: a fake camera returns a fixed ray; a real `Model` with a wall)

`tests/test_opening_tool.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.geometry.wall import wall_box
from pluton.model.model import Model
from pluton.tools.opening_tool import DoorWindowTool
from pluton.tools.tool import ToolContext


class _FakeCamera:
    def __init__(self, origin, direction):
        self._o = np.asarray(origin, np.float64)
        self._d = np.asarray(direction, np.float64)

    def ray_from_screen(self, cx, cy, w, h):
        return self._o, self._d


class _Event:
    def __init__(self, x=10.0, y=10.0):
        self._x, self._y = x, y

    def position(self):
        class _P:
            def __init__(s, x, y):
                s._x, s._y = x, y

            def x(s):
                return s._x

            def y(s):
                return s._y

        return _P(self._x, self._y)


def _model_with_wall():
    model = Model()
    verts, faces = wall_box((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.2, 2.4)
    defn = model.new_definition("Wall", is_group=True)
    ids = [defn.mesh.add_vertex(np.array(v, dtype=np.float32)) for v in verts]
    for loop in faces:
        defn.mesh.add_face_from_loop([ids[i] for i in loop])
    model.active_context.children.append(model.new_instance(defn))
    return model


def _ctx(model, stack, camera):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model, camera=camera,
        widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def test_place_on_wall_face_creates_one_instance():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    cam = _FakeCamera((1.0, 5.0, 1.2), (0.0, -1.0, 0.0))   # ray hits y=+0.1 face
    tool.activate(_ctx(model, stack, cam))
    tool.on_mouse_move(_Event(), None)                      # builds the preview
    before = len(model.active_context.children)
    tool.on_mouse_press(_Event(), None)                     # places the opening
    assert len(model.active_context.children) == before + 1
    placed = model.active_context.children[-1].definition
    assert placed.is_group is False and placed.name == "Door"


def test_no_face_no_placement():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    cam = _FakeCamera((50.0, 50.0, 50.0), (0.0, 0.0, 1.0))  # misses
    tool.activate(_ctx(model, stack, cam))
    tool.on_mouse_move(_Event(), None)
    tool.on_mouse_press(_Event(), None)
    assert len(model.active_context.children) == 0


def test_window_kind_places_window():
    model = _model_with_wall()
    stack = CommandStack()
    tool = DoorWindowTool()
    tool.kind = "window"
    cam = _FakeCamera((1.0, 5.0, 1.2), (0.0, -1.0, 0.0))
    tool.activate(_ctx(model, stack, cam))
    tool.on_mouse_move(_Event(), None)
    tool.on_mouse_press(_Event(), None)
    assert model.active_context.children[-1].definition.name == "Window"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_tool.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.tools.opening_tool`).

- [ ] **Step 3: Implement `DoorWindowTool`**

`python/pluton/tools/opening_tool.py` — confirm the cursor/size/ray plumbing against `select_tool.py` (`_cursor`, `_viewport_size`, `camera.ray_from_screen`) and the overlay shape against `wall_tool.py`:

```python
"""The Door/Window placement tool (M7b).

Pick a wall face; a framed door/window Component is placed flush to it,
upright, floor-anchored (window at a sill height), horizontally following the
cursor. Identical openings share one Component. The wall is not cut.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.opening_commands import PlaceOpeningCommand
from pluton.geometry.opening import opening_placement_transform
from pluton.tools.tool import Tool, ToolContext, ToolOverlay

_NEUTRAL = (0.85, 0.85, 0.85)


class DoorWindowTool(Tool):
    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._camera = None
        self._size_provider = None
        self._preview = None            # (transform 4x4) or None
        self.kind = "door"
        self.width = 0.9                # meters
        self.height = 2.1
        self.sill = 0.0
        self.depth = 0.1

    @property
    def name(self) -> str:
        return "Door/Window"

    @property
    def shortcut(self) -> str:
        return "D"

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._camera = ctx.camera
        self._size_provider = ctx.widget_size_provider
        self._preview = None

    def deactivate(self) -> None:
        self._preview = None

    def _viewport_size(self) -> tuple[int, int]:
        if self._size_provider is None:
            return (1, 1)
        return self._size_provider()

    def _cursor(self, event: QMouseEvent) -> tuple[float, float]:
        pos = event.position()
        return float(pos.x()), float(pos.y())

    def _sill_for_kind(self) -> float:
        return 0.0 if self.kind == "door" else self.sill

    def _resolve(self, event: QMouseEvent):
        if self._model is None or self._camera is None:
            return None
        cx, cy = self._cursor(event)
        w, h = self._viewport_size()
        origin, direction = self._camera.ray_from_screen(cx, cy, w, h)
        hit = self._model.pick_face_local(origin, direction)
        if hit is None:
            return None
        point, normal = hit
        return opening_placement_transform(point, normal, self._sill_for_kind())

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        self._preview = self._resolve(event)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        transform = self._resolve(event)
        if transform is None:
            return
        cmd = PlaceOpeningCommand(
            self.kind, self.width, self.height, self.depth,
            transform, self._model.active_context,
        )
        self._command_stack.execute(cmd, self._model)

    def apply_typed_value(self, text, units) -> bool:
        from pluton.units import parse_length

        value = parse_length(text, units)
        if value is None or value <= 0:
            return False
        self.width = value
        return True

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._preview = None

    def overlay(self) -> ToolOverlay:
        segments = np.zeros((0, 3), dtype=np.float32)
        if self._preview is not None:
            hx = self.width / 2.0
            corners = np.array([
                [-hx, 0.0, 0.0], [hx, 0.0, 0.0],
                [hx, 0.0, self.height], [-hx, 0.0, self.height],
            ], dtype=np.float64)
            world = [(self._preview @ np.append(c, 1.0))[:3] for c in corners]
            loop = world + [world[0]]
            segs = []
            for a, b in zip(loop[:-1], loop[1:]):
                segs.append(a)
                segs.append(b)
            segments = np.array(segs, dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=None,
            snap_marker_color=_NEUTRAL,
            snap_marker_kind=0,
        )

    @property
    def has_active_gesture(self) -> bool:
        return False

    @property
    def anchor_or_none(self):
        return None

    @property
    def status_text(self):
        return None
```

*(Confirm `_cursor`/`_viewport_size`/`ray_from_screen` match `select_tool.py`, and that `ToolOverlay`'s field names match `wall_tool.py`. `has_active_gesture` is False — placement is single-click, no multi-step gesture.)*

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/opening_tool.py tests/test_opening_tool.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/opening_tool.py tests/test_opening_tool.py && git commit -m "$(cat <<'EOF'
feat(m7b): DoorWindowTool (place framed openings on a wall face)

Cursor ray -> pick_face_local -> opening_placement_transform -> one
PlaceOpeningCommand per click (tool stays active). Public kind/width/height/
sill/depth for the options bar; frame-outline preview; Esc clears it; no valid
wall face -> no placement.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `OpeningOptionsBar` (Door|Window toggle + fields)

**Files:**
- Create: `python/pluton/ui/opening_options_bar.py`
- Test: `tests/test_opening_options_bar.py`

**Interfaces:**
- Consumes: `pluton.units.parse_length`/`format_length`; a `DoorWindowTool` (reads/writes `.kind`/`.width`/`.height`/`.sill`/`.depth`); a `units_provider` callable `() -> Units`.
- Produces: `OpeningOptionsBar(tool, units_provider)` — a `QWidget` with a Door|Window toggle + unit-aware width/height/sill/depth fields; `refresh()` reformats from the tool; editing parses back.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_opening_options_bar.py`:

```python
from __future__ import annotations

from pluton.tools.opening_tool import DoorWindowTool
from pluton.ui.opening_options_bar import OpeningOptionsBar
from pluton.units import Units


def test_fields_update_tool(qtbot):
    tool = DoorWindowTool()
    bar = OpeningOptionsBar(tool, units_provider=lambda: Units())
    qtbot.addWidget(bar)
    bar._width_edit.setText("1000mm")
    bar._on_width_committed()
    assert abs(tool.width - 1.0) < 1e-6
    bar._sill_edit.setText("800mm")
    bar._on_sill_committed()
    assert abs(tool.sill - 0.8) < 1e-6


def test_toggle_sets_kind_and_reloads(qtbot):
    tool = DoorWindowTool()
    bar = OpeningOptionsBar(tool, units_provider=lambda: Units())
    qtbot.addWidget(bar)
    bar.set_kind("window")
    assert tool.kind == "window"
    bar.set_kind("door")
    assert tool.kind == "door"


def test_bad_input_ignored(qtbot):
    tool = DoorWindowTool()
    bar = OpeningOptionsBar(tool, units_provider=lambda: Units())
    qtbot.addWidget(bar)
    bar._height_edit.setText("bogus")
    bar._on_height_committed()
    assert tool.height == 2.1
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_options_bar.py -q -p no:cacheprovider
```
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `OpeningOptionsBar`**

`python/pluton/ui/opening_options_bar.py`:

```python
"""OpeningOptionsBar (M7b): Door|Window toggle + size fields for the tool."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QWidget,
)

from pluton.units import format_length, parse_length


class OpeningOptionsBar(QWidget):
    """A compact row: Door|Window radio toggle + unit-aware width/height/sill/
    depth fields bound to a DoorWindowTool. MainWindow shows it only while the
    tool is active."""

    def __init__(self, tool, units_provider) -> None:
        super().__init__()
        self._tool = tool
        self._units = units_provider
        self._door_btn = QRadioButton("Door")
        self._window_btn = QRadioButton("Window")
        self._group = QButtonGroup(self)
        self._group.addButton(self._door_btn)
        self._group.addButton(self._window_btn)
        self._width_edit = QLineEdit()
        self._height_edit = QLineEdit()
        self._sill_edit = QLineEdit()
        self._depth_edit = QLineEdit()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self._door_btn)
        layout.addWidget(self._window_btn)
        layout.addWidget(QLabel("W:"))
        layout.addWidget(self._width_edit)
        layout.addWidget(QLabel("H:"))
        layout.addWidget(self._height_edit)
        layout.addWidget(QLabel("Sill:"))
        layout.addWidget(self._sill_edit)
        layout.addWidget(QLabel("Depth:"))
        layout.addWidget(self._depth_edit)
        layout.addStretch(1)

        self._door_btn.setChecked(self._tool.kind == "door")
        self._window_btn.setChecked(self._tool.kind == "window")
        self._door_btn.clicked.connect(lambda: self.set_kind("door"))
        self._window_btn.clicked.connect(lambda: self.set_kind("window"))
        self._width_edit.editingFinished.connect(self._on_width_committed)
        self._height_edit.editingFinished.connect(self._on_height_committed)
        self._sill_edit.editingFinished.connect(self._on_sill_committed)
        self._depth_edit.editingFinished.connect(self._on_depth_committed)
        self.refresh()

    def set_kind(self, kind) -> None:
        self._tool.kind = kind
        self._door_btn.setChecked(kind == "door")
        self._window_btn.setChecked(kind == "window")
        self._sill_edit.setEnabled(kind == "window")
        self.refresh()

    def refresh(self) -> None:
        u = self._units()
        self._width_edit.setText(format_length(self._tool.width, u))
        self._height_edit.setText(format_length(self._tool.height, u))
        self._sill_edit.setText(format_length(self._tool.sill, u))
        self._depth_edit.setText(format_length(self._tool.depth, u))
        self._sill_edit.setEnabled(self._tool.kind == "window")

    def _commit(self, edit, attr) -> None:
        value = parse_length(edit.text(), self._units())
        if value is not None and value > 0:
            setattr(self._tool, attr, value)
        self.refresh()

    def _on_width_committed(self) -> None:
        self._commit(self._width_edit, "width")

    def _on_height_committed(self) -> None:
        self._commit(self._height_edit, "height")

    def _on_sill_committed(self) -> None:
        self._commit(self._sill_edit, "sill")

    def _on_depth_committed(self) -> None:
        self._commit(self._depth_edit, "depth")
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_opening_options_bar.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/ui/opening_options_bar.py tests/test_opening_options_bar.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/opening_options_bar.py tests/test_opening_options_bar.py && git commit -m "$(cat <<'EOF'
feat(m7b): OpeningOptionsBar (Door|Window toggle + size fields)

A compact row bound to the DoorWindowTool: Door|Window radio toggle plus
unit-aware width/height/sill/depth fields (sill enabled for windows); bad input
ignored.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: MainWindow integration (register `D` + host options bar)

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_opening.py`

**Interfaces:**
- Consumes: `ToolManager.register`; the tool-shortcut dispatch; the layout holding `_status_bar`; the existing `_refresh_tool_options` hook (added in M7a) OR the same pattern.
- Produces: `DoorWindowTool` registered (shortcut `D`); an `OpeningOptionsBar` created + hosted, shown only when the tool is active; a `Tools ▸ Door/Window` entry.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_main_window_opening.py`:

```python
from __future__ import annotations

from pluton.tools.opening_tool import DoorWindowTool
from pluton.ui.main_window import MainWindow


def test_doorwindow_tool_registered_with_d(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("D")
    assert isinstance(w._tool_manager.active, DoorWindowTool)


def test_opening_options_bar_visible_only_for_tool(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("D")
    w._refresh_tool_options()
    assert w._opening_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")   # line tool
    w._refresh_tool_options()
    assert not w._opening_options_bar.isVisibleTo(w)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_opening.py -q -p no:cacheprovider
```
Expected: FAIL (no `D` tool / no `_opening_options_bar`).

- [ ] **Step 3: Wire MainWindow** (additive — do NOT reflow/`ruff --fix`; issue #48)

1. Import `DoorWindowTool` and `OpeningOptionsBar` (with the other tool/ui imports, in correct alphabetical position so no new `I001`).
2. Register the tool alongside the WallTool registration (keep a reference, mirroring `self._wall_tool`):
   ```python
   self._opening_tool = DoorWindowTool()
   self._tool_manager.register(self._opening_tool)
   ```
3. Create + host the options bar next to the wall options bar (same layout slot, start hidden):
   ```python
   self._opening_options_bar = OpeningOptionsBar(self._opening_tool, units_provider=lambda: self._doc.units)
   self._opening_options_bar.hide()
   layout.addWidget(self._opening_options_bar, stretch=0)   # above the status bar
   ```
4. Extend `_refresh_tool_options()` (added in M7a) so it also toggles the opening bar — the WHOLE method becomes:
   ```python
   def _refresh_tool_options(self) -> None:
       active = self._tool_manager.active
       is_wall = isinstance(active, WallTool)
       if is_wall:
           self._wall_options_bar.refresh()
       self._wall_options_bar.setVisible(is_wall)
       is_opening = isinstance(active, DoorWindowTool)
       if is_opening:
           self._opening_options_bar.refresh()
       self._opening_options_bar.setVisible(is_opening)
   ```
   (Edit the existing method additively — add the `is_opening` block; do not rewrite the wall lines.)
5. Add a `Tools ▸ Door/Window (D)` action matching the existing `"Wall\tW"` idiom (calls `activate_by_shortcut("D")` + `_refresh_tool_options()`).

Audit shortcuts to confirm `D` is unused.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_opening.py -q -p no:cacheprovider
```
Expected: 2 passed, no hang. Then confirm issue #48: `.venv/Scripts/python -m ruff check python/pluton/ui/main_window.py` still reports **exactly 9** findings (do NOT autofix; if your additions added one, fix your own new line only).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_opening.py && git commit -m "$(cat <<'EOF'
feat(m7b): register DoorWindowTool (D) + host OpeningOptionsBar in MainWindow

Register the Door/Window tool with the D shortcut, add a Tools entry, and show
the OpeningOptionsBar only while the tool is active (extends
_refresh_tool_options). Additive-only (issue #48).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Full regression + master design-doc annotation

**Files:**
- Modify: `docs/2026-05-16-pluton-design.md` (annotate the M7 line)

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass, above the 797 baseline (M7b adds ~24 tests).

- [ ] **Step 2: C++ regression (unchanged, confirm still green)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure | tail -3)
```
Expected: 79/79 (M7b is Python-only).

- [ ] **Step 3: Annotate the master design doc**

`docs/2026-05-16-pluton-design.md` — on the **M7** line, add an **M7b** ✅ *(shipped v0.2.2)* sub-milestone note after the M7a note: the Door/Window tool (`D`) places framed door/window Components on a picked wall face (no cut — wall stays solid), auto-oriented + floor-anchored, with identical openings sharing one Component (instancing). Note the remaining M7 sub-milestones (M7c Roof, M7d Dimensions, M7e Scenes). Confirm the M8 line is untouched (`grep -c "M8:"` stays 1).

- [ ] **Step 4: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
docs(m7b): annotate master design M7 line — Door/Window tool shipped

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Release v0.2.2

*(Outward-facing steps — push, tag, issues — require explicit per-turn user authorization, as with prior releases. Do the local bump/build/commit first, then ask.)*

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`

- [ ] **Step 1: Bump the version to 0.2.2**

- `pyproject.toml` → `version = "0.2.2"`
- `CMakeLists.txt` → `VERSION 0.2.2`
- `cpp/src/version.cpp` → `return "0.2.2";`

- [ ] **Step 2: Rebuild and verify the reported version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake" .venv/Scripts/python -m pip install -e . --no-build-isolation && .venv/Scripts/python -c "import pluton._core as c; assert c.version()=='0.2.2', c.version(); print('version OK', c.version())"
```
Expected: `version OK 0.2.2`. (Only `version.cpp` recompiles; Assimp is cached.)

- [ ] **Step 3: Final full suite at the new version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass.

- [ ] **Step 4: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -m "$(cat <<'EOF'
release: v0.2.2 — Door/Window tool (M7b)

Bump 0.2.1 -> 0.2.2. Second M7 sub-milestone: a Door/Window tool placing framed
door/window Components on a picked wall face (no cut), auto-oriented and
floor-anchored, with identical openings sharing one Component (instancing).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify signatures on the branch**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && for s in $(git log --format=%H fb78ecf..HEAD); do echo "$s $(git cat-file -p $s | grep -c 'BEGIN SSH SIGNATURE')"; done
```
Expected: every listed commit shows `1`.

- [ ] **Step 6: Push, tag, issues — AFTER explicit user authorization**

Ask the user to authorize the release. Once authorized:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main && git tag -s v0.2.2 -m "Pluton v0.2.2 — Door/Window tool (M7b)" && git push origin v0.2.2
```
Then watch CI to green on both platforms (`gh run watch`). File carry-over issues (real opening cut through the wall; cross-session dedup of the opening registry; door swing / window operability; along-wall snapping + wall-thickness-driven depth; distinct glass material; attaching the opening to its host wall) + any review roll-ups.

- [ ] **Step 7: Manual visual pass (user)**

Launch the app; the user draws a wall, presses `D`, hovers the wall face (frame-outline preview), places doors and windows, toggles Door|Window and sizes in the options row, confirms instancing (identical placements), undo, and that openings paint/move like normal components.

---

## Self-Review

**1. Spec coverage.** D1 no cut → the command places a Component, never mutates the wall (Task 4). D2 framed component → `opening_frame` (Task 1). D3 place on picked face → `pick_face_local` (Task 3) + tool (Task 5). D4 one tool + toggle → Task 5 + `OpeningOptionsBar` (Task 6). D5 shared Component per signature → `PlaceOpeningCommand` + `Model` registry (Task 4). D6 flush + D8 floor-anchored/upright → `opening_placement_transform` (Task 2). D7 fixed profile → `_PROFILE` constant (Task 1). D9 shortcut `D` + defaults → Tasks 5/7. D10 v0.2.2 → Task 9. **All decisions covered.**

**2. Placeholder scan.** No TBD/"add error handling". The "confirm against `select_tool.py` / `wall_tool.py`" notes in Task 5 are concrete confirm-against-code steps (named reference files) for a UI-integrated tool, not hand-waving. No `# noqa: ANN0xx` anywhere (per Global Constraints).

**3. Type/interface consistency.** `opening_frame(kind, width, height, depth) -> (vertices, faces)` used identically in Tasks 1/4. `opening_placement_transform(point, normal, sill) -> 4x4|None` produced in Task 2, consumed in Task 5. `Model.pick_face_local(origin, direction) -> (point, normal)|None` produced in Task 3, consumed in Task 5. `PlaceOpeningCommand(kind, width, height, depth, transform, target_context)` consistent in Tasks 4/5. `DoorWindowTool.kind/width/height/sill/depth` produced in Task 5, consumed in Task 6. `OpeningOptionsBar(tool, units_provider)` consistent in Tasks 6/7. `_refresh_tool_options` extended in Task 7 (built in M7a).

**4. Ordering.** Pure generator (1) → pure placement math (2) → hierarchical pick (3) → command+registry (4) → tool that composes 2+3+4 (5) → options bar binding the tool (6) → MainWindow hosting both (7) → regression/doc (8) → release (9). Each task independently testable; no forward dependency.

Plan complete.

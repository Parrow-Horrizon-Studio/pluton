# M7a — Wall Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Wall tool that draws a chaining polyline of baked solid-box walls (centered thickness + height, ground plane), undoable per segment, shipped as v0.2.1.

**Architecture:** Pure `wall_box` generator → `CreateWallCommand` (model-target, builds a `"Wall"` group) → `WallTool` (Line-tool-style chaining, VCB length, transform-aware) → a `WallOptionsBar` (thickness/height) hosted by MainWindow. Mirrors the M4a drawing-tool layering; no C++/kernel changes.

**Tech Stack:** Python 3.13 + numpy; PySide6 (tool + options widget); pytest (+ pytest-qt for tool/UI).

**Spec:** `docs/2026-07-12-M7a-wall-design.md` (decisions D1–D10).

## Global Constraints

- **Layering:** `geometry/wall.py` is PURE (numpy only — no Model/Scene/Qt/GL). Only the command + tool touch Model/Scene. `wall_box` works in whatever coordinate frame it's given (the tool converts world→active-local before calling it).
- **Baked geometry (D1):** a wall is a closed solid box built into a new group `Definition` named `"Wall"`, instanced in the **active context**. No parametric object, no new node type.
- **Chaining (D2) + per-segment undo (D7):** each committed segment = one `CreateWallCommand` on the stack (Ctrl+Z peels back the last wall). First click sets the anchor; each later click commits a wall and chains (`anchor = endpoint`). Esc/Enter ends the chain (no rollback — segments are already committed).
- **Centered (D4):** thickness/2 each side of the drawn line. **Independent boxes (D3):** no corner mitering. **Ground plane (D7):** base at the active context's local z=0, rising in local +Z.
- **Transform-aware:** convert world click points to the active context's local frame via `world_to_local_point(world, model.active_world_transform)` and zero local-z, before `wall_box`/the command (matches every M4e draw tool). No-op at the root context.
- **Units:** thickness/height stored in **meters** on the tool; the options row parses/formats via `pluton.units.parse_length` / `format_length` with the document's `Units`. Segment length via the VCB `apply_typed_value(text, units)`, like the Line tool.
- **Tests:** `.venv/Scripts/python` explicitly; full suite under a timeout: `timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Baseline (v0.2.0): **778 pytest + 79/79 ctest**. New Python files ruff-clean (`select = ["E","F","W","I","N","UP","B","C4","RUF"]`). NEVER broad `ruff --fix` on `main_window.py` (issue #48 — deliberate `# noqa`).
- **Git:** stage specific files only (no `git add -A`). SSH-signed commits; never `--no-verify`/`--amend`/`--no-gpg-sign`. Trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. On `main`. Verify sig via `git cat-file -p <sha> | grep -c "BEGIN SSH SIGNATURE"` (==1); `git log --show-signature` "No signature" is a KNOWN local gap, not a failure.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) edited ONLY in the release task. `0.2.0` → `0.2.1`.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.

---

## File Structure

- Create `python/pluton/geometry/wall.py` — pure `wall_box`.
- Create `python/pluton/commands/wall_commands.py` — `CreateWallCommand`.
- Create `python/pluton/tools/wall_tool.py` — `WallTool`.
- Create `python/pluton/ui/wall_options_bar.py` — `WallOptionsBar` (thickness/height fields).
- Modify `python/pluton/ui/main_window.py` — register `WallTool`, host the options bar, show/hide on tool switch. (Toolbar/menu entry follows the existing tool-surfacing pattern.)
- Tests: `tests/test_wall_geometry.py`, `tests/test_wall_commands.py`, `tests/test_wall_tool.py`, `tests/test_wall_options_bar.py`, `tests/test_main_window_wall.py`.

---

### Task 1: `wall_box` pure geometry generator

**Files:**
- Create: `python/pluton/geometry/wall.py`
- Test: `tests/test_wall_geometry.py`

**Interfaces:**
- Produces: `wall_box(start, end, thickness, height) -> (vertices: list[tuple[float,float,float]], faces: list[tuple[int,...]])` — 8 verts + 6 outward-wound quad faces of a centered solid box, or `([], [])` for a degenerate segment. Consumed by `CreateWallCommand` (Task 2).

- [ ] **Step 1: Write the failing test**

`tests/test_wall_geometry.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.geometry.wall import wall_box


def _bbox(vertices):
    a = np.array(vertices, dtype=np.float64)
    return a.min(axis=0), a.max(axis=0)


def test_axis_aligned_wall_dimensions_and_centering():
    verts, faces = wall_box((0.0, 0.0, 0.0), (4.0, 0.0, 0.0), thickness=0.2, height=2.4)
    assert len(verts) == 8
    assert len(faces) == 6
    lo, hi = _bbox(verts)
    assert np.allclose(lo, [0.0, -0.1, 0.0])
    assert np.allclose(hi, [4.0, 0.1, 2.4])   # length 4, thickness 0.2 centered, height 2.4


def test_closed_solid_every_edge_shared_by_two_faces():
    _, faces = wall_box((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), 0.2, 2.4)
    from collections import Counter
    edges = Counter()
    for f in faces:
        n = len(f)
        for i in range(n):
            a, b = f[i], f[(i + 1) % n]
            edges[frozenset((a, b))] += 1
    assert len(edges) == 12
    assert all(c == 2 for c in edges.values())   # closed manifold box


def test_diagonal_segment_length_and_height():
    verts, _ = wall_box((0.0, 0.0, 0.0), (3.0, 4.0, 0.0), 0.2, 2.4)
    a = np.array(verts)
    assert np.isclose(a[:, 2].min(), 0.0) and np.isclose(a[:, 2].max(), 2.4)
    # the two base "start" corners are ±perp around (0,0); base centroid near origin end
    base = a[a[:, 2] < 1e-6]
    assert len(base) == 4


def test_bottom_face_normal_points_down():
    verts, faces = wall_box((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), 0.2, 2.4)
    v = np.array(verts)
    loop = faces[0]                     # bottom
    p0, p1, p2 = v[loop[0]], v[loop[1]], v[loop[2]]
    n = np.cross(p1 - p0, p2 - p0)
    assert n[2] < 0                     # outward (down) for the bottom face


def test_degenerate_returns_empty():
    assert wall_box((1, 1, 0), (1, 1, 0), 0.2, 2.4) == ([], [])
    assert wall_box((0, 0, 0), (1, 0, 0), 0.0, 2.4) == ([], [])
    assert wall_box((0, 0, 0), (1, 0, 0), 0.2, 0.0) == ([], [])
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_geometry.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.geometry.wall`).

- [ ] **Step 3: Implement `wall_box`**

`python/pluton/geometry/wall.py`:

```python
"""Pure geometry generator for the Wall tool (M7a).

wall_box builds a centered solid-box wall segment from two base-centerline
points + thickness + height. No Model/Scene/Qt/GL deps — the caller supplies
points in whatever frame it wants the box built in (the WallTool converts
world -> active-context-local first).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9


def wall_box(start, end, thickness, height):  # noqa: ANN001
    """Return (vertices, faces) for a centered wall box, or ([], []) if degenerate.

    vertices: 8 (x, y, z) tuples [A, B, C, D, A', B', C', D'] (base then top).
    faces: 6 quad loops (index tuples), each wound so its right-hand-rule normal
    points OUT of the solid.
    """
    s = np.asarray(start, dtype=np.float64)
    e = np.asarray(end, dtype=np.float64)
    d = e - s
    d[2] = 0.0                                   # centerline is in-plane
    length = float(np.linalg.norm(d))
    if length < _EPS or thickness <= 0.0 or height <= 0.0:
        return [], []
    d /= length
    perp = np.array([d[1], -d[0], 0.0])          # in-plane perpendicular, unit
    o = perp * (thickness / 2.0)
    up = np.array([0.0, 0.0, float(height)])
    base_z = float(s[2])
    s0 = np.array([s[0], s[1], base_z])
    e0 = np.array([e[0], e[1], base_z])
    corners = [s0 - o, s0 + o, e0 + o, e0 - o]   # A, B, C, D (base)
    corners += [c + up for c in corners]         # A', B', C', D' (top)
    vertices = [(float(c[0]), float(c[1]), float(c[2])) for c in corners]
    # 0=A 1=B 2=C 3=D 4=A' 5=B' 6=C' 7=D'
    faces = [
        (0, 3, 2, 1),   # bottom  (-Z)
        (4, 5, 6, 7),   # top     (+Z)
        (0, 1, 5, 4),   # start cap
        (1, 2, 6, 5),   # long side
        (2, 3, 7, 6),   # end cap
        (3, 0, 4, 7),   # long side
    ]
    return vertices, faces
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_geometry.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/geometry/wall.py tests/test_wall_geometry.py
```
Expected: 5 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/geometry/wall.py tests/test_wall_geometry.py && git commit -m "$(cat <<'EOF'
feat(m7a): pure wall_box generator (centered solid box)

Builds 8 verts + 6 outward-wound quad faces of a centered wall segment from two
base-centerline points + thickness + height; degenerate -> empty. Pure numpy.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `CreateWallCommand` (model-target, undoable)

**Files:**
- Create: `python/pluton/commands/wall_commands.py`
- Test: `tests/test_wall_commands.py`

**Interfaces:**
- Consumes: `wall_box` (Task 1); `model.new_definition/new_instance`, `defn.mesh.add_vertex/add_face_from_loop`, `target_context.children`, `model.revalidate_active_path`; the `Command` ABC (`do(self, model)`/`undo(self, model)`, `name` class attr).
- Produces: `CreateWallCommand(start, end, thickness, height, target_context)` with `.summary`-free do/undo; executed via `command_stack.execute(cmd, model)`.

- [ ] **Step 1: Write the failing test**

`tests/test_wall_commands.py`:

```python
from __future__ import annotations

from pluton.commands.wall_commands import CreateWallCommand
from pluton.model.model import Model


def test_do_adds_wall_group_then_undo_removes_it():
    model = Model()
    target = model.active_context
    before = len(target.children)
    cmd = CreateWallCommand((0.0, 0.0, 0.0), (4.0, 0.0, 0.0), 0.2, 2.4, target)
    cmd.do(model)
    assert len(target.children) == before + 1
    wall_def = target.children[-1].definition
    assert wall_def.is_group and wall_def.name == "Wall"
    assert len(list(wall_def.mesh.vertices_iter())) == 8
    assert len(list(wall_def.mesh.faces_iter())) == 6
    cmd.undo(model)
    assert len(target.children) == before


def test_redo_rebuilds_and_double_undo_is_noop():
    model = Model()
    target = model.active_context
    cmd = CreateWallCommand((0.0, 0.0, 0.0), (4.0, 0.0, 0.0), 0.2, 2.4, target)
    cmd.do(model)
    cmd.undo(model)
    cmd.undo(model)                     # guarded
    assert len(target.children) == 0
    cmd.do(model)                       # redo re-runs do()
    assert len(target.children) == 1


def test_degenerate_segment_adds_nothing():
    model = Model()
    target = model.active_context
    cmd = CreateWallCommand((1.0, 1.0, 0.0), (1.0, 1.0, 0.0), 0.2, 2.4, target)
    cmd.do(model)
    assert len(target.children) == 0    # wall_box returned empty -> no group
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_commands.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.commands.wall_commands`).

- [ ] **Step 3: Implement the command**

`python/pluton/commands/wall_commands.py`:

```python
"""CreateWallCommand (M7a): undoably build a baked solid-box wall group."""
from __future__ import annotations

import numpy as np

from pluton.commands.command import Command
from pluton.geometry.wall import wall_box


class CreateWallCommand(Command):
    """Build one centered wall box into `target_context` as a `"Wall"` group.

    start/end are in the target_context's LOCAL frame (the tool converts from
    world). Undo detaches the single created instance; the definition is not
    globally registered, so its subtree becomes unreachable (matches
    ImportGltfCommand). Redo re-runs do()."""

    name = "Create Wall"

    def __init__(self, start, end, thickness, height, target_context) -> None:  # noqa: ANN001
        self._start = start
        self._end = end
        self._thickness = thickness
        self._height = height
        self._target = target_context
        self._instance = None

    def do(self, model) -> None:  # noqa: ANN001
        vertices, faces = wall_box(self._start, self._end, self._thickness, self._height)
        if not vertices:
            self._instance = None
            return
        defn = model.new_definition("Wall", is_group=True)
        local = {}
        for i, (x, y, z) in enumerate(vertices):
            local[i] = defn.mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
        for loop in faces:
            defn.mesh.add_face_from_loop([local[i] for i in loop])
        inst = model.new_instance(defn)
        self._target.children.append(inst)
        self._instance = inst

    def undo(self, model) -> None:  # noqa: ANN001
        if self._instance is None:
            return
        if self._instance in self._target.children:
            self._target.children.remove(self._instance)
        model.revalidate_active_path()
        self._instance = None
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_commands.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/commands/wall_commands.py tests/test_wall_commands.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/wall_commands.py tests/test_wall_commands.py && git commit -m "$(cat <<'EOF'
feat(m7a): CreateWallCommand (undoable baked-box wall group)

do() builds a "Wall" group (8 verts/6 faces via wall_box) into target_context;
undo() detaches the single instance (subtree becomes unreachable, like
ImportGltfCommand); redo re-runs do(); degenerate segment adds nothing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `WallTool` (chaining, VCB, transform-aware)

**Files:**
- Create: `python/pluton/tools/wall_tool.py`
- Test: `tests/test_wall_tool.py`

**Interfaces:**
- Consumes: the `Tool` ABC (`tools/tool.py`); `ToolContext` (scene, command_stack, model, units_provider); `world_to_local_point` (`viewport/picking`); `model.active_world_transform`/`active_context`; `parse_length` (`pluton.units`); `CreateWallCommand`; the snap object (`snap.world_position`, `snap.kind`, `SnapKind`).
- Produces: `WallTool` with public `thickness`/`height` properties (meters, defaults 0.1 / 2.4) the options bar binds to; `shortcut = "W"`.

**Interaction (mirror `line_tool.py`):** first click sets `_anchor` (world). Each later click resolves the endpoint (world), executes one `CreateWallCommand` (points converted to active-local, z zeroed), then chains `_anchor = endpoint`. Esc/Enter clears `_anchor` (segments already committed). `apply_typed_value` places the endpoint at the typed length along the cursor direction and commits. `has_active_gesture` is True while `_anchor` is set. `anchor_or_none` returns `_anchor` (world) for axis-lock. Rubber-band = a centerline segment `_anchor`→cursor.

- [ ] **Step 1: Write the failing test** (headless — drive the tool's methods directly, like the other tool tests; use a fake snap + a real `Model`/`CommandStack`)

`tests/test_wall_tool.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.model.model import Model
from pluton.tools.tool import ToolContext
from pluton.tools.wall_tool import WallTool
from pluton.viewport.snap_engine import SnapKind


@dataclass
class _Snap:
    kind: object
    world_position: np.ndarray
    vertex_id: int = None
    edge_id: int = None
    edge_t: float = None
    axis: int = None


def _ctx(model, stack):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model,
        units_provider=lambda: None,
    )


def _snap(x, y, z=0.0):
    return _Snap(kind=SnapKind.ON_FACE, world_position=np.array([x, y, z], dtype=np.float32))


def test_two_clicks_commit_one_wall_and_chain():
    model = Model()
    stack = CommandStack()
    tool = WallTool()
    tool.activate(_ctx(model, stack))
    tool.on_mouse_press(_snap(0, 0), _snap(0, 0))          # anchor
    assert tool.has_active_gesture
    assert len(model.active_context.children) == 0
    tool.on_mouse_press(_snap(4, 0), _snap(4, 0))          # commit wall #1, chain
    assert len(model.active_context.children) == 1
    tool.on_mouse_press(_snap(4, 3), _snap(4, 3))          # commit wall #2 from (4,0)
    assert len(model.active_context.children) == 2
    assert stack.can_undo


def test_escape_ends_chain_without_removing_committed_walls():
    model = Model()
    stack = CommandStack()
    tool = WallTool()
    tool.activate(_ctx(model, stack))
    tool.on_mouse_press(_snap(0, 0), _snap(0, 0))
    tool.on_mouse_press(_snap(4, 0), _snap(4, 0))
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent, Qt
    tool.on_key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not tool.has_active_gesture
    assert len(model.active_context.children) == 1          # committed wall stays


def test_thickness_height_drive_geometry():
    model = Model()
    stack = CommandStack()
    tool = WallTool()
    tool.thickness = 0.3
    tool.height = 3.0
    tool.activate(_ctx(model, stack))
    tool.on_mouse_press(_snap(0, 0), _snap(0, 0))
    tool.on_mouse_press(_snap(2, 0), _snap(2, 0))
    wall = model.active_context.children[-1].definition
    zs = [v.position[2] for v in wall.mesh.vertices_iter()]
    ys = [v.position[1] for v in wall.mesh.vertices_iter()]
    assert max(zs) == 3.0
    assert max(ys) - min(ys) == 0.3
```

*(The exact snap signature and the `on_mouse_press(event, snap)` call convention should match the other tool tests — adjust the fake `event`/`snap` to whatever `line_tool`'s tests use; the assertions on committed children + geometry are the point.)*

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_tool.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.tools.wall_tool`).

- [ ] **Step 3: Implement `WallTool`**

`python/pluton/tools/wall_tool.py` — mirror `line_tool.py`'s structure (imports, snap handling, `_world_transform`, overlay). Key body:

```python
"""The Wall drawing tool (M7a).

Chaining polyline of baked solid-box walls. Click to start; each later click
commits one wall (CreateWallCommand) and chains. Esc/Enter ends the chain.
Thickness/height are tool settings (meters) driven by the WallOptionsBar.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.wall_commands import CreateWallCommand
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import world_to_local_point
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND

_NEUTRAL = (0.85, 0.85, 0.85)


class WallTool(Tool):
    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._anchor = None                    # world-space start of current segment
        self._preview_tip = None               # world-space cursor
        self._snap_pos = None
        self._snap_color = _NEUTRAL
        self._snap_kind = 0
        self.thickness = 0.1                   # meters
        self.height = 2.4                      # meters

    @property
    def name(self) -> str:
        return "Wall"

    @property
    def shortcut(self) -> str:
        return "W"

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def _world_transform(self):  # noqa: ANN202
        return self._model.active_world_transform if self._model is not None else None

    def _to_local_ground(self, world_pt):  # noqa: ANN001
        local = np.asarray(world_to_local_point(np.asarray(world_pt, np.float32),
                                                self._world_transform()), np.float64)
        local[2] = 0.0                         # base sits on the context ground plane
        return local

    def _commit(self, endpoint_world) -> None:  # noqa: ANN001
        start = self._to_local_ground(self._anchor)
        end = self._to_local_ground(endpoint_world)
        cmd = CreateWallCommand(start, end, self.thickness, self.height,
                                self._model.active_context)
        self._command_stack.execute(cmd, self._model)
        self._anchor = np.asarray(endpoint_world, np.float32).copy()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if snap.kind == SnapKind.NONE:
            self._snap_pos = None
            self._snap_kind = 0
            return
        self._snap_pos = np.asarray(snap.world_position, np.float32).copy()
        self._snap_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL)
        self._snap_kind = int(snap.kind)
        if self._anchor is not None:
            self._preview_tip = np.asarray(snap.world_position, np.float32).copy()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if snap.kind == SnapKind.NONE:
            return
        pt = np.asarray(snap.world_position, np.float32)
        if self._anchor is None:
            self._anchor = pt.copy()
            self._preview_tip = pt.copy()
            return
        if float(np.linalg.norm(pt - self._anchor)) < 1e-6:
            return                             # degenerate click
        self._commit(pt)

    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._anchor is None or self._preview_tip is None:
            return False
        length = parse_length(text, units)
        if length is None or length <= 0:
            return False
        direction = np.asarray(self._preview_tip, np.float64) - np.asarray(self._anchor, np.float64)
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return False
        endpoint = (np.asarray(self._anchor, np.float64) + direction / norm * length)
        self._commit(endpoint.astype(np.float32))
        return True

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._reset()

    def overlay(self) -> ToolOverlay:
        if self._anchor is not None and self._preview_tip is not None:
            segments = np.array([self._anchor, self._preview_tip], dtype=np.float32)
        else:
            segments = np.zeros((0, 3), dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=self._snap_pos.copy() if self._snap_pos is not None else None,
            snap_marker_color=self._snap_color,
            snap_marker_kind=self._snap_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._anchor is not None

    @property
    def anchor_or_none(self):  # noqa: ANN201
        return self._anchor.copy() if self._anchor is not None else None

    @property
    def status_text(self):  # noqa: ANN201
        return None

    def _reset(self) -> None:
        self._anchor = None
        self._preview_tip = None
        self._snap_pos = None
        self._snap_kind = 0
```

*(Confirm `on_mouse_press(event, snap)` matches how the viewport calls tools — `line_tool` is the reference. If `world_to_local_point`/`active_world_transform` need `float64`, cast as `line_tool` does.)*

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/wall_tool.py tests/test_wall_tool.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/wall_tool.py tests/test_wall_tool.py && git commit -m "$(cat <<'EOF'
feat(m7a): WallTool (chaining polyline of baked walls)

Line-tool-style chaining: click to anchor, each later click commits one
CreateWallCommand and chains; VCB sets segment length; transform-aware
(world->active-local, base on the context ground plane); Esc/Enter ends the
chain. Public thickness/height (meters) for the options bar.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `WallOptionsBar` (thickness/height fields)

**Files:**
- Create: `python/pluton/ui/wall_options_bar.py`
- Test: `tests/test_wall_options_bar.py`

**Interfaces:**
- Consumes: `pluton.units.parse_length`/`format_length`; a `WallTool` (reads/writes `.thickness`/`.height`, meters); a `units_provider` callable `() -> Units`.
- Produces: `WallOptionsBar(wall_tool, units_provider)` — a `QWidget` with two unit-aware fields; `refresh()` reformats from the tool; editing a field parses and writes back to the tool.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_wall_options_bar.py`:

```python
from __future__ import annotations

from pluton.tools.wall_tool import WallTool
from pluton.ui.wall_options_bar import WallOptionsBar
from pluton.units import Units


def test_fields_reflect_and_update_tool(qtbot):
    tool = WallTool()
    tool.thickness = 0.1
    tool.height = 2.4
    bar = WallOptionsBar(tool, units_provider=lambda: Units())
    qtbot.addWidget(bar)
    bar.refresh()
    # Editing the thickness field to a metric value updates the tool (meters).
    bar._thickness_edit.setText("200mm")
    bar._on_thickness_committed()
    assert abs(tool.thickness - 0.2) < 1e-6
    bar._height_edit.setText("3m")
    bar._on_height_committed()
    assert abs(tool.height - 3.0) < 1e-6


def test_bad_input_is_ignored(qtbot):
    tool = WallTool()
    bar = WallOptionsBar(tool, units_provider=lambda: Units())
    qtbot.addWidget(bar)
    bar._thickness_edit.setText("not a number")
    bar._on_thickness_committed()
    assert tool.thickness == 0.1        # unchanged
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_options_bar.py -q -p no:cacheprovider
```
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `WallOptionsBar`**

`python/pluton/ui/wall_options_bar.py`:

```python
"""WallOptionsBar (M7a): thickness/height settings row for the Wall tool."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from pluton.units import format_length, parse_length


class WallOptionsBar(QWidget):
    """A compact row with unit-aware Thickness + Height fields bound to a
    WallTool. MainWindow shows it only while the Wall tool is active."""

    def __init__(self, wall_tool, units_provider) -> None:  # noqa: ANN001
        super().__init__()
        self._tool = wall_tool
        self._units = units_provider
        self._thickness_edit = QLineEdit()
        self._height_edit = QLineEdit()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(QLabel("Wall thickness:"))
        layout.addWidget(self._thickness_edit)
        layout.addWidget(QLabel("height:"))
        layout.addWidget(self._height_edit)
        layout.addStretch(1)
        self._thickness_edit.editingFinished.connect(self._on_thickness_committed)
        self._height_edit.editingFinished.connect(self._on_height_committed)
        self.refresh()

    def refresh(self) -> None:
        u = self._units()
        self._thickness_edit.setText(format_length(self._tool.thickness, u))
        self._height_edit.setText(format_length(self._tool.height, u))

    def _on_thickness_committed(self) -> None:
        v = parse_length(self._thickness_edit.text(), self._units())
        if v is not None and v > 0:
            self._tool.thickness = v
        self.refresh()

    def _on_height_committed(self) -> None:
        v = parse_length(self._height_edit.text(), self._units())
        if v is not None and v > 0:
            self._tool.height = v
        self.refresh()
```

*(If `Units()` needs arguments, construct it as the rest of the codebase does — check `pluton.units.Units`.)*

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_wall_options_bar.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/ui/wall_options_bar.py tests/test_wall_options_bar.py
```
Expected: 2 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/wall_options_bar.py tests/test_wall_options_bar.py && git commit -m "$(cat <<'EOF'
feat(m7a): WallOptionsBar (unit-aware thickness/height fields)

A compact row bound to the WallTool's thickness/height (meters); parses/formats
via pluton.units with the document Units; bad input ignored.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: MainWindow integration (register + shortcut + host options bar)

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_wall.py`

**Interfaces:**
- Consumes: `ToolManager.register`; the existing tool-shortcut dispatch; the layout that holds `_status_bar`.
- Produces: `WallTool` registered (shortcut `W`); a `WallOptionsBar` created + added to the layout, shown only when the Wall tool is active; a toolbar/menu entry consistent with the other tools.

- [ ] **Step 1: Write the failing test** (pytest-qt)

`tests/test_main_window_wall.py`:

```python
from __future__ import annotations

from pluton.tools.wall_tool import WallTool
from pluton.ui.main_window import MainWindow


def test_wall_tool_registered_with_w(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("W")
    assert isinstance(w._tool_manager.active, WallTool)


def test_options_bar_visible_only_for_wall(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w._tool_manager.activate_by_shortcut("W")
    w._refresh_tool_options()                 # the hook MainWindow calls on tool switch
    assert w._wall_options_bar.isVisibleTo(w)
    w._tool_manager.activate_by_shortcut("L")  # line tool
    w._refresh_tool_options()
    assert not w._wall_options_bar.isVisibleTo(w)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_main_window_wall.py -q -p no:cacheprovider
```
Expected: FAIL (no `W` tool / no `_wall_options_bar` / no `_refresh_tool_options`).

- [ ] **Step 3: Wire MainWindow**

In `python/pluton/ui/main_window.py` (additive — do NOT reflow/`ruff --fix` the file; issue #48):

1. Import `WallTool` and `WallOptionsBar` (with the other tool/ui imports).
2. Register the tool after the existing `register(...)` calls (near line 85):
   ```python
   self._tool_manager.register(WallTool())
   ```
3. Create the options bar (after the tool manager + `_doc` exist) and add it to the main layout just above the status bar; start hidden:
   ```python
   self._wall_tool = next(t for t in self._tool_manager._tools.values() if isinstance(t, WallTool))
   self._wall_options_bar = WallOptionsBar(self._wall_tool, units_provider=lambda: self._doc.units)
   self._wall_options_bar.hide()
   layout.addWidget(self._wall_options_bar, stretch=0)   # before/above _status_bar
   ```
   (If grabbing the registered instance by `_tools` is awkward, construct `WallTool()` once, keep the reference, and pass the same instance to `register`.)
4. Add `_refresh_tool_options()` and call it wherever the active tool changes (right after `activate_by_shortcut` succeeds in the key handler, and after any programmatic tool switch):
   ```python
   def _refresh_tool_options(self) -> None:
       is_wall = isinstance(self._tool_manager.active, WallTool)
       if is_wall:
           self._wall_options_bar.refresh()
       self._wall_options_bar.setVisible(is_wall)
   ```
5. Add a Wall entry to the toolbar/Tools menu the same way the other tools are surfaced (match the existing idiom; if tools are only shortcut-driven with no per-tool menu items, a `Tools ▸ Wall (W)` action that calls `activate_by_shortcut("W")` + `_refresh_tool_options()` is sufficient).

Audit shortcuts to confirm `W` is unused (grep the tools' `shortcut` properties).

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_main_window_wall.py -q -p no:cacheprovider
```
Expected: 2 passed, no hang. Confirm `main_window.py` gained NO new ruff violation category (diff base vs head; do NOT autofix it).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_wall.py && git commit -m "$(cat <<'EOF'
feat(m7a): register WallTool (W) + host WallOptionsBar in MainWindow

Register the Wall tool with the W shortcut, add a Tools entry, and show the
WallOptionsBar only while the Wall tool is active (_refresh_tool_options on
tool switch).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Full regression + master design-doc annotation

**Files:**
- Modify: `docs/2026-05-16-pluton-design.md` (annotate the M7 line)

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass, no hang (~15 s), above the 778 baseline (M7a adds ~15 tests).

- [ ] **Step 2: C++ regression (unchanged, confirm still green)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure | tail -3)
```
Expected: 79/79 (M7a is Python-only; ctest unaffected).

- [ ] **Step 3: Annotate the master design doc**

`docs/2026-05-16-pluton-design.md` — on the **M7** line, add an M7a ✅ *(shipped v0.2.1)* sub-milestone note describing the Wall tool (baked chaining boxes, centered thickness/height, tool-options row), and note the remaining M7 sub-milestones (M7b Door/Window, M7c Roof, M7d Dimensions, M7e Scenes). Confirm the M8 line is untouched (`grep -c` stays 1).

- [ ] **Step 4: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
docs(m7a): annotate master design M7 line — Wall tool shipped

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Release v0.2.1

*(Outward-facing steps — push, tag, issues — require explicit per-turn user authorization, as with prior releases. Do the local bump/build/commit first, then ask.)*

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`

- [ ] **Step 1: Bump the version to 0.2.1**

- `pyproject.toml` → `version = "0.2.1"`
- `CMakeLists.txt` → `VERSION 0.2.1`
- `cpp/src/version.cpp` → `return "0.2.1";`

- [ ] **Step 2: Rebuild and verify the reported version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake" .venv/Scripts/python -m pip install -e . --no-build-isolation && .venv/Scripts/python -c "import pluton._core as c; assert c.version()=='0.2.1', c.version(); print('version OK', c.version())"
```
Expected: `version OK 0.2.1`. (Only `version.cpp` recompiles; Assimp is cached.)

- [ ] **Step 3: Final full suite at the new version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass.

- [ ] **Step 4: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -m "$(cat <<'EOF'
release: v0.2.1 — Wall tool (M7a)

Bump 0.2.0 -> 0.2.1. First M7 sub-milestone: a Wall tool drawing a chaining
polyline of baked solid-box walls (centered thickness + height, ground plane),
undoable per segment, with a thickness/height tool-options row.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify signatures on the branch**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && for s in $(git log --format=%H dc75032..HEAD); do echo "$s $(git cat-file -p $s | grep -c 'BEGIN SSH SIGNATURE')"; done
```
Expected: every listed commit shows `1`.

- [ ] **Step 6: Push, tag, issues — AFTER explicit user authorization**

Ask the user to authorize the release. Once authorized:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main && git tag -s v0.2.1 -m "Pluton v0.2.1 — Wall tool (M7a)" && git push origin v0.2.1
```
Then watch CI to green on both platforms (`gh run watch`). File carry-over issues (mitered corners, selectable justification, parametric/editable walls, wall-on-face drawing, persist wall defaults in the document) + the M7a tracking issue (closed).

- [ ] **Step 7: Manual visual pass (user)**

Launch the app; the user traces a multi-segment floor plan with the Wall tool, sets thickness/height in the options row, confirms corners/undo, and that walls paint/move/push-pull like normal geometry.

---

## Self-Review

**1. Spec coverage.** D1 baked group → Task 2. D2 chaining + D7 per-segment undo → Task 3. D3 independent boxes → Task 2 (one box per command). D4 centered → Task 1 `wall_box`. D5 tool-options thickness/height → Task 4. D6 VCB length → Task 3 `apply_typed_value`. D8 direct box → Task 1. D9 `W` + registration → Task 5. D10 v0.2.1 → Task 7. Transform-awareness → Task 3 `_to_local_ground`. **All decisions covered.**

**2. Placeholder scan.** No TBD/"add error handling". The "confirm against `line_tool`" notes (snap/event call convention, `Units()` construction, the exact tool-switch hook) are real confirm-against-code steps a UI-integrated tool requires, each with the reference named — not hand-waving.

**3. Type/interface consistency.** `wall_box(start, end, thickness, height) -> (vertices, faces)` used identically in Tasks 1–2. `CreateWallCommand(start, end, thickness, height, target_context)` consistent in Tasks 2–3. `WallTool.thickness/.height` (meters) produced in Task 3, consumed in Task 4. `WallOptionsBar(wall_tool, units_provider)` consistent in Tasks 4–5. `_refresh_tool_options` defined + tested in Task 5.

**4. Ordering.** Pure generator (1) → command that uses it (2) → tool that uses the command (3) → options bar that binds the tool (4) → MainWindow that hosts both (5) → regression/doc (6) → release (7). Each task independently testable; no forward dependency.

Plan complete.

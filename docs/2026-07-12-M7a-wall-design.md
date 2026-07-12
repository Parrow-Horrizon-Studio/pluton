# M7a — Wall Tool — Design

**Date:** 2026-07-12
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio) + Claude (brainstorming)
**Milestone:** M7a (first sub-milestone of M7 — Architecture-specific tools), Phase 2
**Predecessor:** M6 complete (v0.2.0, glTF import/export closed the File-I/O arc). Target release: **v0.2.1**.
**Issue:** M7a (tracking issue filed at release, per prior milestone practice)

---

## 1. Overview & scope

M7a adds the **Wall tool** — the first architecture-specific tool and the
foundational primitive the rest of M7 (Door/Window, Roof) builds on. It lets an
architect trace a floor plan and get solid walls with a set thickness + height,
using the existing draw-on-plane + snapping + component machinery.

A wall in M7a is **baked geometry**: the tool generates a closed solid box per
segment and drops it into the scene graph as a plain **group**. It is *not* a
parametric object — there is no new node type and no regeneration-from-parameters
subsystem. Walls are edited afterward with the tools that already exist (Move,
Push/Pull, Scale, Paint, Eraser, Select), exactly like any other geometry.

### 1.1 Goals

1. A **Wall tool** (shortcut `W`) that draws walls as a **chaining polyline** on
   the ground plane — click to start, click each subsequent point to drop a wall
   segment, the endpoint chains into the next, Esc/Enter finishes — reusing the
   Line tool's snapping/inferencing and the VCB for typed segment length.
2. Each segment becomes a **closed solid box** (length × thickness × height),
   **centered** on the drawn line, base at z=0, rising in +Z, built into the
   active context as an undoable `"Wall"` group.
3. **Thickness + height** set via a small **tool-options row** (two unit-aware
   fields), with remembered defaults (thickness 100 mm, height 2400 mm).

### 1.2 Non-goals (deferred to later M7 sub-milestones or follow-ups)

- **Parametric / re-editable walls** (change height/thickness after the fact via
  a wall object). Deferred — walls are baked geometry.
- **Mitered / cleanly-joined corners.** Adjacent segments are **independent
  boxes** that overlap/butt at corners. Clean mitering is a boolean/merge problem
  — a follow-up.
- **Selectable justification** (left/right of the line). M7a is **centered**
  only; left/right is an easy follow-up modifier.
- **Openings** (doors/windows cut into walls) — that's **M7b**.
- **Drawing walls on an arbitrary face** (non-ground-plane). M7a walls rise from
  the ground plane (base z=0).
- **Per-document persistence** of the thickness/height defaults across save/open
  (they persist on the tool for the session; storing them in the file is a
  follow-up).

---

## 2. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Wall representation | **Baked geometry** — a closed solid box per segment, dropped in as a plain group; no parametric object |
| D2 | Path input | **Chaining polyline** (click points continuously; endpoint chains); Esc/Enter finishes |
| D3 | Corners | **Independent boxes** — overlap/butt at corners; no auto-miter |
| D4 | Justification | **Centered** on the drawn line (thickness/2 each side) |
| D5 | Thickness/height input | **Tool-options row** (two unit-aware fields); defaults 100 mm × 2400 mm, remembered on the tool |
| D6 | Segment length input | The **VCB** (Measurements box), exactly like the Line tool |
| D7 | Placement | Ground plane (base z=0, height in +Z); one **undoable command per committed segment** |
| D8 | Approach | **Direct oriented-box construction** — a pure `wall_box` generator (not reusing push/pull) |
| D9 | Shortcut | **`W`** |
| D10 | Version | **v0.2.1** |

---

## 3. Architecture & file structure

Mirrors the M4a drawing-tool layering (pure geometry generator + tool + command):

- **Create** `python/pluton/geometry/wall.py` — PURE `wall_box(start, end,
  thickness, height) -> (vertices, faces)`. No Model/GL/Qt deps.
- **Create** `python/pluton/commands/wall_commands.py` — `CreateWallCommand`
  (builds one wall box into a `"Wall"` group in the active context; undoable).
- **Create** `python/pluton/tools/wall_tool.py` — `WallTool` (the chaining
  interaction; subclasses the `Tool` ABC).
- **Modify** `python/pluton/tools/tool_manager.py` — register `WallTool`.
- **Modify** `python/pluton/ui/main_window.py` — Wall toolbar/menu entry +
  `W` shortcut + host the tool-options row.
- **Create** `python/pluton/ui/tool_options_bar.py` (or reuse an existing
  options area if one exists) — a lightweight `ToolOptionsBar` the Wall tool
  populates with Thickness + Height fields; shown only when a tool that uses it
  is active.
- Tests: `tests/test_wall_geometry.py`, `tests/test_wall_commands.py`,
  `tests/test_wall_tool.py`, `tests/test_tool_options_bar.py` (or folded in).

---

## 4. The `wall_box` generator (`geometry/wall.py`)

Given `start`/`end` ground-plane points (z=0), `thickness` t, `height` h:

```
dvec = end - start            # in-plane (z stays 0)
length = |dvec|
if length < EPS or t <= 0 or h <= 0:
    return ([], [])           # degenerate -> tool skips this segment
d    = dvec / length          # unit direction
perp = (d.y, -d.x, 0)         # in-plane perpendicular (unit)
o    = perp * (t / 2)         # half-thickness offset (centered)

# 4 base vertices (z=0) forming the footprint rectangle:
A = start - o;  B = start + o;  C = end + o;  D = end - o
# 4 top vertices (z=h):
A' = A + (0,0,h);  B' = B + (0,0,h);  C' = C + (0,0,h);  D' = D + (0,0,h)
```

Returns **8 vertices** `[A,B,C,D,A',B',C',D']` and **6 quad faces** (a closed
solid box): bottom `ABCD`, top `A'B'C'D'`, and the four sides `AB·A'B'`,
`BC·B'C'`, `CD·C'D'`, `DA·D'A'`. Each face loop is wound so its **right-hand-rule
normal points out of the solid** — the implementer fixes the exact loop order and
locks it with a test (see §7); the M4a shape generators established the project's
winding convention to follow.

Pure, deterministic, headlessly testable. The tool/command translate the world
points; `wall_box` is coordinate-space-agnostic (it just needs the two points and
the two scalars).

---

## 5. `CreateWallCommand` (`commands/wall_commands.py`)

Undoable wrapper that builds one wall box into the model, mirroring the M4a
shape-commit commands and the M6c import command:

- `do(model)`: create a group `Definition` (is_group=True) named `"Wall"`; for
  each vertex from `wall_box`, `defn.mesh.add_vertex(...)`; for each face loop,
  `defn.mesh.add_face_from_loop(...)`; `inst = model.new_instance(defn)`;
  `target_context.children.append(inst)`. Record the created instance.
- `undo(model)`: remove the created instance from `target_context.children`
  (+ `model.revalidate_active_path()`), matching the M6c import-undo pattern
  (definitions aren't globally registered, so the subtree becomes unreachable).
- Redo re-runs `do()` (no separate redo), per the `Command` ABC.
- Faces get the **default material** (unpainted); paintable afterward.
- Built via `CommandStack.execute(cmd, model)` so it lands on the undo stack.

The `target_context` is the model's **active context** at commit time (so walls
drawn inside an entered group land there), consistent with the other tools.

---

## 6. `WallTool` (`tools/wall_tool.py`)

Subclasses `Tool` (the ABC in `tools/tool.py`); mirrors `line_tool.py`'s chaining
state machine.

- **`name`** = "Wall"; **`shortcut`** = "W".
- **State:** an optional `_anchor` (the current segment's start point, in world
  space, projected to z=0) and the tool's `_thickness`/`_height` settings.
- **`on_mouse_move`:** resolve the snapped/inferred world point (reuse the
  SnapEngine handed in via the viewport, as the Line tool does), project to z=0,
  and update the rubber-band preview: a wall footprint outline (or a thin
  centerline segment) from `_anchor` to the cursor. `overlay()` returns the
  rubber-band segments + snap marker (a ghost of the wall footprint is a nice
  touch but optional for M7a — a centerline rubber-band is sufficient).
- **`on_mouse_press`:** first click sets `_anchor`. Each subsequent click
  resolves the endpoint, executes `CreateWallCommand(anchor, endpoint,
  _thickness, _height, active_context)` on the command stack, then **chains**:
  `_anchor = endpoint` (ready for the next segment).
- **`on_key_press`:** Esc/Enter (or double-click) finishes the chain (clears
  `_anchor`). Per the ABC, `has_active_gesture` is True while `_anchor` is set so
  MainWindow routes Esc to the tool (cancel gesture) rather than deactivating.
- **`apply_typed_value(text, units)`:** while a segment is in progress, parse the
  typed value as the **segment length** (using the M4d units parser) and place
  the endpoint at that distance along the current cursor direction from
  `_anchor`, then commit — exactly like the Line tool's VCB behavior. Returns
  True when consumed.
- **`anchor_or_none`** returns `_anchor` for the SnapEngine's axis-lock.
- **`status_text`** optionally shows the current thickness × height.
- **`activate`/`deactivate`** wire/unwire the tool-options row (populate it with
  the Thickness/Height fields on activate; hide on deactivate).

Degenerate clicks (endpoint ≈ anchor) are ignored (no command executed), matching
`wall_box`'s guard.

**Transform-awareness (required):** the clicked/snapped points are world-space,
but the wall is built into a group `Definition` instanced at **identity** in the
active context. So the tool converts each world point into the **active context's
local frame** — `local = mat_invert(model.active_world_transform) @ world_pt`
(z then re-zeroed to sit on the context's ground plane) — before handing
`start`/`end` to `wall_box`/`CreateWallCommand`. This is the same transform-aware
handling every draw tool received in M4e, and it makes walls draw correctly when
you're inside an entered or moved group. At the root context (identity) it's a
no-op.

---

## 7. Tool-options row (`ui/tool_options_bar.py`)

A small horizontal widget the Wall tool populates:

- Two **unit-aware numeric fields**: **Thickness** and **Height**, parsed and
  formatted via the existing M4d units code (`pluton.units` — same
  parse/format used by the VCB), respecting the document's metric/imperial unit.
- Defaults: **thickness 100 mm**, **height 2400 mm** (shown in the current unit;
  ~4″ × 8′ imperial). Edited values persist on the `WallTool` for the session and
  drive every subsequently-drawn wall.
- Shown only when a tool that registers options is active (Wall in M7a); hidden
  otherwise. Placed near the VCB / status area.
- If `main_window` already has a tool-options / secondary-input area, reuse it
  instead of adding a new widget (the implementer checks first). Otherwise this
  is a small, reusable addition (future tools can post options to it).

The row is a *settings* input (persistent between segments), distinct from the
VCB, which handles the *transient* segment length during a gesture.

---

## 8. Integration

- Register `WallTool` in `tools/tool_manager.py` alongside the other tools, with
  the `W` shortcut.
- Add a Wall entry to the toolbar and/or Tools menu in `main_window.py`
  (matching how the existing tools are surfaced).
- Ensure `W` doesn't collide with an existing shortcut (audit the current
  tool shortcuts during implementation; `W` is expected free).
- The tool-options row is created/hosted by `main_window.py` and shown/hidden as
  the active tool changes.

---

## 9. Testing

Layered, mostly headless (mirrors M4a):

1. **`test_wall_geometry.py` (pure):**
   - `wall_box((0,0,0),(L,0,0), t, h)` returns 8 vertices + 6 faces.
   - Bounding box is `L × t × h`: x∈[0,L], y∈[−t/2, t/2] (centered), z∈[0,h].
   - **Closed solid:** every one of the 12 box edges is shared by exactly 2 of
     the 6 faces (manifold check) — this also catches winding/loop errors.
   - A **diagonal** segment (e.g. (0,0,0)→(3,4,0)) has the right length (5),
     thickness offset perpendicular, and z∈[0,h].
   - Degenerate: zero-length, zero/negative thickness or height → `([], [])`.
   - Outward-normal spot check (at least the bottom face normal points −Z) to
     lock the winding convention.
2. **`test_wall_commands.py`:** `CreateWallCommand.do` adds a `"Wall"` group
   (8 verts / 6 faces) to the active context; **undo removes it exactly**
   (children count back to baseline, active path revalidated); redo rebuilds.
3. **`test_wall_tool.py` (qtbot / headless harness like other tool tests):**
   click-start then click-end commits one wall via the command stack; a third
   click chains a second wall whose start = the previous end; Esc/Enter clears
   the gesture; `apply_typed_value` places the endpoint at the typed length; the
   tool's thickness/height drive the built geometry.
4. **Tool-options row:** the Thickness/Height fields appear when the Wall tool is
   active, parse/format in the document unit, persist across walls, and change
   the generated geometry.
5. **Regression:** full pytest + ctest stay green (M7a is purely additive; no
   C++/kernel changes, so ctest is unaffected). Baseline at release of v0.2.0:
   778 pytest + 79/79 ctest.
6. **Manual visual pass (user):** trace a multi-segment floor plan; confirm
   thickness/height, corners (overlapping boxes look right), that undo peels back
   segment-by-segment, and that walls paint / move / push-pull like normal
   geometry.

---

## 10. Release

- **Version:** `0.2.1` (pyproject.toml / CMakeLists.txt / cpp/src/version.cpp),
  bumped only in the release task. (No C++ change, but keep the three version
  strings in lockstep as prior milestones did.)
- Master design doc (`docs/2026-05-16-pluton-design.md`) M7 line annotated with
  M7a ✅ *(shipped v0.2.1)* as a sub-milestone note.
- Tag `v0.2.1`; push main + tag; CI green both platforms.
- File the M7a tracking issue (retroactively, closed) + carry-over issues:
  mitered corners, selectable justification, parametric/editable walls,
  wall-on-face drawing, persist wall defaults in the document.

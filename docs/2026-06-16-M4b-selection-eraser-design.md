# M4b — Selection & Eraser

- **Date:** 2026-06-16
- **Status:** Approved (design)
- **Milestone:** M4b — second sub-milestone of **M4 (Modeling polish)**. M4 split: M4a (drawing tools, ✅ v0.1.0) → **M4b (selection & eraser)** → M4c (transforms) → M4d (units & measurement) → M4e (groups & components).
- **Predecessor spec:** `docs/2026-06-15-M4a-drawing-tools-design.md`
- **Release:** completing M4b cuts **v0.1.1** (stays in the v0.1 band; M5 → v0.2).

---

## 1. Context & motivation

Phase 1 + M4a gave Pluton tools that *create* geometry (Line, Rectangle, Circle, Polygon, Arc) and *modify* it in place (Push/Pull). There is **no way to select existing geometry** and **no way to delete it** — the scene has no persistent selection state at all (confirmed by reconnaissance: no `selected_*` containers, no hit-testing for selection, no Delete handling).

M4b builds the **selection subsystem** — the keystone the rest of M4 depends on. **M4c (Move/Rotate/Scale)** transforms a selection; **M4e (Groups & Components)** groups a selection. So selection must be a **first-class, shared, persistent** object, not tool-local state. M4b delivers:

- A **Select tool** with click, Shift-extend, and direction-sensitive **box-select** (window + crossing).
- **Selection highlighting** in the renderer (persistent across tool switches).
- An **Eraser tool** (drag over edges, cascade-deleting their faces) and **Delete/Backspace** on the selection.

Most of it composes existing seams: the M3b **ghost-fill** overlay (face highlighting), `Scene.ray_pick_face` + the M3d snap engine's segment-ray picking (edge/face picking), and the existing `RemoveFace/Edge/VertexCommand` + `CompositeCommand` (undoable deletion). The genuinely new builds are the shared `Selection`, the picking/box-cull module, the renderer selection-highlight pass, and mouse-release routing.

## 2. Goals / Non-goals

**Goals**
- A shared **`Selection`** (sets of edge ids + face ids) owned by `MainWindow`, reachable by tools (via `ToolContext`) and the renderer; **persists across tool switches**.
- **Select tool** (`Spacebar`): hover pre-highlight; click = replace; Shift-click = toggle; empty click = clear; **box-select** — left→right **Window** (enclose-only, solid box), right→left **Crossing** (touch, dashed box).
- **Eraser tool** (`E`): hover/drag over **edges**, deleting each edge **and its incident faces** (cascade), accumulated into one undoable stroke.
- **Delete / Backspace**: delete the current selection (edges cascade to faces; faces leave their edges), undoable.
- **Selection highlight**: selected edges bold blue, selected faces translucent blue (reusing ghost-fill); **lighter hover pre-highlight**.
- Status bar shows a **selection count**.

**Non-goals (this milestone)**
- **Vertex selection** — only edges + faces are selectable (the locked decision; vertices are implied).
- **Double-click / triple-click smart-select** (bounding edges / connected geometry) — carry-over.
- **Select by material / tag, invert, grow/shrink** — carry-over.
- **Eraser modifiers** (Ctrl = soften, Shift = hide instead of delete) — carry-over (no softening/hiding concept until M5).
- **Move/Rotate/Scale of the selection** — that is **M4c**.

## 3. Decisions (locked in brainstorming)

| Decision | Choice |
|----------|--------|
| Selectable entity kinds | **Edges + faces** (not vertices) |
| Eraser target | **Edges**, drag-to-erase, cascading to incident faces |
| Box-select | **Both** modes, direction-sensitive: L→R Window (enclose), R→L Crossing (touch) |
| Highlight style | **Blue** (bold edges + translucent face fill) + **lighter blue hover** pre-highlight |
| Selection ownership | **Shared object** owned by `MainWindow`, renderer-driven highlight (Approach A) |

## 4. Architecture decisions

### D1 — Shared `Selection` object (the keystone choice)
Selection is **shared interaction state**, owned by `MainWindow`, **not** tool-local and **not** part of the `Scene` geometry model. It is:
- Constructed by `MainWindow` and added to the `ToolContext` (new field `selection`) so every tool can read/mutate it.
- Passed to the `SceneRenderer` so it can draw a **persistent highlight pass** independent of which tool is active (select with the Select tool → switch to Move in M4c → selection + highlight still there).

**Rejected B** (SelectTool owns it): selection vanishes on tool switch; M4c would have to relocate it — rework. **Rejected C** (Scene owns it): conflates view state with geometry; scene undo/redo must not touch selection.

### D2 — `Selection` API (`python/pluton/selection.py`, pure, no Qt)
```
class Selection:
    edges: set[int]
    faces: set[int]
    def replace(self, *, edges=(), faces=()) -> None      # clear then set
    def add(self, *, edges=(), faces=()) -> None
    def toggle_edge(self, e_id: int) -> None               # add if absent, remove if present
    def toggle_face(self, f_id: int) -> None
    def clear(self) -> None
    def contains_edge(self, e_id: int) -> bool
    def contains_face(self, f_id: int) -> bool
    def is_empty(self) -> bool
    def counts(self) -> tuple[int, int]                    # (n_edges, n_faces)
    @property
    def version(self) -> int                               # bumped on every mutation
```
`version` lets the renderer cheaply detect "selection changed since last upload" (mirrors `scene.dirty`). Mutators raise nothing for unknown ids — they store ids verbatim; the renderer/consumers skip ids that are no longer live (defensive against post-undo staleness, D9).

### D3 — Picking & box-select (`python/pluton/viewport/picking.py`)
Selection picking is **independent of the drawing-snap precedence** (drawing wants vertex/midpoint; selection wants edge/face). Two pure-ish functions (camera + scene in, ids out):

```
def pick_selectable(cursor_screen, viewport_size, camera, scene) -> tuple[str, int] | None
    # ("edge", id) if any live edge projects within PICK_PIXEL_TOLERANCE (8 px) of the cursor
    #   (nearest such edge by screen distance); else ("face", id) from ray_pick_face; else None.
    # Edge-priority: thin targets are harder to hit, so they win over the face behind them.

def entities_in_box(rect_px, mode, viewport_size, camera, scene) -> tuple[set[int], set[int]]
    # rect_px = (x_min, y_min, x_max, y_max); mode in {"window", "crossing"}.
```
- **Reuse:** edge screen-distance uses `camera.world_to_screen` + the segment-ray closest point; `pick_selectable`'s face fallback uses `scene.ray_pick_face`. The pure helper `closest_point_on_segment_to_ray` is **promoted from `snap_engine` into a new `python/pluton/geometry/ray.py`** and imported by both `snap_engine` and `picking` (small DRY refactor of code we're touching).
- **Window predicate** (enclose): an **edge** qualifies iff **both** endpoints project inside `rect_px`; a **face** iff **all** boundary-loop vertices project inside.
- **Crossing predicate** (touch): an **edge** iff either endpoint inside `rect_px` **or** the projected segment intersects any rect side; a **face** iff any boundary vertex inside **or** any boundary edge's projected segment intersects a rect side.
- Vertices whose `world_to_screen` returns `None` (at/behind camera) are skipped; an edge/face with any unprojectable vertex fails the all-inside window test and is tested only on its projectable parts for crossing.

### D4 — `SelectTool` (`python/pluton/tools/select_tool.py`, `Spacebar`)
State: `IDLE` (button up; hovering) and `PRESSED` (button down; possibly dragging a box). Fields: `_hovered: tuple[str,int]|None`, `_press_px`, `_is_box: bool`, `_box_rect`, `_box_dir`.
- `on_mouse_move(event, snap)`: if button up → `pick_selectable` → set `_hovered` (drives the hover overlay). If `PRESSED` and the cursor has moved past `DRAG_THRESHOLD_PX` (4 px) → `_is_box = True`, update `_box_rect` from `_press_px`→cursor and `_box_dir` from sign of `(cursor.x − press.x)`.
- `on_mouse_press(event, snap)`: record `_press_px`; `_is_box = False`; `PRESSED`.
- `on_mouse_release(event, snap)`:
  - **click** (`not _is_box`): `hit = pick_selectable(...)`. Shift held → if hit: `toggle_*`; else no-op. No Shift → if hit: `replace({hit})`; else `clear()`.
  - **box** (`_is_box`): `edges, faces = entities_in_box(_box_rect, "window" if dir≥0 else "crossing", ...)`. Shift → `add`; no Shift → `replace`.
  - reset to `IDLE`.
- `on_key_press`: `Esc` → `selection.clear()` (does not deactivate the tool).
- `overlay()`: hover → `rubber_band_segments` = hovered edge's segment (light-blue) **or** `face_fill_polygons` = hovered face loop (light-blue); box-drag → `box_rect` (D6). Mutually exclusive in time.
- Reads modifier state from the `QMouseEvent` (`event.modifiers() & ShiftModifier`).

### D5 — `on_mouse_release` routing (`Tool` ABC + `viewport_widget`)
Add `def on_mouse_release(self, event, snap) -> None` to the `Tool` ABC (default no-op). In `viewport_widget.mouseReleaseEvent`, forward **LeftButton** release to the active tool (compute the snap as for press), then `update()` + status refresh — mirroring the existing press/move forwarding. (Middle-button camera handling stays as-is.) Existing tools inherit the no-op, so nothing regresses.

### D6 — Highlight rendering (`scene_renderer`)
Two layers:
1. **Persistent selection pass** (reads the shared `Selection`, drawn every frame regardless of active tool):
   - **Selected faces** → blue ghost-fill: build each selected face's world loop (`scene.face_loop` → positions), feed the **existing** `ghost_fill` earcut path with `_SELECTION_FILL_COLOR` (blue, ~25% alpha). Rebuilt when `selection.version` or `scene` changes.
   - **Selected edges** → bold blue lines: gather selected edges' endpoint segments, draw with the line shader at a wider width in `_SELECTION_EDGE_COLOR`. Ids no longer live are skipped.
2. **Transient overlay** (from the active tool's `ToolOverlay`, existing paths): hover pre-highlight (light-blue edge segment / face fill) and the **box-select rectangle**.

**New `ToolOverlay` field** `box_rect: BoxRect | None` where `BoxRect = (x_min, y_min, x_max, y_max, dashed: bool)` in **screen pixels**. The renderer draws it as a 2-D screen-space outline (corners → NDC), solid for Window / dashed for Crossing, in the mode color (blue/green). This is the one genuinely new render capability (a screen-space rect); everything else reuses existing passes.

### D7 — `EraserTool` (`python/pluton/tools/erase_tool.py`, `E`)
Hover/drag erasing of **edges**, with cascade.
- `on_mouse_move` (button up): `pick_selectable` but **edges only** (ignore the face fallback — the Eraser targets edges); set `_hovered_edge`. Overlay pre-highlights the edge **and its incident faces** in a delete-tint (`_ERASE_HOVER_COLOR`, light red) so the user sees the full cascade.
- `on_mouse_press`: start a stroke — create an empty `CompositeCommand("Erase")`, erase the edge under the cursor into it.
- `on_mouse_move` (button down): erase each newly-hovered edge into the same composite (drag-erase).
- `on_mouse_release`: if the composite has children, `command_stack.push_executed(composite)`; reset.
- **Erase-one-edge** = remove its incident face(s) first (`RemoveFaceCommand` for each non-`None` side of `edge_faces`), then `RemoveEdgeCommand` — appended to the stroke composite in that order, executed immediately (`.do`). One Ctrl+Z undoes the whole stroke (faces + edges restored in reverse).
- Skips edges already erased in this stroke (track erased edge ids) so the drag doesn't double-remove.

### D8 — Delete / Backspace on the selection (`main_window`)
`QShortcut(Delete)` and `QShortcut(Backspace)` → `_on_delete_selection`:
- Build one `CompositeCommand("Delete Selection")`.
- For each selected **edge**: cascade (incident faces then the edge), **de-duplicating** face ids already scheduled.
- For each selected **face** not already removed by a cascade: `RemoveFaceCommand` (its edges remain — open boundary, as in SketchUp).
- Execute children as built, `push_executed`, then `selection.clear()` + repaint.
- No-op when the selection is empty.

### D9 — Selection vs. undo
The `Selection` is **transient** — selecting/deselecting is **never** pushed to the command stack; only deletions are. After an **undo** that restores deleted geometry, the selection is left **cleared** (the just-restored ids exist but are not re-selected) — the simplest rule, avoiding stale highlights pointing at ids whose liveness changed. `MainWindow`'s undo/redo slots call `selection.clear()` before repainting. *(Re-selecting restored geometry on undo is a possible future nicety; deliberately out of scope.)*

### D10 — Shortcuts
`Spacebar` → Select; `E` → Eraser; `Delete` and `Backspace` → delete selection. These align with SketchUp (Select = Spacebar, Eraser = E) and keep `S`/`M`/`Q` free for M4c (Scale/Move/Rotate). `Spacebar`/`E` are unused today.

### D11 — Status-bar selection count
Extend `StatusBar` with a `set_selection(text)` slot (e.g. `"3 edges, 1 face"` / `""` when empty), shown as an extra segment. `MainWindow` refreshes it whenever the selection changes (after press/release/delete/undo). Pluralization handled simply ("1 edge" vs "2 edges").

## 5. Data flow

- **Hover:** `viewport_widget` move → `SelectTool.on_mouse_move` → `pick_selectable` → `_hovered` → `overlay()` emits the light-blue pre-highlight → renderer draws it.
- **Click-select:** press records the pixel; release with no drag → `pick_selectable` → `Selection.replace/toggle/clear` → `selection.version` bumps → renderer's persistent pass redraws the highlight; status bar updates.
- **Box-select:** press → drag past threshold sets `_is_box` + `box_rect` (overlay draws the solid/dashed screen rect) → release → `entities_in_box(rect, mode)` → `Selection.replace/add`.
- **Erase:** press → stroke composite; press/drag erase edges (faces-then-edge) into it; release → `push_executed`. Scene goes dirty; renderer re-uploads.
- **Delete:** `MainWindow._on_delete_selection` builds the cascade+dedup composite → `push_executed` → `selection.clear()` → repaint.

## 6. Error handling & edge cases
- **Click on empty space** (no edge within tolerance, no face hit) → `clear()` (plain) or no-op (Shift).
- **Tiny drag** below `DRAG_THRESHOLD_PX` → treated as a click, not a box.
- **Stale selection ids** (geometry removed/restored): the renderer and delete path **skip ids that are not live** (`edge_is_live`/`face_is_live`); D9 clears the selection after undo to avoid this in practice.
- **Erase / delete order:** incident faces are always removed **before** their edge — never leave the half-edge mesh referencing a dead edge. De-dup prevents removing the same face twice (selected face + a selected/cascaded bounding edge).
- **Delete a face only** (selection has a face, none of its edges): the face is removed, its edges remain (valid open boundary).
- **Box with zero area** (press-release without crossing the threshold) → click path.
- **Behind-camera vertices** in box tests → unprojectable points skipped (D3).
- **Empty selection** + Delete → no-op (nothing pushed).

## 7. Testing strategy (TDD, mirrors M4a rigor)
- **`Selection`** — pure unit tests: replace/add/toggle/clear/contains/counts/`is_empty`; `version` bumps on mutation.
- **`picking`** — synthetic-camera unit tests: nearest-edge pick within/over tolerance; edge-vs-face priority (edge in front wins, edge just out of tolerance falls through to face); **window** predicate (fully-enclosed selected, straddling rejected, outside rejected); **crossing** predicate (straddling selected, outside rejected); behind-camera vertex skipped.
- **`SelectTool`** (pytest-qt, fake snaps + synthetic camera, simulated press/move/release with modifiers): click replaces; Shift-click toggles (add then remove); empty click clears; Shift+empty no-op; box L→R selects only enclosed; box R→L selects touched; Esc clears. Assert `Selection.edges`/`faces`.
- **`EraserTool`** — erase an edge cascades its faces; one composite per stroke; atomic undo/redo restores edge **and** faces with identical ids; drag-erase of multiple edges = one undo.
- **Delete path** — mixed edge+face selection: cascade + de-dup (a face shared by a selected edge isn't double-removed); face-only delete leaves edges; full undo/redo round-trip; empty selection no-op; selection cleared after delete and after undo.
- **Renderer** — selection-highlight pass emits the expected selected-face fill polygons + selected-edge segment count for a given `Selection`; `box_rect` produces the expected screen outline.
- **Regression** — all existing M2/M3/M4a tool, snap, and renderer tests stay green; the `snap_engine` refactor (promoting `closest_point_on_segment_to_ray`) keeps every snap test passing; `on_mouse_release` addition doesn't disturb existing tools.
- **Manual visual verification** — hover pre-highlight; click / Shift-extend; window vs crossing box; erase-drag a few edges (faces vanish) with one undo; Delete a mixed selection; Esc clears; selection survives a tool switch (Select → Line → back).

## 8. Out of scope / carry-over issues
- **Vertex selection** — file an issue.
- **Double-click (face + bounding edges) / triple-click (connected geometry)** smart-select — file an issue.
- **Select by material/tag, invert, grow/shrink** — file an issue.
- **Eraser modifiers** (soften / hide instead of delete) — needs M5's softening/hidden-geometry concept; file an issue.
- **Re-select restored geometry on undo** (vs. D9's clear) — note in the issue tracker if desired.

## 9. Files touched (summary)
| File | Change |
|------|--------|
| `python/pluton/selection.py` | **new** — `Selection` |
| `python/pluton/geometry/ray.py` (+ `__init__.py` export) | **new** — `closest_point_on_segment_to_ray` (promoted from `snap_engine`) |
| `python/pluton/viewport/snap_engine.py` | refactor to import the promoted helper (behavior unchanged) |
| `python/pluton/viewport/picking.py` | **new** — `pick_selectable`, `entities_in_box`, predicates |
| `python/pluton/tools/select_tool.py` | **new** — `SelectTool` (`Spacebar`) |
| `python/pluton/tools/erase_tool.py` | **new** — `EraserTool` (`E`) |
| `python/pluton/tools/tool.py` | + `on_mouse_release` (default no-op); + `ToolOverlay.box_rect` |
| `python/pluton/viewport/viewport_widget.py` | forward LMB release to the active tool |
| `python/pluton/viewport/scene_renderer.py` | persistent selection-highlight pass + screen-space box-rect draw |
| `python/pluton/tools/__init__.py` | export `SelectTool`, `EraserTool` |
| `python/pluton/ui/main_window.py` | own `Selection`; register tools; Spacebar/`E`/Delete/Backspace; pass selection to context + renderer; clear-on-undo; status count |
| `python/pluton/ui/status_bar.py` | + `set_selection` segment |
| `tests/...` | per §7 |
| `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` | **release task only** — bump 0.1.0 → **0.1.1** |
| `docs/2026-05-16-pluton-design.md` | **release task only** — annotate M4b shipped |

No C++ source, binding, or kernel changes — M4b is pure Python over existing primitives (the renderer additions are GL/Python in `scene_renderer.py`).

---

*End of M4b design.*

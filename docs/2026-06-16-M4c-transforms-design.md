# M4c — Move / Rotate / Scale Transforms — Design Spec

- **Milestone:** M4c (third sub-milestone of M4, Phase 2 "Modeling App")
- **Depends on:** M4b selection subsystem (`Selection`, picking, renderer highlight pass), M3d snap engine + axis-lock, M3a command-pattern undo/redo.
- **Target release:** v0.1.2 (single release — Move + Rotate + Scale together).
- **Date:** 2026-06-16

---

## 1. Overview & Goals

Add the three core SketchUp transform tools, all operating on the M4b selection:

- **Move (M)** — point-to-point translation, reusing the snap engine + axis-lock. No gizmo.
- **Rotate (Q)** — a **full auto-tilt protractor**: places onto the plane of the face under the cursor (ground plane otherwise); center → start direction → swept angle.
- **Scale (S)** — a **full bounding-box gizmo**: corner (uniform) / edge (2-axis) / face (1-axis) grips on the selection's axis-aligned bounding box; anchor is the opposite grip.

All three reduce to one spine: **selection → vertex set → new positions → `set_vertex_position` → recompute incident face normals**, with undo restoring the old positions. The single new kernel primitive (`set_vertex_position`) is the only C++ change and is fully exercised by Move.

**Why this milestone is shaped this way:** M4c is the first M4 sub-milestone touching C++. The risk is concentrated in the kernel mutation (dedup-index upkeep + cached-normal recompute). Move exercises that primitive end-to-end; Rotate and Scale then reuse the proven op and add only Python-side interaction + gizmo rendering.

## 2. Non-goals / Deferrals

- **Numeric / typed entry (VCB):** typing an exact distance, angle, or scale factor is **deferred to M4d** (the VCB milestone), consistent with M4a/M4b. M4c is mouse + snap only.
- **Copy-move (Ctrl-drag = duplicate):** needs geometry cloning (new vertex/edge/face IDs); pairs better with Groups/Components (M4e). **Carry-over.**
- **Auto-fold of non-planar faces:** moving a *subset* of a face's vertices off-plane is allowed but produces an approximate normal + stale triangulation (see §6). SketchUp-style auto-fold (splitting the face) is **out of scope.** Whole-face transforms stay planar.
- **Scale mirror (dragging a grip past the anchor → negative factor):** clamped to a small positive epsilon in v1; mirroring is a **carry-over.**
- **Auto-grab (transform the hovered entity when nothing is selected):** v1 requires a non-empty selection. **Carry-over.**
- **C++ batch transform / matrix op:** transform math stays in Python. Pushing it to C++ is premature (perf is M10). YAGNI.

## 3. Key decisions

| Decision | Choice |
|---|---|
| Scope | All three tools in one release (v0.1.2). |
| Rotate fidelity | Full auto-tilt protractor (orients to the hovered face's plane), arrow-key axis-lock override. |
| Scale fidelity | Full handle set: corner = uniform, edge = 2-axis, face = 1-axis. |
| Command structure | One generic `TransformVerticesCommand` storing `{vertex_id: (old_pos, new_pos)}`; tools resolve positions. |
| Operates on | The current non-empty M4b selection; empty selection → no-op + status hint. |
| Transform math | Pure-Python `transforms.py` (translate / rotate / scale), Qt/GL-free, unit-tested. |
| Precise entry | Deferred to M4d. |

## 4. Architecture

### 4.1 Kernel change (C++) — `HalfEdgeMesh::set_vertex_position`

```cpp
void set_vertex_position(std::uint32_t v_id, float x, float y, float z);
```

Behaviour:

1. Validate: throw `std::out_of_range` if `v_id` is out of range or not alive (mirrors `vertex_position`).
2. Collapse negative zero (`if (x == 0.0f) x = 0.0f;` for x/y/z), matching `add_vertex` / `restore_vertex`.
3. **Dedup index upkeep:** erase `position_index_[pack_position(old_pos)]`, write the new position into `vertices_[v_id].pos`, then `position_index_[pack_position(x,y,z)] = v_id`. On a coincident-position collision the map is **last-writer-wins** — a rare degenerate, never a crash (only affects future `add_vertex` idempotency).
4. **Recompute cached normals:** for every face incident to `v_id`, recompute and store `faces_[f].normal`. Incident faces are found by scanning live half-edges with `origin == v_id` and a live face (the same scan pattern `remove_vertex` uses), collecting distinct `he.face != INVALID_ID`. Extract a private helper `recompute_face_normal(f_id)` that writes `faces_[f_id].normal` using the existing `compute_face_normal_geometric` math; reuse it here (and optionally refactor `add_face_from_loop` / `restore_face` to call it).
5. Set `dirty_ = true`.

**Not done here:** no re-triangulation (triangulation indices are topological and remain valid under affine transforms); no topology change; no merge when two vertices coincide.

GoogleTests (`cpp/tests/test_halfedge.cpp`): position updates; `position_index_` no longer resolves the old packed position and resolves the new one (verify via `add_vertex` idempotency at the new spot returning `v_id`); incident face normals flip/track after moving a vertex; moving a vertex on a multi-face fan updates all incident faces; throws on dead/out-of-range id.

### 4.2 nanobind binding + Scene wrapper

- `cpp/bindings/module.cpp`: expose `set_vertex_position`.
- `Scene.set_vertex_position(v_id: int, position: np.ndarray) -> None` — float32 (3,) coercion like `add_vertex`; translate `IndexError → KeyError` like the other mutators. Smoke pytest.

### 4.3 Transform math — `python/pluton/geometry/transforms.py`

Pure functions on `(N, 3) float32` arrays, no Qt/GL:

- `translate(points, delta) -> points'`
- `rotate(points, center, axis, angle_rad) -> points'` — Rodrigues' rotation about the line `(center, axis)`; `axis` need not be unit (normalize internally; raise on near-zero axis).
- `scale(points, anchor, factors) -> points'` — per-axis `anchor + factors * (points - anchor)`; `factors` is a 3-vector.

Unit-tested directly (identity cases, known rotations e.g. 90° about Z, axis offset from origin, anisotropic scale, factor=1 no-op).

### 4.4 Selection → vertex set

Helper (in `transforms.py` or a small `selection_geometry` module): given a `Selection` + `Scene`, return the **ordered unique** list of vertex IDs to transform = union of:
- both endpoints of every selected edge (`scene.edge(e).v1_id / v2_id`), and
- every loop vertex of every selected face (`scene.face_loop(f)`).

Because shared vertices are moved once, adjacent unselected geometry **rubber-bands** along automatically — the desired SketchUp behaviour.

### 4.5 `TransformVerticesCommand` — `python/pluton/commands/scene_commands.py`

```
TransformVerticesCommand(scene, moves: dict[int, tuple[old_xyz, new_xyz]])
```

- `do`: for each `vid`, `scene.set_vertex_position(vid, new_xyz)`.
- `undo`: for each `vid`, `scene.set_vertex_position(vid, old_xyz)`.
- ID-preserving and topology-stable — both directions are just position writes (no tombstone/restore needed). Normal recompute happens inside the kernel op on both paths.
- Skips no-op moves (old == new) at construction; if `moves` is empty the tools do not push a command.

pytests: round-trip do/undo/redo restores exact positions; selection IDs unchanged; a translate then undo leaves the mesh bit-identical.

### 4.6 The three tools (`python/pluton/tools/`)

All follow the existing `Tool` ABC (`activate/deactivate`, `on_mouse_press/move/release`, `on_key_press`, `overlay()`, `has_active_gesture`, `status_text`). All require a **non-empty selection** at gesture start; otherwise the press is a no-op and `status_text` prompts "Select geometry first." Esc / `deactivate` mid-gesture rolls back any partial state and pushes **nothing** (mirrors the M4b Eraser fix). Selection persists across a committed transform (topology is unchanged, IDs stable).

**MoveTool (M)** — point-to-point:
- Press: snapped **grab point** (any snap kind from the M3d engine — need not lie on the selection).
- Move (button held): snapped **destination**; `delta = dest − grab`; arrow-key axis-lock constrains `delta` to X/Y/Z (reuses M3d axis-lock). Live overlay shows the ghosted result (preview positions) + the drag vector.
- Release: build `moves` from the selection vertex set translated by `delta`; push one `TransformVerticesCommand` named "Move".
- No gizmo overlay beyond the snap markers + drag vector + ghost preview.

**RotateTool (Q)** — full auto-tilt protractor, 3 clicks:
1. **Center** click: snapped point. The protractor **plane** = the plane of the face under the cursor (normal = `scene.face_normal`, through the snapped center) if hovering a face, else the ground plane (normal = +Z). Arrow keys override the rotation axis to world X/Y/Z.
2. **Start** click: defines the 0° reference direction (projected into the plane).
3. **Angle** click (or move + click): the current direction defines the swept angle; **snap to 15° increments** (matches SketchUp's default angle snapping; arbitrary angles arrive via typed entry in M4d). Commit `TransformVerticesCommand` named "Rotate" using `rotate(points, center, axis, angle)`.
- Overlay: translucent protractor disk on the plane, outline, the start radius, the current radius, and an angle wedge/arc with the degree readout in `status_text`.
- Esc steps back (angle → start → center) or cancels.

**ScaleTool (S)** — full bounding-box gizmo:
- On activate with a selection, compute the selection's **world-axis-aligned bounding box** (AABB) over the vertex set. Render the box + grips: 8 corners, 12 edge-midpoints, 6 face-centers. Degenerate axes (flat selection) collapse coincident grips → the planar handle set is what remains.
- Press on a grip starts a drag; the **anchor** is the opposite grip (corner↔corner, edge↔edge, face↔face). Modifiers: **Ctrl = scale about the AABB center** (anchor → center); **Shift = uniform** (lock all dragged axes to one factor) on edge/face grips.
- Drag computes the scale `factors` (3-vector; 1.0 on axes the grip doesn't drive): corner = all non-degenerate axes share one uniform factor; edge = two axes; face = one axis. Factor = ratio of current vs. original signed extent from the anchor along each driven axis; clamp each factor to a small positive epsilon (no mirror in v1).
- Release: `scale(points, anchor, factors)` → `TransformVerticesCommand` named "Scale". `status_text` shows the live factor(s).
- Overlay: AABB edges (world segments), grip squares (screen-space markers, active grip highlighted), live-scaled ghost preview.

Register all three in `main_window.py` (`_tool_manager.register(...)`) with QShortcuts **M / Q / S** (confirmed free). Move/Rotate reuse the existing axis-lock arrow-key path (`_on_tool_key` / `on_key_press`); wiring Left/Right arrows if not already present is tracked under issue #41.

### 4.7 Gizmo rendering (`scene_renderer.py` + `tool.py`)

Extend the M4b overlay pass with **generic primitives** so the renderer stays ignorant of tool specifics. Add to `ToolOverlay` (frozen+slots):
- `fill_polygons` — list of `(Nx3 world points, rgba)` translucent fills (protractor disk; reuses `draw_face_fill_overlays`).
- `world_polylines` — list of `(Nx3 world points, rgb, closed?)` drawn via the existing `_draw_world_segments` (protractor outline, radii, angle arc, AABB edges, ghost preview wireframe).
- `screen_markers` — list of `(world point, size_px, rgb, filled?)` projected via `Camera.world_to_screen` and drawn as screen-space squares (scale grips), reusing the M4b screen-space rect machinery.

The renderer draws these in the existing tool-overlay step, depth-aware where appropriate, restoring all GL state (line width, blend) afterwards — the M4b line-width-leak lesson. Tools build these primitives in their `overlay()` methods; no tool-specific structs enter the renderer.

## 5. Interaction summary (per tool)

| | Gesture | Reference | Result |
|---|---|---|---|
| Move | press-drag-release | grab point → destination (snapped), axis-lockable | translate selection by delta |
| Rotate | 3 clicks | center (plane from hovered face) → start dir → angle (15° snap) | rotate selection about plane axis |
| Scale | grip press-drag-release | opposite grip anchor (Ctrl=center) | scale selection by per-axis factors |

## 6. Edge cases & invariants

- **Empty selection:** all three are no-ops; `status_text` prompts to select first.
- **Degenerate axis:** Rotate with a near-zero axis raises in `transforms.rotate` (guarded); Scale collapses coincident grips on flat selections.
- **Non-planar result:** moving a subset of a face's vertices off-plane is allowed. The cached normal is recomputed from the first three loop vertices (approximate for non-planar faces) and the existing triangulation is kept. Whole-face Move/Rotate/Scale preserve planarity, so this only affects partial-face vertex edits. Documented limitation; auto-fold is a carry-over.
- **Coincident vertices after a move:** allowed; no topological merge. `position_index_` is last-writer-wins (affects only future `add_vertex` idempotency at that exact spot).
- **Undo/redo:** exact position restoration; selection currently cleared on undo/redo by the M4b CommandStack listener (consistent existing behaviour; preserving selection across transform-undo is a carry-over refinement).
- **Mid-gesture deactivate / Esc:** rolls back any preview-only state and pushes no command (no un-undoable mutation).

## 7. Testing strategy

- **C++ (GoogleTest):** `set_vertex_position` — position update, dedup-index old/new resolution, single- and multi-face normal recompute, throw on dead/out-of-range.
- **Python unit (no Qt/GL):** `transforms.py` translate/rotate/scale numerics; selection→vertex-set union (edges + faces, dedup, rubber-band sharing); `TransformVerticesCommand` do/undo/redo round-trip + empty-moves guard; AABB + grip/anchor geometry; scale-factor math (corner/edge/face, Ctrl-center, Shift-uniform, epsilon clamp); rotate angle 15° snap.
- **Tool tests (pytest-qt where needed):** Move delta + axis-lock; Rotate 3-click flow + plane-from-face vs. ground; Scale grip→anchor selection + factor; Esc/deactivate rollback for each; no-op on empty selection.
- **Regression:** existing 336 pytest + 72 C++ stay green; selection highlight + box-select + Eraser unaffected; renderer GL state restored (no leaks).

## 8. Acceptance criteria

1. New `set_vertex_position` kernel op + binding + `Scene` wrapper, with the cached-normal recompute and dedup-index upkeep, all tested.
2. Move, Rotate, Scale registered on M / Q / S, each operating on the M4b selection.
3. Move: snapped point-to-point with arrow-key axis-lock; one undoable command per drag.
4. Rotate: protractor that orients to the hovered face's plane (ground otherwise), 15° angle snap, axis-lock override; one undoable command.
5. Scale: full corner/edge/face handle set on the selection AABB, opposite-grip anchor, Ctrl-center, Shift-uniform; one undoable command.
6. Gizmos render via the generic overlay primitives; GL state restored; no regression to M4b visuals.
7. Undo/redo restores exact positions; mid-gesture Esc/deactivate leaves the scene and undo stack clean.
8. Full suite green on Windows + Linux CI; manual visual verification passes.

## 9. Carry-over issues (file at release)

- Copy-move (Ctrl-drag duplicate) — needs geometry cloning; revisit with M4e.
- Auto-fold of non-planar faces on partial-vertex moves.
- Scale mirror (negative factor past the anchor).
- Auto-grab transform of the hovered entity when nothing is selected.
- Preserve selection across transform undo/redo (vs. the M4b clear-on-undo default).
- Typed numeric entry for distance/angle/factor — folds into M4d's VCB.

## 10. Risks

- **Kernel mutation correctness** (dedup index + normal recompute) is the main risk; isolated, fully unit-tested, and exercised by Move first.
- **Protractor plane inference + tilted-disk rendering** is the most novel rendering work; mitigated by the generic-primitive overlay (a segmented world-space circle, not a new shader).
- **Scale grip picking** (26 handles) — screen-space nearest-grip pick within a pixel tolerance, reusing M4b picking patterns.

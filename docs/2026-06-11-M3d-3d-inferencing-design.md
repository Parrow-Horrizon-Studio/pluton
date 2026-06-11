# M3d — 3D Inferencing (Tier 2: perception + edge-split)

- **Date:** 2026-06-11
- **Status:** Approved (design)
- **Milestone:** M3d (closes the M3 "Push/Pull" arc: M3a topology → M3b basic push/pull → M3c closed-manifold merge → **M3d inferencing**)
- **Predecessor spec:** `docs/2026-06-10-M3c-closed-manifold-push-pull-design.md`

---

## 1. Context & motivation

M2 shipped a `SnapEngine` with four inference kinds — Grid, Axis-lock, Midpoint, Endpoint — but it evaluates them **only on the ground plane (Z=0)**. The engine's input is a single `cursor_world_on_ground` point produced by `Camera.ray_intersect_ground`, and every test (endpoint/midpoint/axis/grid) runs against that 2D point.

After M3b/M3c, the scene contains real 3D geometry floating above the ground — pushed boxes with top faces, vertical edges, and vertices at non-zero Z. The current engine is blind to all of it: you cannot snap to the top corner of a box, the midpoint of a vertical edge, or a point on a slanted face. The master design lists M3d as *"first version of inferencing — snap to edges, midpoints, intersections."* This milestone lifts inferencing into 3D and adds the visual affordances that make it usable.

A second, subtler requirement falls out of "snap to edges/midpoints": snapping a new vertex onto a point **interior to an existing edge** (a midpoint, an on-edge point, an axis×edge intersection) creates a **T-junction** unless the host edge is split. T-junctions are invalid CAD topology. So delivering *usable* edge/midpoint snapping requires a topology operation — `split_edge` — not just detection. This is the "Tier 2" scope confirmed during brainstorming.

## 2. Goals / Non-goals

**Goals**
- Inference engine evaluates **3D geometry via raycasting**, using **screen-space proximity** (constant pixel feel at any zoom).
- Five point inferences detected and rendered with distinct glyph+color: **Endpoint, Midpoint, On-Edge, On-Face, Intersection**.
- **3D axis-lock**, now including the blue/Z (vertical) axis that never fired in M2's ground-only world.
- `split_edge` kernel op so Midpoint / On-Edge / Intersection snaps produce **clean, manifold topology** when drawn to.
- Line and Rectangle tools consume 3D snaps for their endpoints, splitting edges as needed.

**Non-goals (this milestone)**
- **Face-split** (drawing onto a face interior splits the face) — Tier 3, deferred. On-Face snap is *reference-only* in v1.
- **Parallel / perpendicular "from point" linear inferences** (the magenta guide lines) — deferred.
- **Spatial acceleration** for snap candidates — per-mouse-move linear scan is acceptable at M3d model sizes; BVH/indexing is M10.
- **Combined inferences** (point + axis simultaneously, e.g. "on red axis AND on edge") — v1 picks a single highest-precedence result.

## 3. Inference set & precedence

Precedence, highest → lowest. The engine collects all candidates within tolerance, then returns the single highest-precedence one; ties within a kind break by **nearest depth** (closest to camera).

| Kind | Glyph | Color | Fires when |
|------|-------|-------|-----------|
| **Endpoint** | square | green | cursor within 8 px of a vertex |
| **Intersection** | X | magenta | (drawing only) an axis line from the anchor crosses an edge near the cursor |
| **Midpoint** | triangle | cyan | cursor within 8 px of an edge's midpoint |
| **On-Edge** | diamond | red | cursor over an edge → nearest point on the 3D segment |
| **On-Face** | square (blue) | blue | cursor ray hits a face surface |
| **Axis-lock** | colored line | R/G/B | (drawing only) draw direction aligns to X/Y/Z within 5° |
| **Grid** | square | grey | ground-plane fallback when the ray hits nothing |

Rationale for ordering: Endpoint is the most specific (an exact existing vertex). Intersection and Midpoint are precise constructed points and outrank the continuous On-Edge / On-Face snaps. On-Edge (1D) outranks On-Face (2D). Axis-lock and Grid are last as directional/fallback hints. Endpoint and On-Face share the square glyph but never confuse in practice (Endpoint wins whenever near a vertex) and are color-separated (green vs blue).

## 4. Architecture decisions

### D1 — Screen-space proximity, not world-space distance
Candidates are projected to pixels via `world_to_screen` and thresholded at a constant `PIXEL_TOLERANCE = 8`. This keeps "snap feel" constant regardless of zoom. (M2's `snap_engine` carries a TODO acknowledging its fixed `0.2 m` world tolerance is a zoom-dependent hack; this decision retires that hack.) **Rejected alternative:** world-space ray-distance thresholds — tolerance feel drifts with zoom and camera distance.

### D2 — `Camera.world_to_screen(world_xyz, width, height) -> (sx, sy, depth) | None`
The new primitive everything leans on. Math is the exact inverse of `ray_from_screen`:
- `clip = projection_matrix() @ (view_matrix() @ [x,y,z,1])`
- If `clip.w <= 0` (point at or behind the camera) → return `None`.
- NDC = `clip.xyz / clip.w`; `sx = (ndc.x + 1)/2 * width`, `sy = (1 - ndc.y)/2 * height` (screen-y top-down, matching `ray_from_screen`).
- `depth` = camera-space `-z` (or `clip.w`), a positive monotonic distance used for tie-breaking. Larger = farther.

Pure function of camera state → fully unit-testable with synthetic cameras (round-trip against `ray_from_screen`).

### D3 — Ray-based `SnapEngine.snap()` signature
```
snap(ray_origin, ray_direction,         # NEW: full cursor ray (camera.ray_from_screen)
     cursor_world_on_ground,            # kept: grid + ground-fallback
     cursor_screen, camera, scene,
     anchor=None) -> SnapResult
```
`viewport_widget._snap_for_event` computes the ray with `camera.ray_from_screen` (in addition to the existing ground hit) and passes both. Tools are unaffected at the call site — they still read `snap.world_position` (and `snap.vertex_id` for endpoint reuse).

### D4 — Internal candidate model + selection
Each generator yields zero or more `_Candidate(kind, world_position, screen_dist_px, depth, vertex_id?, edge_id?, face_id?, axis?, edge_t?)`. The engine filters to `screen_dist_px <= PIXEL_TOLERANCE`, sorts by `(precedence desc, depth asc)`, and returns the winner as a `SnapResult`. Precedence is an explicit ordered list (decoupled from the enum's integer value, so future kinds slot in without renumbering). Empty → falls back to Grid (ground) or `NONE`.

### D5 — On-Face via existing `ray_pick_face`
Reuses `scene.ray_pick_face(origin, direction)` → C++ Möller-Trumbore (`ray_intersect_mesh`). The returned `RayMeshHit.point` is the On-Face snap (screen_dist 0 by construction since it lies under the cursor), `face_id` recorded, `depth` from `hit.t`. This also supplies the depth reference for "which surface am I over."

### D6 — On-Edge via ray–segment closest point
For each live edge, compute the closest point between the cursor ray and the 3D edge **segment** (clamped to the segment). Project that point with `world_to_screen`; if within tolerance it's an On-Edge candidate with `edge_t` (the parameter along the edge, needed by `split_edge`). Endpoints/midpoint of the same edge naturally win by precedence when the cursor is near them.

### D7 — Intersection = axis-line × edge (drawing-only)
Only evaluated when `anchor` is set (an active gesture). For each axis direction d ∈ {X,Y,Z} through `anchor`, and each live edge, compute the closest approach between the two 3D lines; if the approach distance is below an epsilon (the lines genuinely cross in 3D) and the crossing point projects within tolerance, emit an Intersection candidate carrying the host `edge_id` and `edge_t`. This is the single most useful intersection while drawing and reuses the axis machinery from D8. **Deferred:** free-floating edge–edge intersections (rare; ambiguous in depth).

### D8 — 3D axis-lock (incl. Z)
Generalizes M2's ground-only axis-lock. With `anchor` set, for each axis line through the anchor, project the cursor **ray** onto the axis line (line–line closest point) to get the locked world position; gate by the screen-space distance between the cursor and that projected point (≤ tolerance) rather than M2's ground-plane angle test, so it works for off-ground anchors. Z-lock (vertical) now fires because geometry exists off the ground plane.

### D9 — `split_edge` kernel op (C++)
```
std::uint32_t split_edge(std::uint32_t e_id, float t);   // 0 < t < 1
```
- Adds vertex `w` at `v1 + t*(v2 - v1)` (idempotent `add_vertex` by packed position).
- Replaces edge `e` with two collinear edges (v1–w, w–v2). Because half-edges are **implicit twin-pairs at adjacent indices** (`2e`/`2e+1`), the split cannot mutate twins in place: it **allocates two new edges (four half-edges), tombstones `e`**, and rewires `next`/`twin`/`origin`/`face` — the same id-allocation discipline `dissolve_edge` uses.
- For each face incident to `e` (either may be `INVALID_ID` on a boundary edge), inserts `w` into the face's `loop` between v1 and v2, re-fan-triangulates, and rebuilds the face.
- Returns the id of `w`. Returns `INVALID_ID` if `e` is not live or `t ∉ (0,1)`.
- Preserves manifold invariants (every interior half-edge has a valid twin; face loops are closed).

Bound through nanobind on the `HalfEdgeMesh` class chain, mirroring `dissolve_edge`.

### D10 — `SplitEdgeCommand` reversibility
Follows the **id-preserving capture/restore** pattern that fixed M3c's atomic-undo bug. `do()` captures the original edge id + endpoints and each incident face's `(id, loop, tris)` **before** splitting, and records the produced ids (`w`, two new edge ids, new face ids). `undo()`: remove the new faces, new edges, and vertex `w`, then `restore_edge(orig_id, v1, v2)` and `restore_face(orig_id, loop, tris)` for each captured face — restore the edge **before** the faces (faces reference it). Round-trip undo/redo must return identical ids and counts (verified by test, as in M3c).

### D11 — Tool consumption rules
- **Endpoint** → reuse the existing `vertex_id` (no new geometry); already how M2's line tool behaves.
- **Midpoint / On-Edge / Intersection** → the gesture's `CompositeCommand` first runs a `SplitEdgeCommand(edge_id, edge_t)` to materialize a clean vertex, then connects to it. Undo of the whole gesture unwinds the split atomically.
- **On-Face** → **reference-only in v1.** The marker renders and the point is returned, but tools do **not** place a vertex into a face interior (that needs face-split, Tier 3). A carry-over issue tracks enabling it.
- **Grid / Axis** → unchanged (place at the snapped world position).

### D12 — Renderer glyph+color table
`scene_renderer._draw_tool_overlay` currently special-cases MIDPOINT→triangle, else square. Replace with a per-kind table mapping `SnapKind → (glyph, rgb)`: square/green (Endpoint), triangle/cyan (Midpoint), diamond/red (On-Edge), square/blue (On-Face), X/magenta (Intersection), and the existing colored rubber-band for Axis-lock. Markers stay fixed-world-size GL_LINES outlines drawn with depth-test disabled (always on top), as today.

### D13 — `SnapResult` / `SnapKind` extension
Add `ON_EDGE`, `ON_FACE`, `INTERSECTION` to `SnapKind`. Add `edge_id: int | None` and `face_id: int | None` (and an internal `edge_t` carried to the command) to `SnapResult`. Existing `axis`, `vertex_id`, `world_position`, `label` retained.

## 5. Data flow

**Hover (mouse move):**
`viewport_widget._snap_for_event` → `camera.ray_from_screen` (+ `ray_intersect_ground`) → `SnapEngine.snap(...)` gathers candidates (endpoint/midpoint/on-edge via projection; on-face via `ray_pick_face`; intersection/axis if anchored) → selects winner → `SnapResult`. Tool stores `snap.world_position` + `snap.kind` in its overlay; `scene_renderer` draws the matching glyph at the 3D point. `update()` repaints.

**Commit (e.g. Line tool 2nd click on a box's edge):**
`on_mouse_press` with `snap.kind == ON_EDGE` → build `CompositeCommand`: `SplitEdgeCommand(snap.edge_id, snap.edge_t)` (yields vertex `w`) → the existing edge-creation command connecting the previous point to `w` → push to command stack. A single Ctrl+Z unwinds split + connect together. (The exact edge-creation command name is whatever the M2 line tool already uses; the plan will confirm it.)

## 6. Error handling & edge cases
- `world_to_screen` returns `None` for points at/behind the camera; such candidates are skipped (never thresholded).
- `split_edge` with `t` at/over the endpoints, or a dead edge, returns `INVALID_ID`; the command treats that as a no-op gesture (defensive — the engine should never emit On-Edge `t` outside `(0,1)`, but the kernel guards anyway).
- Degenerate edges (zero length) and degenerate-normal faces: skipped by the candidate generators (mirrors `faces_are_coplanar`'s `|n| < 1e-7` guard).
- Snapping to a midpoint/on-edge point that **coincides with an existing vertex** (idempotent `add_vertex`): `split_edge` would return that existing id; the command must detect "no new vertex created" and degrade to an Endpoint-style reuse (no dangling split). Covered by a test.
- Boundary edges (one incident face): `split_edge` handles the `INVALID_ID` outside half-edge.

## 7. Testing strategy (mirrors M3c rigor)
- **C++ GoogleTests** for `split_edge`: interior split (t=0.5) on an interior edge (manifold invariants, face vertex counts +1, twins valid); split on a boundary edge; split near-endpoint coincidence; invalid t / dead edge → `INVALID_ID`.
- **pytest** for `SplitEdgeCommand`: do/undo/redo round-trip returns identical ids + slab counts; composite-gesture atomic undo.
- **Snap-engine unit tests** with synthetic cameras: each inference kind in isolation; precedence ordering; depth tie-break; `world_to_screen` ↔ `ray_from_screen` round-trip; the off-ground (3D) cases that M2 could not reach.
- **Renderer test:** the glyph+color table maps each kind to the expected vertex count / color.
- **Regression guards:** existing M2/M3 snap and tool tests stay green (ground-plane snapping must be unchanged when geometry is on Z=0).
- **Manual visual verification task:** push a box; hover with the Line tool → correct markers at the box's vertices / edge midpoints / on-edge / on-face; draw a line vertex onto an edge → edge splits cleanly (no T-junction; box stays manifold; Ctrl+Z restores).

## 8. Out of scope / carry-over issues
- **Face-split / On-Face drawing (Tier 3)** — file an issue; needed to let tools place geometry on face interiors.
- **Parallel/perpendicular "from point" linear inferences** (magenta guides) — file an issue.
- **Free edge–edge intersection inference** — file an issue (low value until denser models).
- **Spatial index for snap candidates** — rolls into M10 performance.

## 9. Files touched (summary)
| File | Change |
|------|--------|
| `python/pluton/viewport/camera.py` | + `world_to_screen` |
| `cpp/include/pluton/halfedge.h`, `cpp/src/halfedge.cpp` | + `split_edge` |
| `cpp/bindings/module.cpp` | bind `split_edge` |
| `python/pluton/scene/scene.py` | + `split_edge` wrapper, query helpers |
| `python/pluton/commands/scene_commands.py` | + `SplitEdgeCommand` |
| `python/pluton/viewport/snap_engine.py` | ray-based `snap()`, 3D candidate generators, new kinds |
| `python/pluton/viewport/scene_renderer.py` | per-kind glyph+color table |
| `python/pluton/viewport/viewport_widget.py` | pass ray to `snap()` |
| `python/pluton/tools/line_tool.py`, `rectangle_tool.py` | consume 3D snaps; split-on-edge gesture commits |
| `tests/...` | GoogleTests + pytest per §7 |

---

*End of M3d design.*

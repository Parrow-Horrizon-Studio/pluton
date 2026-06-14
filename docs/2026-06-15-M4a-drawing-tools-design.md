# M4a — Drawing tools (Circle, Polygon, 2-Point Arc)

- **Date:** 2026-06-15
- **Status:** Approved (design)
- **Milestone:** M4a — first sub-milestone of **M4 (Modeling polish)** and the opener of **Phase 2 (Modeling App)**. M4 is split into M4a (drawing tools) → M4b (selection & eraser) → M4c (transforms) → M4d (units & measurement) → M4e (groups & components).
- **Predecessor spec:** `docs/2026-06-11-M3d-3d-inferencing-design.md`
- **Release:** completing M4a cuts **v0.1.0** — the first minor release, marking entry into the v0.1→v0.3 Phase 2 band.

---

## 1. Context & motivation

Phase 1 shipped two geometry-creation tools — **Line** (`L`) and **Rectangle** (`R`) — plus Push/Pull (`P`) and the M3d 3D inference engine. Rectangle draws only on the ground plane (Z=0); Line draws via the snap engine and can reach 3D geometry. There is no way yet to create curved or regular-polygon footprints — the staple shapes of architectural modeling (columns, pipes, arched openings, hex bolts, round tables).

M4a adds the three canonical SketchUp drawing tools — **Circle**, **Polygon**, and the **2-Point Arc** — built on the existing tool/command/snap machinery. The work is **pure Python**: it composes the half-edge primitives already exposed (`add_vertex`/`add_edge`/`add_face_from_loop`) and needs **no C++/kernel changes** (unlike the sibling M4c, which will need vertex-position mutation). That makes M4a a deliberately low-risk milestone opener.

Two cross-cutting features that SketchUp couples to these tools are **deferred by an explicit scope decision** (brainstorming):
- **Typed precise entry (the VCB / Measurements box)** — `type 5m for radius, 12s for sides`. Parsing `5m` vs `5'` requires the units system, which lives in **M4d**; the VCB lands there and retrofits to all tools at once. M4a is mouse + snap driven.
- **Face-split on draw** — in SketchUp, drawing a circle on a face cuts the face. That was deferred from M3d (issue [#27]) and stays deferred here (see D13).

## 2. Goals / Non-goals

**Goals**
- Three new tools — **Circle** (`C`), **Polygon** (`G`), **2-Point Arc** (`A`) — each a thin gesture state machine reusing the M3d `SnapEngine` for precision.
- Geometry can be drawn on the **ground plane, a ground-parallel plane through the first snapped point, or any existing face's plane** (the first click's snap decides — D4).
- Closed shapes (circle, polygon) create a **face**; the arc creates **edges only**.
- All geometry generation factored into a **pure, Qt-free `geometry/` package** (plane math + curve point generators) that is unit-tested independently and reused by later milestones (M4b/M4c transforms also need plane math).
- Each gesture commits as **one `CompositeCommand`** → atomic single-`Ctrl+Z` undo, reusing existing `AddVertex`/`AddEdge`/`AddFace` commands.

**Non-goals (this milestone)**
- **Typed numeric entry / VCB** — M4d. Radius/segment precision comes from snapping; segment counts use defaults with a keyboard nudge for polygon sides (D7).
- **3-Point Arc and Pie** gestures — fast-follow; the 2-Point Arc is the canonical `A`.
- **Circumscribed polygons** and the inscribed/circumscribed toggle — M4d (with the VCB).
- **Face-split on draw** — drawing on a face overlays a coplanar face; it does not cut the host (D13, [#27]).
- **Curve as a logical entity + smooth ("softened") shading** — circles render as faceted N-gons. Logical curves need the grouping work in M4e; smooth shading needs M5 viewport styles.
- **Arc edge-tangency** is a flagged **stretch** (D8), the first thing cut if the milestone bloats.

## 3. Tool & default summary

| Tool | Shortcut | Gesture (clicks) | Default density | Creates |
|------|----------|------------------|-----------------|---------|
| **Circle** | `C` | center → radius point | 24 segments (fixed in M4a) | N vertices + N edges + 1 face |
| **Polygon** | `G` | center → radius point | 6 sides (remembered in-session; `↑`/`↓` adjust, clamp [3, 64]) | N vertices + N edges + 1 face |
| **2-Point Arc** | `A` | start → end → bulge | 12 segments (fixed in M4a) | N+1 vertices + N edges (open) |

Shortcuts `C`/`A` match SketchUp; `G` ("polyGon") is a Pluton choice (no SketchUp default exists) and is free today. All three are revisitable in the plan.

## 4. Architecture decisions

### D1 — New pure `geometry/` package (Qt-free, numpy)
Create `python/pluton/geometry/` holding the shared math the three tools (and future transforms) lean on. No Qt, no scene mutation — pure functions over numpy arrays, so it unit-tests fast and is reusable. Two modules:
- `plane.py` — `DrawingPlane`.
- `curves.py` — circle / polygon / arc point generators.

**Rejected alternative:** self-contained per-tool math (duplicates plane + curve logic across three tools, and again for M4c transforms; harder to test). **Rejected alternative:** one generalized parametric-shape tool (YAGNI — the three gestures differ enough that unifying them tangles the state machines).

### D2 — `DrawingPlane`
An immutable orthonormal frame: `origin` (world point on the plane), unit `normal`, and an in-plane orthonormal basis `u`, `v` (with `u × v = normal`).
```
class DrawingPlane:
    origin: np.ndarray  # (3,)
    u: np.ndarray       # (3,) unit, in-plane
    v: np.ndarray       # (3,) unit, in-plane
    normal: np.ndarray  # (3,) unit

    @classmethod
    def horizontal(cls, origin) -> "DrawingPlane"        # normal +Z, u=+X, v=+Y, through origin
    @classmethod
    def from_face(cls, scene, face_id, origin) -> "DrawingPlane"  # normal = scene.face_normal(face_id)

    def to_world(self, uv: np.ndarray) -> np.ndarray     # (…,2) plane coords → (…,3) world
    def project(self, world: np.ndarray) -> np.ndarray   # (…,3) world → (…,2) plane coords (drops normal component)
```
Basis derivation from a normal `n` (used by `from_face`): pick a reference axis least parallel to `n` (`+Z` unless `|n·Z| > 0.9`, else `+X`), `u = normalize(ref × n)`, `v = n × u`. Stable, deterministic. `horizontal()` hard-codes `u=+X, v=+Y` so ground footprints keep world-axis alignment.

### D3 — Curve point generators (`curves.py`, pure 2D)
Generate vertex rings in **plane coordinates** (2D); the tool lifts them to world via `DrawingPlane.to_world`. Keeping generation 2D makes the geometry trivially testable (counts, radius, winding) without a camera or scene.
```
def circle(center_uv, radius, segments=24, start_angle=0.0) -> np.ndarray   # (segments, 2)
def polygon(center_uv, radius, sides, start_angle=0.0) -> np.ndarray        # (sides, 2), inscribed
def arc_2pt(start_uv, end_uv, bulge_uv, segments=12) -> np.ndarray          # (segments+1, 2), includes both endpoints
```
- `circle` / `polygon` are the same parametric ring; circle is just a high-`sides` polygon. **Inscribed** (vertices on the radius circle — locked decision). `start_angle` is set by the tool to the radius-point direction (D6), so the first vertex points at the cursor as in SketchUp.
- Winding is consistent (CCW in plane coords) so the resulting face normal aligns with the plane normal.
- `arc_2pt`: given chord endpoints and an in-plane `bulge_uv` point, compute the sagitta (signed perpendicular distance from the chord), solve the circular arc through both endpoints with that sagitta, and sample `segments+1` points inclusive of the endpoints. Degenerate bulge (≈ collinear) → emit the straight chord (2 points); the tool treats that as a single edge.

### D4 — Drawing-plane resolution from the first click
The first click's `SnapResult` picks the plane (consistent with the locked "ground + existing faces" scope):
- `snap.kind == ON_FACE` → `DrawingPlane.from_face(scene, snap.face_id, origin=snap.world_position)`. This is the only path to a **tilted/vertical** plane — you draw on a face by hovering its interior.
- **otherwise** (endpoint, on-edge, midpoint, intersection, axis, grid, or empty) → `DrawingPlane.horizontal(origin=snap.world_position)` — a ground-**parallel** plane through the snapped point's height. Clicking the floor draws at Z=0; clicking a box's top corner draws a horizontal shape at that corner's Z (no jarring teleport to the floor).

Arbitrary tilted planes inferred from an edge/axis with no face under the cursor are **out of scope** (the larger option we declined). Every subsequent snapped point is **projected onto the active plane** (D10), so geometry stays planar even when the user snaps the radius to off-plane geometry.

### D5 — Tool structure
Three `Tool` subclasses in `python/pluton/tools/`, each mirroring the `LineTool`/`RectangleTool` shape: a small `_State` enum (`IDLE` → `DRAWING`), `activate`/`deactivate`, `on_mouse_move(event, snap)`, `on_mouse_press(event, snap)`, `on_key_press(event)`, plus `overlay`, `anchor_or_none`, `status_text`. They read `scene`, `command_stack`, `camera`, `widget_size_provider` from the `ToolContext`. Registered with the `ToolManager` and wired to shortcuts in `main_window.py` exactly like the existing tools.

### D6 — Circle & Polygon gesture
1. **Click 1 — center.** Resolve the drawing plane (D4); store center (world + plane-uv).
2. **Move.** Project the snapped cursor onto the plane → radius point; `radius = ||radius_uv − center_uv||`; `start_angle = atan2(radius_uv − center_uv)`. Build a live **rubber-band preview** of the ring (closed) plus the snap marker. `status_text`: `"Radius: <r>"` (circle) / `"Radius: <r>   Sides: <n>"` (polygon).
3. **Click 2 — commit.** Generate the ring (D3), lift to world (D2), build the `CompositeCommand` (D9): one `AddVertex` per ring point, one `AddEdge` per consecutive pair (closing the loop), one `AddFace` over the loop. Push to the stack. Return to `IDLE`.

Polygon side count is adjusted live with `↑`/`↓` (clamped [3, 64]); the chosen value is remembered for the session. Circle segment count is fixed at 24 in M4a (adjustment arrives with the VCB in M4d).

### D7 — 2-Point Arc gesture
1. **Click 1 — start** (resolves the plane).
2. **Click 2 — end** (chord; projected onto the plane).
3. **Move — bulge.** Project the cursor onto the plane; preview the sampled arc; `status_text` shows the bulge/radius. **Cardinal-angle snap:** when the bulge is near a clean half-circle (sagitta = half-chord) or a flat chord, snap to it (mirrors SketchUp's "half circle" inference) so common arcs land exactly.
4. **Click 3 — commit.** Generate `arc_2pt` points, lift to world, build a `CompositeCommand` of `AddVertex` (each sample, reusing the snapped start/end vertices where they already exist) + `AddEdge` (consecutive). **No face** (open curve).

**Stretch — edge tangency (D8).**

### D8 — Arc tangency (flagged stretch — first to cut)
When the start point snaps to an **endpoint** of exactly one existing edge, offer a **tangent arc**: constrain the arc to leave the start tangent to that edge's direction. Given start, end, and the start-tangent direction, the circular arc is uniquely determined (center lies on the line through start perpendicular to the tangent, equidistant from start and end). Detected via the snapped `vertex_id` and its single incident non-degenerate edge. If tangency proves to bloat the milestone, ship the **free-bulge** arc (steps 1–4 above) and move tangency to a fast-follow — the tool is fully useful without it.

### D9 — Command composition & undo
Each gesture builds a `CompositeCommand` of existing primitives — `AddVertexCommand`, `AddEdgeCommand`, `AddFaceCommand` — executed in order; `CompositeCommand` already undoes children in reverse. Those primitive commands already implement the id-preserving `_first_do`/`_redo` pattern (M3c/M3d), so atomic undo/redo round-trips with stable ids for free. The tool builds and incrementally executes the composite during the gesture only at **commit** (not per preview frame — previews are pure overlay, no scene mutation), then `push_executed`. `Esc` mid-gesture undoes any partial composite and resets to `IDLE` (the Line-tool cancel pattern). Reuse of an existing vertex (snapped start/end/radius landing on a live vertex) goes through the same `_vertex_for_snap`-style resolver the Line tool uses (endpoint → reuse id; no duplicate vertex).

### D10 — Snapping integration & plane projection
Reuse the M3d `SnapEngine` unchanged for the center, endpoints, and radius/bulge points — they snap to endpoints, midpoints, on-edge, on-face, intersections, and axes, which is where M4a's precision comes from (no VCB). **Every snapped world point after the first is projected onto the active `DrawingPlane`** before use, guaranteeing planar output even when the snap target is off-plane. The active gesture exposes the center/start as the snap `anchor` (so axis-lock and intersection inferences fire while dragging the radius/bulge), matching how the Line tool feeds its anchor.

### D11 — Preview / overlay
Previews use the existing `ToolOverlay` with **no renderer changes**: the in-progress ring/arc is emitted as `rubber_band_segments` (already `(2·N, 3)` line segments — a 24-segment circle is well within budget), the snap marker via `snap_marker_*`, and optionally a translucent `face_fill_polygons` ghost for the closed shapes (the M3b fill path already exists). `status_text` carries the live radius / side-count / bulge readout.

### D12 — Faceting & curve-entity deferral (appearance note)
Circles/arcs render as visible straight-segment N-gons (all segment edges drawn, flat shading) because Pluton has no edge-softening or smooth normals yet — those are **M5** (viewport styles). M4a also does **not** model a circle/arc as a single logical "curve" entity; the segments are independent edges and faces. Logical curves (select one segment → select the whole curve) depend on the grouping infrastructure in **M4e**. Both are intentional deferrals, documented so v0.1.0's faceted circles read as expected, not as a bug.

### D13 — Drawing on a face does **not** cut it ([#27])
Face-split was deferred from M3d. A circle/polygon drawn while hovering an existing face produces a **coplanar face laid on top** of the host — correct geometry, but **no boolean cut**: the host face is not split into a hole-capable sub-face. Practical consequence for v0.1.0: the "draw a circle on a wall, then Push/Pull a hole" workflow does **not** work yet. This is the single biggest expectation-setter in M4a; the spec and release notes link [#27]. Drawing on the ground or a ground-parallel plane is unaffected (independent geometry).

## 5. Data flow

**Hover (mouse move, mid-gesture):** `viewport_widget._snap_for_event` → `SnapEngine.snap(...)` (with the gesture anchor) → `SnapResult` → tool projects `snap.world_position` onto the active `DrawingPlane`, recomputes radius/bulge, regenerates the preview ring/arc from `curves.*`, lifts to world via `DrawingPlane.to_world`, and writes it into its `ToolOverlay`. `update()` repaints; no scene mutation.

**Commit (final click):** tool generates the final point ring → resolves start/end/radius vertices (reuse-or-create) → assembles a `CompositeCommand` of `AddVertex`/`AddEdge`(/`AddFace`) → `command_stack.push_executed(composite)`. Scene goes dirty; renderer re-uploads buffers next frame. A single `Ctrl+Z` removes the whole shape; redo restores it with identical ids.

## 6. Error handling & edge cases
- **Zero / sub-epsilon radius** (radius point ≈ center) → no commit; gesture stays in `DRAWING` (or resets), nothing pushed.
- **Polygon sides** clamped to `[3, 64]`; `↑`/`↓` never escape the range.
- **Degenerate arc** (start ≈ end, or near-zero sagitta) → emit a single straight edge (or no-op if start ≈ end); never emit zero-length edges.
- **Snapped point coincides with an existing vertex** → reuse that vertex id (idempotent `add_vertex` already collapses coincident positions); no duplicate vertices, no dangling geometry.
- **`from_face` on a degenerate/near-zero-area face normal** → guarded (`|n| < 1e-7` → fall back to `horizontal`), mirroring the `faces_are_coplanar` epsilon guard.
- **Snap returns a point behind the camera / off-screen** → handled upstream by `world_to_screen` returning `None`; the tool keeps the last valid preview.
- **`Esc`** cancels and unwinds any partial composite; **tool switch mid-gesture** calls `deactivate`, which cancels cleanly (no orphaned half-built command — the latent bug class fixed in M3d's Line tool).

## 7. Testing strategy (TDD, mirrors M3c/M3d rigor)
- **`geometry/` pure unit tests** (fast, no Qt):
  - `plane.py`: basis orthonormality (`u·v = u·n = v·n = 0`, all unit, `u×v = n`); `from_face` normal matches `scene.face_normal`; `project`∘`to_world` round-trip identity; horizontal-plane axis alignment.
  - `curves.py`: circle/polygon vertex **counts**, all points at `radius` from center (inscribed), CCW winding, `start_angle` orientation; arc endpoint exactness, sagitta correctness, segment count, degenerate-bulge → chord.
- **Tool gesture tests** (pytest-qt, mirroring `test_line_tool.py` / `test_rectangle_tool.py`): simulate the click sequence; assert resulting topology (vertex/edge/face counts, coplanarity with the intended plane, face normal direction); polygon `↑`/`↓` side adjustment; commit atomicity — one composite, single-`Ctrl+Z` undo restores empty scene, redo restores identical ids; `Esc` cancel leaves the scene unchanged; draw-on-face produces a coplanar face on the face's plane.
- **Regression guards:** all existing M2/M3 tool and snap tests stay green; no kernel/binding changes means C++ GoogleTests are untouched (and must still pass).
- **Manual visual verification task:** draw a circle and a hexagon on the ground; draw a hexagon on a box's top face (lands on the face plane, faceted, faces correct way); draw a 2-Point Arc and confirm the half-circle snap; `Ctrl+Z`/redo each; `Esc` mid-gesture.

## 8. Out of scope / carry-over issues
- **VCB / typed precise entry** (radius, sides, segments, bulge) → **M4d** (with units). Tracked as the M4d scope; no new issue needed.
- **3-Point Arc and Pie** gestures → fast-follow; file an issue.
- **Circumscribed polygons + inscribed/circumscribed toggle** → **M4d**.
- **Arc edge-tangency**, if cut from M4a (D8) → fast-follow issue.
- **Curve-as-logical-entity** (grouped segments) → depends on **M4e**; file an issue.
- **Smooth / softened curve shading** → **M5** viewport styles.
- **Face-split on draw** → existing issue [#27].

## 9. Files touched (summary)
| File | Change |
|------|--------|
| `python/pluton/geometry/__init__.py` | **new** — package init |
| `python/pluton/geometry/plane.py` | **new** — `DrawingPlane` |
| `python/pluton/geometry/curves.py` | **new** — `circle` / `polygon` / `arc_2pt` |
| `python/pluton/tools/circle_tool.py` | **new** — `CircleTool` (`C`) |
| `python/pluton/tools/polygon_tool.py` | **new** — `PolygonTool` (`G`) |
| `python/pluton/tools/arc_tool.py` | **new** — `ArcTool` (`A`) |
| `python/pluton/ui/main_window.py` | register the three tools + shortcuts |
| `tests/test_geometry_plane.py`, `test_geometry_curves.py` | **new** — pure geometry unit tests |
| `tests/test_circle_tool.py`, `test_polygon_tool.py`, `test_arc_tool.py` | **new** — gesture tests |
| `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` | **release task only** — bump 0.0.7 → **0.1.0** |
| `docs/2026-05-16-pluton-design.md` | **release task only** — annotate M4a shipped under M4 |

No C++ source, binding, scene-API, or renderer changes — M4a is pure Python over the existing primitives.

---

*End of M4a design.*

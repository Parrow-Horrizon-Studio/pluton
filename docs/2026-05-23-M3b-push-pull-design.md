# Pluton M3b — Push/Pull (basic): Design Spec

**Date:** 2026-05-23
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio)
**Milestone:** M3b — Push/Pull (basic) (Phase 1, Foundation; second sub-milestone of M3)
**Prerequisite:** M3a complete (tag `v0.0.4-m3a`)
**License:** GPL-3.0-or-later

---

## 1. Purpose

M3a delivered the kernel substrate — a C++ `HalfEdgeMesh`, the `Scene` wrapper, command-pattern undo. None of that geometry is yet exercised by a *new* user-visible tool. M3b is the first tool that consumes the half-edge structure: **the SketchUp-style Push/Pull tool**, in its simplest topologically-honest form.

M3b is the *minimum cut* that ships a working push/pull. Two things M3b deliberately does **not** do, both deferred to M3c:

- **No CGAL boolean merge** — the extrusion result is topologically valid (manifold around new geometry; existing geometry preserved) but does not merge with surrounding geometry. Where two pieces of geometry now share a coplanar region, M3b leaves the seam visible.
- **No inferencing on existing geometry** — the snap engine in M3b is unchanged from M2 (grid + axis-lock + endpoint + midpoint of in-progress segments). Snap-to-existing-edge / midpoint-of-existing-edges / edge-edge-intersection inferencing waits for M3c.

What M3b *does* deliver is the headline interaction: click a face, drag along the face normal, click to commit, undo restores the original face.

## 2. End State

When M3b is complete, `python -m pluton` gains one new keyboard shortcut and one new tool:

- **`P`** activates the **Push/Pull** tool. The tool's name appears in the status bar.
- With Push/Pull active and the cursor over a live face, the face **highlights light blue** ("hover-highlight").
- **Click** the highlighted face → the highlight strengthens to a darker blue ("armed").
- **Move the cursor** → a semi-transparent ghost prism is rendered, extruded along the face's normal. The status bar shows the current depth as a number (no units in M3b; units land with M4 issue #13).
- **Click again** → the ghost is committed: the source face is removed, a top face and four side faces (for a rectangle) are added, the scene now contains a 3D box. One `Ctrl+Z` undoes the entire extrusion.
- **`Esc`** mid-drag cancels the gesture without committing. Same two-stage `Esc` model as M2/M3a: a second `Esc` deactivates the tool.
- All M2 + M3a behavior is preserved — `R` / `L` / `Ctrl+N` / `Ctrl+Z` / `Ctrl+Y` are unchanged.

Under the hood:

- The C++ kernel gains a free function `pluton::ray_intersect_mesh(mesh, origin, direction)` — brute-force per-triangle Möller-Trumbore over all live faces. Closest positive `t` wins.
- `HalfEdgeMesh` gains a `face_triangulation(face_id)` accessor (per-face triangulation slice, needed by ray-mesh and by the future M3c boolean conversion).
- The Python `Scene` wrapper gains `ray_pick_face`, `face_loop`, `face_normal`, `face_center` — read-only helpers built on the M3a primitives.
- A new `PushPullTool` (`python/pluton/tools/push_pull_tool.py`) implements the click-move-click state machine.
- `ToolOverlay` gains `face_fill_polygons` + `face_fill_color` fields (with defaults so existing M2 tools don't change).
- `SceneRenderer` gains a `draw_face_fill_overlays` pass for the semi-transparent ghost and the hover/armed highlights.

**CI must be green on Windows + Linux**, with **≈ 155-165 pytest tests** and **≈ 51-54 GoogleTest tests** passing. **No new C++ dependencies** in M3b (`vcpkg.json` unchanged); CGAL still waits for M3c.

## 3. Architecture

### 3.1 Decisions captured from brainstorming

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | **Extrude direction** | Positive only along `+normal`. `depth = max(0, t_proj)`. Negative drag is a no-op. | Carving inward genuinely needs M3c booleans. The 90% case in SketchUp is "draw rectangle → pull up to make a box." Ship that cleanly. |
| 2 | **Ray-mesh algorithm** | Brute-force per-triangle Möller-Trumbore over all live faces' triangulations. Closest positive `t` wins. | O(N) is microseconds for M3b scenes. BVH = M10 perf milestone, tracked as a fresh carry-over issue. |
| 3 | **Pick location** | C++ free function `pluton::ray_intersect_mesh(mesh, origin, dir) → optional<RayMeshHit>`. Bound to Python via nanobind. | Picks read the half-edge mesh directly. Matches M3a contract §7 ("M3b inherits HalfEdgeMesh `next/twin/origin/face`"). |
| 4 | **Tool state machine** | `IDLE → HOVERING ↔ IDLE → DRAGGING → IDLE/HOVERING`. Click in HOVERING arms; click in DRAGGING commits (or cancels if depth < 1e-3); `Esc` in DRAGGING cancels. | Click-move-click matches RectangleTool / LineTool's M2 pattern. |
| 5 | **Hover-highlight** | Yes, in HOVERING state. Subtle light-blue fill on the face under the cursor. | Without this the user has to "blind-click" — they don't know which face they'll arm until after the click. The single bit of UX that separates "feels broken" from "feels right." |
| 6 | **Source-face highlight in DRAGGING** | Stronger blue fill — visually distinct from HOVERING. | Confirms "this is the face you armed." |
| 7 | **Preview style** | Semi-transparent ghost prism (~15% opacity fill + opaque wireframe edges) via `ToolOverlay`. No scene mutation during drag. | Same architectural pattern M2 tools use (overlay shapes outside the scene graph). Keeps the command stack clean — one command at commit, not per frame. |
| 8 | **Depth metric** | Closest-point on the line `face_center + t·normal` to the camera ray. Then `clamp(t, 0, ∞)`. | Standard line-line CPA. Visually tracks cursor intuitively along the normal axis. |
| 9 | **Min commit threshold** | `0.001` world units. `depth < 1e-3` at commit time = treat as cancel (no command pushed). | Prevents accidental zero-height extrusion that would silently churn IDs and pollute the redo stack. Threshold is world-units (not pixels) for simplicity; revisit if it feels wrong during visual verification. |
| 10 | **Composite atomicity** | Single `CompositeCommand("Push/Pull")` containing `[RemoveFace, AddVertex×N, AddEdge×2N, AddFace×(N+1)]`. Pushed once on commit. | Per-gesture pattern from M3a. One `Ctrl+Z` undoes the whole extrusion. |
| 11 | **Tool name / shortcut** | "Push/Pull" / `P`. | SketchUp convention. Doesn't collide with M2's `R` / `L`. |
| 12 | **Status bar during DRAGGING** | Shows current depth as a number. No units (units = M4 #13). | Matches M2's status bar pattern. |
| 13 | **Normal computation** | From the first three boundary vertices of the source face's loop (assumes planar). | M2 / M3a only produce planar faces. Documented as assumption; M4+ may revisit. |
| 14 | **Renderer change** | `SceneRenderer` gains a `draw_face_fill_overlays(polygons, color)` pass. Existing scene rendering pipeline unchanged. | Localized change; doesn't disturb M1 geometry pipeline. |
| 15 | **Closed-bottom prism** | **No.** Bottom of the extruded prism is open (source face removed; no replacement). Closed-bottom waits for M3c's booleans to handle the "source-face-was-on-existing-geometry" case correctly. | M3b's honest "no booleans yet" answer. Visible during orbit-below; documented in §6 and visual checklist. |

### 3.2 Files added relative to M3a

```
pluton/
├── cpp/
│   ├── include/pluton/
│   │   └── ray_intersect.h              # NEW — RayMeshHit struct + free function
│   ├── src/
│   │   └── ray_intersect.cpp            # NEW — Möller-Trumbore impl, per-face iteration
│   ├── bindings/
│   │   └── module.cpp                   # MODIFIED — bind ray_intersect_mesh + RayMeshHit
│   ├── tests/
│   │   ├── test_ray_intersect.cpp       # NEW — GoogleTest for ray-mesh
│   │   └── test_halfedge.cpp            # MODIFIED — face_triangulation accessor coverage
│   └── CMakeLists.txt                   # MODIFIED — add ray_intersect.cpp + test_ray_intersect.cpp
│
├── python/pluton/
│   ├── scene/
│   │   └── scene.py                     # MODIFIED — adds ray_pick_face / face_loop / face_normal / face_center
│   ├── tools/
│   │   ├── push_pull_tool.py            # NEW — PushPullTool class + state machine
│   │   ├── tool.py                      # MODIFIED — ToolOverlay gains face_fill fields; Tool gets optional status_text property
│   │   └── __init__.py                  # MODIFIED — export PushPullTool
│   ├── viewport/
│   │   └── scene_renderer.py            # MODIFIED — draw_face_fill_overlays pass
│   └── ui/
│       └── main_window.py               # MODIFIED — register PushPullTool, bind P, read status_text into status bar
│
└── tests/
    ├── test_ray_intersect_python.py     # NEW — nanobind binding smoke test
    ├── test_push_pull_tool.py           # NEW — state machine + depth metric
    ├── test_push_pull_topology.py       # NEW — extrusion composite correctness
    ├── test_push_pull_overlay.py        # NEW — overlay polygons per state
    ├── test_scene.py                    # MODIFIED — ray_pick_face / face_loop / face_normal / face_center
    ├── test_scene_renderer.py           # MODIFIED — face-fill overlay smoke test
    └── test_viewport.py                 # MODIFIED — P keybind + status bar depth display
```

No new top-level dependencies. `pyproject.toml`, `vcpkg.json`, `CMakeLists.txt` (root) are not modified beyond the cpp subdirectory's CMakeLists.txt entries.

### 3.3 C++ API surface added

```cpp
// pluton/ray_intersect.h
namespace pluton {

struct RayMeshHit {
    uint32_t face_id;
    float    t;      // ray parameter at hit (always > 0)
    Vector3  point;  // origin + t * direction
};

std::optional<RayMeshHit> ray_intersect_mesh(
    const HalfEdgeMesh& mesh,
    const Vector3& origin,
    const Vector3& direction);

}  // namespace pluton
```

```cpp
// pluton/halfedge.h additions
class HalfEdgeMesh {
    // ... existing M3a API ...

    // Returns the triangulation (as (v_a, v_b, v_c) vertex-ID triples) for a single live face.
    // Throws std::out_of_range if face_id is invalid or tombstoned.
    std::span<const std::array<uint32_t, 3>> face_triangulation(uint32_t face_id) const;
};
```

`face_loop(face_id) -> std::vector<uint32_t>` is expected to already exist from M3a Task 10 (per the M3a → M3b contract); Task 1 of the M3b implementation plan confirms this before everything else builds on top.

### 3.4 Python API surface added

```python
class Scene:
    # ... existing M2/M3a API unchanged ...

    def ray_pick_face(
        self, origin: np.ndarray, direction: np.ndarray
    ) -> RayMeshHit | None:
        """Return the closest live face hit, or None. Thin wrapper over the C++ free fn."""

    def face_loop(self, face_id: int) -> list[int]:
        """Ordered boundary vertex IDs of the given face. Raises KeyError if invalid."""

    def face_normal(self, face_id: int) -> np.ndarray:
        """(3,) unit normal of the planar face, computed from the first three boundary vertices."""

    def face_center(self, face_id: int) -> np.ndarray:
        """(3,) centroid (average) of the boundary vertex positions."""
```

```python
@dataclass
class ToolOverlay:
    # ... existing M2 / M3a fields preserved with defaults ...

    face_fill_polygons: list[np.ndarray] = field(default_factory=list)
    """List of (N, 3) world-space vertex loops to fill semi-transparently."""

    face_fill_color: tuple[float, float, float, float] = (0.4, 0.7, 1.0, 0.15)
    """RGBA. Default is the M3b "ghost prism" color."""


class Tool(ABC):
    # ... existing M2 / M3a ABC unchanged ...

    @property
    def status_text(self) -> str | None:
        """Optional text segment for the status bar. Default None means tool contributes nothing extra."""
        return None
```

```python
class PushPullTool(Tool):
    name = "Push/Pull"
    shortcut = "P"

    # Public properties used by MainWindow / tests:
    @property
    def current_depth(self) -> float: ...

    @property
    def status_text(self) -> str | None: ...  # "depth: 12.34" during DRAGGING, else None
```

### 3.5 Dependency arrows (M3b additions)

```
PushPullTool ─→ Scene.ray_pick_face ─→ ray_intersect_mesh (C++)
            └─→ Scene.face_loop / face_normal / face_center
            └─→ CompositeCommand + existing M3a Add/Remove commands
            └─→ ToolOverlay.face_fill_polygons (new field)

SceneRenderer ─→ draw_face_fill_overlays (new method)

MainWindow ─→ PushPullTool (P keybind)
          └─→ Tool.status_text (new property; read each frame for status bar)
```

Everything else is the same as M3a.

## 4. Tool behavior

### 4.1 PushPullTool state machine

| From → To | Trigger | Action |
|---|---|---|
| `IDLE → HOVERING` | `on_mouse_move`; `ray_pick_face` hits a face | Cache `_hovered_face_id`. Overlay shows light-blue fill on that face. |
| `HOVERING → HOVERING` (different face) | `on_mouse_move`, different face id | Replace `_hovered_face_id`. |
| `HOVERING → IDLE` | `on_mouse_move`, no hit | Clear `_hovered_face_id`. No overlay. |
| `IDLE → IDLE` | `on_mouse_press` (no face hovered) | No-op. |
| `HOVERING → DRAGGING` | `on_mouse_press` | Cache `_armed_face_id`, `_armed_face_loop`, `_armed_face_normal`, `_armed_face_center`. `_current_depth = 0.0`. |
| `DRAGGING → DRAGGING` | `on_mouse_move` | Update `_current_depth` via line-line CPA (see §4.2). |
| `DRAGGING → IDLE/HOVERING` | `on_mouse_press` AND `_current_depth ≥ 1e-3` | Build composite, `command_stack.push_executed(composite)`. Reset; transition to HOVERING if cursor still over a face, else IDLE. |
| `DRAGGING → IDLE/HOVERING` | `on_mouse_press` AND `_current_depth < 1e-3` | Cancel (no push). Reset to IDLE or HOVERING per cursor. |
| `DRAGGING → IDLE/HOVERING` | `Esc` | Cancel (no push). Reset to IDLE or HOVERING per cursor. |
| `any → IDLE` | tool deactivated (different tool, second `Esc` from HOVERING) | Clear all state. |

### 4.2 Depth metric (line-line closest-point)

Given camera ray `O + s·d̂` and the face's normal line `C + t·n̂`:

```
w     = O - C
b     = dot(d̂, n̂)
denom = 1 - b²
if abs(denom) < 1e-4:
    return  # view ~parallel to normal; don't update depth (last valid value persists)
t     = (dot(n̂, w) - b · dot(d̂, w)) / denom
depth = max(0.0, t)
```

The degenerate branch handles "look straight down on a Z-up face" — the cursor has no projection onto the normal. SketchUp behaves the same way: orbit a few degrees and the depth becomes drivable.

### 4.3 Extrusion composite — exact ordering

For a source face with boundary loop `[V₀, V₁, …, V_{N-1}]` (CCW from outside), normal `n̂`, depth `d`:

```
composite = CompositeCommand("Push/Pull")

# 1. Remove source (face only — its edges and vertices stay alive)
composite.append( RemoveFaceCommand(source_id).do(scene) )

# 2. Top vertices: V'ᵢ = Vᵢ + d·n̂
for V_i in loop:
    composite.append( AddVertexCommand(V_i.pos + d*n̂).do(scene) )

# 3. Vertical edges: Vᵢ ↔ V'ᵢ
for i in range(N):
    composite.append( AddEdgeCommand(V_i, V'_i).do(scene) )

# 4. Top boundary edges: V'ᵢ ↔ V'_{(i+1) % N}
for i in range(N):
    composite.append( AddEdgeCommand(V'_i, V'_{(i+1) % N}).do(scene) )

# 5. Side faces: Sᵢ = (Vᵢ, V_{(i+1)%N}, V'_{(i+1)%N}, V'ᵢ)  — CCW from outside
for i in range(N):
    composite.append( AddFaceCommand((V_i, V_{(i+1)%N}, V'_{(i+1)%N}, V'_i)).do(scene) )

# 6. Top face: same winding as source
composite.append( AddFaceCommand(tuple(V'_i for i in range(N))).do(scene) )

command_stack.push_executed(composite)
```

**Command count for an N-gon source:** `1 + N + N + N + N + 1 = 4N + 2`. Rectangle (N=4) → **18 commands**. Triangle (N=3) → 14. All grouped under one `Ctrl+Z`.

**Winding correctness:**

- Side face `Sᵢ = (Vᵢ, V_{i+1}, V'_{i+1}, V'ᵢ)` — viewed from outside the prism this is CCW, so the outward normal is correct.
- Top face uses the same loop order as source. Since the source's outward normal was `+n̂` (no other face on that side), the top face inherits that orientation → its outward normal is also `+n̂`.

**Why edges (steps 3 & 4) are added BEFORE the faces (steps 5 & 6):** M3a's `AddFaceCommand` requires all boundary edges to exist as half-edge pairs at `do()` time. The vertical and top boundary edges must already be in the mesh before any side face or top face is added.

### 4.4 Reuse of the source's boundary half-edges

After step 1 (`RemoveFace`), the source's inner half-edges have `face = INVALID_ID` (boundary), and their twins were already `face = INVALID_ID`. So all `N` boundary edges have **both** half-edges available.

When step 5 adds side face `S₀` with boundary edge `V₀ → V₁`, M3a's `add_face_from_loop` finds the existing half-edge `V₀ → V₁` (face = INVALID_ID) and assigns `face = S₀`. The twin (`V₁ → V₀`) stays boundary. This is exactly the M3a code path that's already tested — no new half-edge logic required.

**Implementation plan Task 1 verifies this assumption** on the existing M3a kernel before the rest of M3b is built on top.

### 4.5 Edge cases

| Situation | Behavior |
|---|---|
| Cursor in empty space when tool activated | State stays IDLE. No overlay. |
| Click with no face under cursor | No-op (IDLE → IDLE). |
| Cursor moves OFF the source face mid-drag | DRAGGING continues. Depth keeps updating via CPA — same as SketchUp. |
| View is exactly orthogonal to the face normal | Depth doesn't update on `on_mouse_move`. Current value persists. User can orbit and resume. |
| Second click at near-zero depth (< 1e-3) | Cancel — no command pushed. State back to IDLE/HOVERING. |
| `Esc` mid-drag | Cancel — no command pushed. State to IDLE/HOVERING. |
| `Esc` in HOVERING / IDLE | Deactivates the tool (M2 two-stage `Esc` behavior preserved). |
| `Ctrl+Z` after a commit | Undoes the entire extrusion composite — source face back, top + sides + verts gone. |

## 5. Renderer changes

### 5.1 `SceneRenderer.draw_face_fill_overlays(polygons, color)`

New render pass invoked **after** the main scene draw and **before** the existing M2 line/marker overlays. For each polygon in `polygons`:

1. Earcut-triangulate the (N, 3) world-space loop (Python-side via `mapbox_earcut`).
2. Upload to a transient VBO.
3. Draw triangles with:
   - **Depth test:** `GL_LESS` (so overlays behind opaque scene geometry are correctly occluded).
   - **Depth write:** disabled (so subsequent overlay passes don't z-fight against the fill).
   - **Blend:** `GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA` (standard alpha blending).
   - **Cull:** disabled (overlay polygons may be viewed from either side during orbit).

The pass is a no-op if `polygons` is empty.

### 5.2 No other renderer changes

Scene draw, M2 edge overlays, snap markers — all unchanged.

## 6. Known limitations (documented in spec, visible during verification)

1. **Open-bottom prism.** The source face is removed and not replaced with a new bottom face. Orbiting the camera below the ground plane reveals the open bottom. Will close with M3c's booleans (the ground plane gets boolean-merged into the bottom).
2. **Seam at the previous extrusion boundary.** When push/pulling a face that's already attached to a 3D mesh (e.g. the top of an existing box), the old boundary becomes a coplanar shared edge between the old side face and the new side face. The edge is rendered as a visible line. M3c's boolean union eliminates this by merging the coplanar faces.
3. **Brute-force ray-mesh.** O(N) per pick is fine for M3b scenes (≤ a few hundred triangles). BVH lands at M10; a fresh issue tracks it.
4. **Planar source face assumed.** Normal is computed from the first three boundary vertices. M2 / M3a only produce planar faces. Document with `# TODO M4+` if non-planar faces ever enter the kernel.
5. **No drawing on the new top face.** Push/pull produces faces in 3D space but the M2 drawing tools (Line, Rectangle) still operate only on the ground plane (Z=0). Drawing on extruded surfaces is tracked by issue [#12](https://github.com/Parrow-Horrizon-Studio/pluton/issues/12) (M4).
6. **No numeric depth input.** Cursor-driven depth only. Type-in (measurements box) is issue [#13](https://github.com/Parrow-Horrizon-Studio/pluton/issues/13) (M4).
7. **No inferencing during the drag.** The depth is driven purely by the line-line CPA; no snap-to-vertical-gridlines, no snap-to-existing-edge-height. Inferencing extensions are M3c.
8. **No edge / vertex push/pull.** Faces only — matches SketchUp's model.

## 7. Out of scope for M3b

| Not in M3b | Lands in |
|---|---|
| CGAL booleans (closed-bottom prism; seam elimination) | **M3c** |
| Inferencing on existing edges / midpoints / intersections | **M3c** |
| BVH spatial index for ray-mesh | M10 (perf) — new carry-over issue at tag time |
| Drawing on extruded faces ([#12](https://github.com/Parrow-Horrizon-Studio/pluton/issues/12)) | M4 |
| Measurements box / numeric depth input ([#13](https://github.com/Parrow-Horrizon-Studio/pluton/issues/13)) | M4 |
| Edge or vertex extrusion | Not planned |
| Units / unit conversion | M4+ |
| Multi-face push/pull (extrude multiple selected faces) | Post-M4 (needs selection system) |
| Toolbar widget | M4 |

## 8. The M3b → M3c contract

**M3c (Booleans & Inferencing) inherits:**

- `pluton::ray_intersect_mesh` signature stable. M3c may add face-filter / mask parameters but does not break existing callers.
- `HalfEdgeMesh::face_triangulation` accessor.
- `PushPullTool` state machine + UX (the user-facing flow does not change in M3c — only the internal commit step gets a boolean-merge pass).
- `ToolOverlay.face_fill_polygons` + `face_fill_color`.
- `SceneRenderer.draw_face_fill_overlays`.
- `Tool.status_text` property.
- Open-bottom prism topology — M3c **replaces** this with closed-manifold topology. The §6 known limitations #1 (open-bottom) and #2 (seam) become "should NOT be visible" after M3c.
- All M2 + M3a + M3b public APIs.

**M3c must add fresh:**

- CGAL added to `vcpkg.json` (first vcpkg change since M0 — likely surfaces dev-env carry-overs from issue [#8](https://github.com/Parrow-Horrizon-Studio/pluton/issues/8)).
- `HalfEdgeMesh` ↔ CGAL `Surface_mesh` round-trip conversion.
- Boolean union in `PushPullTool`'s commit step — replaces the M3b "RemoveFace + AddPrism" composite with a boolean-merged equivalent. The composite still gets `Ctrl+Z` semantics; the inner mechanism changes.
- Inferencing extensions: snap to existing edges, midpoints of existing edges, edge-edge intersections projected onto the drawing plane.
- Tests for §6 items 1 and 2 become positive expectations.

**Public-API surface M3c should NOT break:**

- `ray_intersect_mesh` existing signature.
- `PushPullTool` state machine transitions and shortcut.
- `Scene` wrapper methods added in M3b.
- `ToolOverlay` dataclass shape (M3c may add fields with defaults).

## 9. Testing strategy

Following the M1 / M2 / M3a TDD discipline. Test count targets:

| Layer | After M3a | After M3b target |
|---|---|---|
| Pytest | 134 | **≈ 155-165** |
| GoogleTest | 46 | **≈ 51-54** |

### 9.1 Automated tests

| Component | Test file | Coverage |
|---|---|---|
| `pluton::ray_intersect_mesh` (C++) | `cpp/tests/test_ray_intersect.cpp` **NEW** | Single-triangle face hit; multi-triangle face (rectangle = 2 tris) hit; closest-hit when two faces both lie along the ray; ray-misses-all returns `nullopt`; empty mesh returns `nullopt`; tombstoned faces are skipped; degenerate (zero-area) triangles produce no hit. |
| `ray_intersect_mesh` Python binding | `tests/test_ray_intersect_python.py` **NEW** | Construct mesh, add face, call from Python, get `RayMeshHit` with correct `face_id` / `t` / `point`. Miss returns `None`. |
| `HalfEdgeMesh::face_triangulation` + `face_loop` | `cpp/tests/test_halfedge.cpp` **MODIFIED** | Per-face triangulation accessor returns the same triangles as the existing `face_triangle_buffer` filtered to that face. `face_loop` returns ordered boundary vertex IDs. Invalid / tombstoned face_id throws. |
| `Scene.ray_pick_face` / `face_loop` / `face_normal` / `face_center` | `tests/test_scene.py` **MODIFIED** | Round-trip a known face, assert returned data matches geometric expectation. Picking on tombstoned face returns None. Invalid face_id raises KeyError. |
| PushPullTool state machine | `tests/test_push_pull_tool.py` **NEW** | All §4.1 transitions; depth clamp to ≥ 0; min threshold cancels; `Esc` cancels; view-parallel-to-normal degenerate branch holds depth steady. Mocks Camera + Scene. |
| Extrusion composite topology | `tests/test_push_pull_topology.py` **NEW** | After push/pull a rectangle by `d`: assert 4 new verts at `z = z_source + d`, 8 new edges, 5 new faces, source face tombstoned, side face normals outward, top normal `= +n̂`. Triangle source (N=3): 3+6+4 expected. Undo restores exactly. Redo replays. |
| ToolOverlay extensions | `tests/test_push_pull_overlay.py` **NEW** | HOVERING returns one fill polygon (hover color); DRAGGING returns source-face fill (armed color) + 5 ghost prism polygons (ghost color); IDLE returns empty overlay. |
| Renderer face-fill overlay | `tests/test_scene_renderer.py` **MODIFIED** | New `draw_face_fill_overlays` path: assert calls don't crash, GL state flags correct (depth-test on, depth-write off, alpha-blended). Smoke test via offscreen context. |
| MainWindow `P` keybind + status bar | `tests/test_viewport.py` **MODIFIED** | `P` activates PushPullTool. Status bar displays `depth: N.NN` during DRAGGING (via `Tool.status_text`). |

### 9.2 Manual visual verification checklist (pre-tag)

1. **Baseline:** Empty scene at startup. M3a behavior unchanged. Press `P` → tool activates; status bar reflects it.
2. **Hover-highlight:** Draw a rectangle with `R`, then press `P`. Hover cursor over the rectangle → face fills light blue. Hover off the face → fill clears. Hover empty space → no fill.
3. **Push/pull happy path:** With cursor over the rectangle face, click. Highlight strengthens (armed color). Move cursor upward → ghost prism appears, depth value in status bar grows. Click again → ghost replaced by a solid box. Press `Ctrl+Z` → box disappears, original rectangle returns. Press `Ctrl+Y` → box reappears.
4. **Negative drag = no-op:** Click face → drag cursor DOWN (below face plane) → ghost stays at depth = 0. Status bar shows depth = 0. Click → cancel (no commit). Source face still present.
5. **Near-zero depth at commit:** Click face → click again immediately without moving the cursor → no commit. Source face still present.
6. **`Esc` mid-drag:** Click face → move cursor up (ghost prism visible) → press `Esc` → ghost disappears, source face restored, no commit.
7. **`Esc` in HOVERING:** With Push/Pull active and cursor over a face → `Esc` → tool deactivates (M2 two-stage `Esc` behavior preserved).
8. **View parallel to normal:** Orbit camera to look straight down at the ground rectangle. Click face → move cursor → depth stays put (no signal). Orbit slightly → cursor moves now drive depth.
9. **Known limitation #1 (open-bottom):** After committing a push/pull box, orbit the camera below the ground plane. **Expected:** you can see through the bottom of the box. This matches the documented limitation.
10. **Undo / redo cycle:** Draw rectangle, push/pull, `Ctrl+Z`, `Ctrl+Y`, `Ctrl+Z` → scene returns to rectangle. Scene stays consistent across rapid undo/redo presses.
11. **Known limitation #2 (seam):** Push/pull a rectangle to make a box. Press `P`, hover top face → highlights. Click + drag up → second extrusion. Commit. **Expected:** there may be a visible horizontal seam line where the old top boundary was. This matches the documented limitation.

Items 9 and 11 are flagged in advance so the user doesn't report them as bugs.

## 10. Implementation order (preview)

The implementation plan owns the exact decomposition. Tentative shape — ~17-18 tasks. C++ first, Python second, tool integration third, polish + release last.

1. `HalfEdgeMesh::face_triangulation(face_id)` accessor + verify `face_loop` exists — TDD.
2. `pluton::RayMeshHit` + `ray_intersect_mesh` (Möller-Trumbore) — TDD.
3. nanobind binding for `ray_intersect_mesh` + Python smoke test — TDD.
4. `Scene.ray_pick_face` / `face_loop` / `face_normal` / `face_center` — TDD.
5. `ToolOverlay` extensions (`face_fill_polygons`, `face_fill_color`) — TDD.
6. `SceneRenderer.draw_face_fill_overlays` (new GL pass) — TDD (smoke).
7. PushPullTool state machine + transitions — TDD.
8. PushPullTool depth metric (line-line CPA + degenerate branch + clamp) — TDD.
9. PushPullTool overlay (hover + armed + ghost prism polygons) — TDD.
10. PushPullTool composite-building (extrusion topology) — TDD.
11. `Tool.status_text` property + MainWindow status bar wiring — TDD.
12. MainWindow integration: register PushPullTool, bind `P` — TDD.
13. ViewportWidget: verify / enable `setMouseTracking(True)` for hover events.
14. Manual visual verification (11-step checklist) — manual.
15. Push + verify CI on Windows + Linux — manual.
16. Version bump `0.0.4` → `0.0.5` (`pyproject.toml`, root `CMakeLists.txt`, `cpp/src/version.cpp`).
17. Annotated, SSH-signed tag `v0.0.5-m3b` + push.
18. Open carry-over GitHub issues: (a) BVH for ray-mesh (M10), (b) closed-bottom prism (M3c), (c) seam-line elimination via face-merge or booleans (M3c), (d) any execution-time discoveries.

## 11. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `add_face_from_loop` doesn't correctly reuse a boundary half-edge whose twin is still alive in another face | Low (architecturally expected to work, but unverified path on existing M3a kernel) | Task 1 explicitly tests this scenario before the rest of M3b is built on top. Cheap to verify (a unit test on M3a's existing API). |
| Möller-Trumbore precision at glancing angles (very oblique camera-to-face) | Low | Standard algorithm; well-trodden. Tested with hand-computed edge cases. |
| `setMouseTracking(True)` interferes with M2 tools' existing mouse-move expectations | Low | M2 tools already rely on no-button mouse_move events for their preview shapes (RectangleTool's rubber-band, LineTool's polyline preview). If they work today, `setMouseTracking(True)` is already on or the widget already gets the events; Task 13 verifies. |
| Per-face triangulation isn't stored at the time `face_triangulation` is called (M3a stored only the flat buffer) | Medium | If M3a's `HalfEdgeMesh` doesn't already store per-face triangulation, Task 1 adds it. Either way the data is small (`std::vector<std::array<uint32_t,3>>` per face, sized by `N - 2` triangles for convex N-gons). |
| Alpha-blending order causes ghost prism to render incorrectly over hover-highlight | Low | All overlay polygons drawn in a single pass with depth-test on, depth-write off. Order: armed-face fill first, then ghost prism (which is behind the armed face from the camera's perspective in most cases). Verified during visual verification. |
| Open-bottom prism is too jarring for visual verification | Medium | Documented as known limitation #1 with explicit pre-tag checklist item #9. User has accepted the tradeoff in brainstorming. If genuinely unacceptable, the fallback is to also add a `AddFaceCommand(loop reversed)` for the bottom in step 6 — a 2-line change. |

## 12. Definition of done

- [ ] All §9.1 automated tests pass (Pytest ≥ 155, GoogleTest ≥ 51).
- [ ] All §9.2 manual visual verification checklist items pass (or are documented limitations).
- [ ] CI is green on `ubuntu-24.04` and `windows-2022` jobs.
- [ ] `pyproject.toml`, root `CMakeLists.txt`, and `cpp/src/version.cpp` bumped to `0.0.5`.
- [ ] Annotated tag `v0.0.5-m3b` pushed, SSH-signed.
- [ ] Carry-over issues (§10 task 18) opened on GitHub.
- [ ] Spec §6 known limitations are still accurate (no regressions; no new undocumented limitations).

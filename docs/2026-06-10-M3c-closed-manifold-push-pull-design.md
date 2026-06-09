# Pluton M3c — Closed-manifold Push/Pull: Design Spec

**Date:** 2026-06-10
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio)
**Milestone:** M3c — Closed-manifold Push/Pull (Phase 1, Foundation; third sub-milestone of M3)
**Prerequisite:** M3b complete (tag `v0.0.5-m3b`)
**License:** GPL-3.0-or-later

---

## 1. Purpose

M3b shipped push/pull as a working interactive tool but with two known-and-documented limitations: extruded prisms have **open bottoms**, and stacked extrusions leave **visible horizontal seams** where the new side faces meet the parent's old side faces. Both were punted to M3c on the assumption that closing them required CGAL booleans.

M3c re-examines that assumption and rejects it. Both limitations are reframed as **pure half-edge operations** on the kernel we already own:

- **Open bottom** → add a single face for the reversed source loop (a no-op when the source was already attached to other geometry).
- **Horizontal seam** → detect coplanar adjacent faces sharing an edge, dissolve the edge.

The result: M3c is the **first half of what the master design called "M3c (CGAL booleans + inferencing)"**, reframed as **"closed-manifold push/pull, no CGAL"**. The second half — inferencing — splits off into a separate M3d. The CGAL dependency is deferred to Phase 2, where its first real consumer (push/pull *into* existing geometry, the Hole tool, mesh import + carve) will justify the integration cost.

M3c is deliberately scoped to what's needed to flip two manual-checklist items from "expected limitation" to "should not appear." Nothing more.

## 2. End State

When M3c is complete, `python -m pluton` behavior changes in two visible ways:

- **Closed-bottom prisms.** Draw a rectangle on the ground plane, press `P`, push/pull it upward. Orbit beneath the floor → **no hole**. The prism is a closed manifold solid.
- **Seamless stacked extrusion.** With an existing box on the canvas, push/pull its top face upward by any amount. The result is a taller box with **no horizontal seam** at the previous top height. The four old-top-loop edges are gone from the mesh; the four side faces span the full new height as single quads.

All other M2 + M3a + M3b behavior is preserved. The `P` shortcut, the click-move-click state machine, the ghost prism preview, the depth-during-drag status bar, the `Esc` cancellation, the single-`Ctrl+Z` undo of the entire extrusion — all unchanged.

Under the hood:

- The C++ kernel gains two new methods on `HalfEdgeMesh`:
  - `dissolve_edge(EdgeId) → FaceId` — collapses two faces sharing an edge into one; returns surviving face id (or `INVALID_ID` if the operation isn't well-defined).
  - `faces_are_coplanar(FaceId, FaceId, float angle_tol_cos, float dist_tol) → bool` — robust two-test coplanarity check.
- The Python `Scene` wrapper gains thin `dissolve_edge` and `faces_are_coplanar` wrappers using project-default tolerances.
- A new `DissolveEdgeCommand` joins the command set, fully undoable.
- `PushPullTool._commit_extrusion` is extended (not restructured) with a conditional bottom-cap and a post-extrusion seam-merge pass.
- **No renderer changes.** Dissolved edges naturally disappear from the mesh, so the existing edge-iterating renderer stops drawing them. Merged faces flow through the existing M3b dominant-axis-projection earcut.
- **No picking changes.** Ray-mesh face picking already iterates over per-face triangulations; merged faces have larger triangulations but the same interface.

**CI must be green on Windows + Linux**, with **≈ 200-205 pytest tests** and **≈ 65-67 GoogleTest tests** passing. **No new C++ dependencies** in M3c (`vcpkg.json` unchanged); CGAL still waits for Phase 2.

## 3. Architecture

### 3.1 Decisions captured from brainstorming

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | **Milestone scope** | CGAL booleans split out of M3c entirely. Inferencing splits out as M3d. M3c is "closed-manifold push/pull" only. | Two independent subsystems with different risk profiles. CGAL = chunky vcpkg dep + integration risk. Inferencing = UX iteration. Each deserves its own milestone. |
| 2 | **Use CGAL for M3c?** | **No.** Half-edge ops only. | Both acceptance items (#21, #22) are trivial half-edge ops. CGAL pays nothing for the two known cases. Real boolean cases (Case 3, Hole tool) come in Phase 2, justifying CGAL then. |
| 3 | **Layering split** | **Hybrid Z.** Two new C++ kernel ops (`dissolve_edge`, `faces_are_coplanar`). Python orchestrates via expanded P/P composite. | `dissolve_edge` is a primitive half-edge op — belongs in C++ next to `add_face_from_loop`. Coplanarity is a robustness-sensitive geometry test — also C++. Orchestration (when to fire, which edges to scan) is application-level — stays in Python where the tool lives. |
| 4 | **P/P case contract** | Case 1 (standalone source) and Case 2 (attached, sticking out) are in scope. Case 3 (P/P into existing solid) stays out of scope — documented as Phase 2 / CGAL. | Cases 1 and 2 are pure half-edge ops; Case 3 needs volumetric boolean. Drawing the line here matches the no-CGAL decision. |
| 5 | **Bottom-cap conditional** | Add bottom cap iff every boundary edge of the source face had only one half-edge before removal (= source was standalone). Skip otherwise. | Adding a bottom cap when the source was attached creates non-manifold geometry (3 half-edges on one edge). The conditional is one cheap pre-check. |
| 6 | **Seam-merge scope** | **Single-pass over OLD source face's boundary edges only.** ~4-N edge checks per P/P. | Exactly matches the #22 acceptance criteria. No chains possible in either Case 1 or Case 2 by construction. Broader scope or fixed-point iteration would add complexity without clear win. |
| 7 | **Coplanarity tolerance** | Two tests, both must pass: `dot(n1, n2) > cos(0.5°)` ≈ `0.9999619`, AND every vertex of face B within `1e-4` world-units of face A's plane (symmetric). | Guards against both rotational and translational drift. Numbers match SketchUp-scale architectural geometry. Documented as world-unit-absolute; AABB-relative is a future improvement. |
| 8 | **Undo granularity** | One `CompositeCommand("Push/Pull")` containing the M3b sub-commands plus 0-1 `AddFaceCommand` (bottom) plus 0-N `DissolveEdgeCommand`. | Same per-gesture pattern as M3a/M3b. Each new sub-command is independently testable, but a single `Ctrl+Z` reverses the entire extrusion. |
| 9 | **Dissolve robustness** | `dissolve_edge` returns `INVALID_ID` (not crash) for boundary edges or pathological multi-shared-edge topology. `DissolveEdgeCommand` records itself as no-op when the kernel refuses. | Robust to malformed input; no command stack corruption. |
| 10 | **Tombstone edge IDs on dissolve** | Dissolved edge IDs are tombstoned (not compacted) consistent with issue #19's M3b prep. Undo allocates new edge IDs for restored edges. | Matches existing kernel pattern; avoids ID reuse hazards. |
| 11 | **Milestone rename** | "M3c: CGAL booleans" (master design) → "M3c: Closed-manifold Push/Pull". | The work no longer involves CGAL. Master design §M3 also updated at end of milestone. |
| 12 | **Manual checklist** | M3b §9.2 items #9 and #11 flip from "expected limitation" to "should NOT appear." Add new items #12 (pentagon P/P) and #13 (tilted-plane P/P). | Directly maps acceptance criteria to verifiable user actions. |

### 3.2 Files added/modified relative to M3b

```
pluton/
├── cpp/
│   ├── include/pluton/
│   │   └── halfedge.h                              # MODIFIED — 2 method decls
│   ├── src/
│   │   └── halfedge.cpp                            # MODIFIED — 2 method impls + helpers
│   ├── bindings/
│   │   └── module.cpp                              # MODIFIED — bind 2 methods
│   ├── tests/
│   │   └── test_halfedge.cpp                       # MODIFIED — 11 new tests
│   └── ...                                         # everything else unchanged
├── python/pluton/
│   ├── scene/
│   │   └── scene.py                                # MODIFIED — 2 wrappers + default tolerances
│   ├── commands/
│   │   └── scene_commands.py                       # MODIFIED — append DissolveEdgeCommand class
│   └── tools/
│       └── push_pull_tool.py                       # MODIFIED — _commit_extrusion expansion
├── tests/
│   ├── test_dissolve_edge_command.py               # NEW
│   ├── test_scene_dissolve.py                      # NEW
│   ├── test_push_pull_topology.py                  # MODIFIED — strengthened assertions
│   ├── test_push_pull_tool_closed_manifold.py      # NEW
│   ├── test_picking_after_merge.py                 # NEW
│   └── test_renderer_merged_face.py                # NEW
├── docs/
│   ├── 2026-05-16-pluton-design.md                 # MODIFIED — drop CGAL line in §M3
│   ├── 2026-06-10-M3c-closed-manifold-push-pull-design.md   # NEW (this file)
│   └── 2026-06-10-M3c-closed-manifold-push-pull-plan.md     # NEW (next step)
```

No new top-level dependencies. `vcpkg.json` unchanged. `pyproject.toml` unchanged.

### 3.3 Module split

```
┌─ C++ kernel ─────────────────────────────────────────────────────┐
│  NEW:  HalfEdgeMesh::dissolve_edge(EdgeId) -> FaceId             │
│        HalfEdgeMesh::faces_are_coplanar(FaceId, FaceId,          │
│                                          float angle_tol_cos,    │
│                                          float dist_tol) -> bool │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │ nanobind: +2 method bindings
                              ▼
┌─ Python Scene wrapper ───────────────────────────────────────────┐
│  NEW:  Scene.dissolve_edge(edge_id) -> face_id                   │
│        Scene.faces_are_coplanar(f1, f2) -> bool                  │
│           (wraps with project-default tolerances)                │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              ▼
┌─ Commands ───────────────────────────────────────────────────────┐
│  NEW:  DissolveEdgeCommand                                       │
│           do(): captures both face descriptors, dissolves edge   │
│           undo(): restores both original faces                   │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              ▼
┌─ Push/Pull tool ─────────────────────────────────────────────────┐
│  EXTENDED _commit_extrusion():                                   │
│    1. (NEW) Compute should_add_bottom_cap before removing source │
│    2. RemoveFaceCommand(src)         ← existing                  │
│    3. AddFaceCommand(top)            ← existing                  │
│    4. AddFaceCommand(side) × N       ← existing                  │
│    5. (NEW) AddFaceCommand(bottom)   ← iff is_standalone         │
│    6. (NEW) DissolveEdgeCommand × M  ← seam-merge pass           │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              ▼
┌─ Renderer + Picking ─────────────────────────────────────────────┐
│  UNCHANGED.                                                       │
│  Dissolve removes edges from mesh → renderer stops drawing them. │
│  Merged faces go through existing dominant-axis earcut.          │
│  Picking iterates per-face triangulation → merged face returns   │
│  its own surviving face id.                                      │
└──────────────────────────────────────────────────────────────────┘
```

**Decomposition principle:** `dissolve_edge` is the smallest reusable C++ topology op; the seam-merge *policy* (when to fire, which edges to scan) lives in Python where the tool lives. Each command remains independently testable.

## 4. Data Flow

### 4.1 Case 1 — Standalone rectangle (closes #21)

User has drawn a 2×2 rectangle on the ground plane. Source face has 4 boundary edges, each with **only one half-edge** (the source itself).

```
User clicks face       PushPullTool: IDLE → HOVERING → DRAGGING
   │
   ▼
User moves mouse       Ghost prism preview (M3b code, unchanged)
   │
   ▼
User clicks again      PushPullTool._commit_extrusion(depth=2.0)
   │
   ├─ STEP A: capture source metadata BEFORE mutation
   │    src_loop = scene.face_vertex_loop(src_face_id)
   │    src_normal = scene.face_normal(src_face_id)
   │    is_standalone = all(scene.edge_is_boundary(e)
   │                        for e in scene.face_edges(src_face_id))
   │    # is_standalone == True for this case
   │
   ├─ STEP B: build new-vertex loop
   │    new_top_loop = [v + src_normal * depth for v in src_loop]
   │
   ├─ STEP C: build CompositeCommand
   │    cmds = [
   │      RemoveFaceCommand(src_face_id),              # existing
   │      AddFaceCommand(new_top_loop),                # existing
   │      AddFaceCommand(side_loop_0..N-1),            # existing × N
   │      AddFaceCommand(reversed(src_loop)),  ← NEW  # bottom cap
   │    ]
   │    # Seam-merge pass yields ZERO edges (no coplanar
   │    # adjacent faces because source was standalone)
   │
   ▼
   composite.do() → undo_stack.push(composite)
   │
   ▼
   Mesh now has: top face, N side faces, bottom face
                 = N + 2 faces, fully closed manifold ✅
```

**Result:** orbit below ground plane → no hole. `face_count == 6` for a rectangle source.

### 4.2 Case 2 — P/P top of existing box upward (closes #22)

User previously did Case 1 to build a 2×2×1 box. Now clicks the box's top face and P/Ps up by 1.0. The top face's 4 boundary edges each have **two half-edges** (top face + adjacent side face of the box).

```
User clicks top face   PushPullTool: IDLE → HOVERING → DRAGGING
   │
   ▼
User clicks again      PushPullTool._commit_extrusion(depth=1.0)
   │
   ├─ STEP A: capture source metadata BEFORE mutation
   │    src_loop = scene.face_vertex_loop(src_face_id)   # OLD top loop
   │    src_normal = scene.face_normal(src_face_id)      # +Z
   │    is_standalone = all(...)
   │    # is_standalone == False (each edge has 2 half-edges) ← KEY
   │
   ├─ STEP B: build new-vertex loop
   │    new_top_loop = [v + src_normal * 1.0 for v in src_loop]
   │
   ├─ STEP C: identify candidate seam edges
   │    # Single-pass over OLD source face's boundary edges only (decision #6)
   │    candidate_edges = list(scene.face_edges(src_face_id))
   │
   ├─ STEP D: build CompositeCommand
   │    cmds = [
   │      RemoveFaceCommand(src_face_id),              # existing
   │      AddFaceCommand(new_top_loop),                # existing
   │      AddFaceCommand(side_loop_0..3),              # existing × 4
   │      # NO bottom cap — is_standalone is False
   │    ]
   │
   ├─ STEP E: seam-merge pass (AFTER sides exist in the mesh)
   │    for edge in candidate_edges:
   │      # edge now has 2 half-edges: parent's old side + new prism's side
   │      f1, f2 = scene.edge_faces(edge)
   │      if scene.faces_are_coplanar(f1, f2):
   │        cmds.append(DissolveEdgeCommand(edge))
   │    # For a flat top, all 4 candidate edges qualify → 4 dissolves
   │
   ▼
   composite.do() → undo_stack.push(composite)
   │
   ▼
   Mesh now has: 1 top face, 4 tall side faces, original bottom
                 = 6 faces total, no horizontal seam ✅
```

**Result:** the box just got taller. No horizontal line at the old top height.

### 4.3 Single-Ctrl+Z undo

In both cases, the CompositeCommand is one entry on the undo stack. Pressing Ctrl+Z:

```
composite.undo()
   ├─ DissolveEdgeCommand × M       ← undo in reverse order
   │   (each restores 2 original faces by replaying their loops)
   ├─ AddFaceCommand(bottom).undo() ← remove bottom (Case 1 only)
   ├─ AddFaceCommand(side).undo() × N
   ├─ AddFaceCommand(top).undo()
   └─ RemoveFaceCommand(src).undo() ← restore original source face
```

Mesh returns exactly to the pre-P/P state.

### 4.4 Edge cases handled

- **Tilted source face** (e.g., a rectangle on a sloped roof, then P/P): `src_normal` comes from the geometry-derived face normal (the M3b fix). Side faces extrude along that normal. Coplanarity test uses the same normal, so seam-merge logic is rotation-agnostic.
- **Non-axis-aligned coplanar adjacency**: handled by `faces_are_coplanar` using `dot(n1, n2)` and signed distance — no XY-axis assumption.
- **Source face with N > 4 vertices** (e.g., pentagon): everything scales linearly with N (N sides, N candidate edges, up to N dissolves).
- **Zero-depth P/P**: M3b's existing "near-zero cancel" path still triggers; no commit, no new logic exercised.

## 5. Error Handling & Robustness

### 5.1 `dissolve_edge` failure modes

`dissolve_edge(edge_id)` is only well-defined when the edge has **exactly two adjacent faces** that share **only that single edge**.

| Condition | Behavior |
|---|---|
| Edge has 1 half-edge (boundary edge, no opposite face) | Return `INVALID_ID`. Mesh unchanged. |
| Edge has 0 half-edges (tombstoned) | Return `INVALID_ID`. Mesh unchanged. |
| Edge has > 2 incident faces (non-manifold input) | Never happens in our half-edge structure by construction. Debug-build `assert`. |
| Two adjacent faces share multiple edges (degenerate topology) | Return `INVALID_ID`. Mesh unchanged. Log `WARN`. |

C++ contract:

```cpp
FaceId HalfEdgeMesh::dissolve_edge(EdgeId e) {
    if (!is_valid(e)) return INVALID_ID;
    auto [he1, he2] = edge_halfedges(e);
    if (he2 == INVALID_ID) return INVALID_ID;             // boundary edge
    if (faces_share_multiple_edges(he1, he2)) return INVALID_ID;
    // ... actual dissolve work ...
    return surviving_face_id;
}
```

Python `DissolveEdgeCommand.do()` checks the return value. If `INVALID_ID`, the command records itself as a no-op; its `undo()` is also a no-op — keeps the undo stack consistent.

### 5.2 `faces_are_coplanar` failure modes

- **Degenerate face normal** (zero-area sliver, numerical underflow): if `||n1||` or `||n2||` is below `1e-7`, return `False` (refuse to merge). Caller treats as "no merge."
- **Very large coordinate magnitudes** where `1e-4` world-units becomes inappropriate: tolerances are world-unit-fixed for now; a future issue will parameterize them by mesh AABB diagonal. Documented as known limitation §7.4.

### 5.3 Bottom-cap winding mistake (regression risk)

The bottom cap must use **reversed** source-face winding so its normal points down (opposite the prism's extrusion direction). Forgetting the reverse → normal points up → flipped backface culling, lighting wrong, picking still works but renderer shows it as a black face from below.

**Defense:** unit test in `test_push_pull_tool_closed_manifold.py` that asserts the bottom face's computed normal dots negatively with `src_normal`. This is exactly the kind of regression that M3b's visual verification surfaced — cheaper to catch in CI.

### 5.4 CompositeCommand size

For a high-vertex source (e.g., a 32-gon), the worst-case composite is:

```
1 (remove) + 1 (top) + 32 (sides) + 1 (bottom) + 32 (dissolves) = 67 sub-commands
```

This is a perf consideration only, not correctness. CompositeCommand is a flat list, undo replays in reverse. Linear in sub-command count — fine at N=67, fine at N=200. No optimization needed for M3c.

### 5.5 Other robustness items

| Concern | Handling |
|---|---|
| Edge ID stability after dissolve | Dissolved edge tombstoned (#19 pattern). Slot stays unused; ID never reissued. `DissolveEdgeCommand.undo()` allocates a NEW edge ID for the restored edge — captured in the command's recorded state. |
| Renderer crashes on the new merged-face polygon | Won't — earcut handles arbitrary simple polygons since the M3b dominant-axis fix. Regression-guarded by `test_renderer_merged_face.py`. |
| Picking fails on merged face | Won't — ray hits any triangle of the merged face's triangulation, returns the merged face id. Regression-guarded by `test_picking_after_merge.py`. |
| Floating-point drift across many stacked P/Ps | Each P/P uses scene-stored vertex positions exactly; no accumulation. Coplanarity tolerances are absolute, not relative, so very deep stacks could in principle drift past `1e-4` distance tolerance. Documented in §7.4. |

### 5.6 Logging

Two new debug-log call sites:

- `dissolve_edge` failures (degenerate/non-manifold) — `WARN` level with edge id and reason.
- Seam-merge pass summary — `DEBUG` level with edges scanned / edges dissolved per P/P commit.

**No new user-visible error messages.** Failures degrade gracefully to "seam stays visible" or "bottom stays open" — never crash, never corrupt mesh state.

## 6. Testing Strategy

### 6.1 C++ (GoogleTest) — kernel ops in isolation

**File:** `cpp/tests/test_halfedge.cpp` (extend existing).

**`dissolve_edge` — 6 tests:**

| Test | Setup | Assertion |
|---|---|---|
| `DissolvesEdgeBetweenTwoTriangles` | Two triangles sharing an edge → quad | Returns valid face id; mesh has 1 face, 4 vertices, 4 edges |
| `DissolvesEdgeBetweenTwoQuads` | Two quads sharing an edge → hexagon | Returns valid face id; surviving face has 6-vertex loop |
| `RejectsBoundaryEdge` | Single triangle, one boundary edge | Returns `INVALID_ID`; mesh unchanged |
| `RejectsEdgeWithMultipleSharedFaces` | Pathological: two faces share 2 edges | Returns `INVALID_ID`; mesh unchanged |
| `TombstonesDissolvedEdgeId` | After dissolve, query the old edge id | Returns invalid; edge slot count unchanged (no compaction) |
| `RestoresMeshAfterDissolveAndRebuild` | Dissolve, then add a face that reconstructs original | Topology returns to original face count |

**`faces_are_coplanar` — 5 tests:**

| Test | Setup | Assertion |
|---|---|---|
| `TrueForIdenticalPlanes` | Two faces on the XY plane | `True` |
| `TrueWithinTolerance` | Tilted face at 0.3° to another | `True` (under 0.5°) |
| `FalseBeyondAngleTolerance` | Tilted at 1.0° | `False` |
| `FalseBeyondDistanceTolerance` | Parallel planes offset by 1e-3 | `False` |
| `FalseForDegenerateNormal` | Zero-area sliver face | `False` (doesn't crash) |

### 6.2 Python (pytest) — orchestration and integration

**`DissolveEdgeCommand` — 4 tests** (`tests/test_dissolve_edge_command.py`):

| Test | Assertion |
|---|---|
| `do_removes_shared_edge_and_merges_faces` | Before: 2 faces, 1 shared edge. After: 1 face, edge gone |
| `undo_restores_both_original_faces` | After undo: face count + topology match original |
| `do_returns_false_on_boundary_edge` | Command records no-op, undo also no-op, stack consistent |
| `do_then_undo_then_redo_idempotent` | Mesh state matches do-state after redo |

**`PushPullTool` closed-manifold — 8 tests** (`tests/test_push_pull_tool_closed_manifold.py`):

| Test | Setup | Assertion |
|---|---|---|
| `case1_standalone_rect_produces_closed_prism` | Draw rect, P/P 2.0 up | `face_count == 6`; all edges have 2 half-edges |
| `case1_bottom_face_normal_points_down` | Same setup | Bottom face normal · src_normal < 0 |
| `case1_pentagon_source_produces_7_faces` | Draw pentagon, P/P up | `face_count == 7` (5 sides + top + bottom) |
| `case2_stacked_pp_has_no_horizontal_seam` | Box + P/P top upward | Old top loop's edges no longer exist in mesh |
| `case2_stacked_pp_face_count_correct` | Same | `face_count == 6` (same as original box, just taller) |
| `case2_no_bottom_cap_for_attached_source` | Box + P/P top | No face exists at old top height |
| `composite_undoes_atomically` | Case 2, then Ctrl+Z | Pre-P/P face count + edge count restored |
| `tilted_source_seam_merge_works` | Rect on sloped roof, P/P along its normal | Seam-merge dissolves edges on the slope |

**Extended topology test** (`tests/test_push_pull_topology.py`):

In the existing M3b test, strengthen assertions to:

- Assert per-face triangle counts > 0 (the latent earcut bug we caught in M3b).
- Assert every interior edge has exactly 2 half-edges after Case 1 P/P (closed manifold check).

**Picking + rendering regression guards — 2 tests** (flat under `tests/`):

- `tests/test_picking_after_merge.py` — pick the merged face, confirm picker returns the merged face's id (not a stale id of either pre-merge face).
- `tests/test_renderer_merged_face.py` — Case 2 merge produces a 6-vert face; render pass produces > 0 triangles for it.

### 6.3 Test count summary

| Layer | M3b end | M3c added | M3c end |
|---|---|---|---|
| GoogleTest | 55 | +11 | 66 |
| pytest | 189 | +14 | 203 |

### 6.4 Manual test plan (`§9.2` equivalent)

The M3b manual checklist already exists. For M3c, items #9 and #11 flip from "expected limitation" to "should NOT appear":

| # | Old M3b expectation | New M3c expectation |
|---|---|---|
| #9 | "Orbit below floor → open bottom visible (known limitation)" | "Orbit below floor → no hole, closed prism" |
| #11 | "After 2nd P/P on box top → horizontal seam visible (known limitation)" | "After 2nd P/P on box top → no seam visible" |

Plus two new items:

| # | Step | Expected |
|---|---|---|
| #12 | Draw pentagon, P/P up, orbit underneath | No hole; pentagonal bottom visible |
| #13 | Draw rectangle on a sloped construction face, P/P along its normal | Closed prism; bottom is the tilted rectangle |

## 7. Out of Scope

Documented limitations carried forward from M3c, with their resolution path.

### 7.1 Case 3 — Push/pull INTO existing geometry

When the user push/pulls a face *negatively* such that the new prism's volume intersects the parent solid's interior, M3c produces the same non-manifold intersection M3b does. To get correct topology requires volumetric boolean (subtraction). **Resolution: Phase 2 CGAL milestone.**

A new GitHub issue will be filed at the end of M3c: *"Phase 2: CGAL booleans — push/pull into existing solid + Hole tool."*

### 7.2 Standalone "Make Solid" / "Merge Coplanar Faces" command

M3c only seam-merges as part of a P/P gesture, scoped to the OLD source face's boundary edges. If the user wants to merge coplanar faces created by other means (e.g., a future Line tool that splits an edge mid-face), they have no command for it. **Resolution: file as Phase 2 enhancement.**

### 7.3 Fixed-point chain merge

M3c's seam-merge is single-pass. If a merged face becomes coplanar-adjacent to a face it wasn't touching before (theoretically possible with already-coplanar non-shared-edge neighbors), the chain stops after one round. The acceptance criteria (#21, #22) don't expose this. **Resolution: handled by the standalone "Make Solid" command in §7.2 above.**

### 7.4 AABB-relative coplanarity tolerance

Tolerances are world-unit-fixed (`0.5°` angle, `1e-4` distance). For models at extreme scales (1e6 world units or larger), these may need to scale with the AABB diagonal. **Resolution: file as future enhancement if real workflows surface the problem.**

### 7.5 Inferencing

The original master design's "M3c (CGAL booleans + inferencing)" bundled snap detection (endpoint, midpoint, edge, intersection) with booleans. M3c does not include inferencing. **Resolution: M3d milestone.**

## 8. Done-criteria for M3c

All of these must hold before tag:

- ✅ All M3c automated tests passing locally (Windows + Linux via WSL if available).
- ✅ CI green on `ubuntu-24.04` + `windows-2022`.
- ✅ Manual checklist: items #9 and #11 flipped behavior verified visually.
- ✅ Manual checklist: items #12 and #13 (new) pass.
- ✅ Existing M3a/M3b manual items still pass (no regressions).
- ✅ Master design doc §M3 updated (drop CGAL line; note inferencing → M3d).
- ✅ Issues #21 and #22 closed with a comment linking the M3c tag.
- ✅ New Phase 2 issue filed: *"Phase 2: CGAL booleans — push/pull into existing solid + Hole tool."*
- ✅ `v0.0.6-m3c` annotated, SSH-signed, pushed to origin.

## 9. Estimated File-by-File Inventory

| File | Status | LoC ± | Notes |
|---|---|---|---|
| `cpp/include/pluton/halfedge.h` | extend | +20 | 2 method declarations |
| `cpp/src/halfedge.cpp` | extend | +180 | `dissolve_edge` (~120), `faces_are_coplanar` (~40), helpers (~20) |
| `cpp/bindings/module.cpp` | extend | +12 | 2 `.def` calls + docstrings |
| `cpp/tests/test_halfedge.cpp` | extend | +200 | 11 new tests |
| `python/pluton/scene/scene.py` | extend | +30 | 2 wrappers + default tolerances |
| `python/pluton/commands/scene_commands.py` | extend | +80 | append `DissolveEdgeCommand` class |
| `python/pluton/tools/push_pull_tool.py` | extend | +60 | `_commit_extrusion` expansion + `_seam_merge_pass` helper |
| `tests/test_dissolve_edge_command.py` | new | +120 | 4 tests |
| `tests/test_scene_dissolve.py` | new | +80 | scene-level wrapper tests |
| `tests/test_push_pull_topology.py` | extend | +40 | strengthened assertions |
| `tests/test_push_pull_tool_closed_manifold.py` | new | +280 | 8 tests |
| `tests/test_picking_after_merge.py` | new | +60 | 1 regression guard |
| `tests/test_renderer_merged_face.py` | new | +50 | 1 regression guard |
| `docs/2026-05-16-pluton-design.md` | edit | ±5 | drop CGAL line in §M3; note inferencing → M3d |
| `docs/2026-06-10-M3c-closed-manifold-push-pull-design.md` | new | — | this doc |
| `docs/2026-06-10-M3c-closed-manifold-push-pull-plan.md` | new (next) | — | implementation plan |
| **Total** | | **~+1140 LoC**, 5 new test files | |

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `dissolve_edge` half-edge bookkeeping bugs (forgetting to update opposite pointers, leaving dangling refs) | **Medium** — half-edge dissolve is fiddly | C++ tests cover topology invariants explicitly (every half-edge's next/prev/twin/face/vertex chain must stay valid). Optional: add a `validate_invariants()` debug pass that runs after every M3c operation in test builds. |
| Coplanarity tolerance ε is wrong for some real workflows | **Low** | Defaults match SketchUp-scale architectural geometry. §7.4 carries forward as future enhancement. |
| Picking returns a stale ID after merge | **Low** | Explicit regression test. The merge's surviving face id is well-defined. |
| Visual verification surfaces a bug missed by automation (M3b lesson) | **Medium** | Visual round is a planned task in the implementation plan, not optional. |
| Bottom-cap winding regression | **Low** | Explicit unit test on normal direction. |
| Editable install `_core.pyd` shadow strikes again | **Medium** (recurring) | Pre-flight check: implementer + reviewers all run `python -c "import pluton._core; print(pluton._core.__file__)"` once before claiming tests pass. Separate `.gitignore` issue worth filing. |

## 11. Plan deliverable

The implementation plan (`docs/2026-06-10-M3c-closed-manifold-push-pull-plan.md`) is the next document, written via the writing-plans skill. Expected shape: **10-12 tasks**, similar cadence to M3b. Approximate breakdown:

1. C++: `faces_are_coplanar` + tests
2. C++: `dissolve_edge` happy path + tests
3. C++: `dissolve_edge` edge cases (boundary, multi-shared) + tests
4. nanobind bindings for both methods
5. Python: `Scene` wrappers + tests
6. Python: `DissolveEdgeCommand` + tests
7. Python: `_commit_extrusion` Case 1 (bottom-cap conditional) + tests
8. Python: `_commit_extrusion` Case 2 (seam-merge pass) + tests
9. Picking + renderer regression guards
10. Visual verification round (manual checklist)
11. CI watch + carry-over issue updates + master design edit
12. Version bump (0.0.6) + tag `v0.0.6-m3c`

Same subagent-driven workflow as M3b: per-task fresh implementer + spec reviewer + code quality reviewer.

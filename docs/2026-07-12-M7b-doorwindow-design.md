# M7b — Door/Window Placement — Design Spec

**Milestone:** M7b (second M7 "Architecture-specific tools" sub-milestone), following M7a (Wall tool, shipped v0.2.1).

**Goal:** Place parametric framed **door/window Components** onto a picked wall face — auto-oriented to the wall, vertically anchored to the floor, with identical doors/windows sharing one Component definition (real instancing). Ship as **v0.2.2**.

**One-line summary:** A `Door/Window` tool (`D`): pick a wall face, a framed door or window (procedurally generated) is placed flush to the surface and instanced; identical ones share geometry.

## Context & constraints (what shapes this design)

- **Kernel has no boolean/CSG and faces are single-loop** (no faces-with-holes). Bound mesh ops: `add_vertex`, `add_face_from_loop`, `split_edge`, `dissolve_edge`, `remove_*`/`restore_*`, `set_vertex_position`, `faces_are_coplanar`, `make_cube`, `ray_intersect_mesh`. So cutting a real opening through a solid wall is not directly supported.
- **M7a walls are baked solid-box `"Wall"` groups** with **no parametric record** — a `Definition` stores only `id / name / is_group / mesh`. There is no stored wall thickness/extent to drive a cut.
- **Given both facts, M7b does NOT cut the wall** (decision D1). A door/window is a framed Component *placed on* the wall; the solid wall remains behind it. The visual overlap between the frame and the still-solid wall is the accepted, explicit tradeoff of "no cut"; a true opening (re-tessellation or a kernel boolean) is a tracked follow-up, not this milestone.
- **Instancing already works end-to-end** — the renderer traverses shared Definitions, the M6a `.pluton` codec preserves shared Definitions by identity, and glTF export reconstructs instancing. M7b leans on this: a door/window is a shared **Component**.
- **No C++/kernel change.** Pure Python throughout, mirroring the M7a layering. `ctest` stays 79/79.

---

## Section 1 — Architecture & layering

Bottom-up, each unit independently testable (mirrors M7a's wall layering):

- **`python/pluton/geometry/opening.py`** — a **pure** generator `opening_frame(kind, width, height, depth) -> (vertices, faces)`. Numpy only; no Model/Scene/Qt/GL. Builds a framed door/window in a **canonical local frame** (origin at the opening's bottom-center; `+X` = width/along-wall, `+Y` = depth-into-wall, `+Z` = up). Reuses the `wall_box`-style outward-wound quad emitter for each solid sub-box.
- **`python/pluton/commands/opening_commands.py`** — `PlaceOpeningCommand` (undoable, model-target). Dedup-or-create a shared Component `Definition` keyed by `(kind, width, height, depth)`, then instance it with the placement transform in the active context.
- **`python/pluton/tools/opening_tool.py`** — `DoorWindowTool` (shortcut `D`). Pick a wall face → derive its frame → preview → place. Transform-aware (world → active-context-local).
- **`python/pluton/ui/opening_options_bar.py`** — `OpeningOptionsBar`: a Door|Window toggle + unit-aware `width` / `height` / `sill` / `depth` fields bound to the tool.
- **`python/pluton/ui/main_window.py`** — register the tool, host the options row (shown only while active), add the `D` shortcut + a `Tools ▸ Door/Window` entry. **Additive-only** (issue #48).

---

## Section 2 — Geometry generator

`opening_frame(kind, width, height, depth)` returns `(vertices, faces)` for a framed object assembled from closed solid sub-boxes (each outward-wound, edges shared by exactly two faces), in the canonical local frame:

- **Frame members** (a fixed internal **profile width** constant `_PROFILE`, e.g. 60 mm — **not** a user knob, per YAGNI):
  - left jamb, right jamb, head (top rail) — always present;
  - **window:** also a sill (bottom rail) → a fully enclosed frame;
  - **door:** **no bottom rail** (open threshold).
- **Infill** (centered in the frame opening, thinner than the frame depth):
  - **door:** a solid **panel** box;
  - **window:** a thin **glazing** pane (a slim box; a distinct material/name so it reads as glass).
- **Canonical origin** at the opening's **bottom-center** so the placement transform is a clean position + orient. Because the geometry is deterministic in local coords, identical `(kind, width, height, depth)` produce **identical** vertices/faces → shareable as one Component.
- Degenerate guard: non-positive `width`/`height`/`depth` (or a `width`/`height` too small to fit two profiles) → `([], [])`.

---

## Section 3 — Placement & orientation

- **Pick a wall face** under the cursor (existing face-picking / `ray_intersect_mesh` / `ON_FACE` snap). From the pick, build an orthonormal placement basis:
  - `out` = face normal (the direction the door/window faces),
  - `up` = world-Z projected onto the face plane and normalized,
  - `along` = `up × out` (horizontal, in the wall plane).
  - **Degenerate-basis guard:** on a near-horizontal face (floor/ceiling), the world-Z projection collapses toward zero and no valid `up` exists — the tool treats this as "no valid wall face" (no preview, no placement). Placement targets vertical-ish wall faces.
- **Vertical anchoring to the floor:** the frame bottom sits at the **active context's ground plane** (local `z = 0`) plus `sill` — *independent of the click's vertical position*. A **door** uses `sill = 0` (on the floor); a **window** uses `sill` (default 900 mm). The frame top is `sill + height`.
- **Horizontal:** the opening centers on the cursor's position **projected along the wall** (`along` axis). (Along-wall snapping/centering refinements are follow-ups.)
- **Depth:** the frame's **outer face is flush with the picked wall face**, extending **inward** by `depth`. The solid wall behind overlaps the frame — the accepted "no cut" tradeoff.
- **Transform-aware:** the tool converts the world-space placement basis + origin into the **active context's local frame** (via the same `world_to_local_point` / `active_world_transform` path every M4e/M7a tool uses) and hands the command a placement **transform** (a 4×4) plus the opening parameters. Placement is a no-op unless a valid wall face is under the cursor.

---

## Section 4 — Instancing & the command

- **Dedup registry:** a runtime dict on `Model` keyed by the signature `(kind, width, height, depth)` → `Definition`.
- **`PlaceOpeningCommand.do(model)`:**
  1. Look up the signature. If present → reuse that `Definition`. Else build geometry via `opening_frame`, create a **Component** `Definition` (`is_group=False`, so it is shareable/instanceable), populate its mesh, and register it under the signature.
  2. Create an `Instance` of that Definition carrying the placement transform; append it to the active context's `children`. Store the instance (and whether this call created the Definition) for undo.
  - Degenerate geometry (`opening_frame` empty) → add nothing.
- **`undo(model)`:** detach the single created instance (its subtree becomes unreachable if it was the last instance) + `revalidate_active_path()` — the same detach-undo as `ImportGltfCommand` / `CreateWallCommand`. The Definition + registry entry are **left intact for reuse** (a zero-instance Definition is harmless, exactly like a wall after undo). Redo re-runs `do()` (which will now find the registered Definition and reuse it).
- **Persistence (scoped out of M7b):** placed instances round-trip through the M6a codec with **shared Definitions preserved by identity**, so a saved file keeps the instancing. The dedup **registry** is a session-runtime convenience and is **not** persisted; re-deduplicating across a save/reload is a tracked follow-up.

---

## Section 5 — Tool, options row, MainWindow

- **`DoorWindowTool`** — shortcut **`D`**, name `"Door/Window"`. Public state (meters): `kind` (`"door"` / `"window"`), `width`, `height`, `sill`, `depth`. Defaults: **door 900 × 2100, sill 0**; **window 1200 × 1200, sill 900**. A sensible default `depth` (e.g. 100 mm).
  - `on_mouse_move`: pick the wall face → compute the preview placement transform → overlay a **frame-outline preview**.
  - `on_mouse_press`: execute one `PlaceOpeningCommand`; the tool **stays active** for repeated placements (no chaining state).
  - `apply_typed_value`: sets `width` (the primary dimension) via `parse_length`.
  - `on_key_press` Esc: clear the preview.
  - No valid wall face under the cursor → no placement (and no preview).
- **`OpeningOptionsBar`** — a **Door|Window toggle** (e.g. two radio buttons / a combo) plus unit-aware `width` / `height` / `sill` / `depth` `QLineEdit`s, bound to the tool (`refresh()` reformats from the tool; editing parses back, like `WallOptionsBar`). Switching the toggle sets `tool.kind` and reloads that kind's current dimensions; `sill` applies to windows (doors keep `sill = 0`).
- **MainWindow** — register `DoorWindowTool`, host `OpeningOptionsBar` (shown only while the tool is active, via the existing `_refresh_tool_options` hook pattern), add the `D` shortcut and a `Tools ▸ Door/Window` entry. **Additive-only**; `main_window.py` must stay at its exact pre-existing ruff-finding count (issue #48).

---

## Section 6 — Testing & version

- **Pure generator** (`tests/test_opening_geometry.py`): vertex/face counts for door vs window; every sub-box closed (each edge shared by exactly two faces); door has an **open threshold** (no bottom rail) + solid panel, window has a **sill rail** + glazing; canonical origin at bottom-center; identical params → identical geometry; degenerate params → `([], [])`.
- **Command** (`tests/test_opening_commands.py`): two identical placements → **one Definition, two Instances** (dedup); differing params → distinct Definitions; the Definition is a Component (`is_group=False`); undo detaches the instance and leaves the Definition registered; redo re-adds one instance reusing the Definition; the placement transform is applied to the instance.
- **Tool / options / MainWindow** (pytest-qt): face-pick → place; door vs window vertical anchoring (door bottom at floor, window bottom at sill); repeated placements; no-face → no placement; toggle + unit-aware fields update the tool; registration under `D`; options-bar visibility only while active.
- **Version → v0.2.2.** Python-only → **`ctest` stays 79/79**; the pytest baseline (797) grows by the new suite. Every commit SSH-signed.

---

## Decisions (D1–D10)

- **D1 — No cut.** The wall stays solid; the door/window is placed on it; overlap is accepted; real cutting is a follow-up.
- **D2 — Framed component.** Procedural frame (jambs + head + sill for windows) with a door panel / window glazing.
- **D3 — Place on a picked wall face**, auto-oriented to the face (out/up/along basis).
- **D4 — One tool** with a Door|Window toggle.
- **D5 — Shared Component per `(kind, width, height, depth)`** via a runtime dedup registry on `Model` (real instancing; `is_group=False`).
- **D6 — Outer face flush with the wall**, depth extends inward.
- **D7 — Fixed frame profile width** (internal constant, not a user knob).
- **D8 — Vertical anchored to the floor** (context ground plane): door `sill = 0`, window `sill` default 900 mm; horizontal follows the cursor along the wall.
- **D9 — Shortcut `D`**; defaults door 900 × 2100, window 1200 × 1200 (sill 900), depth 100 mm.
- **D10 — Ship v0.2.2**, Python-only (ctest 79/79).

## Out of scope (tracked follow-ups)

- **Real opening cut** through the wall (re-tessellation into surrounding panels + reveals, or a kernel boolean) — the physically-correct hole. (Relates to parametric walls, #88.)
- **Cross-session dedup** — persisting/rebuilding the opening registry so a placement after save/reload reuses an existing Definition.
- **Door swing / window operability** (swing arcs, casement/sliding types), muntins/mullions, glazing bars.
- **Along-wall snapping** (center-of-wall, equal spacing, edge offsets) and **wall-thickness-driven depth** (auto-setting `depth` from the picked wall's measured thickness).
- **Richer frame profiles** (moulding, sills with drip, thresholds) and a door/window **preset library**.
- **Attaching the opening to its host wall** (so moving/erasing the wall carries the opening).

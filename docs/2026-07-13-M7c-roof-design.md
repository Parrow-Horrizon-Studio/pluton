# M7c — Roof Tools — Design Spec

**Milestone:** M7c (third M7 "Architecture-specific tools" sub-milestone), following M7a (Wall tool, v0.2.1) and M7b (Door/Window, v0.2.2).

**Goal:** A **Roof tool** (`O`) that generates parametric **Gable / Hip / Shed** roofs as baked closed-solid `"Roof"` groups over a drawn rectangular footprint, auto-oriented and floor-plane-anchored, with the roof form and slope taken from an options row. Ship as **v0.2.3**.

**One-line summary:** Draw a rectangle footprint, pick Gable/Hip/Shed + a slope angle, and a closed solid roof is baked into the active context, ridge auto-aligned to the longer edge (flip key to swap).

## Context & constraints (what shapes this design)

- **Kernel has no boolean/CSG and faces are single-loop** (no faces-with-holes). A parametric roof is **pure polygon generation** — a closed manifold of outward-wound faces — exactly like `wall_box` (M7a) and `opening_frame` (M7b). **No C++/kernel change**; `ctest` stays **79/79**.
- **M7a walls are separate baked boxes** (a chained polyline), so there is no single building "top face" to cap. The footprint is therefore **drawn** (a rectangle), not picked — decision D2.
- **Pure Python throughout**, mirroring the M7a/M7b layering. The generator is numpy-only and headlessly testable.
- **Roofs are unique per building** (footprint dimensions vary), so — unlike M7b's shared door/window Components — a roof is a **baked group** (one `Definition` per placement), like a wall. No dedup registry.
- **Lifecycle lesson from M7b's final review:** the command uses the *correct* undo/redo instance lifecycle (`CreateInstanceCommand` pattern: cache + reuse on redo, detach from both `children` and `defn.instances` on undo), not `CreateWallCommand`'s benign-but-leaky fresh-on-redo. This pre-empts the alignment item filed as #92.

---

## Section 1 — Architecture & layering

Bottom-up, one file per stage, each independently testable (identical spine to M7a/M7b):

- **`python/pluton/geometry/roof.py`** — a **pure** `roof_solid(kind, width, depth, angle) -> (vertices, faces)`. Numpy only; no Model/Scene/Qt/GL. Builds a closed solid in a **canonical footprint frame** (centred at origin; `+X` = across-ridge span, `+Y` = along-ridge span, `+Z` = up; base at `z = 0`). `kind ∈ {"gable","hip","shed"}`. Degenerate params → `([], [])`.
- **`python/pluton/commands/roof_commands.py`** — `CreateRoofCommand` (undoable, model-target): bake the generated solid into a new `"Roof"` group in the active context; detach-undo with the clean reuse-on-redo lifecycle.
- **`python/pluton/tools/roof_tool.py`** — `RoofTool` (shortcut `O`): draw a 2-click rectangle footprint on the active drawing plane → build the roof from the options row's type + slope → place. Transform-aware (world → active-context-local, same path as the wall/rectangle tools).
- **`python/pluton/ui/roof_options_bar.py`** — `RoofOptionsBar`: a Gable|Hip|Shed toggle + a slope-degrees field, bound to the tool.
- **`python/pluton/ui/main_window.py`** — register the tool, host the options row (shown only while active), add the `O` shortcut (both a `QShortcut` and a `Tools ▸ Roof` entry). **Additive-only** (issue #48).

---

## Section 2 — Geometry generator (the three roof solids)

`roof_solid(kind, width, depth, angle)` returns `(vertices, faces)` — a closed manifold (outward-wound faces, every edge shared by exactly two faces), in the canonical frame. Footprint corners at `(±w/2, ±d/2, 0)` with `w = width` (across-ridge, X) and `d = depth` (along-ridge, Y). The ridge (where present) runs along **Y**; slopes fall toward **±X**.

- **Shed** (mono-pitch) — the top plane rises from the low eave (`x = −w/2`, `z = 0`) to the high edge (`x = +w/2`, `z = w·tan(angle)`). **6 vertices** (4 base + 2 high corners), **5 faces**: base quad, sloped-top quad, high vertical wall quad, 2 triangular sides.
- **Gable** — ridge height `h = (w/2)·tan(angle)`, ridge line from `(0, −d/2, h)` to `(0, +d/2, h)` (full depth). **6 vertices** (4 base + 2 ridge), **5 faces**: base quad, 2 sloped eave quads (±X), 2 gable-end triangles (±Y).
- **Hip** — equal pitch on all four planes ⇒ apex height `h = min(w, d)/2 · tan(angle)`, ridge set back from both ends by the hip run (`= w/2` in the `d > w` case, giving ridge length `d − w`).
  - **`d > w`:** ridge from `(0, −(d−w)/2, h)` to `(0, +(d−w)/2, h)`. **6 vertices**, **5 faces**: base quad, 2 sloped **trapezoids** (±X eaves), 2 **triangular** hip ends (±Y). (Verified closed: e.g. the ridge edge is shared by the two eave trapezoids; each hip-end run `= w/2` with rise `h` so the hip planes carry the same `tan(angle)`.)
  - **`d ≤ w`:** the ridge collapses to a point → a **pyramidal (tented) hip**, apex `(0, 0, (d/2)·tan(angle))`. **5 vertices** (4 base + apex), **5 faces**: base quad + 4 triangles.

**Degenerate guards:** `w ≤ 0`, `d ≤ 0`, or `angle` outside `(0°, 85°]` → `([], [])`. Deterministic: identical `(kind, w, d, angle)` produce identical vertices/faces.

---

## Section 3 — Tool interaction

- **Footprint gesture:** click 1 sets a corner, click 2 the opposite corner — a rubber-band rectangle on the **active drawing plane** (the same `DrawingPlane` the Rectangle/Circle tools use). Draw on the ground → roof base at `z = 0`; draw while hovering a wall-top face → the plane snaps to that height, so the roof lands **on the walls** with no separate height field.
- **Ridge orientation:** the tool maps the footprint's **shorter** edge to canonical `+X` (across-ridge) and the **longer** edge to canonical `+Y` (along-ridge), so the ridge auto-runs along the longer edge. A flip key — the **arrow keys**, via the existing M4d `on_tool_key` plumbing that polygon-sides already uses — swaps the ridge axis for Gable/Hip (and, for Shed, flips which eave is the low side). The generator is always called in its canonical frame; the tool supplies the rotation that maps canonical → the chosen world orientation.
- **Params from the options row** (not dragged): type (Gable/Hip/Shed) and slope° come from `RoofOptionsBar`, exactly as M7b reads width/height from its row — the gesture only fixes the footprint rectangle and its height plane.
- **Preview:** while dragging the second corner, the resulting roof solid's silhouette/outline edges are drawn as a **world-space** rubber-band overlay (world-space so it is correct inside an entered/transformed group — the M7b overlay-frame fix lesson). Esc cancels the in-progress rectangle.

---

## Section 4 — Instancing & the command

- **`CreateRoofCommand(kind, width, depth, angle, transform, target_context)`.** `do()` calls `roof_solid`; degenerate (empty) → add nothing. Otherwise build a new `"Roof"` **group** `Definition` (`is_group=True`), populate its mesh (`add_vertex` / `add_face_from_loop`), instance it with `transform`, append to `target_context.children`.
- **No dedup registry** — each roof is unique (this is the M7a wall model, not the M7b shared-Component model).
- **Undo/redo — clean lifecycle** (mirrors `CreateInstanceCommand`, the proven-correct pattern): cache the built `Definition` + `Instance`; **redo** re-attaches the *same* objects (re-append to `children`, and to `defn.instances` only if absent — no fresh Definition); **undo** detaches from **both** `children` and `defn.instances`, then `revalidate_active_path()`. This avoids `CreateWallCommand`'s benign-but-leaky fresh-on-redo (the alignment item in #92).

---

## Section 5 — Options row + MainWindow wiring

- **`RoofOptionsBar(tool, units_provider)`** — a **Gable|Hip|Shed** toggle (three radio buttons) + a **slope-degrees** field. The slope field parses/formats degrees (via M4d's angle helpers), clamped to `(0°, 85°]`; the toggle sets `tool.kind`; `refresh()` reloads from the tool. Same bind-to-tool shape as `WallOptionsBar` / `OpeningOptionsBar` (editing parses back; bad input ignored + field resynced).
- **MainWindow** — register `RoofTool` (`self._roof_tool`), host `RoofOptionsBar` (hidden; in the layout above the status bar), extend `_refresh_tool_options` **additively** with an `is_roof` block (do not rewrite the wall/opening blocks), and add **both** a bare-key `QShortcut("O")` (next to the other single-key tool shortcuts) **and** a `Tools ▸ Roof (O)` menu entry — the M7b lesson: the menu `\tO` is only a display hint, the `QShortcut` is what binds the key. **Additive-only**; `main_window.py` stays at its exact pre-existing ruff-finding count (issue #48).

---

## Section 6 — Testing & version

- **Pure generator** (`tests/test_roof_geometry.py`): vertex/face counts per type (shed 6/5, gable 6/5, hip `d>w` 6/5, hip `d≤w` pyramid 5/5); every edge shared by exactly two faces (closed manifold); apex/ridge height equals the `tan(angle)` derivation; canonical extents + bottom-centred origin; degenerate params → `([], [])`; identical params → identical geometry.
- **Command** (`tests/test_roof_commands.py`): one `"Roof"` group created (`is_group=True`); undo detaches and keeps `children`/`defn.instances` consistent; redo re-attaches the **same** Definition/Instance (no leak, no fresh Definition); degenerate adds nothing; the placement transform is applied to the instance.
- **Tool / options / MainWindow** (pytest-qt + headless): footprint drag → one roof placed; ridge along the longer axis; flip key swaps the ridge; type/slope read from the options row; registration under `O`; `QShortcut("O")` present on the window; options bar visible only while the tool is active.
- **Version → v0.2.3.** Python-only → **`ctest` stays 79/79**; the pytest baseline (826) grows by the new suite. Every commit SSH-signed.

---

## Decisions (D1–D10)

- **D1 — Three roof forms** (Gable, Hip, Shed) in **one Roof tool** with a type toggle.
- **D2 — Rectangle footprint drawn** on the active drawing plane (reuse `DrawingPlane`); no face-pick, no wall-loop detection.
- **D3 — Slope as an angle in degrees** (options row); ridge/apex height derived from the footprint.
- **D4 — Flush, no overhang**; roof is a **closed solid** "attic" volume (renders/paints/exports cleanly, no kernel change).
- **D5 — Baked `"Roof"` group** per placement (`is_group=True`); no dedup registry; clean reuse-on-redo undo lifecycle.
- **D6 — Ridge auto along the longer footprint edge**; a flip key swaps the ridge axis / Shed low-side.
- **D7 — Canonical frame:** `+X` across-ridge, `+Y` along-ridge, `+Z` up; base at `z = 0`.
- **D8 — Slope clamped to `(0°, 85°]`;** any degenerate footprint/angle → `([], [])`.
- **D9 — Shortcut `O`** (bare-key `QShortcut` **and** Tools menu); defaults Gable, slope 30°.
- **D10 — Ship v0.2.3**, Python-only (ctest 79/79).

## Out of scope (tracked follow-ups)

- **Eave overhang** with a proper thin fascia / soffit (better suited to a thin-slab roof model than the solid attic volume).
- **Arbitrary (non-rectangular) footprints** — polygon roofs, valleys, and true multi-plane hips via a straight-skeleton (Approach B).
- **Gambrel / mansard / dutch-gable / dormers** and other compound roof forms.
- **Roof-to-wall trimming** (cutting the wall tops to the roof underside) and attaching the roof to its host walls (move/erase together).
- **Roof thickness / rafters / ridge caps** and material-aware roofing surfaces.
- **Picking an existing face / wall-loop** as the footprint source (Approach: "cap this box").

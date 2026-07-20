# M7d — Dimensions & Annotations — Design Spec

**Milestone:** M7d (fourth M7 "Architecture-specific tools" sub-milestone), following M7a (Wall, v0.2.1), M7b (Door/Window, v0.2.2) and M7c (Roof, v0.2.3).

**Goal:** Persistent, selectable **linear dimensions** and **text labels with leaders**, drawn as screen-space annotations over the 3D viewport, stored per editing context, round-tripped through `.pluton`, and fully editable (select / erase / retype / move). Ship as **v0.2.4**.

**One-line summary:** A Dimension tool (`I`) and a Text tool (`N`) create architectural-style annotations that live in the active context, draw crisply at any zoom via `QPainter`, and can be selected, erased, retyped and moved.

## Context & constraints (what shapes this design)

- **The viewport has no text rendering at all.** No `QPainter` use, no glyph atlas, no font handling; the shaders are only `phong` / `line` / `ghost_fill`, and the renderer has **no texture support whatsoever** (M5b explicitly deferred textures). M7d must therefore introduce text rendering — and the cheapest correct route is Qt's own 2D painter over the `QOpenGLWidget`, not a GL glyph atlas (decision D3).
- **`Camera.world_to_screen(world, w, h) -> (sx, sy, depth) | None` already exists** (built in M3d) — exactly the projection primitive screen-space annotations need, depth included.
- **Annotations are a new entity class.** Unlike M7a/M7b/M7c — which all generated ordinary mesh geometry through the existing pipeline — annotations are not mesh. They need their own storage, rendering, picking, selection and persistence.
- **`Model` already has library-style state** (`materials`, `tags`) and `Definition` already holds `mesh` + `children`; the `.pluton` codec has clean top-level sections with a `schema_version` gate. Annotations follow these established shapes rather than inventing new ones.
- **Python-only. No C++/kernel change** → `ctest` stays **79/79**.

---

## Section 1 — Architecture & layering (the pure draw-plan spine)

The failure mode for an annotation system is that everything becomes untestable UI code. The spine that avoids it: **one pure function turns an annotation into screen-space primitives, and both rendering and picking consume it.**

- **`python/pluton/model/annotation.py`** — pure data. `Dimension(id, p1, p2, offset)` and `Label(id, anchor, text_pos, text)`, all coordinates **context-local**. `Model` owns `_next_annotation_id`.
- **`Definition.annotations: list[Annotation]`** — annotations live **per-context**, beside `mesh` and `children`. This is what makes them ride along when their group/component moves (D2), with no entity-reference machinery.
- **`python/pluton/annotations/draw_plan.py`** — **PURE**: `plan_annotation(ann, world_transform, camera, width, height) -> AnnotationDraw | None`, returning `segments_px`, `texts` (string + screen position + alignment) and `hit_boxes`. Projects through `Camera.world_to_screen` and lays out the full anatomy (Section 3). Numpy only — **no Qt** — so the entire geometry/layout of the feature is headlessly testable. Returns `None` when the annotation cannot be drawn (e.g. an endpoint behind the camera).
- **`python/pluton/viewport/annotation_painter.py`** — thin and UI-only: executes an `AnnotationDraw` with `QPainter` after the GL pass. Almost no logic lives here.
- **Picking** hit-tests the **same** plan's `hit_boxes`, so what the user can click is exactly what they can see, by construction — one source of truth, no drift between render and pick.
- **`python/pluton/commands/annotation_commands.py`** — `CreateDimensionCommand`, `CreateLabelCommand`, `DeleteAnnotationsCommand`, `EditLabelTextCommand`, `MoveAnnotationsCommand` (all undoable).
- **`python/pluton/tools/dimension_tool.py`** / **`text_tool.py`** — the two creation tools.
- **Integration:** `Selection.annotations`; Select/Eraser/Delete; the existing Move tool; `io/document_codec`; `ui/main_window.py` (additive — issue #48).

---

## Section 2 — Entity model & persistence

- **`Dimension`** — two context-local points `p1`, `p2`, plus an **`offset`** 3D context-local vector from the segment midpoint to the dimension-line midpoint (set by the third click). The measurement **text is derived, never stored**: computed from `‖p2 − p1‖` and formatted with the document's `Units` at draw time (D8), so switching metric↔imperial updates every dimension in the model instantly and no stored text can ever go out of sync with its own geometry.
- **`Label`** — a context-local `anchor` (the point being described), a context-local `text_pos` (where the text sits), and the `text` string. The leader is **derived** from those two points (Section 3), so moving either end re-aims it automatically.
- **Persistence** — `document_codec` gains an `"annotations"` array on each serialized `Definition`, alongside its existing geometry/children encoding, using the same index-based style. `schema_version` is bumped; reading a document **without** an `"annotations"` key yields an empty list, so older `.pluton` files continue to open unchanged.
- **Export** — annotations are deliberately **not** written to OBJ or glTF (neither format carries an annotation concept). This is a documented no-op, not a silent drop.

---

## Section 3 — Rendering & picking

- **Draw order** — annotations paint **after** the GL pass, in screen space, so they stay legible on top of geometry. Text is upright and constant pixel size at any zoom (D3). Annotations respect the active-context dim pass and tag visibility, consistent with every other entity.
- **Dimension style — "Architectural" (D4):** extension lines rise from `p1`/`p2` with a small **gap** from the geometry and a slight **overshoot** past the dimension line; **45° tick/slash** terminators at each end; the measurement text sits **above an unbroken** dimension line, centred.
- **Label style — "Classic callout" (D5):** a filled **arrowhead** at the anchor, a slanted leader that **bends into a short horizontal landing**, and the text sitting **on** the landing. The landing side (left/right) flips automatically so the text always reads away from the anchor.
- **Picking** — `pick_annotation(cursor_px, ...)` walks the visible annotations' planned `hit_boxes` (the text rectangle plus the leader / dimension-line segments) and returns the nearest hit. Pure screen-space; no ray casting.

---

## Section 4 — Tools & gestures

- **Dimension tool (`I`)** — three clicks: snap `p1`, snap `p2`, then a third click sets the **offset**. Between clicks the dimension previews live with the offset tracking the cursor. The stored offset is the perpendicular component of `(click3 − midpoint)` relative to the `p1→p2` axis, so it behaves correctly at any orientation in 3D and is trivially testable. Esc cancels; the tool stays active for the next dimension.
- **Text tool (`N`)** — click the anchor, move to position the text, click again; a **`QInputDialog`** then asks for the text. Cancelled or empty input creates nothing. Esc cancels.
- **Text entry is a dialog, not in-viewport editing (D9).** Pluton already uses this exact pattern (`_prompt_component_name` for Make Component), it is overridable for headless testing, and **the same dialog serves both create and edit** — which removes the largest chunk of new UI machinery from the milestone without losing any capability.
- Both tools are transform-aware: snapped world points are converted to the active context's local frame before being stored, the same conversion every M4e-era tool performs.

---

## Section 5 — Select, erase, edit, move

- **`Selection.annotations: set[int]`** — annotation ids, mirroring the existing `.edges` / `.faces` / `.instances`. Ids are allocated **model-wide** (from `Model._next_annotation_id`) so they are globally unique, but selection and picking operate on the **active context's** annotations only — exactly as edge/face selection operates on the active scene. Entering or exiting a group therefore changes which annotations are selectable, consistently with every other entity. The Select tool hit-tests annotations through the draw plan (click, Shift-toggle, hover highlight); the renderer highlights selected annotations in the standard selection colour.
- **Erase** — the Delete key and the Eraser tool both remove selected annotations via `DeleteAnnotationsCommand` (undoable, restoring them in place).
- **Edit text** — double-clicking a label (Select or Text tool) reopens the same dialog pre-filled with its current text, committing an undoable `EditLabelTextCommand`.
- **Move** — with annotations selected, the **existing Move tool** translates them: a Dimension's `offset` vector shifts (moving the dimension line away from or toward the geometry), while a Label's `text_pos` shifts and its `anchor` stays put so the leader re-aims itself. This reuses the M4c Move gesture and command pattern instead of introducing drag-handle machinery.
- **No options bar** for M7d — text height, tick size and arrow scale remain constants; annotation styling is a tracked follow-up.

---

## Section 6 — Testing

- **Pure `draw_plan` suite (the bulk of the coverage)** — dimension anatomy (tick placement and 45° orientation, extension-line gap + overshoot, text centred above an unbroken line), callout anatomy (arrowhead at the anchor, dogleg, landing, side-flip), a point behind the camera → `None`, and `hit_boxes` genuinely covering the text rectangle and the line segments. Entirely headless, no Qt.
- **Entity + commands** — create / delete / edit-text / move with undo-redo; per-context storage; an annotation rides along when its containing group is moved.
- **Persistence** — `.pluton` round-trip including annotations inside nested groups; a document saved without annotations still opens; changing the document's units re-derives every dimension's displayed text.
- **Tools** — the 3-click dimension gesture; the 2-click + stubbed-dialog label gesture; Esc cancellation; transform-awareness inside an entered group.
- **Integration** — selection / erase / edit / move; both tools registered with their `QShortcut`s and Tools-menu entries; `main_window.py` stays at its exact pre-existing ruff-finding count (issue #48).
- **Version → v0.2.4.** Python-only → **`ctest` stays 79/79**; the pytest baseline (852) grows substantially. Every commit SSH-signed.

---

## Decisions (D1–D12)

- **D1 — Two annotation kinds** in one milestone: linear dimensions **and** text labels with leaders.
- **D2 — Static captured points stored per-context** (`Definition.annotations`); annotations move with their group via the existing M4e hierarchy; no entity references, no auto-update on vertex edits.
- **D3 — Screen-space text via `QPainter`** over the GL pass — no glyph atlas, no texture support required.
- **D4 — Architectural dimension style**: 45° ticks, text above an unbroken dimension line, extension-line gap + overshoot.
- **D5 — Classic callout label style**: arrowhead anchor, dogleg leader, horizontal landing, text on the landing.
- **D6 — Leader-only labels** — no leaderless or screen-pinned notes.
- **D7 — A pure `plan_annotation` draw plan is the single source of truth**, shared by rendering and picking.
- **D8 — Measurement text is derived at draw time**, never stored — unit changes update all dimensions instantly.
- **D9 — Full lifecycle**: select + erase + edit text + move. Text entry via `QInputDialog` (create *and* edit); move via the existing Move tool.
- **D10 — Persistence** via a per-`Definition` `annotations` block with a `schema_version` bump; missing key reads as empty; **not** exported to OBJ/glTF.
- **D11 — Shortcuts**: Dimension `I`, Text `N`; no options bar (styling constants).
- **D12 — Ship v0.2.4**, Python-only (ctest 79/79).

## Out of scope (tracked follow-ups)

- **Angular, radial and diameter dimensions**; dimension chains/baselines.
- **Leaderless and screen-pinned notes** (SketchUp's "screen text").
- **Annotation styling options** — text height, font, colour, tick/arrow size, per-annotation overrides, and a styles UI.
- **True associativity** — attaching annotations to vertices/edges so they auto-update when geometry is edited (and the dangling-reference story that requires).
- **Depth-aware occlusion** — annotations currently always draw on top rather than being hidden behind geometry.
- **Dimension text override** — manually replacing a measured value with custom text.
- **Multi-line and rich text** labels.
- **Annotation output** — 2D drawing/PDF export, and carrying annotations into OBJ/glTF (neither format supports them).

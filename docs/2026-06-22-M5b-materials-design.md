# M5b — Materials (solid color + paint tool) — Design Spec

- **Milestone:** M5b (second sub-milestone of M5 "Materials & viewport styles", Phase 2 "Modeling App")
- **Depends on:** the renderer/scene-graph pipeline (M4e — `SceneRenderer` over `model.traverse()`); the M5a face-style resolver (`render_style.resolve_face_pass` + the phong `u_alpha` path); the tool framework (`Tool`/`ToolContext`, `pick_selectable`); the command stack (id-preserving undo); the Qt menubar + viewport (M4d/M4e).
- **Target release:** v0.1.6 (solid-color materials + paint tool).
- **Date:** 2026-06-22

---

## 1. Overview & Goals

Give the architect SketchUp's **Paint Bucket**: a small palette of named solid-color materials, a dockable Materials panel to choose the **active material**, and a **Paint tool (B)** that applies it to individual faces. This is what makes M5a's **Monochrome** vs **Shaded** distinction finally visible — Shaded now shows real per-face colors.

What ships in M5b:

- **Solid-color materials** — a `Material` is a named base RGB color. A built-in palette of ~8–12 architecture colors, plus user "Custom color…" picks.
- **Per-face painting** — one click of the Paint tool assigns the active material to the single face under the cursor. Because component instances share their definition's geometry, painting a face shows up in every instance of that component (correct SketchUp behavior).
- **Default material** — the first swatch; painting with it removes paint and returns a face to the standard look.
- **Alt-click sampling** (eyedropper) — picks up the clicked face's material as the new active material.
- **Materials dock** — a `QDockWidget` swatch grid with an active-material indicator and a custom-color button.

**Guiding constraint — reuse, don't rebuild.** Per-face color is delivered by **batching a definition's triangles by material** and drawing one batch per material through M5a's existing `resolve_face_pass(style, material=…)`. This means **no shader change** and **no change to the M5a resolver**: Monochrome / Hidden Line / X-Ray keep working per batch for free. There are **no C++ kernel changes** — material data is a Python-side sidecar keyed by face id.

**Regression safety net.** A model with zero painted faces produces exactly one batch (all triangles → the Default material) drawn with today's `_DEFAULT_MATERIAL` — so the default render path is **byte-identical to v0.1.5**.

## 2. Non-goals / Deferrals

Explicitly **out of scope** for M5b (candidate follow-ups noted):

- **Textures / UV mapping** — image loading, texture coordinates (the half-edge mesh has none today), a textured shader path, and texture-positioning UI. A whole subsystem; its own later milestone.
- **Drag-to-paint strokes** — painting a swept run of faces in one gesture (the eraser's `CompositeCommand` pattern). Deferred; M5b is one `PaintFaceCommand` per click.
- **In-place material editing / rename / delete with re-propagation** — changing a material's color and having every face using it update. Deferred; the palette is choose-and-paint only. (`add_custom` grows the palette but materials are never edited.)
- **Per-side (front/back) face materials** — SketchUp's two-sided materials. M5b is one material per face.
- **Translucent materials** (e.g. glass) — would interact with blend/depth ordering. Deferred; material colors are opaque RGB.
- **Material persistence** in the document / file format — **M6** (File I/O). Materials are session-only; the data model is intentionally serialization-ready.
- **C++ kernel changes** — none. Storage is a Python sidecar.

## 3. Data model & storage

### 3.1 `Material` (new `python/pluton/model/material.py`)

```python
@dataclass(frozen=True, slots=True)
class Material:
    id: int                              # stable, monotonic within a Model's library
    name: str                            # "Brick Red", "Concrete", custom names…
    color: tuple[float, float, float]    # base RGB in 0..1 (opaque)
```

A frozen value object. Faces reference a material by `id` (not by value), so the library owns the canonical color — SketchUp's shared model, and serialization-ready for M6.

### 3.2 `MaterialLibrary` (in the same module)

- `DEFAULT_ID = 0` — a sentinel meaning *"unpainted / standard look."* It is **never stored** in any face map; painting with `DEFAULT_ID` = clearing the face's entry. `get(DEFAULT_ID)` returns a "Default" `Material` whose `.color` is a representative gray matching the renderer's default-shaded look (`(0.65, 0.65, 0.70)`, the renderer's default diffuse — duplicated as a literal here to avoid a `viewport → model` import). That color is used **only** for the dock swatch and (if Default is active) the hover-preview tint; the renderer shades the default batch with `_DEFAULT_MATERIAL` directly (§4), never via `phong_material_for`.
- Seeds a built-in palette of ~8–12 named architecture colors (e.g. White, Warm Gray, Concrete, Brick Red, Wood Tan, Slate Blue, Forest Green, Charcoal) with stable ids `1..N`.
- `materials() -> list[Material]` — ordered list (Default first) for the dock.
- `get(mid: int) -> Material`.
- `add_custom(name: str, color) -> Material` — appends a new material with a fresh monotonic id and returns it. Not undoable (an unused material is harmless).

One `MaterialLibrary` lives on the **`Model`** (`model.materials`, seeded at construction): faces across all definitions reference its ids, the renderer already receives `model` in `render()`, and it travels with the model for M6.

### 3.3 Face → material storage (per Definition's `Scene`)

- `Scene._face_materials: dict[int, int]` — `face_id → material_id`, never `DEFAULT_ID`.
- API: `set_face_material(fid, mid)`, `clear_face_material(fid)`, `face_material(fid) -> int` (returns `DEFAULT_ID` when absent), and a read accessor used by `face_triangle_materials()` (§4).
- **No lifecycle coupling.** C++ face ids are monotonic and never reused (`halfedge.cpp:94` allocates `f_id = faces_.size()`; `halfedge.cpp:567` confirms dead slots are tombstoned). Consequences:
  - Erasing a painted face leaves a harmless **orphan** entry the renderer ignores (it only colors live faces).
  - Erase → undo restores the *same* face id via `restore_face`, so the still-present material entry re-applies — **paint survives erase/undo for free**, and no geometry command needs to know about materials.
  - Id reuse can never mis-color a new face. Orphan accumulation over a session is negligible (one dict entry per painted-then-erased face); opportunistic pruning is possible but not required.

### 3.4 Naming cleanup: `render_style.Material → PhongMaterial`

M5a's `render_style.Material` (ambient/diffuse/specular/shininess) is the phong *uniform bundle*, not a user material. To avoid two classes named `Material`, rename it to **`PhongMaterial`** (purely nominal — no behavior change, so the byte-identical regression and all M5a style tests hold unchanged) and add:

```python
_AMBIENT_FACTOR = 0.55   # shadowed areas are a darker shade of the same hue

def phong_material_for(color: tuple[float, float, float]) -> PhongMaterial:
    """Map a painted base RGB to phong uniforms:
       diffuse  = color
       ambient  = color * _AMBIENT_FACTOR
       specular = _MATERIAL_SPECULAR   (shared subtle gray highlight)
       shininess = _MATERIAL_SHININESS"""
```

The specular/shininess values are the existing shared defaults (`_MATERIAL_SPECULAR = (0.10, 0.10, 0.10)`, `_MATERIAL_SHININESS = 16.0`), so every painted material gets the same highlight character; only the hue varies. This rule deliberately does **not** try to reproduce `_DEFAULT_MATERIAL` (whose ambient/diffuse are hand-tuned and not proportional to any single base color) — unpainted faces are shaded by `_DEFAULT_MATERIAL` directly and are untouched, preserving the byte-identical regression.

## 4. Rendering — material-batched draw calls

### 4.1 Pure batching seam (new `python/pluton/viewport/face_batches.py`)

```python
@dataclass(frozen=True, slots=True)
class FaceBatch:
    material_id: int
    first: int      # first vertex index into the (reordered) face VBO
    count: int      # vertex count (a multiple of 3)

def plan_face_batches(triangle_material_ids: Sequence[int]) -> tuple[np.ndarray, list[FaceBatch]]:
    """Stable-sort triangles by material id. Returns:
       - vertex_order: an int index permutation to apply to the (3T, ·) vertex arrays
         (each triangle i expands to vertices 3i, 3i+1, 3i+2)
       - batches: one FaceBatch per distinct material, in ascending material-id order
    """
```

Pure, no GL — the testability seam. `DEFAULT_ID = 0` sorts first, so the default batch is `batches[0]` whenever unpainted faces exist.

### 4.2 `Scene` additions (no C++ change)

- `face_triangle_materials() -> np.ndarray` (length `T` = triangle count): the material id of each triangle, walking `next_live_face(0..)` ascending and emitting `face_material(fid)` repeated by that face's triangle count. This is the **exact order** the C++ `face_triangle_buffer()` uses (verified: it iterates `next_live_face` and emits `face.tris` in order), so the array aligns 1:1 with the positions buffer.
- A Python `_render_dirty` flag: `set_face_material()` / `clear_face_material()` set it; the `dirty` property returns `self._mesh.is_dirty() or self._render_dirty`; `mark_clean()` clears both (`self._mesh.mark_clean(); self._render_dirty = False`). This is what makes a paint action trigger a buffer rebuild even though no C++ geometry changed.

### 4.3 Renderer changes (`scene_renderer.py`)

- `_DefBuffers` gains `batches: list[FaceBatch]` (alongside `face_count`).
- `_upload_definition`: after building the interleaved `(3T, 6)` positions+normals, fetch `triangle_material_ids = scene.face_triangle_materials()`, call `plan_face_batches`, apply `vertex_order` to reorder the interleaved array so each material's triangles are contiguous, upload, store `buf.batches`. (When `T == 0`, `batches = []`.)
- `render()` per-definition loop — replace the single resolve+draw with a loop over `buf.batches`:

  ```python
  for batch in buf.batches:
      mat = _DEFAULT_MATERIAL if batch.material_id == DEFAULT_ID \
            else phong_material_for(model.materials.get(batch.material_id).color)
      resolved = resolve_face_pass(style, dimmed=dimmed, material=mat, …)   # M5a resolver, UNCHANGED
      if resolved.draw_faces and batch.count > 0:
          self._draw_definition_faces(buf, …, resolved=resolved,
                                      first=batch.first, count=batch.count)
  ```

- `_draw_definition_faces` gains `first`/`count` params → `glDrawArrays(GL_TRIANGLES, first, count)` instead of `0, face_count`. GL-state hygiene (blend/depth-mask enable+restore) is unchanged from M5a.

### 4.4 Why the regression invariant holds for free

Zero painted faces ⇒ every triangle maps to `DEFAULT_ID` ⇒ `plan_face_batches` returns one batch covering the whole buffer with `material_id == DEFAULT_ID` ⇒ drawn with `_DEFAULT_MATERIAL` and `vertex_order` is the identity permutation (stable sort of equal keys). Output is byte-identical to v0.1.5. Monochrome / Hidden Line / X-Ray are unaffected because each batch flows through the unchanged M5a resolver (Monochrome ignores the batch's material diffuse → all batches stay uniform; Hidden Line fills with bg; Wireframe skips the face pass entirely).

**Cost:** one extra `glDrawArrays` per distinct material per definition (negligible at architecture scale), and a stable sort only on dirty-rebuild (not per frame).

## 5. Paint tool + command

### 5.1 `PaintFaceCommand` (new `python/pluton/commands/material_commands.py`)

```python
class PaintFaceCommand(Command):
    def __init__(self, face_id: int, new_material_id: int):
        self._fid, self._new, self._old = face_id, new_material_id, None
    def do(self, scene):
        self._old = scene.face_material(self._fid)        # DEFAULT_ID if unpainted
        _apply(scene, self._fid, self._new)
    def undo(self, scene):
        _apply(scene, self._fid, self._old)
# _apply(scene, fid, mid): set_face_material if mid != DEFAULT_ID else clear_face_material
```

Captures the old material at `do()` (id-preserving undo pattern). Painting with `DEFAULT_ID` = clear; undo restores exactly, including paint→Default→undo and over-paint→undo. Operates on the active-context scene (`ctx.scene`), like the eraser.

### 5.2 `ToolContext` additions

Two new optional fields, matching the existing provider style (`units_provider`, `request_context_rebuild`):

- `active_material_provider: () -> Material` — returns the dock's current active material (tool reads `.id` to paint, `.color` to tint the hover preview).
- `set_active_material: (int) -> None` — the eyedropper pushes a sampled material id back to the dock.

### 5.3 `PaintTool` (new `python/pluton/tools/paint_tool.py`, shortcut **B**)

- `activate(ctx)` captures scene, camera, size provider, command stack, model, and the two new hooks.
- `_pick_face(event)` → `pick_selectable(cursor, viewport_size, camera, scene, world_transform=_world_transform())` filtered to `kind == "face"`; returns a face id or `None`.
- `on_mouse_press`:
  - **Alt held → sample:** `mid = scene.face_material(fid)`; `set_active_material(mid)`. Not a mutation — no command.
  - **else → paint:** `mid = active_material_provider().id`; if `fid is not None` **and** `mid != scene.face_material(fid)` (no-op guard avoids empty undo entries), push `PaintFaceCommand(fid, mid)` via `command_stack.push_executed`.
- `overlay()`: the hovered face filled with a translucent tint of the **active material's color** (live preview), reusing the eraser's transform-aware `face_fill_polygons` mechanism.
- `status_text()`: `"Paint: <name> · Alt-click to sample"`.

## 6. Materials dock + MainWindow wiring

### 6.1 `MaterialsDock(QDockWidget)` (new `python/pluton/ui/materials_dock.py`)

- A `QGridLayout` (≈4 columns) of flat colored swatch buttons built from `model.materials.materials()` — **Default** first (neutral gray = un-paint), then built-ins, then customs.
- The active swatch shows a highlighted border.
- A **"Custom color…"** button → `QColorDialog.getColor()` → `library.add_custom(name, rgb)` → new swatch appended and made active. The new material's `name` defaults to its hex string (e.g. `"#A1B2C3"`) since the color dialog yields a color, not a name.
- Clicking a swatch sets the active material and emits `active_material_changed(Material)`.
- `set_active(material_id)` — lets the eyedropper update the highlighted swatch (also updates the stored active id).

### 6.2 MainWindow

- `Model` gains `materials: MaterialLibrary` (seeded with the built-in palette).
- `self._materials_dock = MaterialsDock(self._model.materials)`; `addDockWidget(Qt.RightDockWidgetArea, dock)`.
- `self._active_material_id = MaterialLibrary.DEFAULT_ID` (starts on Default); the dock's `active_material_changed` / `set_active` keep it in sync.
- Register `PaintTool()` alongside the other tools.
- Extend the `ToolContext` in `_rebuild_tool_context()`:
  - `active_material_provider = lambda: self._model.materials.get(self._active_material_id)`
  - `set_active_material = self._materials_dock.set_active`

## 7. Testing strategy

GL pixels are not headlessly testable (no GL context in CI), so all decision logic lives in pure functions that **are** unit-tested; pixel output is verified by a manual visual pass.

**Unit-tested (pure / no GL):**

- `material.py` — `MaterialLibrary` seeds the built-in palette; `DEFAULT_ID` sentinel; `add_custom` mints fresh monotonic ids; `get`/`materials` round-trip; Default is first.
- `face_batches.py` — `plan_face_batches`: empty → no batches; single material → one batch spanning all; interleaved materials → grouped & contiguous after reorder; DEFAULT-only → one batch with identity `vertex_order`; ascending-material-id ordering is deterministic; `vertex_order` is a valid permutation of `0..3T-1`.
- `phong_material_for(color)` — diffuse == color; ambient == color × `_AMBIENT_FACTOR`; specular/shininess == the shared `_MATERIAL_SPECULAR`/`_MATERIAL_SHININESS` defaults.
- `Scene` materials — `set`/`face`/`clear_face_material`; `DEFAULT_ID` default; `_render_dirty` flips `dirty` and `mark_clean` clears it; `face_triangle_materials()` length & order align 1:1 with `face_triangle_buffer()`.
- `PaintFaceCommand` — do captures old, undo restores (paint, paint→Default, over-paint); no-op guard.
- `PaintTool` (fake context) — paint pushes a command; Alt samples without a command; no-op when material unchanged; only acts on `kind=="face"` picks.
- `MaterialsDock` (pytest-qt) — swatches built from the library; click changes active + emits; "Custom color…" appends & activates; `set_active` highlights.

**Regression invariants (must stay green / byte-identical):**

- Zero painted faces ⇒ one `DEFAULT_ID` batch with `_DEFAULT_MATERIAL` ⇒ byte-identical to v0.1.5; no shader change.
- The `Material → PhongMaterial` rename is nominal; all M5a resolver/style tests pass unchanged.
- Full suite (593 pytest + 76/76 ctest) stays green; new tests add on top.

**Manual visual pass (final task, needs the user):** paint faces with several palette colors; Default un-paints; Alt-sample picks a face's color; hover preview tints with the active color; undo/redo of paint; painted component instances all update; paint survives erase→undo; cycle all four face styles + X-Ray over a painted model (Monochrome flattens to mono, Hidden Line fills bg, Shaded shows colors, Wireframe unaffected by paint).

## 8. Deliverables & sequencing

**New files:** `model/material.py`, `viewport/face_batches.py`, `tools/paint_tool.py`, `commands/material_commands.py`, `ui/materials_dock.py`, and ~7 test files.

**Edited files:** `scene/scene.py` (materials sidecar + `face_triangle_materials` + `_render_dirty`), `model/model.py` (`materials` library), `viewport/scene_renderer.py` (batched draw loop + `first`/`count`), `viewport/render_style.py` (`Material → PhongMaterial` rename + `phong_material_for`), `tools/tool.py` (`ToolContext` fields), `ui/main_window.py` (dock + tool registration + context hooks).

**No C++ kernel changes.**

**Indicative task order** (final plan produced by writing-plans): (1) `Material`/`MaterialLibrary` + tests → (2) `render_style` rename + `phong_material_for` + tests → (3) `Scene` materials sidecar + `_render_dirty` + `face_triangle_materials` + tests → (4) `plan_face_batches` + tests → (5) renderer batched draw loop → (6) `PaintFaceCommand` + tests → (7) `ToolContext` fields + `PaintTool` + tests → (8) `MaterialsDock` + MainWindow wiring + tests → (9) full regression + manual visual pass → (10) release v0.1.6-m5b.

**Target release:** v0.1.6-m5b. Deferred items (textures, drag-paint, material editing, front/back materials, translucency) filed as follow-up issues at release.

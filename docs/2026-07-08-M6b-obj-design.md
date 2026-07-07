# M6b — OBJ Import / Export — Design

**Date:** 2026-07-08
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio) + Claude (brainstorming)
**Milestone:** M6b (second sub-milestone of M6 — File I/O), Phase 2
**Predecessor:** M6a complete (v0.1.8-m6a, native `.pluton`). Target release: **v0.1.9-m6b**.
**Issue:** #74

---

## 1. Overview & scope

M6b adds **OBJ import and export** — the second M6 sub-milestone. Pure Python
(no C++ dependency; glTF via Assimp is **M6c**, issue #75).

OBJ is a **lossy interchange bridge**, not a lossless format like `.pluton`. It
is a flat, world-space polygon soup with optional `o`/`g` object tags and a
sidecar `.mtl` for colors. It has **no** concept of components/instances/
transforms, tags, or document units. So:

- **Export** = *flatten* the scene graph to world-space geometry + write colors
  to `.mtl`. Straightforward — we already have the geometry.
- **Import** = *parse* an arbitrary `.obj` and *rebuild* half-edge topology,
  **best-effort** (a downloaded OBJ may be non-manifold / n-gon soup that the
  kernel's `add_face_from_loop` rejects).

### 1.1 Goals

1. `File ▸ Export OBJ…` — the whole model, flattened, with group/component
   structure preserved as OBJ `o` objects and painted colors in a sidecar `.mtl`.
2. `File ▸ Import OBJ…` — read `.obj` (+ `.mtl`) into the current document,
   **adaptively** (grouped files → groups; flat files → merge), best-effort,
   with a status summary.
3. An isolated, headlessly-testable OBJ codec (`ObjDocument` IR) mirroring M6a's
   `io/` layering; import is a single **undoable** command.

### 1.2 Non-goals (deferred)

- glTF / any non-OBJ format (M6c, #75).
- Normals (`vn`) and texture coords (`vt`) / UV mapping — ignored on read, not
  written on export (Pluton recomputes normals; textures are deferred since M5b).
- Texture maps in `.mtl` (`map_Kd` etc.) — color (`Kd`) only.
- Selection-only export (whole model only for M6b).
- Reconstructing Pluton's component/instance sharing or tags from an import
  (OBJ has no such concept — imports become plain groups / loose geometry).
- Non-1:1 unit scaling / axis conversion (OBJ imported/exported at 1 unit = 1 m).

---

## 2. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Direction | **Export + Import** (both) |
| D2 | Export structure | **Preserve groups** — each traversed instance → a world-space OBJ `o` object |
| D3 | Materials | **`.mtl` color round-trip** (`Kd`); `usemtl` per face; `mtllib` |
| D4 | Import placement | **Adaptive** — OBJ with `o`/`g` → one group per object in active context; flat OBJ → **merge into active scene** |
| D5 | Import robustness | **Best-effort** — skip + count faces the kernel rejects; status summary |
| D6 | Faces | **n-gons preserved** (OBJ `f` supports polygons; faithful + simple) |
| D7 | Units | **1:1** (1 OBJ unit = 1 Pluton meter; no scaling/axis conversion) |
| D8 | Normals / UVs | **Ignored** on read; **not written** on export |
| D9 | Import undo | **Undoable** — a single `ImportObjCommand` |
| D10 | Code organization | **Approach A** — pure `obj_codec` (text ↔ `ObjDocument` IR) + `obj_io` (fs + model); mirrors M6a |

---

## 3. OBJ subset + the `ObjDocument` IR

### 3.1 OBJ subset

| Directive | Read | Write |
|---|------|-------|
| `v x y z` | vertex (global pool, 1-based refs) | ✅ |
| `f a b c …` (incl. `a/vt/vn`) | face; take the **v** index only; n-gons kept | ✅ n-gons |
| `o Name` / `g Name` | starts an object; **sets `has_object_tags`** | ✅ `o` per object |
| `usemtl Name` | material for following faces | ✅ before each face run |
| `mtllib file.mtl` | names the sidecar to read | ✅ (only if materials) |
| `vn` / `vt` | **ignored** | not written |
| `newmtl` / `Kd` (in `.mtl`) | material color | ✅ |
| anything else (`s`, comments, …) | ignored | not written |

Face indices are 1-based; OBJ **negative (relative)** indices are supported on
read. `g`/`o` are treated equivalently as "object" markers (either sets
`has_object_tags`).

### 3.2 The IR (`obj_codec.py`, pure — no Qt/GL/fs/model)

```python
@dataclass(frozen=True)
class ObjFace:
    vertex_indices: tuple[int, ...]      # 0-based, into ObjDocument.vertices
    material: str | None                 # sanitized material name, or None (unpainted)

@dataclass(frozen=True)
class ObjObject:
    name: str
    faces: tuple[ObjFace, ...]

@dataclass(frozen=True)
class ObjDocument:
    vertices: tuple[tuple[float, float, float], ...]   # shared global pool (world-space)
    objects: tuple[ObjObject, ...]                      # ≥1
    materials: dict[str, tuple[float, float, float]]    # name → RGB (0..1)
    has_object_tags: bool                               # source declared o/g? → drives adaptive import
```

- **Shared vertex pool** matches OBJ semantics (`v` global; `f` references global
  indices). Objects reference into it.
- A **flat file** (no `o`/`g`) parses to a single synthetic `ObjObject`, with
  `has_object_tags=False` — the flag the adaptive import switches on.
- **Material name sanitization** is a bidirectional codec rule: on write, a
  `Model` material name like `"Brick Red"` becomes `Brick_Red` (whitespace → `_`);
  on read the OBJ name is used as-is. Round-trip through OBJ therefore renames
  spaces to underscores (an accepted OBJ limitation).

Pure codec functions:
```python
def parse_obj(obj_text: str, mtl_text: str | None) -> ObjDocument
def write_obj(doc: ObjDocument) -> tuple[str, str | None]   # (obj_text, mtl_text|None)
```
`parse_obj` raises `PlutonFormatError` (reused from M6a) on structurally invalid
content (non-numeric / out-of-range face index).

---

## 4. Export (model → `ObjDocument` → files)

`export_obj(path, model) -> None` in `obj_io.py`.

### 4.1 `model_to_objdoc(model) -> ObjDocument` (pure model→IR)

- Walk `Model.traverse()` — yields `(definition, world_transform)` for every node
  depth-first. Each node with geometry becomes one `ObjObject`.
- Per node: transform its local vertices by `world_transform` → **world-space**,
  append to the growing shared pool (track the offset). Faces (`faces_iter` →
  `loop_vertex_ids`) remap to global pool indices; each face's `material` = the
  sanitized name of `scene.face_material(fid)` via `MaterialLibrary` (Default /
  unpainted → `None`).
- Object name = `definition.name`, **de-duplicated** for OBJ uniqueness
  (`Chair`, `Chair.001`, … when a component recurs).
- Every **used** non-Default material is collected into `doc.materials`
  (sanitized name → RGB). `has_object_tags` is `True` for a non-empty model.
- A component placed 3× ⇒ 3 nodes in `traverse` ⇒ 3 world-space `ObjObject`s.

### 4.2 `write_obj(doc)` (pure IR→text, in the codec)

- `.obj`: a `mtllib <stem>.mtl` line (only if `doc.materials`), then **all `v`**
  lines (shared pool), then per object: `o <name>`, faces grouped by material —
  emit `usemtl <name>` on material change, then `f i j k …` with **1-based**
  global indices. `material=None` faces are written under no `usemtl`.
- `.mtl`: per material, `newmtl <name>` + `Kd r g b` + sane `Ka`/`Ns`/`d`
  defaults so viewers don't shade it flat-black.

### 4.3 Files (`export_obj`)

- Sidecar name = `<stem>.mtl` next to the `.obj`. Write both **atomically**
  (temp + `os.replace`, M6a pattern). No materials ⇒ no `.mtl` file, no `mtllib`.
- Empty model (root, no geometry) ⇒ a valid header-only `.obj`.
- Export never mutates the model, never sets `current_path`, never dirties the
  document (OBJ is a side export).

---

## 5. Import (files → `ObjDocument` → model)

Import is three well-separated steps: **read + parse** (`obj_io.read_obj_document`),
**adaptive best-effort build** (`obj_io.build_obj_into_model`, the one place the
build lives), and **undo wrapping** (`ImportObjCommand`, §6). `MainWindow` chains
them: read → wrap in the command → execute on the command stack.

### 5.1 Read + parse

- Read the `.obj`; if it has a `mtllib`, read that sidecar next to it (a missing
  `.mtl` → no colors, **not** an error). `parse_obj(obj_text, mtl_text)`.
- A malformed `.obj` → `PlutonFormatError` (dialog); OS errors propagate.

### 5.2 Materials into the library

- For each `doc.materials` entry, add a custom material to `model.materials`
  (`add_custom(name, color)`), **reusing** an existing material when name **and**
  color already match (re-import doesn't pile up duplicates). Build a
  `name → material_id` map.

### 5.3 Build geometry, adaptively

- **`has_object_tags == True`** → per `ObjObject`: create a `Definition`
  (`is_group=True`, named after the object), add the vertices its faces reference
  (remapped to fresh local ids), build faces, apply materials; place as an
  `Instance` (identity transform) in the **active context**. One movable group
  per OBJ object.
- **`has_object_tags == False`** → add vertices + faces **directly into the
  active scene** (`active_context.mesh`), no wrapper — merge as-is.

### 5.4 Best-effort face building + summary

- Each face is built via `add_face_from_loop`, wrapped so a face the kernel
  rejects (non-manifold, degenerate, duplicate) is **skipped and counted**,
  never aborting. Faces with < 3 unique vertices are skipped up front.
- `build_obj_into_model(doc, model, target_context) -> BuildResult` returns both
  the `ImportSummary` and the **created ids** the command needs for undo (the new
  `Instance`s + their `Definition`s in the group case; the vertex/edge/face ids in
  the merge case):

```python
@dataclass(frozen=True)
class ImportSummary:
    objects: int          # groups created (0 for the merge case)
    faces_imported: int
    faces_skipped: int

@dataclass
class BuildResult:
    summary: ImportSummary
    created_instances: list          # Instances added to target_context (group case)
    created_geometry: tuple          # (vertex_ids, edge_ids, face_ids) added to the scene (merge case)
```

`MainWindow` shows the summary: *"Imported 1,204 faces in 3 objects (skipped 12
non-manifold)."*

---

## 6. `obj_io`, the command, and File-menu UX

### 6.1 `obj_io.py` surface (fs + model orchestration; mirrors `pluton_file`)

```python
def export_obj(path, model) -> None                                  # atomic .obj (+ .mtl)
def model_to_objdoc(model) -> ObjDocument                            # export mapping (pure)
def read_obj_document(path) -> ObjDocument                           # fs read (.obj + sidecar .mtl) + parse
def build_obj_into_model(doc, model, target_context) -> BuildResult  # adaptive best-effort build (§5.3–5.4)
```
`export_obj` is pure output. `read_obj_document` does only fs + parse (no model
mutation). `build_obj_into_model` is the single place the adaptive build lives and
returns the created ids — the command wraps it for undo; tests call it directly.

### 6.2 `ImportObjCommand` (`commands/obj_commands.py`)

Single undoable wrapper around `build_obj_into_model`. `do(model)` runs the build,
stores the returned `BuildResult` (created instances/definitions in the group
case; created vertex/edge/face ids in the merge case) and its `ImportSummary`.
`undo(model)` reverses it — detach the recorded instances, or remove the recorded
faces → edges → vertices (reverse order, via `Scene.remove_*`). `redo` re-runs the
build, re-recording fresh ids (the pattern the M4e instance commands use). The
command holds the parsed `ObjDocument` + target context so `do`/`redo` are
deterministic; `MainWindow` reads `cmd.summary` for the status line.

**Materials added on import are *not* undone** (library additions are not
undoable anywhere in Pluton — consistent with M5b's add-custom). Undo removes only
the geometry/instances; a re-import reuses the already-present materials (§5.2
dedupe), so no duplication accumulates across undo/redo.

### 6.3 File menu (`MainWindow`, after Save As + a separator)

```
File ▸ …
      Import OBJ…        → _on_import_obj
      Export OBJ…        → _on_export_obj
```

- **`_on_import_obj`**: `_prompt_open_path("OBJ files (*.obj)")` →
  `doc = read_obj_document(path)` → `cmd = ImportObjCommand(doc, model.active_context)`
  → `command_stack.execute(cmd, model)` (⇒ dirties + undoable) → status-bar
  `cmd.summary` → `viewport.update()`. `PlutonFormatError`/`OSError` →
  `QMessageBox.critical`, nothing changed.
- **`_on_export_obj`**: `_prompt_save_path("OBJ files (*.obj)")` (defaulting the
  `.obj` extension) → `export_obj`. `OSError` → dialog. Export does **not** change
  `current_path` or the dirty flag.
- The existing `_prompt_open_path`/`_prompt_save_path` gain a **filter string**
  argument (used by both `.pluton` and `.obj`); they stay the overridable test
  seams from M6a.

### 6.4 No unsaved-guard on import/export

Import is an in-document, undoable edit; export writes elsewhere. Neither
replaces the document, so the New/Open discard-guard does not apply.

---

## 7. Testing strategy

### Tier 1 — codec round-trip (pure, headless; the bulk) — `tests/test_obj_codec.py`
- Single triangle / quad; **n-gon (5-gon) preserved** (not triangulated).
- Multi-object → `has_object_tags=True`, faces partitioned; flat file → one
  synthetic object, `has_object_tags=False`.
- Materials: `mtllib`/`usemtl`/`newmtl`/`Kd` round-trip; name **sanitization**
  (`"Brick Red"` ↔ `Brick_Red`); unpainted faces emit no `usemtl`.
- Face-index parsing: `a/vt/vn` triplets (take `v`), 1-based → 0-based,
  **negative/relative** indices.
- Malformed (non-numeric / out-of-range face index) → `PlutonFormatError`.

### Tier 2 — model ↔ IR (pure, real `Model`/`Scene`) — `tests/test_obj_model.py`
- **Export**: root geometry + a component placed 2× + a painted face →
  `model_to_objdoc` yields world-space verts (transform applied), one object per
  node with **de-duplicated** names, the painted material in `doc.materials`.
- **Import — grouped** (`has_object_tags=True`): one group (Definition+Instance)
  per object in active context; materials added; faces painted.
- **Import — merge** (`has_object_tags=False`): geometry in the active scene, no
  group.
- **Best-effort**: a non-manifold/degenerate face is skipped, `faces_skipped`
  counted, the rest imported.
- **Material dedupe**: same name+color twice → no duplicate library entries.

### Tier 3 — file layer (`tmp_path`) — `tests/test_obj_io.py`
- `export_obj` → real `.obj`+`.mtl` → `read_obj_document` + `build_obj_into_model`
  → geometrically-equivalent model (**end-to-end round-trip** across the real
  text/fs boundary).
- Export with no materials writes no `.mtl`; missing `.mtl` on import is
  non-fatal; corrupt `.obj` → `PlutonFormatError`; atomic export leaves the old
  file intact on injected failure.

### Tier 4 — command + MainWindow (light, pytest-qt) — `tests/test_obj_commands.py` + `tests/test_main_window_objio.py`
- `ImportObjCommand.do`/`undo`/`redo`: group case removes/re-adds the instances;
  merge case removes/re-adds the geometry.
- Import dirties the doc + shows the status summary; export leaves
  `current_path`/dirty untouched; Import/Export menu actions exist. Guarded by the
  existing autouse no-blocking-dialog fixture; prompts overridden per-instance.

### Regression bar
Full suite (**711 pytest + 76/76 ctest**) stays green — M6b is purely additive.
Manual visual pass: export a painted, grouped model → open the `.obj` in Blender
(colors + objects present); import an external OBJ → lands adaptively, bad faces
reported; `Ctrl+Z` undoes the import.

---

## 8. File inventory

**New**
- `python/pluton/io/obj_codec.py` — `ObjDocument`/`ObjObject`/`ObjFace` IR +
  `parse_obj` / `write_obj` (pure) + material-name sanitization.
- `python/pluton/io/obj_io.py` — `export_obj` / `import_obj` (fs + model) +
  `model_to_objdoc` + `ImportSummary`.
- `python/pluton/commands/obj_commands.py` — `ImportObjCommand`.
- `tests/test_obj_codec.py`, `tests/test_obj_model.py`, `tests/test_obj_io.py`,
  `tests/test_obj_commands.py`, `tests/test_main_window_objio.py`.

**Edited**
- `python/pluton/io/__init__.py` — re-export `export_obj`, `read_obj_document`,
  `build_obj_into_model`, `ImportSummary`.
- `python/pluton/ui/main_window.py` — File ▸ Import OBJ… / Export OBJ… actions +
  `_on_import_obj` / `_on_export_obj`; generalize `_prompt_open_path` /
  `_prompt_save_path` to take a filter string.

**No changes:** C++ kernel, shaders, tools/ToolContext, renderer, existing
commands' logic, version files (except the release task).

---

## 9. Regression invariants & constraints

- **Purely additive.** The only edit to existing production code is generalizing
  `_prompt_*_path` to accept a filter string (default preserves `.pluton`
  behavior) + new File-menu actions.
- **`.venv/Scripts/python`** explicitly for tests/pip.
- **Stage specific files only**; SSH-signed commits; never `--no-verify` /
  `--amend` / `--no-gpg-sign`; `Co-Authored-By: Claude Opus 4.8 (1M context)
  <noreply@anthropic.com>`.
- Preserve issue-#48 `# noqa: ANN001` markers on files that carry them; no broad
  `ruff --fix` on those. New `io/` + `commands/` files stay ruff-clean.
- Version files (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`)
  touched **only** in the release task.
- **Always run any full-suite pytest under a `timeout` wrapper** (the M6a
  modal-teardown hang history) — a healthy run is ~10s; the autouse
  `_no_blocking_close_dialog` conftest fixture prevents the known hang.

---

## 10. Deferred / follow-ups (carry-over candidates)

- glTF import/export via Assimp (M6c, #75).
- `vn`/`vt` export (nicer viewer shading) + UV import when textures land (#64).
- Texture maps in `.mtl` (`map_Kd`) once textures exist.
- Selection-only export; export options dialog (triangulate toggle, axis/units).
- Reconstruct groups' nesting / component sharing on import (OBJ is flat — a
  best-effort heuristic only).
- Import as a component (shared definition) rather than a plain group.

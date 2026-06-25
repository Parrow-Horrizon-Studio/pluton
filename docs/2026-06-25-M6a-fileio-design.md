# M6a — Native `.pluton` File I/O — Design

**Date:** 2026-06-25
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio) + Claude (brainstorming)
**Milestone:** M6a (first sub-milestone of M6 — File I/O), Phase 2
**Predecessor:** M5 complete (v0.1.7-m5c). Target release: **v0.1.8-m6a**.

---

## 1. Overview & scope

M6 (File I/O) bundles three deliverables. This spec covers only the **first**:

- **M6a (this spec): native `.pluton` save / open / new** — full round-trip of the
  in-memory document. Pure Python; **no C++ kernel, build, or CI changes**.
- **M6b (deferred): OBJ import / export** — pure Python text format.
- **M6c (deferred): glTF import / export via Assimp** — adds a C++ dependency
  (vcpkg + CMake + CI on Windows & Linux). Sequenced last because it is a
  different *kind* of work (build dependency) than the format itself.

M6a is the highest-value slice: until it ships, **nothing the user makes
persists**. It is also the lowest-risk: purely additive, isolated in a new
`pluton/io/` package, with one tiny hook added to `CommandStack`.

### 1.1 Goals

1. A `.pluton` file that round-trips the **entire document**: scene graph
   (groups/components incl. sharing), per-face materials, the material library,
   tags + visibility, document units, and the camera view.
2. A **schema-versioned** container from day 1 (the roadmap's hard requirement).
3. Standard **New / Open / Save / Save As** UX with full **unsaved-changes
   guarding** (no silent data loss).
4. The format and its (de)serialization logic live in one isolated, **headlessly
   unit-testable** package.

### 1.2 Non-goals (deferred, out of scope for M6a)

- OBJ / glTF / any non-native format (M6b / M6c).
- Textures / image assets in the file (textures themselves are deferred since M5b).
- Recent-files list, autosave / crash recovery, file thumbnails.
- Opening a file from the command line / OS file association.
- Cross-document copy/paste, external references, partial import/merge.
- Persisting undo history, selection, or the active editing path (session state).

---

## 2. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | M6 decomposition | **M6a = native format only**; OBJ → M6b, glTF/Assimp → M6c |
| D2 | File encoding / container | **Zip archive holding JSON** (`manifest.json` + `document.json`); schema-versioned |
| D3 | Save scope | **Model state + camera** (camera restores the saved view on open) |
| D4 | Unsaved-changes handling | **Full dirty-tracking + guard** (title `*`; Save/Don't-Save/Cancel on New/Open/close) |
| D5 | Code organization | **Approach A** — dedicated `io/` package, model classes stay format-agnostic; pure codec core |
| D6 | Geometry id strategy | **Index-based** encoding (compacts id gaps; rebuild via replay) for geometry; **preserve** structural `definition.id`/`instance.id` |
| D7 | Libraries on load | **Authoritative** — rebuild materials/tags from the file, not from the auto-seed |
| D8 | Camera & dirty | Camera is saved but **non-dirtying** — orbit/pan/zoom never sets the `*` (matches SketchUp) |
| D9 | `ClearSceneCommand` | **Kept** as an Edit-menu item ("Clear Active Context"); `Ctrl+N` is repurposed to File ▸ New |
| D10 | JSON formatting | **Compact** separators inside the zip (deflate handles size; unzip to inspect) |

---

## 3. The file format & schema

A `.pluton` file is a **zip archive** (`zipfile`, `ZIP_DEFLATED`):

```
myhouse.pluton  (zip)
├── manifest.json     {"format": "pluton", "schema_version": 1, "app_version": "0.1.8"}
└── document.json     the whole document (§3.2)
```

`manifest.json` is read **first** and is the version gate. `app_version`
(= `pluton._core.version()` at save time) is informational provenance;
`schema_version` is the enforced contract. Future binary assets (thumbnails,
textures) become sibling zip entries — **no format break**.

`CURRENT_SCHEMA = 1`.

### 3.1 Encoding principles

1. **Geometry is index-based.** Edges/faces reference a vertex's **position in
   `vertices[]`**, not its kernel id. On load we replay
   `add_vertex` → `add_edge` → `add_face_from_loop` (the existing
   `Model.clone_definition` pattern), so id gaps from prior deletions vanish and
   the C++ kernel re-derives fresh dense ids. Triangulation is **not** stored —
   `mapbox_earcut` recomputes it on load. `face_materials` is keyed by **face
   index** (the order faces are written == `faces_iter` order == the order they
   are rebuilt), so it re-applies deterministically.
2. **Structural ids are preserved.** `definition.id` and `instance.id` are
   written verbatim, alongside the `next_def_id` / `next_inst_id` counters. This
   makes **component sharing** round-trip (multiple children with the same
   `definition_id` rebind to one rebuilt `Definition`) and keeps post-load edits
   collision-free.
3. **Libraries are authoritative.** The full materials/tags lists (incl. Default,
   Untagged, and builtins) are written and rebuilt **from the file**, so a model
   round-trips faithfully even if a future Pluton changes the builtin palette.

### 3.2 `document.json` structure

```jsonc
{
  "units": {
    "system": "metric",          // "metric" | "imperial"
    "metric_unit": "m",          // "m" | "cm" | "mm"
    "metric_precision": 3,
    "imperial_denominator": 16
  },

  "camera": {
    "position": [8.0, -8.0, 6.0],
    "target":   [0.0,  0.0, 0.5],
    "up":       [0.0,  0.0, 1.0],
    "fov_y_deg": 45.0
  },

  "materials": {
    "next_id": 9,
    "items": [
      {"id": 0, "name": "Default", "color": [0.65, 0.65, 0.70]},
      {"id": 1, "name": "White",   "color": [0.92, 0.92, 0.92]},
      // …remaining builtins (ids 2..8)…
      {"id": 9, "name": "My Teal", "color": [0.10, 0.60, 0.60]}
    ]
  },

  "tags": {
    "next_id": 3,
    "items": [
      {"id": 0, "name": "Untagged",  "visible": true},
      {"id": 1, "name": "Walls",     "visible": true},
      {"id": 2, "name": "Furniture", "visible": false}
    ]
  },

  "model": {
    "next_def_id": 4,
    "next_inst_id": 7,
    "root_id": 0,
    "definitions": [
      {
        "id": 0, "name": "Model", "is_group": false,
        "geometry": {
          "vertices": [[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
          "edges":    [[0,1],[1,2],[2,3],[3,0]],
          "faces":    [[0,1,2,3]],
          "face_materials": {"0": 9}    // sparse: face-index → material id; unpainted omitted
        },
        "children": [
          {"id": 5, "definition_id": 1, "transform": [/* 16 floats, row-major */], "tag_id": 1}
        ]
      },
      {
        "id": 1, "name": "Chair", "is_group": false,
        "geometry": { "vertices": [/*…*/], "edges": [/*…*/], "faces": [/*…*/], "face_materials": {} },
        "children": []
        // a component referenced by several children across the tree still appears ONCE here
      }
    ]
  }
}
```

**Notes**
- `transform` is the 4×4 instance matrix flattened **row-major** (16 numbers).
- `face_materials` omits faces on the Default material (id 0); an empty map `{}`
  means "all faces unpainted."
- `root_id` identifies which definition is the scene root (id 0 in practice, but
  stored explicitly rather than assumed).

---

## 4. The codec (pure serialize / deserialize core)

Module: **`pluton/io/document_codec.py`** — **no Qt, GL, zip, or filesystem**.
Pure dict ↔ objects, so the entire round-trip is headlessly unit-testable.

### 4.1 Public surface

```python
def document_to_dict(model: Model, camera: Camera, doc: DocumentSettings) -> dict: ...
def document_from_dict(data: dict) -> LoadedDocument: ...

class LoadedDocument(NamedTuple):
    model: Model
    camera_state: CameraState   # saved fields only (position/target/up/fov_y_deg)
    units: Units
```

`document_from_dict` **builds but does not adopt** — it returns a bundle the
caller swaps in only on full success (enables the atomic load in §6). The caller
applies `camera_state` onto the live `Camera` and `units` into `DocumentSettings`.

### 4.2 Serialize — `document_to_dict`

- **Definitions are enumerated once by id** (not via `traverse`, which would
  expand shared definitions repeatedly): DFS/BFS from `root` following
  `instance.definition`, collecting into an id-keyed dict → emit the flat
  `definitions` list. A definition reached twice is emitted once (sharing
  preserved).
- **Per definition** → `geometry`:
  - iterate `vertices_iter()`, building an **id → index** remap (`clone_definition`'s
    idmap); emit `vertices` as positions in that order.
  - iterate `edges_iter()` → `[idmap[v1], idmap[v2]]`.
  - iterate `faces_iter()` → `[idmap[v] for v in loop_vertex_ids]`; in the same
    pass build `face_materials` from `scene.face_material(f_id)` keyed by the
    face's **emit index**, skipping Default (0).
  - emit `children` as `{id, definition_id: child.definition.id,
    transform: child.transform.flatten().tolist(), tag_id}`.
- **`materials`** from `library.materials()` + the library's `next_id`;
  **`tags`** from `library.tags()` + the library's `next_id` (each library
  gains a small `to_records()`/`next_id` accessor alongside its `_from_records`
  factory — see §8 — so the codec never reaches into private state).
- **`camera`** / **`units`** are trivial field reads (via small `to_dict` helpers).

### 4.3 Deserialize — `document_from_dict` (two-pass, DAG-safe)

1. **Pass 1 — skeleton:** create one empty `Definition` per record (preserving
   `id`); register in an `id → Definition` map. Build `MaterialLibrary` and
   `TagLibrary` from their records via `_from_records` factories (bypass the
   auto-seed), restoring `next_id`.
2. **Pass 2 — populate:** for each definition record:
   - rebuild geometry by replaying `add_vertex` (in `vertices` order →
     index == fresh id), `add_edge`, `add_face_from_loop`; re-apply
     `face_materials` to the new face ids in `faces_iter` order.
   - wire `children`: build `Instance`s, rebinding `definition_id → Definition`
     via the map; set `transform` (reshape 16→4×4) and `tag_id`; append to both
     parent `.children` and the child def's `.instances` (mirror
     `Model.new_instance`).
   - Restore `model.root` (via `root_id`), `model.active_path = []`,
     `model.materials`, `model.tags`, and the `_next_def_id` / `_next_inst_id`
     counters.

### 4.4 Structural validation (raises `PlutonFormatError`)

Missing required keys; a `definition_id` or `root_id` that doesn't resolve; a
`transform` that isn't 16 numbers; a face/edge index out of range; a non-list
where a list is required. The codec **never half-builds into the live model** —
it builds an isolated `Model` and only that throwaway is touched on failure.

### 4.5 Hybrid helpers

`Units`, `Material`, `Tag`, and `CameraState` carry trivial `to_dict` /
`from_dict` (or the libraries' `_from_records`) where it reads cleanly. The
graph-walking — the part with real logic — stays in the codec.

---

## 5. The file/zip layer & schema versioning

Module: **`pluton/io/pluton_file.py`** — the only part of `io/` that touches the
filesystem.

### 5.1 Public surface

```python
def save_document(path, model: Model, camera: Camera, doc: DocumentSettings) -> None: ...
def load_document(path) -> LoadedDocument: ...
```

### 5.2 `save_document`

- `data = document_to_dict(...)`; `manifest = {"format": "pluton",
  "schema_version": CURRENT_SCHEMA, "app_version": _core.version()}`.
- **Atomic write:** write the zip (both JSON blobs, compact separators) to a
  temp file in the **same directory**, then `os.replace()` onto the target. A
  crash mid-write never corrupts an existing good file.
- f64 JSON round-trips positions exactly.

### 5.3 `load_document`

1. Open zip; read `manifest.json` **first**.
2. **Version gate:**
   - `format != "pluton"` → `PlutonFormatError`.
   - `schema_version > CURRENT_SCHEMA` → `PlutonVersionError` ("made with a newer
     Pluton") — refuse rather than guess.
   - `schema_version < CURRENT_SCHEMA` → reserved migration hook; unreachable at
     v1 (the floor), but the branch exists for the future.
3. Read `document.json` → `document_from_dict(data)` → return `LoadedDocument`.

### 5.4 Error taxonomy — `pluton/io/errors.py`

```
PlutonIOError              (base)
├── PlutonFormatError      not a zip / missing entries / not "pluton" / malformed structure
└── PlutonVersionError     schema_version newer than this build supports
```

`zipfile.BadZipFile`, missing-entry `KeyError`, and `json.JSONDecodeError` are
caught inside `load_document` and re-raised as `PlutonFormatError` with a
readable message. OS-level `OSError` (permission denied, disk full, path gone)
is **left to propagate** — `MainWindow` (§6) turns both families into a dialog.
Distinction: `PlutonIOError` = "this file is bad"; `OSError` = "the filesystem
said no."

### 5.5 Package shape

```
pluton/io/
├── __init__.py          re-exports save_document, load_document, error types
├── errors.py            the exception hierarchy
├── document_codec.py    §4 (pure dict ↔ objects)
└── pluton_file.py       §5 (zip + manifest + versioning)
```

---

## 6. Document controller, dirty-state & File menu (MainWindow integration)

### 6.1 `DocumentController` (`pluton/ui/document_controller.py`)

Owns the *document session state* orthogonal to the scene graph. No Qt widgets,
so it is unit-testable.

```python
class DocumentController:
    current_path: Path | None      # None == untitled
    dirty: bool
    def mark_dirty(self) -> None: ...
    def mark_clean(self) -> None: ...
    def display_title(self) -> str # "myhouse.pluton* — Pluton" / "Untitled — Pluton"
```

`MainWindow` reads `display_title()` and calls `setWindowTitle()` whenever the
flag or path changes.

### 6.2 Dirty signal — the one `CommandStack` change

Add a change-listener fired at the end of `execute`, `push_executed`, `undo`,
and `redo`:

```python
def add_change_listener(self, fn) -> None: ...   # fn() called after any stack mutation
```

`MainWindow` registers `controller.mark_dirty`. That single hook covers **every**
geometry edit, paint, tag-assign, group/component/explode/delete op (all route
through the stack). The few **non-command** persisted mutations call
`mark_dirty()` directly at their existing handlers: add-custom-material,
add-tag, rename-tag, tag-visibility toggle, and the Units menu actions.
Camera moves and selection/enter-group do **not** dirty (D8).

### 6.3 File menu (new, inserted leftmost, before Edit)

| Action | Shortcut | Behavior |
|--------|----------|----------|
| **New** | `Ctrl+N` | guard → reset to a fresh empty `Model`/libraries/camera; `current_path=None`; clean |
| **Open…** | `Ctrl+O` | guard → `QFileDialog` → `load_document` → adopt on success (§6.5) |
| **Save** | `Ctrl+S` | if `current_path` → `save_document`; else fall through to Save As |
| **Save As…** | `Ctrl+Shift+S` | `QFileDialog` (default `.pluton`) → `save_document` → set `current_path`; clean |

`Ctrl+N` is **repurposed** from today's "clear active scene." `ClearSceneCommand`
is retained as an **Edit-menu item ("Clear Active Context")** so the (undoable,
active-context-only) capability is not silently dropped (D9).

### 6.4 The guard — `_confirm_discard_if_dirty() -> bool`

If `controller.dirty`, show a `QMessageBox` *Save / Don't Save / Cancel*:
- **Save** → run Save; returns `False` if Save is itself cancelled (e.g. Save-As
  dialog dismissed).
- **Don't Save** → proceed.
- **Cancel** → abort.

New and Open call it first. Window **close** (`closeEvent`) calls it too and
`event.ignore()`s on Cancel/failed-save. Returns whether it's safe to proceed.

### 6.5 Adopting a loaded document (atomic swap)

On successful `load_document`, `MainWindow`:
1. replaces `self._model` with the loaded `Model`;
2. applies `camera_state` onto the live `Camera`;
3. restores `units` into `DocumentSettings` (+ refresh Units menu / status);
4. rebuilds the tool context and the Materials/Tags docks against the new
   libraries;
5. clears `Selection`; **clears undo/redo stacks** (history does not cross
   documents); resets the breadcrumb;
6. sets `current_path`, marks **clean**; `viewport.update()`.

If `load_document` raised → error dialog, **nothing swapped**, current session
untouched.

`app.py` continues to start with an empty untitled document. Launch-with-file is
deferred.

---

## 7. Testing strategy

### Tier 1 — codec round-trip (pure, headless; the bulk) — `tests/io/test_document_codec.py`
Build models in memory, `document_to_dict` → `document_from_dict`, assert
structural equivalence via a helper that walks `traverse()` on both comparing
`(name, is_group, vertex positions, edges, faces, face_materials, child
transforms + tag_ids)`. Cases:
- **Empty document** (root only).
- **Flat painted cube** — geometry + `face_materials` re-applied to the right faces.
- **Geometry with id gaps** — delete verts/faces then round-trip; rebuilt mesh
  geometrically identical (the index-based-encoding lynchpin).
- **Nested groups** — transforms preserved.
- **Shared component** — one def, ≥3 instances → exactly one definition record;
  after load all instances point at the **same** `Definition` (assert identity).
- **Custom / renamed / recolored materials** — authoritative rebuild, `next_id`.
- **Tags with mixed visibility** — visibility + `next_id` survive.
- **Imperial units + non-default precision** — survive.
- **Camera** — fields survive.
- **Counters** — `next_def_id` / `next_inst_id` restored (post-load edit gets a
  non-colliding id).

### Tier 2 — file/zip layer — `tests/io/test_pluton_file.py` (`tmp_path`)
- `save_document` → real `.pluton` → `load_document` → Tier-1 equivalence.
- **Manifest gate:** `schema_version: 999` → `PlutonVersionError`;
  `format: "sketchup"` → `PlutonFormatError`.
- **Corruption:** non-zip file; zip missing `document.json`; truncated/invalid
  JSON; dangling `definition_id` → each raises the right typed error.
- **Atomic save:** save over an existing file; old file intact if a failure is
  injected mid-write.

### Tier 3 — controller/dirty (pure) — `tests/io/test_document_controller.py`
`mark_dirty`/`mark_clean` transitions; `display_title()` across
untitled/named × clean/dirty.

### Tier 4 — MainWindow wiring (light, pytest-qt, headless-safe)
Mirrors the M5 dock tests (assert state/handlers, not pixels):
- a command `execute` flips `dirty` true; Save flips clean.
- New-while-dirty invokes the guard (monkeypatch `QMessageBox` → Save /
  Don't-Save / Cancel; assert proceed/abort).
- Open success swaps the model + clears undo stack; Open failure (patched
  `load_document` raising) leaves the old model and shows a dialog.
- File-menu actions exist with the right shortcuts.

### Regression bar
Full existing suite (**674 pytest + 76/76 ctest**) stays green — M6a is purely
additive. Manual visual pass: save → quit → relaunch → open → model + camera +
materials + tags + units restored; dirty-guard prompts on New / Open / close.

---

## 8. File inventory

**New**
- `python/pluton/io/__init__.py`
- `python/pluton/io/errors.py`
- `python/pluton/io/document_codec.py`
- `python/pluton/io/pluton_file.py`
- `python/pluton/ui/document_controller.py`
- `tests/io/test_document_codec.py`
- `tests/io/test_pluton_file.py`
- `tests/io/test_document_controller.py`
- `tests/io/test_main_window_fileio.py` (Tier 4)

**Edited**
- `python/pluton/commands/command_stack.py` — add `add_change_listener` + fire it
  in `execute` / `push_executed` / `undo` / `redo`.
- `python/pluton/ui/main_window.py` — File menu; `DocumentController`; dirty
  wiring; guard; adopt-loaded-document; repurpose `Ctrl+N`; keep ClearScene on
  Edit menu; window-title updates; `closeEvent`.
- Small `to_dict`/`from_dict` (or `_from_records`) helpers on `Units`
  (`document.py`/`units.py`), `Material` + `MaterialLibrary` (`model/material.py`),
  `Tag` + `TagLibrary` (`model/tag.py`). Additive only.

**No changes:** C++ kernel, shaders, tools/ToolContext, existing commands' logic,
renderer, version files (except the release task).

---

## 9. Regression invariants & constraints

- **Purely additive.** No existing command/tool/renderer/kernel behavior changes;
  the only edit to a shared class is the additive `CommandStack` listener.
- **`.venv/Scripts/python`** explicitly for tests/pip.
- **Stage specific files only**; SSH-signed commits; never `--no-verify` /
  `--amend` / `--no-gpg-sign`; `Co-Authored-By: Claude Opus 4.8 (1M context)
  <noreply@anthropic.com>`.
- Preserve the issue-#48 `# noqa: ANN001` convention; no broad `ruff --fix` on
  files carrying intentional noqa.
- Version files (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`)
  touched **only** in the release task.

---

## 10. Deferred / follow-ups (carry-over candidates)

- OBJ import/export (M6b); glTF/Assimp (M6c).
- Recent-files list; autosave / crash recovery; file thumbnail in the zip.
- Launch-with-file / OS file association; "Revert to Saved".
- Camera near/far/aspect persistence (currently re-derived); multiple saved
  cameras / Scenes (M7).
- Textures in the container (when textures land).
```

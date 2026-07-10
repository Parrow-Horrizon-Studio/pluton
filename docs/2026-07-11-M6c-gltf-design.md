# M6c — glTF Import / Export — Design

**Date:** 2026-07-11
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio) + Claude (brainstorming)
**Milestone:** M6c (third and final sub-milestone of M6 — File I/O), Phase 2
**Predecessor:** M6b complete (v0.1.9-m6b, OBJ import/export). Target release: **v0.2.0**.
**Issue:** #75

---

## 1. Overview & scope

M6c adds **glTF import and export** — the final M6 sub-milestone and Pluton's
**first C++ format dependency (Assimp)**. Unlike OBJ (a flat world-space polygon
soup), glTF 2.0 is a **structured scene format**: a node hierarchy with
transforms, meshes shared across nodes (instancing), and PBR materials. It is
also the modern *delivery* format consumed by web viewers (`three.js`,
`<model-viewer>`), Blender, Twinmotion, and Enscape.

The milestone is **import-primary**: the hard, high-value work is reading real
third-party `.glb`/`.gltf` assets (Sketchfab, Poly Haven, Khronos samples) into
Pluton faithfully. Export is included and complete, but structurally simpler
because we own the source data.

### 1.1 The engine split (Approach B — hybrid)

- **Import → Assimp** (a C++ dependency via vcpkg, bridged with nanobind).
  Assimp decodes the messy real world for free: **Draco mesh compression**
  (`KHR_draco_mesh_compression`, the default of Sketchfab's auto-glTF export),
  sparse accessors, odd component types, `KHR_materials_*` extensions, embedded
  textures. Critically, the *same* `aiScene → Pluton Model` bridge extends to
  **FBX / USD / DAE** in the roadmap's M11 (Industry integration) — building it
  now for glTF is a strategic multiplier, not a one-off.
- **Export → pure Python.** We own the Model, and glTF is pleasant to write by
  hand (JSON + a binary buffer). A hand-written writer gives **deterministic,
  headlessly-unit-testable** output with exact control over node hierarchy,
  shared-mesh instancing, and material mapping. Routing export through Assimp
  would mean assembling an `aiScene` just to hand it back — more indirection,
  less control, and it would drag all glTF I/O behind the compiled kernel.

Each direction uses the tool it is best at, and both sides reuse M6b's proven
`codec ↔ IR ↔ model-bridge ↔ command ↔ UI` layering.

### 1.2 Goals

1. `File ▸ Import glTF…` — read a `.glb` or `.gltf` (incl. Draco-compressed) into
   the current document, **preserving the node hierarchy as nested Pluton
   groups**, **shared meshes as shared Components** (real instancing), and PBR
   base colors as Pluton materials — **best-effort**, with a status summary,
   delivered as a single **undoable** `ImportGltfCommand`.
2. `File ▸ Export glTF…` — write the whole model to `.glb` **or** `.gltf`,
   preserving hierarchy + instancing, triangulated, with `baseColorFactor`
   materials.
3. Isolated, headlessly-testable layers: a pure export `gltf_codec`, a pure
   import IR (`gltf_scene.py`), and a thin Assimp bridge whose neutral output is
   mapped into the Model in pure Python.

### 1.3 Non-goals (deferred)

- **Textures / UV mapping** — `baseColorTexture` and all texture maps are ignored
  on import and not written on export (textures deferred since M5b — issues
  #64 / #80). Only the flat `baseColorFactor` color is used.
- **Animations, skins/skeletons, cameras, lights, morph targets** — ignored on
  import; never written on export. Geometry + hierarchy + base color only.
- **Normals / UV sets** — ignored on import (Pluton recomputes normals); not
  written on export (compliant viewers compute flat normals). Smooth-normal
  export is a later nicety.
- **Draco *encoding* on export** — export is uncompressed glTF (universally
  readable). Draco is decode-only.
- **Selection-only export** — whole model only (same as OBJ; issue #81).
- **Translucency** — glTF `baseColorFactor` alpha and `KHR_materials_transmission`
  are not modeled (Pluton materials are opaque RGB; issue #68). Alpha is read but
  dropped.
- **Non-1:1 unit scaling** — glTF is meters, Pluton is 1 unit = 1 m, so scale is
  1:1; only the mandated **Y-up ↔ Z-up axis conversion** is applied.

---

## 2. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Direction | **Import and export** (both) |
| D2 | Engine | **Assimp** import bridge (C++) + **pure-Python** export (Approach B, hybrid) |
| D3 | Import bridge surface | Assimp → **neutral plain data** (nanobind structs) → pure-Python IR (`gltf_scene.py`); Assimp types never reach Python |
| D4 | Axis / units | **Y-up ↔ Z-up** conversion (Rx ±90°); **1:1** meters, no scaling |
| D5 | Hierarchy | **Preserve** node tree; **each node → one object** (single-mesh childless node collapses to a direct Component instance; multi-mesh/parent/empty node → a group); **shared mesh → shared Component** (instancing) both directions; keep empty grouping nodes |
| D6 | Import placement | One top-level group named after the file, added to the **active context**; a single **undoable** `ImportGltfCommand` |
| D7 | Robustness | **Best-effort** — triangulate + weld; skip + count faces the kernel rejects; never hard-fail |
| D8 | Materials | glTF `baseColorFactor` ↔ Pluton color; export metallic 0 / roughness 1; **textures/UVs deferred** |
| D9 | Ignored on import | animations, skins, cameras, lights, morphs, normals, UV sets |
| D10 | Export container | **`.glb` and `.gltf`** (both, via save-dialog filter); whole-model only |
| D11 | Draco | **Decoded** on import (Assimp); export **uncompressed** |
| D12 | Version | **v0.2.0** |

---

## 3. Architecture & file structure

New/modified files (mirrors M6b's split, by direction):

### C++ (import bridge only)
- **Create** `cpp/include/pluton/gltf_import.h` — declares the neutral result
  structs + `import_gltf(path)`.
- **Create** `cpp/src/gltf_import.cpp` — the Assimp wrapper. Added to the
  `pluton_core` STATIC library source list in `cpp/CMakeLists.txt`.
- **Modify** `cpp/bindings/module.cpp` — nanobind bindings exposing
  `_core.import_gltf` + the read-only result structs.
- **Create** `cpp/tests/test_gltf_import.cpp` — GoogleTest over a sample file;
  registered in `cpp/tests/CMakeLists.txt`.

### Python — import
- **Create** `python/pluton/io/gltf_scene.py` — **neutral IR** dataclasses
  (`GltfSceneData`, `GltfNode`, `GltfMesh`, `GltfMaterial`) + axis constants.
  Pure: no Model, no `_core`, no Assimp. The bridge structs adapt into these, and
  the whole import-mapping layer is testable with hand-built fixtures.
- **Create** `python/pluton/io/gltf_import.py` — `read_gltf_scene(path)` (calls
  `_core.import_gltf`, adapts to the IR, maps errors to `pluton.io.errors`) +
  `build_gltf_into_model(scene, model, target_context) -> GltfBuildResult`. The
  **only** glTF module that imports Model/Scene.
- **Create** `python/pluton/commands/gltf_commands.py` — `ImportGltfCommand`
  (`do`/`undo`/`.summary`), mirroring `ImportObjCommand`.

### Python — export
- **Create** `python/pluton/io/gltf_codec.py` — **pure** buffer/JSON assembly: a
  `GltfAsset` builder (accessors, bufferViews, one binary buffer) →
  `write_glb(asset) -> bytes` and `write_gltf(asset, bin_name) -> (json_text,
  bin_bytes)`. No Model deps.
- **Create** `python/pluton/io/gltf_export.py` — `model_to_gltf(model) ->
  GltfAsset` (hierarchy, triangulation, Z-up→Y-up, materials) + atomic
  `export_gltf(model, path)` (dispatches `.glb` vs `.gltf` by suffix).

### Shared
- **Modify** `python/pluton/io/__init__.py` — re-export the public glTF entry
  points (`read_gltf_scene`, `build_gltf_into_model`, `export_gltf`,
  `GltfBuildResult`, `GltfImportSummary`).
- **Modify** `python/pluton/ui/main_window.py` — `File ▸ Import glTF…` /
  `Export glTF…` actions + `_on_import_gltf` / `_on_export_gltf`, reusing the
  generalized `_prompt_open_path(file_filter, title)` /
  `_prompt_save_path(file_filter, title)` from M6b.

### Build
- **Modify** `vcpkg.json` — add `assimp` (with Draco support).
- **Modify** `CMakeLists.txt` (top level) — `find_package(assimp CONFIG
  REQUIRED)`; link `assimp::assimp` into `pluton_core`.

---

## 4. The C++ import bridge (`gltf_import.cpp`)

A deliberately thin wrapper. **Assimp types never cross the nanobind boundary** —
the bridge walks `aiScene` and copies into neutral C++ structs of plain scalars
and vectors:

```cpp
namespace pluton {

struct ImportedMaterial {
    std::string name;                 // "" if unnamed
    std::array<float, 4> base_color;  // RGBA baseColorFactor; alpha kept, dropped in Python
};

struct ImportedMesh {
    std::vector<std::array<float, 3>> positions;   // per-vertex, mesh-local
    std::vector<std::array<uint32_t, 3>> triangles;// index triples into positions
    int material_index;                            // -1 = none
};

struct ImportedNode {
    std::string name;                 // "" if unnamed
    int parent;                       // -1 for a root node
    std::array<float, 16> transform;  // node-local, row-major (Assimp convention)
    std::vector<int> mesh_indices;    // indices into ImportedScene.meshes
};

struct ImportedScene {
    std::vector<ImportedNode> nodes;      // flattened, parent-before-child order
    std::vector<ImportedMesh> meshes;     // deduplicated by aiMesh index (enables instancing)
    std::vector<ImportedMaterial> materials;
};

// Throws std::runtime_error on a load failure (missing file, undecodable) —
// bound so nanobind surfaces it as a Python exception mapped to PlutonIOError.
ImportedScene import_gltf(const std::string& path);

}  // namespace pluton
```

**Postprocessing flags:** `aiProcess_Triangulate` (n-gons → triangles) +
`aiProcess_JoinIdenticalVertices` (weld, so shared edges rebuild clean topology).
We deliberately **do not** request normal/tangent generation or UV flips — those
outputs are ignored. Draco is decoded transparently by the glTF importer when the
vcpkg `assimp` build includes it (verified in Task 0).

**Mesh dedup for instancing:** Assimp meshes are already deduplicated by index;
an `aiMesh` referenced by multiple `aiNode`s appears once in
`ImportedScene.meshes` and is referenced by index from each node — this is what
lets the Python builder reconstruct shared Components.

**Node flattening:** the recursive `aiNode` tree is emitted as a flat vector in
**parent-before-child** order with `parent` back-indices, so the Python side can
rebuild the tree in a single forward pass.

**nanobind binding (`module.cpp`):** expose `import_gltf` and the four structs as
read-only classes (fields exposed via `.def_ro`). Arrays surface as Python
tuples/lists of floats/ints.

---

## 5. The neutral IR (`gltf_scene.py`)

Pure-Python dataclasses that mirror the bridge structs 1:1, so
`build_gltf_into_model` never touches `_core` and is fully unit-testable with
hand-built fixtures:

```python
@dataclass(frozen=True)
class GltfMaterial:
    name: str
    color: tuple[float, float, float]   # RGB; alpha dropped

@dataclass(frozen=True)
class GltfMesh:
    positions: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    material_index: int                 # -1 = none

@dataclass(frozen=True)
class GltfNode:
    name: str
    parent: int                         # -1 = root
    transform: tuple[float, ...]        # 16 floats, row-major
    mesh_indices: tuple[int, ...]

@dataclass(frozen=True)
class GltfSceneData:
    nodes: tuple[GltfNode, ...]
    meshes: tuple[GltfMesh, ...]
    materials: tuple[GltfMaterial, ...]
```

`read_gltf_scene(path)` calls `_core.import_gltf`, copies fields into these
dataclasses, and wraps any `RuntimeError`/`OSError` into a
`PlutonFormatError` / `PlutonIOError` (from `pluton.io.errors`).

---

## 6. Import mapping (`build_gltf_into_model`)

Signature:
```python
def build_gltf_into_model(scene, model, target_context) -> GltfBuildResult: ...
```

### 6.1 Axis & units
glTF is **Y-up**; Pluton is **Z-up**. Rather than rotate every node, the
conversion is baked into the **file wrapper group's transform** (§6.3): a single
Rx +90° matrix `A`. Assimp node transforms are **row-major**; the adapter
transposes each 16-float array to Pluton's numpy 4×4 convention (verified against
`pluton.geometry.transforms` in the import task). Scale is 1:1.

### 6.2 Meshes → shared Component Definitions
Build each `GltfMesh` **once** into its own Definition and cache by mesh index:
```
meshdef[i] = model.new_definition(name_or("Mesh"), is_group=False)   # a Component
# weld positions → local vertex ids, best-effort faces (triangles), apply material
```
- Vertices: `meshdef[i].mesh.add_vertex(np.array([x, y, z], np.float32))`,
  index-mapped like `build_obj_into_model`.
- Faces: each triangle via `add_face_from_loop`, **best-effort** — degenerate
  (<3 unique) or kernel-rejected triangles are skipped + counted (reuse the
  `_add_faces` pattern from `obj_io`).
- Material: if `material_index >= 0`, resolve to a Pluton material id via a
  shared `_ensure_materials`-style dedup (by name **and** color) and
  `set_face_material` per built face.

Because a mesh is built once and referenced by many nodes, **instancing is
preserved**: N nodes referencing mesh i → N Instances of `meshdef[i]`.

### 6.3 Nodes → hierarchy (each node → one object)
This mirrors how reference glTF importers (Blender) map a scene: **a node
becomes exactly one object**, not an object-wrapped-in-a-group. This preserves
instancing *and* keeps the scene graph clean, and it avoids a correctness trap
(see below).

Precompute which nodes have children (a node is a **container** iff it has any
child node): `has_children = {n.parent for n in scene.nodes if n.parent >= 0}`.
Then process nodes in **parent-before-child** order:

```
collapsible = (len(node.mesh_indices) == 1) and (n not in has_children)

if collapsible:                                   # common leaf case
    inst = model.new_instance(meshdef[node.mesh_indices[0]], transform=A4x4)
    # no container: a collapsed node can have no children by definition
else:
    g = model.new_definition(node.name or "Node", is_group=True)
    for mi in node.mesh_indices:                  # this node's own geometry
        g.children.append(model.new_instance(meshdef[mi]))   # identity transform
    inst = model.new_instance(g, transform=A4x4)
    container_def[n] = g                          # children append here

parent_container = wrapper_def if node.parent == -1 else container_def[node.parent]
parent_container.children.append(inst)            # parent is always a container
```
`A4x4` = the node's local transform (Assimp row-major → transposed to Pluton).
A node's parent is guaranteed to be a container (it has this node as a child), so
`container_def[parent]` always exists.

- **The correctness trap the collapse avoids:** a node with *both* a mesh and
  children must get its own group — if such a node instead pointed its Instance
  directly at a shared mesh Component, its children would become children of that
  Component and leak into **every** other instance of the same mesh. Only
  single-mesh **childless** nodes are collapsed, so this can't happen.
- **Empty grouping nodes** (no meshes, transform only) → empty groups; hierarchy
  preserved honestly (D5).
- **Instancing is preserved regardless of collapse:** the shared unit is always
  the mesh `meshdef[i]` Component; N nodes referencing mesh i → N Instances of
  it, collapsed or grouped.
- A collapsed leaf inherits the Component's (mesh) name; the node's own name is
  not separately modeled (Instances are unnamed) — the standard trade-off, and
  what Blender does.
- The **file wrapper**: `wrapper_def = model.new_definition(<file stem>,
  is_group=True)`; its Instance carries the Y-up→Z-up matrix `A` and is the
  single node appended to `target_context.children`. Root glTF nodes hang under
  `wrapper_def`.

### 6.4 Result & summary
```python
@dataclass(frozen=True)
class GltfImportSummary:
    nodes: int          # glTF nodes mapped (one object each — collapsed or grouped)
    meshes: int         # distinct meshes built (shared Components)
    faces_imported: int
    faces_skipped: int

@dataclass
class GltfBuildResult:
    summary: GltfImportSummary
    root_instance: object          # the single Instance appended to target_context.children
```
Status line (MainWindow): *"Imported {nodes} objects, {faces_imported} faces
(skipped {faces_skipped})."*

### 6.5 Undo cleanliness
Definitions are **not** globally registered (`Model.new_definition` only mints an
id; see `model.py`). Nothing is reachable except through `children`. So undo is:
**remove `root_instance` from `target_context.children`**, then
`model.revalidate_active_path()` (in case the user had entered the imported
group). The whole imported subtree — wrapper, node groups, mesh components,
geometry — becomes unreachable and is not traversed or serialized. This is
strictly simpler than OBJ's undo (which had a merge case with explicit
face/edge/vertex removal) because glTF import **always** produces a single
wrapped group — there is no bare-merge path. Redo re-runs `do()` (fresh ids),
matching the M6b command model (no separate `redo`).

As with `ImportObjCommand`, **materials added to the library are not undone** —
library additions are not undoable anywhere in Pluton, and a re-import reuses
them via the name+color dedup in `_ensure_materials`.

---

## 7. `ImportGltfCommand` (`commands/gltf_commands.py`)

Mirrors `ImportObjCommand`:
```python
class ImportGltfCommand(Command):
    name = "Import glTF"
    def __init__(self, scene, target_context):
        self._scene = scene
        self._target = target_context
        self._result = None
        self.summary = None
    def do(self, model):
        self._result = build_gltf_into_model(self._scene, model, self._target)
        self.summary = self._result.summary
    def undo(self, model):
        if self._result is None:
            return
        if self._result.root_instance in self._target.children:
            self._target.children.remove(self._result.root_instance)
        model.revalidate_active_path()
        self._result = None          # guard double-undo (redo re-runs do())
```
(Exact `Command` ABC signature — `do(self, target)` / `undo(self, target)` and
whether `target` is the Model or Scene — is matched to the codebase in the
command task, same as M6b.)

---

## 8. Export (`gltf_codec.py` + `gltf_export.py`)

### 8.1 Mapping (`model_to_gltf`)
The mirror of import. Walk the scene graph and emit glTF nodes/meshes:
- Each **Instance** → a glTF **node** with its transform (Z-up→Y-up applied at
  the root wrapper node, inverse of import).
- Each **shared Definition** → **one glTF `mesh`** referenced by every node whose
  Instance points at it — instancing preserved outward (cache by definition id).
- A Definition's `mesh` faces (possibly n-gons) are **fan-triangulated** and
  grouped **by material into primitives** (one `primitive` per material per
  `mesh`, like M6b's `usemtl` runs / M5b's `plan_face_batches`).
- **Materials → PBR:** each Pluton `Material` → a `pbrMetallicRoughness` with
  `baseColorFactor = [r, g, b, 1]`, `metallicFactor = 0`, `roughnessFactor = 1`.
  Unpainted (Default) faces → a single default material / no material ref.
- **Normals omitted** (positions + indices only).

### 8.2 Buffer assembly (`gltf_codec.py`, pure)
`GltfAsset` collects accessors (positions `VEC3`/`FLOAT`, indices `SCALAR`/
`UNSIGNED_INT`), bufferViews, and one packed binary buffer, and computes accessor
`min`/`max` for positions (required by the spec).
- `write_glb(asset) -> bytes`: the 12-byte header + JSON chunk (4-byte aligned,
  space-padded) + BIN chunk (4-byte aligned, zero-padded).
- `write_gltf(asset, bin_name) -> (json_text, bin_bytes)`: JSON with a
  `buffers[0].uri = bin_name`, plus the sidecar `.bin`.

### 8.3 Filesystem (`gltf_export.py`)
`export_gltf(model, path)` dispatches by suffix:
- `.glb` → one atomic write of `write_glb(...)` (temp + `os.replace`).
- `.gltf` → atomic write of the JSON to `path` and the `.bin` sidecar to
  `path.with_suffix(".bin")` (both atomic, like OBJ's sidecar `.mtl`).

---

## 9. MainWindow wiring

- `File ▸ Import glTF…` → `_on_import_gltf`: `_prompt_open_path("glTF (*.glb
  *.gltf)", "Import glTF")` → `read_gltf_scene(path)` → execute
  `ImportGltfCommand(scene, model.active_context)` on the command stack → status
  summary. Errors (`PlutonIOError`) → a non-fatal message box.
- `File ▸ Export glTF…` → `_on_export_gltf`: `_prompt_save_path("glTF Binary
  (*.glb);;glTF (*.gltf)", "Export glTF")` → `export_gltf(model, path)`.
- Cancelled dialogs (path `None`) early-return. Reuses the generalized prompts
  from M6b (no-arg `.pluton` callers stay intact).

---

## 10. Build & CI

- **`vcpkg.json`:** add `assimp` with Draco. The exact feature spelling is
  confirmed in **Task 0** (either a `draco` feature on the port or Assimp's
  bundled Draco via a CMake option). Prefer a **static** triplet
  (`x64-windows-static-md` on Windows) so the wheel needs no bundled runtime
  DLL; otherwise ensure the Assimp DLL is discoverable/bundled.
- **`CMakeLists.txt`:** `find_package(assimp CONFIG REQUIRED)`; link
  `assimp::assimp` into `pluton_core` (PRIVATE — the public header exposes only
  neutral structs).
- **CI:** vcpkg compiles Assimp (+Draco) on `windows-2022` and `ubuntu-24.04` —
  noticeably longer **cold** builds; the wheel grows. Acceptable; expected. Rely
  on the existing vcpkg binary cache where present.
- **Baseline to preserve:** 740 pytest + 76/76 ctest green (v0.1.9-m6b).

---

## 11. Testing strategy

Layered; most of it headless (no compiled kernel needed):

1. **`gltf_codec` (pure):** assemble a `GltfAsset` for a known cube; assert
   `.glb` chunk framing, 4-byte alignments, accessor byte layout + `min`/`max`;
   round-trip through a tiny in-test reader; assert `.gltf` JSON + `.bin` split.
2. **`build_gltf_into_model` (pure IR fixtures):** hand-built `GltfSceneData` →
   assert (a) nested groups match the node tree, (b) a mesh referenced twice →
   **one Definition, two Instances** (instancing), (c) material dedup by
   name+color, (d) Y-up→Z-up applied, (e) best-effort skip counts, (f) empty
   grouping node → empty group, (g) `GltfBuildResult.root_instance` is the sole
   child added to `target_context`.
3. **`ImportGltfCommand` (pure):** `do` then `undo` leaves `target_context`
   byte-for-byte as before (no orphaned children, active path revalidated);
   redo (`do` again) rebuilds.
4. **Bridge integration (needs kernel):** small **self-authored** files in
   `tests/data/` — a single triangle `.glb`, a `.gltf`+`.bin` pair, a two-node
   hierarchy, a shared-mesh instanced file (asserts collapse + one Component /
   two Instances) — plus **one vendored CC0 Draco sample** (Khronos `Box`,
   license verified) — exercising `_core.import_gltf` and the full
   `read_gltf_scene → build` path. **The Draco decode test is a permanent,
   non-skippable CI gate on both platforms** — it is the guard that the Assimp
   dependency still provides the capability that justified taking it on (a future
   vcpkg `assimp` bump that drops Draco must fail CI here, not degrade silently).
5. **Export round-trip:** build a Model (a painted, grouped scene) → `export_gltf`
   (`.glb` and `.gltf`) → re-read via `_core.import_gltf` → assert geometry,
   material colors, and hierarchy/instancing survive.
6. **MainWindow:** `File ▸ Import/Export glTF` actions exist; handlers call the
   right io functions (mocked); cancelled dialog early-returns — like
   `test_main_window_objio.py`.
7. **C++ GoogleTest:** `test_gltf_import.cpp` loads a sample and asserts
   node/mesh/material counts + triangulation.
8. **Regression:** full pytest + ctest stay green (run under the usual timeout
   guard); nanobind at-exit "leaked function" noise remains benign.
9. **Manual visual pass (user):** import a real downloaded `.glb` (Draco) — stands
   upright, hierarchy visible in the outliner, colors present; export the result
   to `.glb`, re-import to confirm the round-trip.

---

## 12. Task decomposition preview

Sequenced so the build risk is retired first, then import (the value), then
export, then integration/release (~14 tasks — final count set by writing-plans):

0. **Build spike** — `vcpkg.json` + CMake `find_package(assimp)` + stub
   `gltf_import.cpp`; prove local link + a plain `.glb` decode + **a Draco `.glb`
   decode**; fix triplet/DLL bundling.
1. C++ `import_gltf` full walk → neutral structs + GoogleTest.
2. nanobind binding (`_core.import_gltf` + structs) + smoke test.
3. `gltf_scene.py` IR + `read_gltf_scene` adapter (bridge → IR, error mapping).
4. `build_gltf_into_model` meshes → shared Components (instancing + best-effort).
5. `build_gltf_into_model` nodes → hierarchy (each node → one object: leaf
   collapse vs group) + axis + wrapper + summary.
6. `ImportGltfCommand` (undo cleanliness) + pytests.
7. `gltf_codec.py` pure buffer/`.glb`/`.gltf` assembly + tests.
8. `gltf_export.py` mapping (hierarchy, triangulation, materials, axis) + atomic write.
9. Export round-trip tests.
10. MainWindow Import/Export glTF actions + handlers + tests.
11. `tests/data/` sample fixtures (+ CC0 Draco sample) + bridge integration tests.
12. Full regression + master design-doc annotation.
13. Manual visual pass (user) + release **v0.2.0** (version bump, tag, CI,
    carry-over issues).

---

## 13. Release

- **Version:** `0.2.0` (pyproject.toml / CMakeLists.txt / cpp/src/version.cpp) —
  bumped **only** in the release task.
- Master design doc (`docs/2026-05-16-pluton-design.md`) M6 line annotated: M6c
  ✅ *(shipped v0.2.0)*, closing the M6 File-I/O arc.
- Tag `v0.2.0`; push main + tag; CI green both platforms.
- Close tracking issue **#75**; file carry-over issues for the deferred niceties
  (glTF textures/UV, smooth-normal export, selection-only export overlap with
  #81, animations/cameras, `.gltf` external-texture resolution).

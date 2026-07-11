# M6c — glTF Import / Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add glTF import (Assimp-backed, Draco-capable, hierarchy-preserving, best-effort, undoable) and export (pure-Python `.glb`/`.gltf`) to Pluton, shipped as v0.2.0.

**Architecture:** Hybrid engine (spec Approach B). Import goes through a thin Assimp C++ nanobind bridge that returns neutral plain data → a pure-Python IR (`gltf_scene.py`) → a Model builder (`gltf_import.py`) wrapped in an undoable `ImportGltfCommand`. Export is a pure-Python writer: a Model→`GltfAsset` mapping (`gltf_export.py`) over a pure buffer/JSON codec (`gltf_codec.py`). Mirrors M6b's `codec ↔ IR ↔ model-bridge ↔ command ↔ UI` layering.

**Tech Stack:** C++20 + Assimp (vcpkg) + nanobind; Python 3.13 + numpy; PySide6 (menu wiring only); pytest + GoogleTest.

**Spec:** `docs/2026-07-11-M6c-gltf-design.md` (decisions D1–D12).

## Global Constraints

*(Every task's requirements implicitly include this section. Values copied verbatim from the spec + standing project constraints.)*

- **Layering (D2, D3, D10):** `gltf_codec.py` and `gltf_scene.py` are **pure** — no Model, no `_core`, no Assimp, no Qt, no filesystem (except `gltf_export.py`, which owns fs writes). Only `gltf_import.py` and `gltf_export.py` import Model/Scene. The C++ bridge never leaks Assimp types across nanobind.
- **Axis/units (D4):** glTF is Y-up meters; Pluton is Z-up meters. Import bakes a single **Y-up→Z-up** matrix `A = Rx(+90°)` into the file-wrapper instance; export bakes `A⁻¹ = Rx(−90°)`. Scale 1:1. Node transforms are otherwise unchanged.
- **Best-effort (D7):** never hard-fail an import on bad geometry — build each triangle via `add_face_from_loop`, skip + count rejects (reuse the `_add_faces` pattern from `obj_io`). A whole-file load failure raises `PlutonFormatError`/`PlutonIOError`; the UI shows a message box (non-fatal).
- **Materials (D8):** glTF `baseColorFactor` (RGB; alpha dropped) ↔ Pluton `Material` color; export `metallicFactor=0`, `roughnessFactor=1`. Dedup by name+color. Assimp's synthesized default material (name `""`/`"DefaultMaterial"`) maps to Pluton **Default** (unpainted). Textures/UVs deferred.
- **Ignored on import (D9):** animations, skins, cameras, lights, morphs, normals, UV sets.
- **Undo:** import is a single `ImportGltfCommand`; `undo` removes the one wrapper Instance from `target_context.children` + `model.revalidate_active_path()`. Material-library adds are not undone (parity with `ImportObjCommand`).
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) are edited **only in the release task (Task 13)**. Baseline: `0.1.9` → `0.2.0`.
- **Tests:** run the full suite under a timeout guard: `timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider` (healthy ≈ 10–15 s). C++: `ctest` in `build/cp313-cp313-win_amd64`. Pre-M6c baseline: **740 pytest + 76/76 ctest** green. Use `.venv/Scripts/python` explicitly.
- **Git:** stage specific files only (no `git add -A`/`.`). SSH-signed commits; never `--no-verify`/`--amend`/`--no-gpg-sign`. Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Work on `main`. Verify signature via `git cat-file -p <sha> | grep -c "BEGIN SSH SIGNATURE"` (==1); `git log --show-signature` printing "No signature" is a KNOWN local `allowedSignersFile` gap, not a failure.
- **ruff:** new `io/`, `commands/`, and C++-adjacent Python files must be ruff-clean (`select = ["E","F","W","I","N","UP","B","C4","RUF"]`). NEVER run broad `ruff --fix` on `main_window.py` (issue #48: deliberate `# noqa`). CI does not gate ruff.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.

---

## File Structure

**C++ (import bridge):**
- Create `cpp/include/pluton/gltf_import.h` — neutral result structs + `import_gltf(path)` declaration.
- Create `cpp/src/gltf_import.cpp` — Assimp wrapper; added to `pluton_core` in `cpp/CMakeLists.txt`.
- Modify `cpp/bindings/module.cpp` — nanobind bindings for `import_gltf` + the four structs.
- Create `cpp/tests/test_gltf_import.cpp` — GoogleTest over a sample; registered in `cpp/tests/CMakeLists.txt`.

**Python — import:**
- Create `python/pluton/io/gltf_scene.py` — neutral IR dataclasses.
- Create `python/pluton/io/gltf_import.py` — `read_gltf_scene` + `build_gltf_into_model` (+ `GltfImportSummary`, `GltfBuildResult`).
- Create `python/pluton/commands/gltf_commands.py` — `ImportGltfCommand`.

**Python — export:**
- Create `python/pluton/io/gltf_codec.py` — pure `GltfAsset` builder → `.glb`/`.gltf` bytes.
- Create `python/pluton/io/gltf_export.py` — `model_to_gltf` + atomic `export_gltf`.

**Shared:**
- Modify `python/pluton/io/__init__.py` — re-export public glTF entry points.
- Modify `python/pluton/ui/main_window.py` — File ▸ Import/Export glTF actions + handlers.

**Build:**
- Modify `vcpkg.json` — add `assimp`.
- Modify `CMakeLists.txt` — `find_package(assimp)` + link.
- Modify `.github/workflows/build.yml` — enable vcpkg binary caching so Assimp doesn't rebuild from source every run.

**Tests / fixtures:**
- Create `tests/data/gltf/` — self-authored `.glb`/`.gltf` samples + one vendored CC0 Draco `.glb`.
- Create `tests/test_gltf_*.py` — codec, IR, build, command, export, MainWindow, bridge-integration suites.

---

### Task 0: Build integration spike (retire the Assimp/Draco/CI risk first)

**Goal:** Prove — before any feature code — that Assimp builds and links into `_core` locally, that a plain `.glb` and a **Draco-compressed** `.glb` both decode, and that CI won't rebuild Assimp from scratch every run. This is the whole justification for the C++ dependency; if Draco doesn't come through, we learn it now.

**Files:**
- Modify: `vcpkg.json`
- Modify: `CMakeLists.txt`, `cpp/CMakeLists.txt`
- Create: `cpp/include/pluton/gltf_import.h`, `cpp/src/gltf_import.cpp` (stub)
- Modify: `cpp/bindings/module.cpp` (minimal `import_gltf` returning a stub)
- Create: `tests/data/gltf/plain_box.glb`, `tests/data/gltf/draco_box.glb`
- Modify: `.github/workflows/build.yml`

**Interfaces:**
- Produces: `_core.import_gltf(path: str) -> object` (stub returns an object exposing `.nodes`, `.meshes`, `.materials` — empty in this task); full struct shapes land in Tasks 1–2.

- [ ] **Step 1: Add Assimp to the vcpkg manifest**

`vcpkg.json` — add `assimp` with the Draco feature. The exact feature spelling is the first thing to confirm (`vcpkg search assimp` / inspect the port's `vcpkg.json`); recent ports expose Draco via a feature. Baseline:

```json
{
    "name": "pluton",
    "version": "0.0.1",
    "description": "Polygonal 3D modeler for architecture",
    "homepage": "https://pluton3d.org",
    "license": "GPL-3.0-or-later",
    "dependencies": [
        "gtest",
        { "name": "assimp", "features": ["draco"] }
    ]
}
```

If the port has no `draco` feature, use `"assimp"` plain and confirm Assimp's bundled Draco is enabled (Assimp builds glTF Draco support when its `ASSIMP_BUILD_DRACO` option is on, which the vcpkg port sets by default in current versions). **Do not proceed past Step 6 until the Draco decode in Step 6 passes.**

- [ ] **Step 2: Wire find_package + link in CMake**

`CMakeLists.txt` (top level) — after the `nanobind` find (line 29), add:

```cmake
# Find Assimp (glTF/GLB import — vcpkg, M6c)
find_package(assimp CONFIG REQUIRED)
```

`cpp/CMakeLists.txt` — add the new source to `pluton_core` and link Assimp (PRIVATE — the public header exposes only neutral structs):

```cmake
add_library(pluton_core STATIC
    src/version.cpp
    src/mesh.cpp
    src/primitives.cpp
    src/halfedge.cpp
    src/ray_intersect.cpp
    src/gltf_import.cpp
)

# ... existing target_include_directories / POSITION_INDEPENDENT_CODE ...

target_link_libraries(pluton_core PRIVATE assimp::assimp)
```

- [ ] **Step 3: Stub header**

Create `cpp/include/pluton/gltf_import.h`:

```cpp
#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace pluton {

struct ImportedMaterial {
    std::string name;
    std::array<float, 4> base_color;  // RGBA
};

struct ImportedMesh {
    std::vector<std::array<float, 3>> positions;
    std::vector<std::array<std::uint32_t, 3>> triangles;
    int material_index;  // -1 = none
};

struct ImportedNode {
    std::string name;
    int parent;                       // -1 = root
    std::array<float, 16> transform;  // row-major (aiMatrix4x4 order)
    std::vector<int> mesh_indices;
};

struct ImportedScene {
    std::vector<ImportedNode> nodes;
    std::vector<ImportedMesh> meshes;
    std::vector<ImportedMaterial> materials;
};

// Load a glTF/GLB and flatten to neutral data. Throws std::runtime_error on
// a whole-file load failure (missing/undecodable).
ImportedScene import_gltf(const std::string& path);

}  // namespace pluton
```

- [ ] **Step 4: Stub source that actually calls Assimp (proves the link)**

Create `cpp/src/gltf_import.cpp` — for this task, load the file and return only counts-worth of structure (a real walk lands in Task 1), but genuinely invoke Assimp so the build proves linkage + Draco:

```cpp
#include "pluton/gltf_import.h"

#include <stdexcept>

#include <assimp/Importer.hpp>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

namespace pluton {

ImportedScene import_gltf(const std::string& path) {
    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        path, aiProcess_Triangulate | aiProcess_JoinIdenticalVertices);
    if (scene == nullptr || (scene->mFlags & AI_SCENE_FLAGS_INCOMPLETE) != 0
        || scene->mRootNode == nullptr) {
        throw std::runtime_error(std::string("glTF import failed: ")
                                 + importer.GetErrorString());
    }
    ImportedScene result;
    // STUB (Task 0): prove decode by exposing one mesh's vertex count as a
    // single-triangle placeholder if the scene has geometry. Real walk in Task 1.
    if (scene->mNumMeshes > 0 && scene->mMeshes[0]->mNumVertices > 0) {
        ImportedMesh m;
        m.material_index = -1;
        const auto& p = scene->mMeshes[0]->mVertices[0];
        m.positions.push_back({p.x, p.y, p.z});
        result.meshes.push_back(std::move(m));
    }
    return result;
}

}  // namespace pluton
```

- [ ] **Step 5: Minimal binding**

`cpp/bindings/module.cpp` — add the include and a minimal binding so Python can call it (full struct bindings in Task 2). Add near the other includes:

```cpp
#include "pluton/gltf_import.h"
```

and inside `NB_MODULE`, bind the structs minimally + the function:

```cpp
    nb::class_<pluton::ImportedMesh>(m, "ImportedMesh")
        .def_ro("positions", &pluton::ImportedMesh::positions)
        .def_ro("triangles", &pluton::ImportedMesh::triangles)
        .def_ro("material_index", &pluton::ImportedMesh::material_index);
    nb::class_<pluton::ImportedNode>(m, "ImportedNode")
        .def_ro("name", &pluton::ImportedNode::name)
        .def_ro("parent", &pluton::ImportedNode::parent)
        .def_ro("transform", &pluton::ImportedNode::transform)
        .def_ro("mesh_indices", &pluton::ImportedNode::mesh_indices);
    nb::class_<pluton::ImportedMaterial>(m, "ImportedMaterial")
        .def_ro("name", &pluton::ImportedMaterial::name)
        .def_ro("base_color", &pluton::ImportedMaterial::base_color);
    nb::class_<pluton::ImportedScene>(m, "ImportedScene")
        .def_ro("nodes", &pluton::ImportedScene::nodes)
        .def_ro("meshes", &pluton::ImportedScene::meshes)
        .def_ro("materials", &pluton::ImportedScene::materials);
    m.def("import_gltf", &pluton::import_gltf, nb::arg("path"),
          "Load a glTF/GLB file into a neutral ImportedScene (M6c import bridge).");
```

- [ ] **Step 6: Vendor two sample files + prove local build, plain decode, AND Draco decode**

Obtain two tiny samples into `tests/data/gltf/`:
- `plain_box.glb` — an uncompressed GLB (author with any glTF tool, or vendor Khronos `Box.glb`, CC0).
- `draco_box.glb` — the **CC0** Khronos `Box` with `KHR_draco_mesh_compression` (from KhronosGroup/glTF-Sample-Assets, CC0 — verify the license file and record it in the commit message).

Rebuild the wheel (first Assimp build is slow locally — expected):

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pip install -e . --no-build-isolation
```

Then prove both decodes:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -c "import pluton._core as c; import pathlib; d=pathlib.Path('tests/data/gltf'); s1=c.import_gltf(str(d/'plain_box.glb')); s2=c.import_gltf(str(d/'draco_box.glb')); print('plain meshes:', len(s1.meshes)); print('draco meshes:', len(s2.meshes)); assert len(s1.meshes)>0 and len(s2.meshes)>0, 'decode returned no geometry'; print('OK: plain + Draco decode')"
```

Expected: `OK: plain + Draco decode`. **If the Draco file returns no geometry, Draco is not enabled — fix the vcpkg feature (Step 1) before continuing.**

- [ ] **Step 7: Keep CI from rebuilding Assimp every run**

`.github/workflows/build.yml` — Assimp from source on every run (both platforms) is too slow. Enable the vcpkg GHA binary cache so it builds once and is restored thereafter. `lukka/run-vcpkg@v11` already sets `VCPKG_BINARY_SOURCES="clear;x-gha,readwrite"`; the current workflow overrides it with `clear` in the install/configure steps (M0 comment). For the editable-install and both C++-test-configure steps, **remove the `VCPKG_BINARY_SOURCES: clear` override** and add the GHA cache token export so vcpkg can read/write the cache:

```yaml
      - name: Export GitHub Actions cache env for vcpkg
        uses: actions/github-script@v7
        with:
          script: |
            core.exportVariable('ACTIONS_CACHE_URL', process.env.ACTIONS_CACHE_URL || '');
            core.exportVariable('ACTIONS_RUNTIME_TOKEN', process.env.ACTIONS_RUNTIME_TOKEN || '');
```

Place it after the `Set up vcpkg` step and before the install step; drop the three `VCPKG_BINARY_SOURCES: clear` env blocks. (Confirm the first CI run populates the cache and the second is fast. If the token export proves flaky, fall back to `x-gha` via `run-vcpkg`'s built-in support.)

- [ ] **Step 8: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add vcpkg.json CMakeLists.txt cpp/CMakeLists.txt cpp/include/pluton/gltf_import.h cpp/src/gltf_import.cpp cpp/bindings/module.cpp .github/workflows/build.yml tests/data/gltf/plain_box.glb tests/data/gltf/draco_box.glb && git commit -m "$(cat <<'EOF'
feat(m6c): Assimp build spike — link + plain/Draco GLB decode

Add assimp (with Draco) to vcpkg.json, find_package + link into pluton_core,
a stub gltf_import bridge that genuinely calls Assimp, and a minimal _core
binding. Proves locally that Assimp links and decodes both a plain and a
Draco-compressed GLB. Enable the vcpkg GHA binary cache so CI doesn't rebuild
Assimp from source every run. Vendored samples are Khronos CC0.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1: C++ `import_gltf` full walk → neutral structs

**Files:**
- Modify: `cpp/src/gltf_import.cpp`
- Create: `cpp/tests/test_gltf_import.cpp`
- Modify: `cpp/tests/CMakeLists.txt`

**Interfaces:**
- Consumes: the structs from `gltf_import.h` (Task 0).
- Produces: a fully-populated `ImportedScene` — all materials (base color via `AI_MATKEY_BASE_COLOR`, fallback `AI_MATKEY_COLOR_DIFFUSE`), all meshes (positions + triangle index triples + `material_index`), and all nodes flattened parent-before-child with row-major transforms + `mesh_indices`.

- [ ] **Step 1: Write the failing GoogleTest**

Create `cpp/tests/test_gltf_import.cpp` (uses the vendored `plain_box.glb`; the box has 1 mesh, 24 verts → triangulated, and a node tree):

```cpp
#include <gtest/gtest.h>

#include <cstdlib>
#include <string>

#include "pluton/gltf_import.h"

namespace {

std::string sample(const char* name) {
    // Tests run from the build dir; PLUTON_TEST_DATA is set by CMake.
    return std::string(PLUTON_TEST_DATA) + "/gltf/" + name;
}

TEST(GltfImport, PlainBoxHasGeometryAndNodes) {
    const pluton::ImportedScene s = pluton::import_gltf(sample("plain_box.glb"));
    ASSERT_FALSE(s.meshes.empty());
    EXPECT_GT(s.meshes[0].positions.size(), 0u);
    EXPECT_GT(s.meshes[0].triangles.size(), 0u);
    EXPECT_FALSE(s.nodes.empty());
    EXPECT_EQ(s.nodes[0].parent, -1);           // root first
}

TEST(GltfImport, DracoBoxDecodes) {
    const pluton::ImportedScene s = pluton::import_gltf(sample("draco_box.glb"));
    ASSERT_FALSE(s.meshes.empty());
    EXPECT_GT(s.meshes[0].triangles.size(), 0u);  // Draco actually decoded
}

TEST(GltfImport, MissingFileThrows) {
    EXPECT_THROW(pluton::import_gltf(sample("does_not_exist.glb")), std::runtime_error);
}

}  // namespace
```

Register it + pass the data dir. `cpp/tests/CMakeLists.txt`:

```cmake
add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
    test_primitives.cpp
    test_halfedge.cpp
    test_ray_intersect.cpp
    test_gltf_import.cpp
)

target_compile_definitions(pluton_tests PRIVATE
    PLUTON_TEST_DATA="${CMAKE_SOURCE_DIR}/tests/data")
```

(Keep the existing `target_link_libraries` + `gtest_discover_tests` lines.)

- [ ] **Step 2: Run to verify it fails**

Configure + build the standalone C++ tests (as CI does), then run:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && NANOBIND_DIR=$(.venv/Scripts/python -c "import nanobind; print(nanobind.cmake_dir())") && cmake -B build/tests -S . -G Ninja -Dnanobind_DIR="$NANOBIND_DIR" && cmake --build build/tests && (cd build/tests && ctest -R GltfImport --output-on-failure)
```

Expected: `GltfImport.PlainBoxHasGeometryAndNodes` FAILS (stub returns only 1 vertex, 0 triangles).

- [ ] **Step 3: Implement the full walk**

Replace the stub body of `import_gltf` in `cpp/src/gltf_import.cpp` (keep the includes; add `<assimp/material.h>`):

```cpp
#include "pluton/gltf_import.h"

#include <stdexcept>
#include <utility>

#include <assimp/Importer.hpp>
#include <assimp/material.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

namespace pluton {

namespace {

std::array<float, 16> to_row_major(const aiMatrix4x4& m) {
    return {m.a1, m.a2, m.a3, m.a4, m.b1, m.b2, m.b3, m.b4,
            m.c1, m.c2, m.c3, m.c4, m.d1, m.d2, m.d3, m.d4};
}

void collect_nodes(const aiNode* node, int parent, std::vector<ImportedNode>& out) {
    ImportedNode n;
    n.name = node->mName.C_Str();
    n.parent = parent;
    n.transform = to_row_major(node->mTransformation);
    n.mesh_indices.assign(node->mMeshes, node->mMeshes + node->mNumMeshes);
    const int my_index = static_cast<int>(out.size());
    out.push_back(std::move(n));
    for (unsigned i = 0; i < node->mNumChildren; ++i)
        collect_nodes(node->mChildren[i], my_index, out);
}

}  // namespace

ImportedScene import_gltf(const std::string& path) {
    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        path, aiProcess_Triangulate | aiProcess_JoinIdenticalVertices);
    if (scene == nullptr || (scene->mFlags & AI_SCENE_FLAGS_INCOMPLETE) != 0
        || scene->mRootNode == nullptr) {
        throw std::runtime_error(std::string("glTF import failed: ")
                                 + importer.GetErrorString());
    }

    ImportedScene result;

    for (unsigned i = 0; i < scene->mNumMaterials; ++i) {
        const aiMaterial* mat = scene->mMaterials[i];
        ImportedMaterial im;
        aiString name;
        if (mat->Get(AI_MATKEY_NAME, name) == AI_SUCCESS) im.name = name.C_Str();
        aiColor4D color(0.8f, 0.8f, 0.8f, 1.0f);
        if (mat->Get(AI_MATKEY_BASE_COLOR, color) != AI_SUCCESS)
            mat->Get(AI_MATKEY_COLOR_DIFFUSE, color);
        im.base_color = {color.r, color.g, color.b, color.a};
        result.materials.push_back(std::move(im));
    }

    for (unsigned i = 0; i < scene->mNumMeshes; ++i) {
        const aiMesh* mesh = scene->mMeshes[i];
        ImportedMesh om;
        om.material_index = static_cast<int>(mesh->mMaterialIndex);
        om.positions.reserve(mesh->mNumVertices);
        for (unsigned v = 0; v < mesh->mNumVertices; ++v) {
            const aiVector3D& p = mesh->mVertices[v];
            om.positions.push_back({p.x, p.y, p.z});
        }
        om.triangles.reserve(mesh->mNumFaces);
        for (unsigned f = 0; f < mesh->mNumFaces; ++f) {
            const aiFace& face = mesh->mFaces[f];
            if (face.mNumIndices != 3) continue;
            om.triangles.push_back(
                {face.mIndices[0], face.mIndices[1], face.mIndices[2]});
        }
        result.meshes.push_back(std::move(om));
    }

    collect_nodes(scene->mRootNode, -1, result.nodes);
    return result;
}

}  // namespace pluton
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && cmake --build build/tests && (cd build/tests && ctest -R GltfImport --output-on-failure)
```

Expected: all 3 `GltfImport.*` PASS.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add cpp/src/gltf_import.cpp cpp/tests/test_gltf_import.cpp cpp/tests/CMakeLists.txt && git commit -m "$(cat <<'EOF'
feat(m6c): full Assimp glTF walk -> neutral ImportedScene + GoogleTests

Materials (PBR base color w/ diffuse fallback), meshes (positions + triangle
indices + material index), and nodes flattened parent-before-child with
row-major transforms. GoogleTests cover plain + Draco decode and the
missing-file throw.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: nanobind binding finalization + Python smoke test

*(Task 0 already added minimal bindings; this task confirms the full struct surface is usable from Python and rebuilds the wheel so downstream Python tasks can call `_core.import_gltf`.)*

**Files:**
- Modify: `cpp/bindings/module.cpp` (only if fields are missing — otherwise no-op confirm)
- Create: `tests/test_gltf_bridge.py`

**Interfaces:**
- Produces: `_core.import_gltf(path) -> ImportedScene` callable from Python, with `.nodes/.meshes/.materials`, each element exposing the fields from Task 1 (arrays surface as tuples/lists).

- [ ] **Step 1: Write the failing Python smoke test**

Create `tests/test_gltf_bridge.py`:

```python
"""_core.import_gltf bridge smoke tests (needs the compiled kernel)."""
from __future__ import annotations

from pathlib import Path

import pytest

import pluton._core as core

DATA = Path(__file__).parent / "data" / "gltf"


def test_import_plain_box_exposes_full_struct():
    s = core.import_gltf(str(DATA / "plain_box.glb"))
    assert len(s.meshes) >= 1
    mesh = s.meshes[0]
    assert len(mesh.positions) > 0
    assert len(mesh.positions[0]) == 3          # (x, y, z)
    assert len(mesh.triangles) > 0
    assert len(mesh.triangles[0]) == 3          # index triple
    assert isinstance(mesh.material_index, int)
    assert len(s.nodes) >= 1
    node = s.nodes[0]
    assert node.parent == -1
    assert len(node.transform) == 16
    assert isinstance(list(node.mesh_indices), list)
    assert len(s.materials) >= 1
    assert len(s.materials[0].base_color) == 4


def test_import_missing_file_raises():
    with pytest.raises(Exception):
        core.import_gltf(str(DATA / "nope.glb"))
```

- [ ] **Step 2: Run to verify it fails (or errors on import)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_bridge.py -q -p no:cacheprovider
```

Expected: FAILS if any field isn't exposed (e.g., `transform` length ≠ 16), or passes trivially if Task 0's bindings were already complete.

- [ ] **Step 3: Ensure all struct fields are bound + rebuild**

Confirm `cpp/bindings/module.cpp` binds every field listed in Task 1 (Task 0 already added them). If complete, no edit. Rebuild the wheel so the Python kernel is current:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pip install -e . --no-build-isolation
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_bridge.py -q -p no:cacheprovider
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add cpp/bindings/module.cpp tests/test_gltf_bridge.py && git commit -m "$(cat <<'EOF'
test(m6c): Python bridge smoke test for _core.import_gltf

Confirm the full ImportedScene struct surface is usable from Python
(positions/triangles/material_index, node transform[16]/parent/mesh_indices,
material base_color[4]) and rebuild the wheel.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `gltf_scene.py` IR + `read_gltf_scene` adapter

**Files:**
- Create: `python/pluton/io/gltf_scene.py`
- Create: `python/pluton/io/gltf_import.py` (with `read_gltf_scene` only; builder lands in Tasks 4–5)
- Modify: `python/pluton/io/__init__.py` (re-export `read_gltf_scene`, `GltfSceneData`)
- Create: `tests/test_gltf_scene.py`

**Interfaces:**
- Consumes: `_core.import_gltf` (Task 2).
- Produces: `GltfSceneData`/`GltfNode`/`GltfMesh`/`GltfMaterial` dataclasses; `read_gltf_scene(path) -> GltfSceneData` (adapts the bridge, maps failures to `PlutonFormatError`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_scene.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pluton.io.errors import PlutonIOError
from pluton.io.gltf_scene import GltfMaterial, GltfMesh, GltfNode, GltfSceneData

DATA = Path(__file__).parent / "data" / "gltf"


def test_ir_dataclasses_are_frozen():
    m = GltfMaterial(name="Red", color=(1.0, 0.0, 0.0))
    with pytest.raises(Exception):
        m.name = "Blue"  # frozen


def test_read_gltf_scene_populates_ir():
    from pluton.io.gltf_import import read_gltf_scene

    scene = read_gltf_scene(str(DATA / "plain_box.glb"))
    assert isinstance(scene, GltfSceneData)
    assert len(scene.meshes) >= 1
    assert isinstance(scene.meshes[0], GltfMesh)
    assert len(scene.meshes[0].positions[0]) == 3
    assert isinstance(scene.nodes[0], GltfNode)
    assert scene.nodes[0].parent == -1
    assert len(scene.nodes[0].transform) == 16


def test_read_missing_file_raises_pluton_error():
    from pluton.io.gltf_import import read_gltf_scene

    with pytest.raises((PlutonIOError, OSError)):
        read_gltf_scene(str(DATA / "does_not_exist.glb"))
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_scene.py -q -p no:cacheprovider
```

Expected: FAIL (`ModuleNotFoundError: pluton.io.gltf_scene`).

- [ ] **Step 3: Write the IR + adapter**

Create `python/pluton/io/gltf_scene.py`:

```python
"""Neutral glTF import IR (M6c).

Pure dataclasses mirroring the C++ bridge structs 1:1 — no Model, no _core, no
Assimp. This lets the import-mapping layer be unit-tested with hand-built
fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GltfMaterial:
    name: str
    color: tuple[float, float, float]  # RGB; alpha dropped


@dataclass(frozen=True)
class GltfMesh:
    positions: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    material_index: int  # -1 = none


@dataclass(frozen=True)
class GltfNode:
    name: str
    parent: int  # -1 = root
    transform: tuple[float, ...]  # 16 floats, row-major
    mesh_indices: tuple[int, ...]


@dataclass(frozen=True)
class GltfSceneData:
    nodes: tuple[GltfNode, ...]
    meshes: tuple[GltfMesh, ...]
    materials: tuple[GltfMaterial, ...]
```

Create `python/pluton/io/gltf_import.py`:

```python
"""glTF import: bridge adapter + model builder (M6c).

read_gltf_scene adapts the _core.import_gltf bridge into the neutral IR;
build_gltf_into_model (Tasks 4-5) maps the IR into the Model. This is the only
glTF module that imports Model/Scene.
"""
from __future__ import annotations

from pluton.io.errors import PlutonFormatError
from pluton.io.gltf_scene import GltfMaterial, GltfMesh, GltfNode, GltfSceneData


def read_gltf_scene(path) -> GltfSceneData:  # noqa: ANN001
    """Read a .glb/.gltf via the Assimp bridge into a GltfSceneData.

    Raises PlutonFormatError if the file cannot be decoded. OSError from a
    genuinely missing/unreadable path propagates.
    """
    import pluton._core as core

    try:
        raw = core.import_gltf(str(path))
    except Exception as e:  # bridge raises std::runtime_error -> RuntimeError
        raise PlutonFormatError(f"Could not import glTF: {e}") from e

    materials = tuple(
        GltfMaterial(name=m.name, color=(m.base_color[0], m.base_color[1], m.base_color[2]))
        for m in raw.materials
    )
    meshes = tuple(
        GltfMesh(
            positions=tuple((p[0], p[1], p[2]) for p in m.positions),
            triangles=tuple((t[0], t[1], t[2]) for t in m.triangles),
            material_index=m.material_index,
        )
        for m in raw.meshes
    )
    nodes = tuple(
        GltfNode(
            name=n.name,
            parent=n.parent,
            transform=tuple(n.transform),
            mesh_indices=tuple(n.mesh_indices),
        )
        for n in raw.nodes
    )
    return GltfSceneData(nodes=nodes, meshes=meshes, materials=materials)
```

`python/pluton/io/__init__.py` — add re-exports (append to the existing exports):

```python
from pluton.io.gltf_import import read_gltf_scene
from pluton.io.gltf_scene import GltfSceneData
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_scene.py -q -p no:cacheprovider
```

Expected: 3 passed. Then `ruff check python/pluton/io/gltf_scene.py python/pluton/io/gltf_import.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/gltf_scene.py python/pluton/io/gltf_import.py python/pluton/io/__init__.py tests/test_gltf_scene.py && git commit -m "$(cat <<'EOF'
feat(m6c): glTF neutral IR + read_gltf_scene bridge adapter

Pure dataclasses (GltfSceneData/GltfNode/GltfMesh/GltfMaterial) mirroring the
C++ bridge structs, and read_gltf_scene adapting _core.import_gltf into them
with failures mapped to PlutonFormatError.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `build_gltf_into_model` — meshes → shared Component Definitions

**Files:**
- Modify: `python/pluton/io/gltf_import.py`
- Create: `tests/test_gltf_build_meshes.py`

**Interfaces:**
- Consumes: `GltfSceneData`, `model.new_definition/materials`, `defn.mesh.add_vertex/add_face_from_loop/set_face_material`.
- Produces: `_ensure_gltf_materials(materials, model) -> list[int | None]` (material id per glTF index, None = default/unpainted); `_build_mesh_components(scene, model, mat_id_by_index) -> (meshdefs, imported, skipped, built)` where `meshdefs[i]` is a Component `Definition` or `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_build_meshes.py`:

```python
from __future__ import annotations

from pluton.io.gltf_import import _build_mesh_components, _ensure_gltf_materials
from pluton.io.gltf_scene import GltfMaterial, GltfMesh, GltfSceneData
from pluton.model.model import Model

TRI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def _scene(meshes, materials=()):
    return GltfSceneData(nodes=(), meshes=tuple(meshes), materials=tuple(materials))


def test_valid_mesh_builds_one_component_with_one_face():
    scene = _scene([GltfMesh(positions=TRI, triangles=((0, 1, 2),), material_index=-1)])
    model = Model()
    mats = _ensure_gltf_materials(scene.materials, model)
    meshdefs, imported, skipped, built = _build_mesh_components(scene, model, mats)
    assert built == 1
    assert imported == 1 and skipped == 0
    assert meshdefs[0] is not None
    assert not meshdefs[0].is_group  # a Component
    assert len(list(meshdefs[0].mesh.faces_iter())) == 1


def test_degenerate_triangle_is_skipped_and_component_dropped():
    scene = _scene([GltfMesh(positions=TRI, triangles=((0, 0, 1),), material_index=-1)])
    model = Model()
    mats = _ensure_gltf_materials(scene.materials, model)
    meshdefs, imported, skipped, built = _build_mesh_components(scene, model, mats)
    assert imported == 0 and skipped == 1
    assert meshdefs[0] is None and built == 0


def test_material_is_deduped_and_applied():
    mat = GltfMaterial(name="Red", color=(1.0, 0.0, 0.0))
    scene = _scene(
        [GltfMesh(positions=TRI, triangles=((0, 1, 2),), material_index=0)],
        materials=[mat],
    )
    model = Model()
    mats = _ensure_gltf_materials(scene.materials, model)
    assert mats[0] is not None
    meshdefs, *_ = _build_mesh_components(scene, model, mats)
    fid = next(iter(meshdefs[0].mesh.faces_iter())).id
    assert meshdefs[0].mesh.face_material(fid) == mats[0]


def test_default_material_maps_to_none():
    mat = GltfMaterial(name="DefaultMaterial", color=(0.8, 0.8, 0.8))
    model = Model()
    assert _ensure_gltf_materials((mat,), model) == [None]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_build_meshes.py -q -p no:cacheprovider
```

Expected: FAIL (`ImportError: cannot import name '_build_mesh_components'`).

- [ ] **Step 3: Implement the mesh + material helpers**

Append to `python/pluton/io/gltf_import.py` (add `import numpy as np` at the top):

```python
import numpy as np

_DEFAULT_MATERIAL_NAMES = {"", "DefaultMaterial"}


def _is_default_material(m) -> bool:  # noqa: ANN001
    return m.name in _DEFAULT_MATERIAL_NAMES


def _ensure_gltf_materials(materials, model) -> list:  # noqa: ANN001
    """Material id per glTF material index (None for default/unpainted). Real
    materials deduped by (name, color); add_custom otherwise."""
    result: list = []
    existing = {(m.name, tuple(m.color)): m for m in model.materials.materials()}
    for gm in materials:
        if _is_default_material(gm):
            result.append(None)
            continue
        key = (gm.name, tuple(gm.color))
        m = existing.get(key)
        if m is not None:
            result.append(m.id)
        else:
            new = model.materials.add_custom(gm.name, tuple(gm.color))
            existing[key] = new
            result.append(new.id)
    return result


def _add_triangles(mesh, triangles, localmap, material_id) -> tuple[int, int]:  # noqa: ANN001
    """Best-effort: build each triangle, skipping+counting kernel rejects."""
    imported = skipped = 0
    for tri in triangles:
        try:
            loop = [localmap[gi] for gi in tri]
            if len(set(loop)) < 3:
                skipped += 1
                continue
            fid = mesh.add_face_from_loop(loop)
        except (KeyError, ValueError, IndexError, RuntimeError):
            skipped += 1
            continue
        if material_id is not None:
            mesh.set_face_material(fid, material_id)
        imported += 1
    return imported, skipped


def _build_mesh_components(scene, model, mat_id_by_index):  # noqa: ANN001
    """Build each GltfMesh into a shared Component Definition (built once, later
    instanced). Returns (meshdefs, imported, skipped, built). meshdefs[i] is a
    Definition or None (empty or all-faces-skipped mesh)."""
    meshdefs: list = []
    imported = skipped = built = 0
    for i, gmesh in enumerate(scene.meshes):
        if not gmesh.positions:
            meshdefs.append(None)
            continue
        defn = model.new_definition(f"Mesh.{i:03d}", is_group=False)
        localmap = {}
        for gi, (x, y, z) in enumerate(gmesh.positions):
            localmap[gi] = defn.mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
        mid = None
        if 0 <= gmesh.material_index < len(mat_id_by_index):
            mid = mat_id_by_index[gmesh.material_index]
        imp, skp = _add_triangles(defn.mesh, gmesh.triangles, localmap, mid)
        imported += imp
        skipped += skp
        if imp == 0:
            meshdefs.append(None)  # unreferenced def is GC'd
            continue
        meshdefs.append(defn)
        built += 1
    return meshdefs, imported, skipped, built
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_build_meshes.py -q -p no:cacheprovider
```

Expected: 4 passed. `ruff check python/pluton/io/gltf_import.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/gltf_import.py tests/test_gltf_build_meshes.py && git commit -m "$(cat <<'EOF'
feat(m6c): build glTF meshes into shared Component Definitions

Each GltfMesh becomes one Component Definition (built once for instancing),
best-effort triangle faces (skip+count degenerates/rejects), materials deduped
by name+color with Assimp's default material mapped to Pluton Default.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `build_gltf_into_model` — node hierarchy (each node → one object) + axis + wrapper

**Files:**
- Modify: `python/pluton/io/gltf_import.py`
- Create: `tests/test_gltf_build_nodes.py`

**Interfaces:**
- Consumes: Task 4 helpers; `model.new_instance(defn, transform=)`, `defn.children`, `model.traverse()`.
- Produces: `GltfImportSummary(nodes, meshes, faces_imported, faces_skipped)`; `GltfBuildResult(summary, root_instance)`; `build_gltf_into_model(scene, model, target_context, root_name="glTF") -> GltfBuildResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_build_nodes.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.io.gltf_import import build_gltf_into_model
from pluton.io.gltf_scene import GltfMesh, GltfNode, GltfSceneData
from pluton.model.model import Model

TRI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
UP = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))  # vertex 2 is at glTF +Y
IDENT = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def _one_mesh(nodes, mesh=None):
    mesh = mesh or GltfMesh(positions=TRI, triangles=((0, 1, 2),), material_index=-1)
    return GltfSceneData(nodes=tuple(nodes), meshes=(mesh,), materials=())


def test_shared_mesh_makes_one_component_two_instances():
    # two root leaf nodes both referencing mesh 0
    scene = _one_mesh([
        GltfNode(name="A", parent=-1, transform=IDENT, mesh_indices=(0,)),
        GltfNode(name="B", parent=-1, transform=IDENT, mesh_indices=(0,)),
    ])
    model = Model()
    result = build_gltf_into_model(scene, model, model.active_context, root_name="scene")
    wrapper = result.root_instance.definition
    kids = wrapper.children
    assert len(kids) == 2
    # collapsed leaves reference the SAME Component definition (instancing)
    assert kids[0].definition is kids[1].definition
    assert not kids[0].definition.is_group


def test_leaf_collapses_group_when_node_has_children():
    # node A has a mesh AND a child B -> A must be a group, not collapsed
    scene = _one_mesh([
        GltfNode(name="A", parent=-1, transform=IDENT, mesh_indices=(0,)),
        GltfNode(name="B", parent=0, transform=IDENT, mesh_indices=()),
    ])
    model = Model()
    result = build_gltf_into_model(scene, model, model.active_context)
    a_inst = result.root_instance.definition.children[0]
    assert a_inst.definition.is_group                     # A is a group
    # A's group holds: an instance of the mesh Component + the child node B
    assert len(a_inst.definition.children) == 2


def test_axis_yup_to_zup_puts_up_vertex_on_z():
    scene = _one_mesh(
        [GltfNode(name="A", parent=-1, transform=IDENT, mesh_indices=(0,))],
        mesh=GltfMesh(positions=UP, triangles=((0, 1, 2),), material_index=-1),
    )
    model = Model()
    build_gltf_into_model(scene, model, model.active_context)
    # find the mesh Component + its world transform via traverse
    world_of = {id(d): w for d, w in model.traverse()}
    meshdef = next(d for d, _ in model.traverse()
                   if not d.is_group and len(list(d.mesh.vertices_iter())) == 3)
    w = world_of[id(meshdef)]
    up_local = np.array([0.0, 1.0, 0.0, 1.0])          # glTF +Y
    world = w @ up_local
    assert np.allclose(world[:3], [0.0, 0.0, 1.0], atol=1e-6)  # -> Pluton +Z


def test_summary_counts():
    scene = _one_mesh([
        GltfNode(name="A", parent=-1, transform=IDENT, mesh_indices=(0,)),
        GltfNode(name="B", parent=-1, transform=IDENT, mesh_indices=(0,)),
    ])
    model = Model()
    result = build_gltf_into_model(scene, model, model.active_context)
    assert result.summary.nodes == 2
    assert result.summary.meshes == 1
    assert result.summary.faces_imported == 2   # two instances, but faces are on the one Component... see note
```

*(Note for the implementer: `faces_imported` counts faces **built into Component meshes**, i.e. per distinct mesh — so a shared mesh with 1 triangle counts 1, not 2. Adjust the last assertion to `== 1` if that matches the chosen semantics; document whichever you pick in the summary docstring. Recommended: count built faces per Component = `1` here.)*

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_build_nodes.py -q -p no:cacheprovider
```

Expected: FAIL (`ImportError: cannot import name 'build_gltf_into_model'`). Fix the `faces_imported` assertion to `== 1` per the note before expecting green.

- [ ] **Step 3: Implement the node walk + wrapper + axis**

Append to `python/pluton/io/gltf_import.py` (add `from dataclasses import dataclass` at top):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class GltfImportSummary:
    nodes: int          # glTF nodes mapped (one object each)
    meshes: int         # distinct Component meshes built
    faces_imported: int  # faces built into Component meshes (per distinct mesh)
    faces_skipped: int


@dataclass
class GltfBuildResult:
    summary: GltfImportSummary
    root_instance: object   # the single Instance appended to target_context.children


def _yup_to_zup() -> np.ndarray:
    """Rx(+90°): glTF Y-up -> Pluton Z-up. (x, y, z) -> (x, -z, y)."""
    return np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, -1.0, 0.0],
         [0.0, 1.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def build_gltf_into_model(scene, model, target_context, root_name="glTF") -> GltfBuildResult:  # noqa: ANN001
    """Build a GltfSceneData into the model under target_context. Preserves the
    node hierarchy (each node -> one object; single-mesh childless nodes collapse
    to a direct shared-Component instance), converts Y-up -> Z-up at the file
    wrapper, and is best-effort. Returns the single wrapper Instance for undo."""
    mat_id_by_index = _ensure_gltf_materials(scene.materials, model)
    meshdefs, imported, skipped, built = _build_mesh_components(scene, model, mat_id_by_index)

    wrapper = model.new_definition(root_name or "glTF", is_group=True)
    has_children = {n.parent for n in scene.nodes if n.parent >= 0}
    container_def: dict = {}

    for idx, node in enumerate(scene.nodes):
        local = np.array(node.transform, dtype=np.float64).reshape(4, 4)
        mesh_idxs = [mi for mi in node.mesh_indices
                     if 0 <= mi < len(meshdefs) and meshdefs[mi] is not None]
        collapsible = (len(mesh_idxs) == 1) and (idx not in has_children)
        if collapsible:
            inst = model.new_instance(meshdefs[mesh_idxs[0]], transform=local)
        else:
            g = model.new_definition(node.name or "Node", is_group=True)
            for mi in mesh_idxs:
                g.children.append(model.new_instance(meshdefs[mi]))
            inst = model.new_instance(g, transform=local)
            container_def[idx] = g
        parent = wrapper if node.parent == -1 else container_def[node.parent]
        parent.children.append(inst)

    root_instance = model.new_instance(wrapper, transform=_yup_to_zup())
    target_context.children.append(root_instance)

    summary = GltfImportSummary(
        nodes=len(scene.nodes), meshes=built,
        faces_imported=imported, faces_skipped=skipped)
    return GltfBuildResult(summary=summary, root_instance=root_instance)
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_build_nodes.py -q -p no:cacheprovider
```

Expected: 4 passed. `ruff check python/pluton/io/gltf_import.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/gltf_import.py tests/test_gltf_build_nodes.py && git commit -m "$(cat <<'EOF'
feat(m6c): build glTF node hierarchy (each node -> one object) + axis

Preserve the node tree: single-mesh childless nodes collapse to a direct
shared-Component instance (instancing), multi-mesh/parent/empty nodes become
groups. Bake Y-up -> Z-up at the file wrapper. Return GltfBuildResult with the
single wrapper Instance for undo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `ImportGltfCommand` (undoable)

**Files:**
- Create: `python/pluton/commands/gltf_commands.py`
- Create: `tests/test_gltf_commands.py`

**Interfaces:**
- Consumes: `Command` ABC (`do(self, model)`/`undo(self, model)`, `name` class attr); `build_gltf_into_model`; `model.revalidate_active_path()`.
- Produces: `ImportGltfCommand(scene, target_context, root_name="glTF")` with `.summary`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_commands.py`:

```python
from __future__ import annotations

from pluton.commands.gltf_commands import ImportGltfCommand
from pluton.io.gltf_scene import GltfMesh, GltfNode, GltfSceneData
from pluton.model.model import Model

TRI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
IDENT = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def _scene():
    return GltfSceneData(
        nodes=(GltfNode(name="A", parent=-1, transform=IDENT, mesh_indices=(0,)),),
        meshes=(GltfMesh(positions=TRI, triangles=((0, 1, 2),), material_index=-1),),
        materials=(),
    )


def test_do_adds_one_wrapper_child_then_undo_removes_it():
    model = Model()
    target = model.active_context
    before = len(target.children)
    cmd = ImportGltfCommand(_scene(), target, root_name="scene")
    cmd.do(model)
    assert len(target.children) == before + 1
    assert cmd.summary.faces_imported == 1
    cmd.undo(model)
    assert len(target.children) == before          # fully removed


def test_redo_rebuilds():
    model = Model()
    target = model.active_context
    cmd = ImportGltfCommand(_scene(), target)
    cmd.do(model)
    cmd.undo(model)
    cmd.do(model)                                   # stack re-runs do() for redo
    assert len(target.children) == 1


def test_double_undo_is_noop():
    model = Model()
    target = model.active_context
    cmd = ImportGltfCommand(_scene(), target)
    cmd.do(model)
    cmd.undo(model)
    cmd.undo(model)                                 # guarded, no crash
    assert len(target.children) == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_commands.py -q -p no:cacheprovider
```

Expected: FAIL (`ModuleNotFoundError: pluton.commands.gltf_commands`).

- [ ] **Step 3: Implement the command**

Create `python/pluton/commands/gltf_commands.py`:

```python
"""ImportGltfCommand (M6c): undoable wrapper around build_gltf_into_model."""
from __future__ import annotations

from pluton.commands.command import Command
from pluton.io.gltf_import import build_gltf_into_model


class ImportGltfCommand(Command):
    """Import a GltfSceneData into the model, undoably. do() builds the wrapped
    group; undo() detaches the single wrapper instance (the whole subtree becomes
    unreachable). Materials added to the library are NOT undone (parity with
    ImportObjCommand)."""

    name = "Import glTF"

    def __init__(self, scene, target_context, root_name="glTF") -> None:  # noqa: ANN001
        self._scene = scene
        self._target = target_context
        self._root_name = root_name
        self._result = None
        self.summary = None

    def do(self, model) -> None:  # noqa: ANN001
        self._result = build_gltf_into_model(
            self._scene, model, self._target, root_name=self._root_name)
        self.summary = self._result.summary

    def undo(self, model) -> None:  # noqa: ANN001
        if self._result is None:
            return
        root = self._result.root_instance
        if root in self._target.children:
            self._target.children.remove(root)
        model.revalidate_active_path()
        self._result = None
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_commands.py -q -p no:cacheprovider
```

Expected: 3 passed. `ruff check python/pluton/commands/gltf_commands.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/gltf_commands.py tests/test_gltf_commands.py && git commit -m "$(cat <<'EOF'
feat(m6c): ImportGltfCommand (undoable glTF import)

do() builds the wrapped group via build_gltf_into_model; undo() detaches the
single wrapper instance and revalidates the active path (the subtree becomes
unreachable). Double-undo guarded; redo re-runs do(). Material adds not undone.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `gltf_codec.py` — pure `.glb`/`.gltf` buffer assembly

**Files:**
- Create: `python/pluton/io/gltf_codec.py`
- Create: `tests/test_gltf_codec.py`

**Interfaces:**
- Produces (pure — no Model/fs): `GltfAsset` with `add_material(name, color) -> int`, `add_mesh(primitives) -> int` (primitives = list of `(positions, indices, material_index|None)`), `add_node(name, matrix, mesh, children) -> int`, `.scene_roots`, `write_glb() -> bytes`, `write_gltf(bin_name) -> (json_text, bin_bytes)`. POSITION = VEC3/FLOAT with min/max; indices = SCALAR/UNSIGNED_INT; matrices are **glTF column-major** 16-floats (caller supplies column-major).

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_codec.py`:

```python
from __future__ import annotations

import json
import struct

from pluton.io.gltf_codec import GltfAsset

TRI_POS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
TRI_IDX = [0, 1, 2]
IDENT16 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _parse_glb(blob: bytes):
    magic, version, total = struct.unpack_from("<III", blob, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(blob)
    jlen, jtype = struct.unpack_from("<II", blob, 12)
    assert jtype == 0x4E4F534A
    json_bytes = blob[20:20 + jlen]
    blen, btype = struct.unpack_from("<II", blob, 20 + jlen)
    assert btype == 0x004E4942
    return json.loads(json_bytes), blen


def _asset_with_triangle():
    a = GltfAsset()
    mat = a.add_material("Red", (1.0, 0.0, 0.0))
    mesh = a.add_mesh([(TRI_POS, TRI_IDX, mat)])
    node = a.add_node(name="tri", matrix=IDENT16, mesh=mesh, children=None)
    a.scene_roots.append(node)
    return a


def test_glb_framing_and_structure():
    blob = _asset_with_triangle().write_glb()
    assert len(blob) % 4 == 0
    doc, blen = _parse_glb(blob)
    assert doc["asset"]["version"] == "2.0"
    assert doc["scenes"][0]["nodes"] == [0]
    assert len(doc["meshes"]) == 1
    assert len(doc["materials"]) == 1
    assert doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] == [1.0, 0.0, 0.0, 1.0]
    # POSITION accessor has correct min/max
    pos_acc = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert pos_acc["type"] == "VEC3" and pos_acc["componentType"] == 5126
    assert pos_acc["count"] == 3
    assert pos_acc["min"] == [0.0, 0.0, 0.0] and pos_acc["max"] == [1.0, 1.0, 0.0]
    assert doc["buffers"][0]["byteLength"] == blen


def test_gltf_has_external_buffer_uri():
    a = _asset_with_triangle()
    json_text, bin_bytes = a.write_gltf("model.bin")
    doc = json.loads(json_text)
    assert doc["buffers"][0]["uri"] == "model.bin"
    assert doc["buffers"][0]["byteLength"] == len(bin_bytes)
    assert "uri" not in json.loads(a.write_glb()[20:20 + struct.unpack_from("<I", a.write_glb(), 12)[0]].decode())["buffers"][0]
```

*(The last assertion just confirms `.glb` embeds the buffer (no `uri`); simplify to a direct check if the nested form is awkward.)*

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_codec.py -q -p no:cacheprovider
```

Expected: FAIL (`ModuleNotFoundError: pluton.io.gltf_codec`).

- [ ] **Step 3: Implement the codec**

Create `python/pluton/io/gltf_codec.py`:

```python
"""Pure glTF 2.0 buffer/JSON assembly (M6c export codec).

No Model, no filesystem. Assemble a GltfAsset (nodes/meshes/materials, with
accessors packed into one binary buffer) and serialize to .glb bytes or
(.gltf json, .bin bytes). Positions are VEC3/FLOAT (with min/max); indices are
SCALAR/UNSIGNED_INT. Node matrices are glTF column-major 16-float arrays
(the caller supplies column-major order).
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

_FLOAT = 5126
_UINT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


@dataclass
class GltfAsset:
    _buffer: bytearray = field(default_factory=bytearray)
    accessors: list = field(default_factory=list)
    buffer_views: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    meshes: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    scene_roots: list = field(default_factory=list)

    def add_material(self, name, color) -> int:  # noqa: ANN001
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [float(color[0]), float(color[1]), float(color[2]), 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
        })
        return len(self.materials) - 1

    def _add_buffer_view(self, data: bytes, target: int) -> int:
        self._buffer.extend(b"\x00" * _pad4(len(self._buffer)))
        offset = len(self._buffer)
        self._buffer.extend(data)
        self.buffer_views.append({
            "buffer": 0, "byteOffset": offset,
            "byteLength": len(data), "target": target,
        })
        return len(self.buffer_views) - 1

    def _add_position_accessor(self, positions) -> int:  # noqa: ANN001
        data = bytearray()
        for x, y, z in positions:
            data += struct.pack("<3f", x, y, z)
        bv = self._add_buffer_view(bytes(data), _ARRAY_BUFFER)
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        self.accessors.append({
            "bufferView": bv, "componentType": _FLOAT, "count": len(positions),
            "type": "VEC3",
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        })
        return len(self.accessors) - 1

    def _add_index_accessor(self, indices) -> int:  # noqa: ANN001
        data = struct.pack("<%dI" % len(indices), *indices)
        bv = self._add_buffer_view(data, _ELEMENT_ARRAY_BUFFER)
        self.accessors.append({
            "bufferView": bv, "componentType": _UINT, "count": len(indices),
            "type": "SCALAR",
        })
        return len(self.accessors) - 1

    def add_mesh(self, primitives) -> int:  # noqa: ANN001
        prims = []
        for positions, indices, mat in primitives:
            p = {
                "attributes": {"POSITION": self._add_position_accessor(positions)},
                "indices": self._add_index_accessor(indices),
            }
            if mat is not None:
                p["material"] = mat
            prims.append(p)
        self.meshes.append({"primitives": prims})
        return len(self.meshes) - 1

    def add_node(self, name=None, matrix=None, mesh=None, children=None) -> int:  # noqa: ANN001
        node: dict = {}
        if name:
            node["name"] = name
        if matrix is not None:
            node["matrix"] = [float(v) for v in matrix]
        if mesh is not None:
            node["mesh"] = mesh
        if children:
            node["children"] = list(children)
        self.nodes.append(node)
        return len(self.nodes) - 1

    def _json(self, buffer_obj) -> dict:  # noqa: ANN001
        doc = {
            "asset": {"version": "2.0", "generator": "Pluton"},
            "scene": 0,
            "scenes": [{"nodes": list(self.scene_roots)}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [buffer_obj],
        }
        if self.materials:
            doc["materials"] = self.materials
        return doc

    def write_glb(self) -> bytes:
        bin_blob = bytes(self._buffer) + b"\x00" * _pad4(len(self._buffer))
        doc = self._json({"byteLength": len(bin_blob)})
        json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * _pad4(len(json_bytes))
        total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
        out = bytearray()
        out += struct.pack("<III", _GLB_MAGIC, 2, total)
        out += struct.pack("<II", len(json_bytes), _CHUNK_JSON) + json_bytes
        out += struct.pack("<II", len(bin_blob), _CHUNK_BIN) + bin_blob
        return bytes(out)

    def write_gltf(self, bin_name: str):  # noqa: ANN201  -> (json_text, bin_bytes)
        bin_blob = bytes(self._buffer)
        doc = self._json({"byteLength": len(bin_blob), "uri": bin_name})
        return json.dumps(doc, indent=2), bin_blob
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_codec.py -q -p no:cacheprovider
```

Expected: 2 passed. `ruff check python/pluton/io/gltf_codec.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/gltf_codec.py tests/test_gltf_codec.py && git commit -m "$(cat <<'EOF'
feat(m6c): pure glTF codec — .glb/.gltf buffer assembly

GltfAsset packs POSITION (VEC3/FLOAT w/ min/max) + index (SCALAR/UINT)
accessors into one 4-byte-aligned buffer; write_glb emits the JSON+BIN chunk
container, write_gltf emits JSON + a sidecar .bin. Headlessly testable.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `gltf_export.py` — Model → `GltfAsset` mapping + atomic write

**Files:**
- Create: `python/pluton/io/gltf_export.py`
- Create: `tests/test_gltf_export.py`

**Interfaces:**
- Consumes: `GltfAsset` (Task 7); `model.root`, `defn.children`, `defn.mesh` (`vertices_iter`/`faces_iter`/`face_material`/`loop_vertex_ids`), `model.materials`.
- Produces: `model_to_gltf(model) -> GltfAsset`; `export_gltf(model, path) -> None` (atomic; `.glb` embeds buffer, `.gltf` writes a sidecar `.bin`). Z-up→Y-up baked at the export root; shared Definitions → one shared glTF mesh (mesh-level instancing); n-gon faces fan-triangulated + grouped by material into primitives.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_export.py` (needs the kernel — builds real geometry):

```python
from __future__ import annotations

import struct

import numpy as np

from pluton.io.gltf_export import export_gltf, model_to_gltf
from pluton.model.model import Model


def _painted_quad_model():
    """A model with one quad face at Pluton z=1 (up), painted red."""
    model = Model()
    mesh = model.root.mesh
    ids = [
        mesh.add_vertex(np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([0.0, 1.0, 1.0], dtype=np.float32)),
    ]
    fid = mesh.add_face_from_loop(ids)
    red = model.materials.add_custom("Red", (1.0, 0.0, 0.0))
    mesh.set_face_material(fid, red.id)
    return model


def test_model_to_gltf_has_mesh_material_and_root():
    asset = model_to_gltf(_painted_quad_model())
    assert len(asset.meshes) == 1
    assert len(asset.scene_roots) == 1
    assert len(asset.materials) == 1
    assert asset.materials[0]["pbrMetallicRoughness"]["baseColorFactor"] == [1.0, 0.0, 0.0, 1.0]
    # a quad -> 2 triangles -> 6 indices in the (single-material) primitive
    prim = asset.meshes[0]["primitives"][0]
    idx_acc = asset.accessors[prim["indices"]]
    assert idx_acc["count"] == 6


def test_root_matrix_is_zup_to_yup_column_major():
    asset = model_to_gltf(_painted_quad_model())
    root = asset.nodes[asset.scene_roots[0]]
    m = np.array(root["matrix"], dtype=np.float64).reshape(4, 4, order="F")  # column-major
    # Z-up point (0,0,1) -> Y-up (0,1,0)
    assert np.allclose((m @ np.array([0.0, 0.0, 1.0, 1.0]))[:3], [0.0, 1.0, 0.0], atol=1e-6)


def test_export_glb_writes_magic(tmp_path):
    p = tmp_path / "out.glb"
    export_gltf(_painted_quad_model(), str(p))
    data = p.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == 0x46546C67


def test_export_gltf_writes_sidecar_bin(tmp_path):
    p = tmp_path / "out.gltf"
    export_gltf(_painted_quad_model(), str(p))
    assert p.exists()
    assert (tmp_path / "out.bin").exists()
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_export.py -q -p no:cacheprovider
```

Expected: FAIL (`ModuleNotFoundError: pluton.io.gltf_export`).

- [ ] **Step 3: Implement the mapping + atomic write**

Create `python/pluton/io/gltf_export.py`:

```python
"""glTF export: Model -> GltfAsset mapping + atomic filesystem write (M6c).

Mirrors the import mapping: shared Definitions -> one shared glTF mesh
(mesh-level instancing), each Instance -> a glTF node with its transform,
n-gon faces fan-triangulated and grouped by material into primitives, and a
Z-up -> Y-up conversion baked at the export root. This is the only glTF export
module that knows about Model/Scene.
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from pluton.io.gltf_codec import GltfAsset


def _zup_to_yup() -> np.ndarray:
    """Rx(-90°): Pluton Z-up -> glTF Y-up. (x, y, z) -> (x, z, -y)."""
    return np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 1.0, 0.0],
         [0.0, -1.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _definition_primitives(defn, gltf_material_for):  # noqa: ANN001
    """Fan-triangulate the definition's faces, grouped by material into
    (positions, indices, gltf_material_index|None) primitives."""
    mesh = defn.mesh
    verts = list(mesh.vertices_iter())
    if not verts:
        return []
    idmap: dict = {}
    positions: list = []
    for v in verts:
        idmap[v.id] = len(positions)
        positions.append((float(v.position[0]), float(v.position[1]), float(v.position[2])))
    by_mat: dict = defaultdict(list)
    for f in mesh.faces_iter():
        loop = [idmap[vid] for vid in f.loop_vertex_ids]
        if len(loop) < 3:
            continue
        gmat = gltf_material_for(mesh.face_material(f.id))
        for k in range(1, len(loop) - 1):        # fan
            by_mat[gmat].extend([loop[0], loop[k], loop[k + 1]])
    return [(positions, indices, gmat) for gmat, indices in by_mat.items()]


def model_to_gltf(model) -> GltfAsset:  # noqa: ANN001
    asset = GltfAsset()
    default_id = model.materials.DEFAULT_ID
    mat_index: dict = {}
    mesh_index: dict = {}

    def gltf_material_for(mid):  # noqa: ANN001
        if mid == default_id:
            return None
        if mid not in mat_index:
            m = model.materials.get(mid)
            mat_index[mid] = asset.add_material(m.name, m.color)
        return mat_index[mid]

    def mesh_for(defn):  # noqa: ANN001
        if defn.id in mesh_index:
            return mesh_index[defn.id]
        prims = _definition_primitives(defn, gltf_material_for)
        if not prims:
            return None
        idx = asset.add_mesh(prims)
        mesh_index[defn.id] = idx
        return idx

    def emit(inst):  # noqa: ANN001
        defn = inst.definition
        m = mesh_for(defn)
        children = [emit(child) for child in defn.children]
        matrix = np.asarray(inst.transform, dtype=np.float64).flatten(order="F")
        return asset.add_node(name=defn.name, matrix=matrix, mesh=m,
                              children=children or None)

    root_mesh = mesh_for(model.root)
    root_children = [emit(inst) for inst in model.root.children]
    root_node = asset.add_node(
        name="Pluton",
        matrix=_zup_to_yup().flatten(order="F"),
        mesh=root_mesh,
        children=root_children or None,
    )
    asset.scene_roots.append(root_node)
    return asset


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def export_gltf(model, path) -> None:  # noqa: ANN001
    """Write the whole model to `path`. `.gltf` -> JSON + a sibling `.bin`;
    any other suffix (incl. `.glb`) -> a single binary GLB. Atomic writes."""
    path = Path(path)
    asset = model_to_gltf(model)
    if path.suffix.lower() == ".gltf":
        bin_name = path.stem + ".bin"
        json_text, bin_bytes = asset.write_gltf(bin_name)
        _atomic_write_bytes(path, json_text.encode("utf-8"))
        _atomic_write_bytes(path.with_name(bin_name), bin_bytes)
    else:
        _atomic_write_bytes(path, asset.write_glb())
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_export.py -q -p no:cacheprovider
```

Expected: 4 passed. `ruff check python/pluton/io/gltf_export.py` → clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/gltf_export.py tests/test_gltf_export.py && git commit -m "$(cat <<'EOF'
feat(m6c): glTF export mapping (Model -> GltfAsset) + atomic write

Shared Definitions -> one shared glTF mesh (mesh-level instancing), each
Instance -> a node with its transform, n-gon faces fan-triangulated + grouped
by material into primitives, Z-up -> Y-up baked at the export root. export_gltf
writes .glb (embedded) or .gltf + sidecar .bin, atomically.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Export round-trip + `io/__init__` re-export

**Files:**
- Modify: `python/pluton/io/__init__.py` (re-export `export_gltf`)
- Create: `tests/test_gltf_roundtrip.py`

**Interfaces:**
- Consumes: `export_gltf` (Task 8), `read_gltf_scene` + `build_gltf_into_model` (Tasks 3–5), `_core.import_gltf`.
- Produces: end-to-end proof that a Pluton model exported to `.glb`/`.gltf` re-imports with geometry, colors, and Z-up orientation intact.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gltf_roundtrip.py` (needs the kernel):

```python
from __future__ import annotations

import numpy as np

from pluton.io.gltf_export import export_gltf
from pluton.io.gltf_import import build_gltf_into_model, read_gltf_scene
from pluton.model.model import Model


def _up_quad_model():
    model = Model()
    mesh = model.root.mesh
    ids = [
        mesh.add_vertex(np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([0.0, 1.0, 1.0], dtype=np.float32)),
    ]
    fid = mesh.add_face_from_loop(ids)
    red = model.materials.add_custom("Red", (1.0, 0.0, 0.0))
    mesh.set_face_material(fid, red.id)
    return model


def test_glb_roundtrip_preserves_geometry_orientation_and_color(tmp_path):
    export_gltf(_up_quad_model(), str(tmp_path / "rt.glb"))
    scene = read_gltf_scene(str(tmp_path / "rt.glb"))
    assert len(scene.meshes) >= 1
    assert any(m.color == (1.0, 0.0, 0.0) or np.allclose(m.color, (1.0, 0.0, 0.0), atol=1e-4)
               for m in scene.materials)

    # Rebuild into a fresh model; the up face must land back on Pluton z ~ 1.
    model = Model()
    build_gltf_into_model(scene, model, model.active_context)
    zs = [w @ np.append(v.position, 1.0)
          for d, w in model.traverse()
          for v in d.mesh.vertices_iter()]
    assert zs, "no vertices imported"
    assert max(pt[2] for pt in zs) > 0.9        # up preserved (Z-up)


def test_gltf_roundtrip_writes_and_reads(tmp_path):
    export_gltf(_up_quad_model(), str(tmp_path / "rt.gltf"))
    scene = read_gltf_scene(str(tmp_path / "rt.gltf"))
    assert len(scene.meshes) >= 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_roundtrip.py -q -p no:cacheprovider
```

Expected: FAIL if `export_gltf` not re-exported from `pluton.io`, or a genuine round-trip mismatch (fix any axis/material bug surfaced here).

- [ ] **Step 3: Add the re-export**

`python/pluton/io/__init__.py` — add:

```python
from pluton.io.gltf_export import export_gltf
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_roundtrip.py -q -p no:cacheprovider
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/__init__.py tests/test_gltf_roundtrip.py && git commit -m "$(cat <<'EOF'
test(m6c): glTF export->import round-trip (geometry, color, Z-up)

End-to-end: a painted up-facing quad exported to .glb/.gltf re-imports through
_core + build_gltf_into_model with geometry, base color, and Z-up orientation
intact. Re-export export_gltf from pluton.io.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: MainWindow File ▸ Import/Export glTF

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Create: `tests/test_main_window_gltfio.py`

**Interfaces:**
- Consumes: `read_gltf_scene`, `export_gltf` (from `pluton.io`); `ImportGltfCommand`; the generalized `_prompt_open_path(file_filter, title)` / `_prompt_save_path(file_filter, title)`; `self._command_stack.execute(cmd, self._model)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_window_gltfio.py` (mirrors `test_main_window_objio.py`):

```python
from __future__ import annotations

import pluton.ui.main_window as mw_mod
from pluton.ui.main_window import MainWindow


def _win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_menu_has_gltf_actions(qtbot):
    w = _win(qtbot)
    labels = [a.text() for a in w._file_menu.actions()]
    assert any("glTF" in t and "Import" in t for t in labels)
    assert any("glTF" in t and "Export" in t for t in labels)


def test_export_gltf_calls_export(qtbot, monkeypatch, tmp_path):
    w = _win(qtbot)
    w._prompt_save_path = lambda *a, **k: str(tmp_path / "m.glb")
    called = {}
    monkeypatch.setattr(mw_mod, "export_gltf",
                        lambda model, path: called.setdefault("path", path))
    w._on_export_gltf()
    assert called["path"].endswith(".glb")


def test_import_gltf_cancelled_is_noop(qtbot):
    w = _win(qtbot)
    w._prompt_open_path = lambda *a, **k: None
    w._on_import_gltf()   # must not raise


def test_import_gltf_runs_command(qtbot, monkeypatch, tmp_path):
    from pluton.io.gltf_scene import GltfMesh, GltfNode, GltfSceneData
    tri = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    ident = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    scene = GltfSceneData(
        nodes=(GltfNode(name="A", parent=-1, transform=ident, mesh_indices=(0,)),),
        meshes=(GltfMesh(positions=tri, triangles=((0, 1, 2),), material_index=-1),),
        materials=(),
    )
    w = _win(qtbot)
    w._prompt_open_path = lambda *a, **k: str(tmp_path / "m.glb")
    monkeypatch.setattr(mw_mod, "read_gltf_scene", lambda path: scene)
    before = len(w._model.active_context.children)
    w._on_import_gltf()
    assert len(w._model.active_context.children) == before + 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_main_window_gltfio.py -q -p no:cacheprovider
```

Expected: FAIL (no glTF menu actions / no handlers).

- [ ] **Step 3: Add the menu actions, handlers, and imports**

In `python/pluton/ui/main_window.py`:

(a) Add to the top-level `pluton.io` import (the line/block that already imports `export_obj`, `read_obj_document`) the two new names: `export_gltf`, `read_gltf_scene`.

(b) After the OBJ menu actions (currently lines 180–181):

```python
        self._file_menu.addAction("Import glTF…", self._on_import_gltf)
        self._file_menu.addAction("Export glTF…", self._on_export_gltf)
```

(c) Add the two handlers next to `_on_export_obj`/`_on_import_obj` (mirror them exactly):

```python
    def _on_export_gltf(self) -> None:
        path = self._prompt_save_path("glTF Binary (*.glb);;glTF (*.gltf)", "Export glTF")
        if not path:
            return
        path = str(path)
        if not (path.endswith(".glb") or path.endswith(".gltf")):
            path += ".glb"
        try:
            export_gltf(self._model, path)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._status_bar.set_status(f"Exported {Path(path).name}")

    def _on_import_gltf(self) -> None:
        path = self._prompt_open_path("glTF (*.glb *.gltf)", "Import glTF")
        if not path:
            return
        try:
            scene = read_gltf_scene(path)
        except (PlutonIOError, OSError) as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Import failed", str(e))
            return
        from pluton.commands.gltf_commands import ImportGltfCommand
        cmd = ImportGltfCommand(scene, self._model.active_context, root_name=Path(path).stem)
        self._command_stack.execute(cmd, self._model)
        s = cmd.summary
        msg = f"Imported {s.faces_imported} faces in {s.nodes} object(s)"
        if s.faces_skipped:
            msg += f" (skipped {s.faces_skipped} faces)"
        self._status_bar.set_status(msg)
        self._refresh_breadcrumb()
        self._viewport.update()
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_main_window_gltfio.py -q -p no:cacheprovider
```

Expected: 4 passed. Confirm no NEW ruff violations were introduced (diff base vs head for `main_window.py`; do NOT run broad `ruff --fix` on it — issue #48).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_gltfio.py && git commit -m "$(cat <<'EOF'
feat(m6c): File menu Import/Export glTF actions + handlers

Wire File ▸ Import glTF / Export glTF to read_gltf_scene + ImportGltfCommand
and export_gltf, reusing the generalized path prompts. Import status shows
faces + object count (+ skipped). Named after the file stem.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Bridge integration suite + permanent Draco CI gate

**Files:**
- Create: `tests/test_gltf_integration.py`

**Interfaces:**
- Consumes: the vendored `tests/data/gltf/plain_box.glb` + `draco_box.glb` (Task 0); `export_gltf` (to synthesize instanced/hierarchy inputs at runtime, avoiding many static fixtures); `_core.import_gltf`.

- [ ] **Step 1: Write the integration tests**

Create `tests/test_gltf_integration.py`:

```python
"""End-to-end glTF bridge integration (needs the compiled kernel + Assimp).

Includes the PERMANENT Draco CI gate — do NOT add skip/xfail markers here. If
a vcpkg assimp bump drops Draco, this must fail CI rather than degrade silently.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import pluton._core as core
from pluton.io.gltf_export import export_gltf
from pluton.model.model import Model

DATA = Path(__file__).parent / "data" / "gltf"


def test_plain_box_decodes():
    s = core.import_gltf(str(DATA / "plain_box.glb"))
    assert len(s.meshes) >= 1
    assert len(s.meshes[0].triangles) > 0


def test_draco_box_decodes_CI_GATE():
    """PERMANENT GATE: Assimp must decode KHR_draco_mesh_compression. Never skip."""
    s = core.import_gltf(str(DATA / "draco_box.glb"))
    assert len(s.meshes) >= 1
    assert len(s.meshes[0].triangles) > 0, "Draco decode produced no geometry"


def _shared_component_model():
    """A model with one component instanced twice (mesh-level instancing)."""
    model = Model()
    comp = model.new_definition("Widget", is_group=False)
    ids = [
        comp.mesh.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        comp.mesh.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        comp.mesh.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32)),
    ]
    comp.mesh.add_face_from_loop(ids)
    i1 = model.new_instance(comp)
    i2 = model.new_instance(comp, transform=np.eye(4, dtype=np.float64))
    model.root.children.extend([i1, i2])
    return model


def test_export_preserves_mesh_level_instancing(tmp_path):
    export_gltf(_shared_component_model(), str(tmp_path / "inst.glb"))
    s = core.import_gltf(str(tmp_path / "inst.glb"))
    # one shared mesh, referenced by two nodes
    mesh_refs = [n for n in s.nodes if len(n.mesh_indices) > 0]
    used = {mi for n in s.nodes for mi in n.mesh_indices}
    assert len(used) == 1                      # exactly one distinct mesh
    assert len(mesh_refs) == 2                 # referenced by two nodes


def test_gltf_sidecar_roundtrips(tmp_path):
    export_gltf(_shared_component_model(), str(tmp_path / "h.gltf"))
    assert (tmp_path / "h.bin").exists()
    s = core.import_gltf(str(tmp_path / "h.gltf"))
    assert len(s.meshes) >= 1
```

- [ ] **Step 2: Run to verify (build must be current)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest tests/test_gltf_integration.py -q -p no:cacheprovider
```

Expected: 5 passed. (If `test_export_preserves_mesh_level_instancing` fails with 2 distinct meshes, the export mesh cache isn't keying on definition id — fix `mesh_for` in `gltf_export.py`.)

- [ ] **Step 3: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add tests/test_gltf_integration.py && git commit -m "$(cat <<'EOF'
test(m6c): glTF bridge integration + permanent Draco CI gate

Plain + Draco decode, export mesh-level instancing survives a bridge
round-trip, and .gltf sidecar round-trips. The Draco test is a permanent,
non-skippable CI gate guarding the capability that justified Assimp.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Full regression + master design-doc annotation

**Files:**
- Modify: `docs/2026-05-16-pluton-design.md` (annotate the M6 line)

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```

Expected: all pass, no hang (~15 s), well above the 740 baseline (the M6c suites add ~30+ tests). The nanobind at-exit "leaked function" warning is benign.

- [ ] **Step 2: Full C++ regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure)
```

Expected: all pass (76 baseline + the 3 new `GltfImport.*` = 79/79). If `build/tests` is stale, reconfigure/rebuild as in Task 1 Step 2.

- [ ] **Step 3: Annotate the master design doc**

`docs/2026-05-16-pluton-design.md` — on the M6 line, replace the `**glTF/Assimp (M6c) deferred**` clause (and the M6b note's tail) with an M6c ✅ sub-milestone note, e.g.:

```
… **M6c** ✅ *(shipped v0.2.0)* — glTF import/export via Assimp: a C++ Assimp
nanobind bridge decodes .glb/.gltf (incl. Draco) into a neutral IR that maps
onto Pluton's scene graph (node hierarchy → nested groups, shared meshes →
shared Components, Y-up→Z-up, best-effort + undoable import), plus a pure-Python
.glb/.gltf writer (Z-up→Y-up, per-material primitives, mesh-level instancing).
**M6 is complete** (M6a + M6b + M6c all shipped).
```

Confirm the M7 line is untouched (`grep -c` the M7 heading == 1, no duplication).

- [ ] **Step 4: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
docs(m6c): annotate master design M6 line — M6c shipped, M6 complete

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Release v0.2.0

*(Outward-facing steps — push, tag, filing issues — require explicit per-turn user authorization, as with prior releases. Do the local bump/build/commit first, then ask to release.)*

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`

- [ ] **Step 1: Bump the version to 0.2.0**

- `pyproject.toml:11` → `version = "0.2.0"`
- `CMakeLists.txt:5` → `VERSION 0.2.0`
- `cpp/src/version.cpp` → `return "0.2.0";`

- [ ] **Step 2: Rebuild and verify the reported version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pip install -e . --no-build-isolation && .venv/Scripts/python -c "import pluton._core as c; assert c.version()=='0.2.0', c.version(); print('version OK', c.version())"
```

Expected: `version OK 0.2.0`.

- [ ] **Step 3: Final full suite at the new version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 150 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 4: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -m "$(cat <<'EOF'
release: v0.2.0 — glTF import/export (M6c)

Bump 0.1.9 -> 0.2.0. M6c adds Assimp-backed glTF/GLB import (Draco-capable,
hierarchy + instancing preserved, Y-up<->Z-up, best-effort, undoable) and a
pure-Python .glb/.gltf writer. M6 (File I/O) is complete.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify signatures on the branch**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && for s in $(git log --format=%H 542e4c7..HEAD 2>/dev/null || git log --format=%H -20); do echo "$s $(git cat-file -p $s | grep -c 'BEGIN SSH SIGNATURE')"; done
```

Expected: every listed commit shows `1`.

- [ ] **Step 6: Push, tag, CI, issues — AFTER explicit user authorization**

Ask the user to authorize the release (as with prior milestones). Once authorized:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main && git tag -s v0.2.0 -m "Pluton v0.2.0 — glTF import/export (M6c)" && git push origin v0.2.0
```

Then watch CI to green on both platforms (`gh run watch` / `gh run view`), confirming the **first run populates the vcpkg binary cache** (Assimp from source) and that the Draco CI-gate test passes. File carry-over issues for the deferred niceties:
- glTF textures / UV round-trip (`baseColorTexture`, `.gltf` external textures) — overlaps #80.
- Smooth-normal export.
- Selection-only export — overlaps #81.
- Animations / cameras / lights import.
- Export buffer sharing (positions currently duplicated per material primitive).

Close tracking issue **#75**.

- [ ] **Step 7: Manual visual pass (user)**

Launch the app; the user imports a real downloaded `.glb` (ideally Draco) — it stands upright (Z-up), the hierarchy shows in the outliner/breadcrumb, colors are present, and undo removes the whole import cleanly; then Export glTF and re-import to confirm the round-trip.

---

## Self-Review

*(Run by the plan author against the spec — see writing-plans skill.)*

**1. Spec coverage.** D1 import+export → Tasks 1–11. D2 hybrid engine → Assimp import (0–2), pure export (7–8). D3 neutral bridge → structs (0–1), IR (3). D4 axis → import `_yup_to_zup` (5), export `_zup_to_yup` (8), asserted (5, 9). D5 hierarchy/instancing/collapse → build (5), export (8), integration (11). D6 undoable placement → command (6). D7 best-effort → `_add_triangles` (4), asserted (4). D8 materials → `_ensure_gltf_materials` (4) + PBR export (7–8); textures deferred (issues, 13). D9 ignored channels → not read/written (1, 8). D10 `.glb`+`.gltf` → codec (7), export dispatch (8), menu filter (10). D11 Draco decode + uncompressed export → Task 0 proof + permanent gate (11). D12 v0.2.0 → Task 13. **All decisions covered.**

**2. Placeholder scan.** No "TBD"/"add error handling". Two intentional, honest verification points remain — the vcpkg Draco feature spelling (Task 0 Step 1, gated by the Step 6 proof) and the `faces_imported` counting semantics (Task 5 note, resolved to "per distinct mesh"). Both are real discovery a build/mapping task must do, with the exact check specified — not hand-waving.

**3. Type consistency.** `GltfSceneData`/`GltfNode`/`GltfMesh`/`GltfMaterial` field names match across Tasks 3–11. `build_gltf_into_model(scene, model, target_context, root_name)` signature consistent in Tasks 5, 6, 10. `GltfBuildResult.root_instance` / `.summary` used consistently in 5, 6. `GltfImportSummary(nodes, meshes, faces_imported, faces_skipped)` fields used identically in 5, 10. `GltfAsset` API (`add_material/add_mesh/add_node/scene_roots/write_glb/write_gltf`) consistent in 7, 8. Export `mesh_for` cache-by-`defn.id` matches the instancing assertion in 11.

**4. Ordering.** Build risk retired first (0). C++ before Python that calls it (1–2 before 3+). Codec (7) before its consumer (8) before round-trip (9). Re-exports land before MainWindow needs them (3, 9 before 10). Fixtures for the Draco gate arrive in Task 0 (used by 11). Release last (13), with outward steps gated on user authorization.

Plan complete.


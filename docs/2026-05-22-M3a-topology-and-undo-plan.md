# M3a — Topology & Undo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the half-edge data structure in C++ as the geometric source of truth, refactor the Python `Scene` as a thin wrapper, add `Scene.remove_*` / `restore_*` operations, build the command-pattern undo/redo stack, and rewire the M2 tools (Rectangle, Line) to push composite commands at gesture completion.

**Architecture:** C++ kernel grows a `HalfEdgeMesh` class — `std::vector` slabs of `Vertex` / `HalfEdge` / `Face` with `bool alive` tombstones; IDs are stable for life and never reused. Python `Scene` keeps the M2 public API but delegates every operation to `HalfEdgeMesh` via nanobind. A new `pluton.commands` package adds `Command` ABC, `CompositeCommand`, `CommandStack`, and per-operation commands. Tools execute their composite's children incrementally during a gesture (so the snap engine sees in-progress state) and call `command_stack.push_executed(composite)` at completion. ESC mid-gesture calls `composite.undo()` and discards the composite, giving a clean rollback that eliminates M2 §5.6 #3.

**Tech Stack:** C++20, nanobind 2.x, GoogleTest, PySide6 (Qt 6), PyOpenGL, numpy, mapbox-earcut (Python; unchanged from M2), pytest + pytest-qt. **No new C++ deps** — `vcpkg.json` is untouched; CGAL waits for M3c.

**Spec:** `docs/2026-05-22-M3a-topology-and-undo-design.md`

**Prerequisite:** M2 complete (tag `v0.0.3-m2`). Working tree clean on `main`.

---

## Build & Test Commands Reference

Same incantation as M1 and M2 — M3a doesn't add or change any C++ deps.

**Git Bash / Linux / macOS:**
```bash
export VCPKG_ROOT=/c/vcpkg
export SKBUILD_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake"
export VCPKG_BINARY_SOURCES=clear

alias pluton-build='pip install -e . --no-build-isolation'
alias pluton-cpp-tests='ctest --test-dir "$(ls -d build/*/ | head -1)" --output-on-failure'
alias pluton-py-tests='pytest -v'
```

**Windows PowerShell:**
```powershell
$env:VCPKG_ROOT = "C:\vcpkg"
$env:SKBUILD_CMAKE_ARGS = "-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake"
$env:VCPKG_BINARY_SOURCES = "clear"

function pluton-build { pip install -e . --no-build-isolation }
function pluton-cpp-tests {
    $build = (Get-ChildItem build/ -Directory | Select-Object -First 1).FullName
    ctest --test-dir $build --output-on-failure
}
function pluton-py-tests { pytest -v }
```

Each task below uses `pluton-build`, `pluton-cpp-tests`, `pluton-py-tests` as shorthand. After a C++ source change you MUST run `pluton-build` to rebuild before `pluton-cpp-tests` or `pluton-py-tests` will see the new code. Python-only changes are picked up by the editable install automatically.

---

## File Map

**C++ side (NEW)**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/include/pluton/halfedge.h` | NEW | `HalfEdgeMesh` declaration; struct layouts; `INVALID_ID` constant. |
| `cpp/src/halfedge.cpp` | NEW | `HalfEdgeMesh` implementation. |
| `cpp/bindings/module.cpp` | MODIFY | Expose `HalfEdgeMesh` via nanobind (~80 lines added). |
| `cpp/tests/test_halfedge.cpp` | NEW | GoogleTest cases for the C++ topology. |
| `cpp/CMakeLists.txt` | MODIFY | Add `halfedge.cpp` to `pluton_core`. |
| `cpp/tests/CMakeLists.txt` | MODIFY | Add `test_halfedge.cpp` to `pluton_tests`. |

**Python side**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/scene/scene.py` | MODIFY | Delegate every method to C++ `HalfEdgeMesh`; add `remove_*` / `restore_*`. |
| `python/pluton/commands/__init__.py` | NEW | Re-exports `Command`, `CompositeCommand`, `CommandStack`. |
| `python/pluton/commands/command.py` | NEW | `Command` ABC + `CompositeCommand` dataclass. |
| `python/pluton/commands/command_stack.py` | NEW | `CommandStack` with `execute` / `push_executed` / `undo` / `redo`. |
| `python/pluton/commands/scene_commands.py` | NEW | Per-operation commands + `ClearSceneCommand` + `_AddVertexAtId` / `_AddEdgeAtId` / `_AddFaceAtId` helpers. |
| `python/pluton/tools/tool.py` | MODIFY | `ToolContext` gains `command_stack` field. |
| `python/pluton/tools/rectangle_tool.py` | MODIFY | Builds composite, executes children incrementally, pushes at completion, undoes on ESC. |
| `python/pluton/tools/line_tool.py` | MODIFY | Same pattern as RectangleTool. |
| `python/pluton/ui/main_window.py` | MODIFY | Owns `CommandStack`; binds `Ctrl+Z` / `Ctrl+Y`; `Ctrl+N` becomes `ClearSceneCommand`. |

**Tests**

| Path | Status | Responsibility |
|---|---|---|
| `tests/test_halfedge_python.py` | NEW | nanobind binding smoke tests. |
| `tests/test_scene.py` | MODIFY | Existing M2 tests stay; add `remove_*` / `restore_*` / tombstone tests. |
| `tests/test_command_stack.py` | NEW | `CommandStack` + `CompositeCommand` behavior. |
| `tests/test_scene_commands.py` | NEW | Each `Add*` / `Remove*` / `ClearScene` command do/undo round-trip. |
| `tests/test_rectangle_tool.py` | MODIFY | Add command-stack interaction tests; ESC rollback test. |
| `tests/test_line_tool.py` | MODIFY | Same + the M2 §5.6 #3 elimination test. |
| `tests/test_viewport.py` | MODIFY | `Ctrl+Z` / `Ctrl+Y` qtbot tests + undo-of-Ctrl+N integration. |

**Versioning / build**

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | MODIFY | Bump `version = "0.0.4"` (last task). |
| `CMakeLists.txt` (top-level) | MODIFY | Bump `project(... VERSION 0.0.4 ...)` (last task). |
| `cpp/src/version.cpp` | MODIFY | Return `"0.0.4"` (last task). |

---

## Definition of Done for M3a

1. C++ `HalfEdgeMesh` class compiles cleanly with no warnings on MSVC `/W4` and GCC `-Wall -Wextra -Wpedantic`.
2. All ~26–29 GoogleTest tests pass locally.
3. All M2 Python tests (101 of them) STILL PASS unchanged — the Scene refactor is internal.
4. New Python tests for `remove_*`, `restore_*`, command framework, tools, and MainWindow all pass.
5. Total Python test count: ~125–130.
6. `python -m pluton` launches; M2 baseline (camera, snaps, status bar) works.
7. `Ctrl+Z` undoes the last completed gesture; `Ctrl+Y` redoes; `Ctrl+N` is undoable; ESC mid-gesture rolls back in-progress mutations.
8. CI green on Windows + Linux.
9. Tagged `v0.0.4-m3a` (annotated, SSH-signed).
10. Tag pushed to GitHub.
11. Carry-over GitHub issues opened for §5.4 of the spec.

---

## Task 1: C++ HalfEdgeMesh header skeleton

**Files:**
- Create: `cpp/include/pluton/halfedge.h`
- Create: `cpp/src/halfedge.cpp`
- Create: `cpp/tests/test_halfedge.cpp`
- Modify: `cpp/CMakeLists.txt`
- Modify: `cpp/tests/CMakeLists.txt`

- [ ] **Step 1: Create the header** at `cpp/include/pluton/halfedge.h`

```cpp
#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace pluton {

/// Half-edge mesh — the topology source of truth for Pluton's M3+ kernel.
///
/// Storage layout:
///   - Vertices, half-edges, and faces live in std::vector slabs.
///   - Each entity has a stable uint32_t ID = its index in the slab.
///   - Removal sets `alive = false` (tombstone). Slots are never reused;
///     IDs stay valid for resurrection by restore_*.
///   - Edges are implicit: every "edge" is a pair of twin half-edges at
///     adjacent vector indices (2*edge_id and 2*edge_id+1). The half-edge
///     at the even index has origin = min(v1, v2); the odd one has
///     origin = max(v1, v2).
class HalfEdgeMesh {
public:
    static constexpr std::uint32_t INVALID_ID = 0xFFFFFFFFu;

    // ---- Mutators ----------------------------------------------------
    std::uint32_t add_vertex(float x, float y, float z);
    std::uint32_t add_halfedge_pair(std::uint32_t v1_id, std::uint32_t v2_id);
    std::uint32_t add_face_from_loop(const std::vector<std::uint32_t>& loop,
                                     const std::vector<std::int32_t>& triangles);

    void remove_vertex(std::uint32_t v_id);
    void remove_edge(std::uint32_t e_id);
    void remove_face(std::uint32_t f_id);

    void restore_vertex(std::uint32_t v_id, float x, float y, float z);
    void restore_edge(std::uint32_t e_id, std::uint32_t v1_id, std::uint32_t v2_id);
    void restore_face(std::uint32_t f_id,
                      const std::vector<std::uint32_t>& loop,
                      const std::vector<std::int32_t>& triangles);

    void clear() noexcept;

    // ---- Queries -----------------------------------------------------
    bool vertex_is_live(std::uint32_t v_id) const noexcept;
    bool edge_is_live(std::uint32_t e_id) const noexcept;
    bool face_is_live(std::uint32_t f_id) const noexcept;

    std::array<float, 3> vertex_position(std::uint32_t v_id) const;
    std::array<std::uint32_t, 2> edge_vertices(std::uint32_t e_id) const;
    std::vector<std::uint32_t> face_loop_vertices(std::uint32_t f_id) const;
    std::vector<std::int32_t> face_triangles(std::uint32_t f_id) const;

    std::uint32_t halfedge_origin(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_next(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_twin(std::uint32_t he_id) const noexcept;
    std::uint32_t halfedge_face(std::uint32_t he_id) const noexcept;

    std::uint32_t next_live_vertex(std::uint32_t start = 0) const noexcept;
    std::uint32_t next_live_edge(std::uint32_t start = 0) const noexcept;
    std::uint32_t next_live_face(std::uint32_t start = 0) const noexcept;

    std::vector<float> edge_line_buffer() const;
    std::pair<std::vector<float>, std::vector<float>> face_triangle_buffer() const;

    bool is_dirty() const noexcept { return dirty_; }
    void mark_clean() noexcept { dirty_ = false; }

    std::size_t vertex_slab_size() const noexcept { return vertices_.size(); }
    std::size_t halfedge_slab_size() const noexcept { return halfedges_.size(); }
    std::size_t face_slab_size() const noexcept { return faces_.size(); }

private:
    struct Vertex   { float pos[3]; std::uint32_t outgoing_he; bool alive; };
    struct HalfEdge { std::uint32_t origin; std::uint32_t next; std::uint32_t twin; std::uint32_t face; bool alive; };
    struct Face     { std::uint32_t boundary_he; float normal[3]; std::vector<std::int32_t> tris; std::vector<std::uint32_t> loop; bool alive; };

    std::vector<Vertex>   vertices_;
    std::vector<HalfEdge> halfedges_;
    std::vector<Face>     faces_;

    // Packed position → live vertex id, for idempotent add_vertex.
    std::unordered_map<std::uint64_t, std::uint32_t> position_index_;
    // (min, max) vertex pair → edge id, for idempotent add_halfedge_pair.
    std::unordered_map<std::uint64_t, std::uint32_t> edge_index_;

    bool dirty_ = false;

    // Helpers
    static std::uint64_t pack_position(float x, float y, float z) noexcept;
    static std::uint64_t pack_pair(std::uint32_t a, std::uint32_t b) noexcept;
};

}  // namespace pluton
```

- [ ] **Step 2: Create the implementation stub** at `cpp/src/halfedge.cpp`

```cpp
#include "pluton/halfedge.h"

#include <cstring>

namespace pluton {

// --- Static helpers ----------------------------------------------------

std::uint64_t HalfEdgeMesh::pack_position(float x, float y, float z) noexcept {
    // We need a stable 64-bit hash key derived from the three float32 bits.
    // FNV-1a over the 12 bytes is good enough for dedup; collisions are
    // tolerable because we compare positions on collision (see add_vertex).
    std::uint32_t bx, by, bz;
    std::memcpy(&bx, &x, 4);
    std::memcpy(&by, &y, 4);
    std::memcpy(&bz, &z, 4);
    std::uint64_t h = 0xcbf29ce484222325ull;
    for (std::uint32_t b : {bx, by, bz}) {
        for (int i = 0; i < 4; ++i) {
            h ^= static_cast<std::uint64_t>((b >> (i * 8)) & 0xFFu);
            h *= 0x100000001b3ull;
        }
    }
    return h;
}

std::uint64_t HalfEdgeMesh::pack_pair(std::uint32_t a, std::uint32_t b) noexcept {
    return (static_cast<std::uint64_t>(a) << 32) | static_cast<std::uint64_t>(b);
}

// --- Stubs for Task 2+ -------------------------------------------------

std::uint32_t HalfEdgeMesh::add_vertex(float, float, float) {
    throw std::runtime_error("HalfEdgeMesh::add_vertex not implemented yet");
}

std::uint32_t HalfEdgeMesh::add_halfedge_pair(std::uint32_t, std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::add_halfedge_pair not implemented yet");
}

std::uint32_t HalfEdgeMesh::add_face_from_loop(const std::vector<std::uint32_t>&,
                                                const std::vector<std::int32_t>&) {
    throw std::runtime_error("HalfEdgeMesh::add_face_from_loop not implemented yet");
}

void HalfEdgeMesh::remove_vertex(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_vertex not implemented yet");
}
void HalfEdgeMesh::remove_edge(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_edge not implemented yet");
}
void HalfEdgeMesh::remove_face(std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::remove_face not implemented yet");
}

void HalfEdgeMesh::restore_vertex(std::uint32_t, float, float, float) {
    throw std::runtime_error("HalfEdgeMesh::restore_vertex not implemented yet");
}
void HalfEdgeMesh::restore_edge(std::uint32_t, std::uint32_t, std::uint32_t) {
    throw std::runtime_error("HalfEdgeMesh::restore_edge not implemented yet");
}
void HalfEdgeMesh::restore_face(std::uint32_t,
                                 const std::vector<std::uint32_t>&,
                                 const std::vector<std::int32_t>&) {
    throw std::runtime_error("HalfEdgeMesh::restore_face not implemented yet");
}

void HalfEdgeMesh::clear() noexcept {
    vertices_.clear();
    halfedges_.clear();
    faces_.clear();
    position_index_.clear();
    edge_index_.clear();
    dirty_ = true;
}

bool HalfEdgeMesh::vertex_is_live(std::uint32_t v_id) const noexcept {
    return v_id < vertices_.size() && vertices_[v_id].alive;
}
bool HalfEdgeMesh::edge_is_live(std::uint32_t e_id) const noexcept {
    const std::uint32_t he = e_id * 2;
    return he < halfedges_.size() && halfedges_[he].alive;
}
bool HalfEdgeMesh::face_is_live(std::uint32_t f_id) const noexcept {
    return f_id < faces_.size() && faces_[f_id].alive;
}

std::array<float, 3> HalfEdgeMesh::vertex_position(std::uint32_t v_id) const {
    if (!vertex_is_live(v_id)) {
        throw std::out_of_range("HalfEdgeMesh::vertex_position: vertex " + std::to_string(v_id) + " is not live");
    }
    const auto& v = vertices_[v_id];
    return {v.pos[0], v.pos[1], v.pos[2]};
}

std::array<std::uint32_t, 2> HalfEdgeMesh::edge_vertices(std::uint32_t e_id) const {
    if (!edge_is_live(e_id)) {
        throw std::out_of_range("HalfEdgeMesh::edge_vertices: edge " + std::to_string(e_id) + " is not live");
    }
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    return {halfedges_[he_a].origin, halfedges_[he_b].origin};
}

std::vector<std::uint32_t> HalfEdgeMesh::face_loop_vertices(std::uint32_t f_id) const {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::face_loop_vertices: face " + std::to_string(f_id) + " is not live");
    }
    return faces_[f_id].loop;
}

std::vector<std::int32_t> HalfEdgeMesh::face_triangles(std::uint32_t f_id) const {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::face_triangles: face " + std::to_string(f_id) + " is not live");
    }
    return faces_[f_id].tris;
}

std::uint32_t HalfEdgeMesh::halfedge_origin(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].origin : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_next(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].next : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_twin(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].twin : INVALID_ID;
}
std::uint32_t HalfEdgeMesh::halfedge_face(std::uint32_t he_id) const noexcept {
    return he_id < halfedges_.size() && halfedges_[he_id].alive ? halfedges_[he_id].face : INVALID_ID;
}

std::uint32_t HalfEdgeMesh::next_live_vertex(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; i < vertices_.size(); ++i) {
        if (vertices_[i].alive) return i;
    }
    return INVALID_ID;
}
std::uint32_t HalfEdgeMesh::next_live_edge(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; (i * 2) < halfedges_.size(); ++i) {
        if (halfedges_[i * 2].alive) return i;
    }
    return INVALID_ID;
}
std::uint32_t HalfEdgeMesh::next_live_face(std::uint32_t start) const noexcept {
    for (std::uint32_t i = start; i < faces_.size(); ++i) {
        if (faces_[i].alive) return i;
    }
    return INVALID_ID;
}

std::vector<float> HalfEdgeMesh::edge_line_buffer() const {
    std::vector<float> out;
    for (std::uint32_t e = next_live_edge(0); e != INVALID_ID; e = next_live_edge(e + 1)) {
        const std::uint32_t he_a = e * 2;
        const std::uint32_t va = halfedges_[he_a].origin;
        const std::uint32_t vb = halfedges_[he_a + 1].origin;
        const auto& pa = vertices_[va].pos;
        const auto& pb = vertices_[vb].pos;
        out.insert(out.end(), {pa[0], pa[1], pa[2], pb[0], pb[1], pb[2]});
    }
    return out;
}

std::pair<std::vector<float>, std::vector<float>> HalfEdgeMesh::face_triangle_buffer() const {
    std::vector<float> positions;
    std::vector<float> normals;
    for (std::uint32_t f = next_live_face(0); f != INVALID_ID; f = next_live_face(f + 1)) {
        const auto& face = faces_[f];
        for (std::size_t i = 0; i + 2 < face.tris.size(); i += 3) {
            for (std::size_t k = 0; k < 3; ++k) {
                const std::uint32_t v = static_cast<std::uint32_t>(face.tris[i + k]);
                const auto& p = vertices_[v].pos;
                positions.insert(positions.end(), {p[0], p[1], p[2]});
                normals.insert(normals.end(), {face.normal[0], face.normal[1], face.normal[2]});
            }
        }
    }
    return {std::move(positions), std::move(normals)};
}

}  // namespace pluton
```

- [ ] **Step 3: Add `halfedge.cpp` to `cpp/CMakeLists.txt`**

Find the `add_library(pluton_core STATIC ...)` block and add `src/halfedge.cpp` to the source list:

```cmake
add_library(pluton_core STATIC
    src/version.cpp
    src/mesh.cpp
    src/primitives.cpp
    src/halfedge.cpp
)
```

- [ ] **Step 4: Write the smoke test** at `cpp/tests/test_halfedge.cpp`

```cpp
#include <gtest/gtest.h>

#include "pluton/halfedge.h"

TEST(HalfEdgeMeshTest, DefaultConstructedIsEmpty) {
    pluton::HalfEdgeMesh m;
    EXPECT_EQ(m.vertex_slab_size(), 0u);
    EXPECT_EQ(m.halfedge_slab_size(), 0u);
    EXPECT_EQ(m.face_slab_size(), 0u);
    EXPECT_FALSE(m.is_dirty());
}

TEST(HalfEdgeMeshTest, ClearSetsDirty) {
    pluton::HalfEdgeMesh m;
    m.clear();
    EXPECT_TRUE(m.is_dirty());
    EXPECT_EQ(m.vertex_slab_size(), 0u);
}

TEST(HalfEdgeMeshTest, InvalidIdConstant) {
    EXPECT_EQ(pluton::HalfEdgeMesh::INVALID_ID, 0xFFFFFFFFu);
}
```

- [ ] **Step 5: Add to `cpp/tests/CMakeLists.txt`** — append `test_halfedge.cpp` to the `add_executable(pluton_tests ...)` source list:

```cmake
add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
    test_primitives.cpp
    test_halfedge.cpp
)
```

- [ ] **Step 6: Build and run tests**

```bash
pluton-build
pluton-cpp-tests
```

Expected: all 17 tests pass (14 from M1/M2 + 3 new HalfEdgeMeshTest cases).

- [ ] **Step 7: Run Python tests too — they should still pass**

```bash
pluton-py-tests
```

Expected: 101 passed.

- [ ] **Step 8: Commit**

```bash
git add cpp/include/pluton/halfedge.h cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp cpp/CMakeLists.txt cpp/tests/CMakeLists.txt
git commit -m "feat(halfedge): scaffold HalfEdgeMesh class skeleton

Header declarations, struct layouts, INVALID_ID constant. Mutator methods
stub out with std::runtime_error('not implemented yet') — Tasks 2-9 fill
them in via TDD. Query methods that touch only the slab vectors are
implemented up-front (vertex_is_live, edge_is_live, face_is_live, etc.)
so the early tests have something to assert against."
```

---

## Task 2: HalfEdgeMesh.add_vertex

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace stub)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, AddVertexReturnsNewIds) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    EXPECT_NE(v0, v1);
    EXPECT_TRUE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.vertex_is_live(v1));
    EXPECT_TRUE(m.is_dirty());
}

TEST(HalfEdgeMeshTest, AddVertexIsIdempotentOnExactMatch) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(2.0f, 3.0f, 0.0f);
    auto v1 = m.add_vertex(2.0f, 3.0f, 0.0f);
    EXPECT_EQ(v0, v1);
    EXPECT_EQ(m.vertex_slab_size(), 1u);
}

TEST(HalfEdgeMeshTest, AddVertexCollapsesNegativeZero) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(-0.0f, 0.0f, 0.0f);
    EXPECT_EQ(v0, v1);
}

TEST(HalfEdgeMeshTest, AddVertexStoresPosition) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(5.0f, 6.0f, 7.0f);
    auto p = m.vertex_position(v);
    EXPECT_FLOAT_EQ(p[0], 5.0f);
    EXPECT_FLOAT_EQ(p[1], 6.0f);
    EXPECT_FLOAT_EQ(p[2], 7.0f);
}
```

- [ ] **Step 2: Build and run; verify 4 new tests fail**

```bash
pluton-build
pluton-cpp-tests
```

Expected: the 4 new tests fail with the "add_vertex not implemented yet" runtime_error (visible as test failure messages).

- [ ] **Step 3: Implement `add_vertex`** — replace the stub in `cpp/src/halfedge.cpp`:

```cpp
std::uint32_t HalfEdgeMesh::add_vertex(float x, float y, float z) {
    // Collapse negative zero so -0.0 and 0.0 hash identically.
    if (x == 0.0f) x = 0.0f;
    if (y == 0.0f) y = 0.0f;
    if (z == 0.0f) z = 0.0f;

    const std::uint64_t key = pack_position(x, y, z);
    auto it = position_index_.find(key);
    if (it != position_index_.end() && vertices_[it->second].alive) {
        const auto& p = vertices_[it->second].pos;
        if (p[0] == x && p[1] == y && p[2] == z) {
            return it->second;
        }
        // Hash collision on a different float triple; fall through to allocate.
    }
    const std::uint32_t vid = static_cast<std::uint32_t>(vertices_.size());
    vertices_.push_back(Vertex{{x, y, z}, INVALID_ID, true});
    position_index_[key] = vid;
    dirty_ = true;
    return vid;
}
```

- [ ] **Step 4: Build and re-run; expect all C++ tests pass**

```bash
pluton-build
pluton-cpp-tests
```

Expected: 21 tests passed (17 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): HalfEdgeMesh::add_vertex with position-index dedup

Idempotent on exact float32 equality via a position-bytes hash key.
Collapses negative zero so -0.0 and 0.0 are treated identically (same
fix M2's Scene.add_vertex applies in Python; the C++ side now matches)."
```

---

## Task 3: HalfEdgeMesh.add_halfedge_pair

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace stub)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, AddHalfedgePairReturnsEdgeId) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v0, v1);
    EXPECT_EQ(e, 0u);
    EXPECT_TRUE(m.edge_is_live(e));
    EXPECT_EQ(m.halfedge_slab_size(), 2u);  // exactly one pair allocated
}

TEST(HalfEdgeMeshTest, AddHalfedgePairIsIdempotentUnordered) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto a = m.add_halfedge_pair(v0, v1);
    auto b = m.add_halfedge_pair(v1, v0);
    EXPECT_EQ(a, b);
    EXPECT_EQ(m.halfedge_slab_size(), 2u);
}

TEST(HalfEdgeMeshTest, AddHalfedgePairRejectsSelfLoop) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    EXPECT_THROW(m.add_halfedge_pair(v0, v0), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, AddHalfedgePairWiresTwinsAndOrigins) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v1, v0);  // swapped order on input

    const auto verts = m.edge_vertices(e);
    EXPECT_EQ(verts[0], std::min(v0, v1));   // canonical: v1 < v2
    EXPECT_EQ(verts[1], std::max(v0, v1));

    const std::uint32_t he_a = e * 2;
    const std::uint32_t he_b = he_a + 1;
    EXPECT_EQ(m.halfedge_twin(he_a), he_b);
    EXPECT_EQ(m.halfedge_twin(he_b), he_a);
    EXPECT_EQ(m.halfedge_origin(he_a), std::min(v0, v1));
    EXPECT_EQ(m.halfedge_origin(he_b), std::max(v0, v1));
    EXPECT_EQ(m.halfedge_face(he_a), pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_EQ(m.halfedge_face(he_b), pluton::HalfEdgeMesh::INVALID_ID);
}
```

- [ ] **Step 2: Build and run; verify the 4 new tests fail**

```bash
pluton-build
pluton-cpp-tests
```

Expected: 4 failures from the new tests.

- [ ] **Step 3: Implement `add_halfedge_pair`** — replace the stub in `cpp/src/halfedge.cpp`:

```cpp
std::uint32_t HalfEdgeMesh::add_halfedge_pair(std::uint32_t v1_id, std::uint32_t v2_id) {
    if (v1_id == v2_id) {
        throw std::invalid_argument("HalfEdgeMesh::add_halfedge_pair: self-loop at vertex " + std::to_string(v1_id));
    }
    if (!vertex_is_live(v1_id)) {
        throw std::out_of_range("HalfEdgeMesh::add_halfedge_pair: v1_id " + std::to_string(v1_id) + " is not live");
    }
    if (!vertex_is_live(v2_id)) {
        throw std::out_of_range("HalfEdgeMesh::add_halfedge_pair: v2_id " + std::to_string(v2_id) + " is not live");
    }
    const std::uint32_t v_min = std::min(v1_id, v2_id);
    const std::uint32_t v_max = std::max(v1_id, v2_id);
    const std::uint64_t key = pack_pair(v_min, v_max);
    auto it = edge_index_.find(key);
    if (it != edge_index_.end() && edge_is_live(it->second)) {
        return it->second;
    }
    const std::uint32_t he_a = static_cast<std::uint32_t>(halfedges_.size());
    const std::uint32_t he_b = he_a + 1;
    const std::uint32_t edge_id = he_a / 2;
    halfedges_.push_back(HalfEdge{v_min, INVALID_ID, he_b, INVALID_ID, true});
    halfedges_.push_back(HalfEdge{v_max, INVALID_ID, he_a, INVALID_ID, true});
    edge_index_[key] = edge_id;
    dirty_ = true;
    return edge_id;
}
```

- [ ] **Step 4: Build and re-run; expect all pass**

```bash
pluton-build
pluton-cpp-tests
```

Expected: 25 tests passed (21 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): HalfEdgeMesh::add_halfedge_pair with twin wiring

Always allocates two half-edges at adjacent indices (2*edge_id and
2*edge_id+1) so the edge ID and the pair indices are trivially derived
from each other. Canonical convention: he[2*e_id].origin = min(v1, v2);
he[2*e_id+1].origin = max(v1, v2). Twin pointers set up; face pointers
left as INVALID_ID until add_face_from_loop wires them. Idempotent on
unordered (v1, v2); rejects self-loops with std::invalid_argument."
```

---

## Task 4: HalfEdgeMesh.add_face_from_loop

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace stub)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, AddFaceFromLoopWiresBoundaryCycle) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(1.0f, 1.0f, 0.0f);
    auto v3 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);

    const std::vector<std::uint32_t> loop = {v0, v1, v2, v3};
    const std::vector<std::int32_t> tris = {static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v1), static_cast<std::int32_t>(v2),
                                            static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v2), static_cast<std::int32_t>(v3)};
    auto f = m.add_face_from_loop(loop, tris);
    EXPECT_EQ(f, 0u);
    EXPECT_TRUE(m.face_is_live(f));
    EXPECT_EQ(m.face_loop_vertices(f), loop);
    EXPECT_EQ(m.face_triangles(f), tris);
}

TEST(HalfEdgeMeshTest, AddFaceFromLoopRejectsShortLoop) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    EXPECT_THROW(m.add_face_from_loop({v0, v1}, {}), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, AddFaceFromLoopSetsHalfedgeFacePointers) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    const std::vector<std::int32_t> tris = {static_cast<std::int32_t>(v0),
                                            static_cast<std::int32_t>(v1),
                                            static_cast<std::int32_t>(v2)};
    auto f = m.add_face_from_loop({v0, v1, v2}, tris);

    // For each edge in the loop, exactly ONE of the two halfedges should have
    // its face set to f (the one walking the loop in order). The twin should
    // stay at INVALID_ID (it's a boundary edge).
    for (std::uint32_t e = 0; e < 3; ++e) {
        const std::uint32_t he_a = e * 2;
        const std::uint32_t he_b = he_a + 1;
        EXPECT_TRUE(m.halfedge_face(he_a) == f || m.halfedge_face(he_b) == f);
        EXPECT_TRUE(m.halfedge_face(he_a) == pluton::HalfEdgeMesh::INVALID_ID || m.halfedge_face(he_b) == pluton::HalfEdgeMesh::INVALID_ID);
    }
}
```

- [ ] **Step 2: Build and run; verify 3 new tests fail**

```bash
pluton-build && pluton-cpp-tests
```

- [ ] **Step 3: Implement `add_face_from_loop`** — replace the stub in `cpp/src/halfedge.cpp`:

```cpp
std::uint32_t HalfEdgeMesh::add_face_from_loop(const std::vector<std::uint32_t>& loop,
                                                const std::vector<std::int32_t>& triangles) {
    if (loop.size() < 3) {
        throw std::invalid_argument("HalfEdgeMesh::add_face_from_loop: loop has " + std::to_string(loop.size()) + " vertices; minimum 3");
    }
    for (auto v : loop) {
        if (!vertex_is_live(v)) {
            throw std::out_of_range("HalfEdgeMesh::add_face_from_loop: vertex " + std::to_string(v) + " is not live");
        }
    }
    const std::uint32_t f_id = static_cast<std::uint32_t>(faces_.size());
    Face f{INVALID_ID, {0.0f, 0.0f, 1.0f}, triangles, loop, true};

    // Wire each loop[i] → loop[i+1] half-edge to point to loop[i+1] → loop[i+2].
    // The half-edge from v_from to v_to has origin = v_from. Given the canonical
    // convention (he[2*e].origin = min, he[2*e+1].origin = max), pick the index
    // that matches v_from.
    const std::size_t n = loop.size();
    std::vector<std::uint32_t> loop_halfedges(n, INVALID_ID);
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t v_from = loop[i];
        const std::uint32_t v_to = loop[(i + 1) % n];
        const std::uint32_t v_min = std::min(v_from, v_to);
        const std::uint32_t v_max = std::max(v_from, v_to);
        const std::uint64_t key = pack_pair(v_min, v_max);
        auto it = edge_index_.find(key);
        if (it == edge_index_.end() || !edge_is_live(it->second)) {
            throw std::invalid_argument("HalfEdgeMesh::add_face_from_loop: edge ("
                + std::to_string(v_from) + ", " + std::to_string(v_to) + ") is missing");
        }
        const std::uint32_t edge_id = it->second;
        loop_halfedges[i] = (v_from < v_to) ? (edge_id * 2) : (edge_id * 2 + 1);
    }
    // Wire next pointers + face pointers.
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t he = loop_halfedges[i];
        const std::uint32_t he_next = loop_halfedges[(i + 1) % n];
        halfedges_[he].next = he_next;
        halfedges_[he].face = f_id;
    }
    f.boundary_he = loop_halfedges[0];
    // outgoing_he on each loop vertex points to one of its outgoing half-edges
    // (any will do for now; M3b's adjacency walks pick a starting half-edge).
    for (std::size_t i = 0; i < n; ++i) {
        if (vertices_[loop[i]].outgoing_he == INVALID_ID) {
            vertices_[loop[i]].outgoing_he = loop_halfedges[i];
        }
    }

    faces_.push_back(std::move(f));
    dirty_ = true;
    return f_id;
}
```

- [ ] **Step 4: Build and re-run**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 28 tests passed (25 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): HalfEdgeMesh::add_face_from_loop wires boundary cycle

For each consecutive vertex pair in the loop, picks the appropriate half-edge
(by canonical-ordering convention) and sets its next/face pointers so walking
'next' around the loop yields the boundary. Plane normal stays (0, 0, 1) for
M3a (ground-plane convention from M2). Caller passes pre-computed earcut
triangles; storage is verbatim."
```

---

## Task 5: HalfEdgeMesh.remove_face

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace stub)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, RemoveFaceTombstonesSlot) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {static_cast<std::int32_t>(v0), static_cast<std::int32_t>(v1), static_cast<std::int32_t>(v2)});
    EXPECT_TRUE(m.face_is_live(f));

    m.remove_face(f);
    EXPECT_FALSE(m.face_is_live(f));

    // Vertices and edges stay alive.
    EXPECT_TRUE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.edge_is_live(0u));
}

TEST(HalfEdgeMeshTest, RemoveFaceClearsHalfedgeFacePointers) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});

    m.remove_face(f);
    for (std::uint32_t he = 0; he < m.halfedge_slab_size(); ++he) {
        EXPECT_EQ(m.halfedge_face(he), pluton::HalfEdgeMesh::INVALID_ID);
    }
}

TEST(HalfEdgeMeshTest, RemoveFaceAlreadyDeadThrows) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f = m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});
    m.remove_face(f);
    EXPECT_THROW(m.remove_face(f), std::out_of_range);
}
```

- [ ] **Step 2: Build and run; verify 3 fail**

```bash
pluton-build && pluton-cpp-tests
```

- [ ] **Step 3: Implement `remove_face`**

Replace the `remove_face` stub:

```cpp
void HalfEdgeMesh::remove_face(std::uint32_t f_id) {
    if (!face_is_live(f_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_face: face " + std::to_string(f_id) + " is not live");
    }
    // Walk the boundary half-edge cycle and clear face pointers.
    Face& f = faces_[f_id];
    std::uint32_t he = f.boundary_he;
    if (he != INVALID_ID) {
        const std::uint32_t start = he;
        do {
            halfedges_[he].face = INVALID_ID;
            he = halfedges_[he].next;
            if (he == INVALID_ID) break;  // defensive: malformed cycle
        } while (he != start);
    }
    f.alive = false;
    f.boundary_he = INVALID_ID;
    dirty_ = true;
}
```

- [ ] **Step 4: Build and re-run**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 31 tests passed (28 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): HalfEdgeMesh::remove_face tombstones slot

Walks the boundary half-edge cycle and clears each half-edge's face
pointer (becomes a boundary edge). Vertices and edges stay alive —
push/pull (M3b) needs them around to reuse for the prism's side faces.
Double-remove throws std::out_of_range."
```

---

## Task 6: HalfEdgeMesh.remove_edge + remove_vertex

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace 2 stubs)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, RemoveEdgeRejectsIfFaceUsesIt) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});
    EXPECT_THROW(m.remove_edge(0u), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, RemoveEdgeAfterFaceWorks) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    EXPECT_FALSE(m.edge_is_live(0u));
}

TEST(HalfEdgeMeshTest, RemoveEdgeAlreadyDeadThrows) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    EXPECT_THROW(m.remove_edge(0u), std::out_of_range);
}

TEST(HalfEdgeMeshTest, RemoveVertexRejectsIfEdgeUsesIt) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    EXPECT_THROW(m.remove_vertex(v0), std::invalid_argument);
}

TEST(HalfEdgeMeshTest, RemoveVertexAfterEdgeWorks) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.remove_edge(0u);
    m.remove_vertex(v0);
    EXPECT_FALSE(m.vertex_is_live(v0));
    EXPECT_TRUE(m.vertex_is_live(v1));
}
```

- [ ] **Step 2: Build and run; verify 5 fail**

```bash
pluton-build && pluton-cpp-tests
```

- [ ] **Step 3: Implement `remove_edge` and `remove_vertex`**

Replace both stubs in `cpp/src/halfedge.cpp`:

```cpp
void HalfEdgeMesh::remove_edge(std::uint32_t e_id) {
    if (!edge_is_live(e_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_edge: edge " + std::to_string(e_id) + " is not live");
    }
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    if (halfedges_[he_a].face != INVALID_ID || halfedges_[he_b].face != INVALID_ID) {
        throw std::invalid_argument("HalfEdgeMesh::remove_edge: edge " + std::to_string(e_id) + " still bordered by a face");
    }
    const std::uint32_t v_min = halfedges_[he_a].origin;
    const std::uint32_t v_max = halfedges_[he_b].origin;
    edge_index_.erase(pack_pair(v_min, v_max));
    halfedges_[he_a].alive = false;
    halfedges_[he_b].alive = false;
    dirty_ = true;
}

void HalfEdgeMesh::remove_vertex(std::uint32_t v_id) {
    if (!vertex_is_live(v_id)) {
        throw std::out_of_range("HalfEdgeMesh::remove_vertex: vertex " + std::to_string(v_id) + " is not live");
    }
    // Scan live half-edges; reject if any has origin == v_id.
    for (const auto& he : halfedges_) {
        if (he.alive && he.origin == v_id) {
            throw std::invalid_argument("HalfEdgeMesh::remove_vertex: vertex " + std::to_string(v_id) + " still has incident edges");
        }
    }
    const auto& v = vertices_[v_id];
    position_index_.erase(pack_position(v.pos[0], v.pos[1], v.pos[2]));
    vertices_[v_id].alive = false;
    dirty_ = true;
}
```

- [ ] **Step 4: Build and re-run**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 36 tests passed (31 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): remove_edge / remove_vertex with reject-if-referenced

Strict cascade: remove_edge throws if any half-edge of the pair still has
a face attached; remove_vertex throws if any live half-edge has it as
origin. Caller must tear down in order (face → edge → vertex). Removed
entities tombstone the slot and erase from the dedup indexes; IDs stay
valid for restore_* in subsequent tasks."
```

---

## Task 7: HalfEdgeMesh.restore_*

**Files:**
- Modify: `cpp/src/halfedge.cpp` (replace 3 stubs)
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the failing tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, RestoreVertexRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(1.0f, 2.0f, 3.0f);
    m.remove_vertex(v);
    EXPECT_FALSE(m.vertex_is_live(v));

    m.restore_vertex(v, 1.0f, 2.0f, 3.0f);
    EXPECT_TRUE(m.vertex_is_live(v));
    auto p = m.vertex_position(v);
    EXPECT_FLOAT_EQ(p[0], 1.0f);
    EXPECT_FLOAT_EQ(p[1], 2.0f);
    EXPECT_FLOAT_EQ(p[2], 3.0f);
}

TEST(HalfEdgeMeshTest, RestoreVertexLiveSlotThrows) {
    pluton::HalfEdgeMesh m;
    auto v = m.add_vertex(1.0f, 2.0f, 3.0f);
    EXPECT_THROW(m.restore_vertex(v, 0.0f, 0.0f, 0.0f), std::logic_error);
}

TEST(HalfEdgeMeshTest, RestoreEdgeRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto e = m.add_halfedge_pair(v0, v1);
    m.remove_edge(e);
    EXPECT_FALSE(m.edge_is_live(e));

    m.restore_edge(e, v0, v1);
    EXPECT_TRUE(m.edge_is_live(e));
    auto verts = m.edge_vertices(e);
    EXPECT_EQ(verts[0], std::min(v0, v1));
    EXPECT_EQ(verts[1], std::max(v0, v1));
}

TEST(HalfEdgeMeshTest, RestoreFaceRoundTrips) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    const std::vector<std::int32_t> tris = {0, 1, 2};
    auto f = m.add_face_from_loop({v0, v1, v2}, tris);
    m.remove_face(f);
    EXPECT_FALSE(m.face_is_live(f));

    m.restore_face(f, {v0, v1, v2}, tris);
    EXPECT_TRUE(m.face_is_live(f));
    EXPECT_EQ(m.face_loop_vertices(f), std::vector<std::uint32_t>({v0, v1, v2}));
}
```

- [ ] **Step 2: Build and run; verify 4 fail**

```bash
pluton-build && pluton-cpp-tests
```

- [ ] **Step 3: Implement the three `restore_*` methods**

Replace the stubs in `cpp/src/halfedge.cpp`:

```cpp
void HalfEdgeMesh::restore_vertex(std::uint32_t v_id, float x, float y, float z) {
    if (v_id >= vertices_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_vertex: v_id " + std::to_string(v_id) + " out of range");
    }
    if (vertices_[v_id].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_vertex: slot " + std::to_string(v_id) + " is already live");
    }
    if (x == 0.0f) x = 0.0f;
    if (y == 0.0f) y = 0.0f;
    if (z == 0.0f) z = 0.0f;
    vertices_[v_id].pos[0] = x;
    vertices_[v_id].pos[1] = y;
    vertices_[v_id].pos[2] = z;
    vertices_[v_id].alive = true;
    position_index_[pack_position(x, y, z)] = v_id;
    dirty_ = true;
}

void HalfEdgeMesh::restore_edge(std::uint32_t e_id, std::uint32_t v1_id, std::uint32_t v2_id) {
    const std::uint32_t he_a = e_id * 2;
    const std::uint32_t he_b = he_a + 1;
    if (he_b >= halfedges_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_edge: e_id " + std::to_string(e_id) + " out of range");
    }
    if (halfedges_[he_a].alive || halfedges_[he_b].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_edge: slot " + std::to_string(e_id) + " is already live");
    }
    const std::uint32_t v_min = std::min(v1_id, v2_id);
    const std::uint32_t v_max = std::max(v1_id, v2_id);
    halfedges_[he_a].origin = v_min;
    halfedges_[he_a].face = INVALID_ID;
    halfedges_[he_a].next = INVALID_ID;
    halfedges_[he_a].alive = true;
    halfedges_[he_b].origin = v_max;
    halfedges_[he_b].face = INVALID_ID;
    halfedges_[he_b].next = INVALID_ID;
    halfedges_[he_b].alive = true;
    edge_index_[pack_pair(v_min, v_max)] = e_id;
    dirty_ = true;
}

void HalfEdgeMesh::restore_face(std::uint32_t f_id,
                                 const std::vector<std::uint32_t>& loop,
                                 const std::vector<std::int32_t>& triangles) {
    if (f_id >= faces_.size()) {
        throw std::out_of_range("HalfEdgeMesh::restore_face: f_id " + std::to_string(f_id) + " out of range");
    }
    if (faces_[f_id].alive) {
        throw std::logic_error("HalfEdgeMesh::restore_face: slot " + std::to_string(f_id) + " is already live");
    }
    // Same wiring as add_face_from_loop but writes into the existing slot.
    const std::size_t n = loop.size();
    std::vector<std::uint32_t> loop_halfedges(n, INVALID_ID);
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t v_from = loop[i];
        const std::uint32_t v_to = loop[(i + 1) % n];
        const std::uint32_t v_min = std::min(v_from, v_to);
        const std::uint32_t v_max = std::max(v_from, v_to);
        auto it = edge_index_.find(pack_pair(v_min, v_max));
        if (it == edge_index_.end() || !edge_is_live(it->second)) {
            throw std::invalid_argument("HalfEdgeMesh::restore_face: edge ("
                + std::to_string(v_from) + ", " + std::to_string(v_to) + ") is missing");
        }
        loop_halfedges[i] = (v_from < v_to) ? (it->second * 2) : (it->second * 2 + 1);
    }
    for (std::size_t i = 0; i < n; ++i) {
        const std::uint32_t he = loop_halfedges[i];
        halfedges_[he].next = loop_halfedges[(i + 1) % n];
        halfedges_[he].face = f_id;
    }
    Face& f = faces_[f_id];
    f.boundary_he = loop_halfedges[0];
    f.tris = triangles;
    f.loop = loop;
    f.alive = true;
    dirty_ = true;
}
```

- [ ] **Step 4: Build and re-run**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 40 tests passed (36 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): restore_vertex / restore_edge / restore_face

Inverse of the remove_* methods. Each restore_* asserts the slot is
currently tombstoned (raises std::logic_error if already live —
prevents double-undo bugs). Caller passes the original ID plus the
payload (position; vertex pair; loop + triangles). The slot is brought
back to life with the same ID it had before removal."
```

---

## Task 8: `next_live_*` ↔ Python iteration safety (covered already in Task 1) + tests for `clear` and `dirty`

The query helpers `next_live_vertex` / `next_live_edge` / `next_live_face` were already implemented in Task 1's setup along with `clear` and `is_dirty`/`mark_clean`. This task adds explicit tests for that behavior.

**Files:**
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the tests**

```cpp
TEST(HalfEdgeMeshTest, NextLiveVertexSkipsTombstones) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(2.0f, 0.0f, 0.0f);
    EXPECT_EQ(m.next_live_vertex(0), v0);
    EXPECT_EQ(m.next_live_vertex(v0 + 1), v1);
    EXPECT_EQ(m.next_live_vertex(v1 + 1), v2);

    m.remove_vertex(v1);
    EXPECT_EQ(m.next_live_vertex(0), v0);
    EXPECT_EQ(m.next_live_vertex(v0 + 1), v2);   // skipped v1
    EXPECT_EQ(m.next_live_vertex(v2 + 1), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, ClearEmptiesEverythingAndMarksDirty) {
    pluton::HalfEdgeMesh m;
    m.add_vertex(0.0f, 0.0f, 0.0f);
    m.add_vertex(1.0f, 0.0f, 0.0f);
    m.mark_clean();
    EXPECT_FALSE(m.is_dirty());

    m.clear();
    EXPECT_TRUE(m.is_dirty());
    EXPECT_EQ(m.vertex_slab_size(), 0u);
    EXPECT_EQ(m.next_live_vertex(0), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, MarkCleanClearsDirty) {
    pluton::HalfEdgeMesh m;
    m.add_vertex(0.0f, 0.0f, 0.0f);
    EXPECT_TRUE(m.is_dirty());
    m.mark_clean();
    EXPECT_FALSE(m.is_dirty());
}
```

- [ ] **Step 2: Build and run — should pass immediately since the implementations are already present from Task 1**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 43 tests passed (40 + 3 new).

- [ ] **Step 3: Commit**

```bash
git add cpp/tests/test_halfedge.cpp
git commit -m "test(halfedge): cover next_live_* + clear + dirty flag semantics

The implementations have been in place since Task 1 (they touch only the
slab vectors, no method bodies needed beyond the queries). This task adds
the explicit behavioral tests."
```

---

## Task 9: HalfEdgeMesh.edge_line_buffer + face_triangle_buffer

These were also implemented in Task 1. This task adds tests.

**Files:**
- Modify: `cpp/tests/test_halfedge.cpp` (append tests)

- [ ] **Step 1: Write the tests**

```cpp
TEST(HalfEdgeMeshTest, EdgeLineBufferShape) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);

    const auto buf = m.edge_line_buffer();
    ASSERT_EQ(buf.size(), 6u);  // 2 endpoints × 3 floats
    EXPECT_FLOAT_EQ(buf[0], 0.0f); EXPECT_FLOAT_EQ(buf[1], 0.0f); EXPECT_FLOAT_EQ(buf[2], 0.0f);
    EXPECT_FLOAT_EQ(buf[3], 1.0f); EXPECT_FLOAT_EQ(buf[4], 0.0f); EXPECT_FLOAT_EQ(buf[5], 0.0f);
}

TEST(HalfEdgeMeshTest, EdgeLineBufferSkipsTombstones) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(2.0f, 0.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.remove_edge(0u);

    const auto buf = m.edge_line_buffer();
    EXPECT_EQ(buf.size(), 6u);  // only the live edge contributes
}

TEST(HalfEdgeMeshTest, FaceTriangleBufferShape) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    auto v2 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {0, 1, 2});

    auto [positions, normals] = m.face_triangle_buffer();
    EXPECT_EQ(positions.size(), 9u);  // 1 triangle × 3 verts × 3 floats
    EXPECT_EQ(normals.size(), 9u);
    // Normal of every vertex is the face's +Z normal.
    for (std::size_t i = 0; i + 2 < normals.size(); i += 3) {
        EXPECT_FLOAT_EQ(normals[i + 0], 0.0f);
        EXPECT_FLOAT_EQ(normals[i + 1], 0.0f);
        EXPECT_FLOAT_EQ(normals[i + 2], 1.0f);
    }
}
```

- [ ] **Step 2: Build and run**

```bash
pluton-build && pluton-cpp-tests
```

Expected: 46 tests passed (43 + 3 new).

- [ ] **Step 3: Commit**

```bash
git add cpp/tests/test_halfedge.cpp
git commit -m "test(halfedge): cover edge_line_buffer + face_triangle_buffer

Verifies shape, tombstone-skipping, and +Z normal output. Implementations
have been in place since Task 1."
```

---

## Task 10: nanobind bindings for HalfEdgeMesh

**Files:**
- Modify: `cpp/bindings/module.cpp`
- Create: `tests/test_halfedge_python.py`

- [ ] **Step 1: Write the Python smoke tests** at `tests/test_halfedge_python.py`

```python
"""Tests for the nanobind bindings exposing HalfEdgeMesh to Python."""

from __future__ import annotations

import numpy as np
import pytest


def test_halfedge_mesh_constructs_empty():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    assert m.vertex_slab_size() == 0
    assert m.halfedge_slab_size() == 0
    assert m.face_slab_size() == 0


def test_invalid_id_constant():
    from pluton._core import HalfEdgeMesh

    assert HalfEdgeMesh.INVALID_ID == 0xFFFFFFFF


def test_add_vertex_returns_int_id():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    assert v0 == 0
    assert v1 == 1
    assert m.vertex_position(v0) == (0.0, 0.0, 0.0)


def test_add_halfedge_pair_and_face():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v0)
    f = m.add_face_from_loop([v0, v1, v2], [0, 1, 2])
    assert f == 0
    assert m.face_is_live(f)
    assert list(m.face_loop_vertices(f)) == [v0, v1, v2]


def test_remove_face_throws_on_double_remove():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v0)
    f = m.add_face_from_loop([v0, v1, v2], [0, 1, 2])
    m.remove_face(f)
    with pytest.raises(Exception):  # std::out_of_range → IndexError in nanobind
        m.remove_face(f)


def test_buffer_projections_return_lists():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    m.add_halfedge_pair(v0, v1)

    buf = list(m.edge_line_buffer())
    assert len(buf) == 6
```

- [ ] **Step 2: Run; verify they fail with "no attribute HalfEdgeMesh"**

```bash
pluton-py-tests tests/test_halfedge_python.py -v
```

Expected: collection ERROR or 6 FAILs with `AttributeError: module 'pluton._core' has no attribute 'HalfEdgeMesh'`.

- [ ] **Step 3: Add bindings** — edit `cpp/bindings/module.cpp`. Add the include + the binding block.

Add this include after the existing ones:

```cpp
#include "pluton/halfedge.h"
```

Add `using pluton::HalfEdgeMesh;` near the other `using` lines.

Add this binding block inside the `NB_MODULE(_core, m) { ... }` body (after the existing Mesh / make_cube / version bindings):

```cpp
    nb::class_<HalfEdgeMesh>(m, "HalfEdgeMesh", "Half-edge topology mesh — geometric source of truth")
        .def(nb::init<>())

        // Mutators
        .def("add_vertex", &HalfEdgeMesh::add_vertex)
        .def("add_halfedge_pair", &HalfEdgeMesh::add_halfedge_pair)
        .def("add_face_from_loop", &HalfEdgeMesh::add_face_from_loop)
        .def("remove_vertex", &HalfEdgeMesh::remove_vertex)
        .def("remove_edge", &HalfEdgeMesh::remove_edge)
        .def("remove_face", &HalfEdgeMesh::remove_face)
        .def("restore_vertex", &HalfEdgeMesh::restore_vertex)
        .def("restore_edge", &HalfEdgeMesh::restore_edge)
        .def("restore_face", &HalfEdgeMesh::restore_face)
        .def("clear", &HalfEdgeMesh::clear)

        // Queries
        .def("vertex_is_live", &HalfEdgeMesh::vertex_is_live)
        .def("edge_is_live", &HalfEdgeMesh::edge_is_live)
        .def("face_is_live", &HalfEdgeMesh::face_is_live)
        .def("vertex_position", &HalfEdgeMesh::vertex_position)
        .def("edge_vertices", &HalfEdgeMesh::edge_vertices)
        .def("face_loop_vertices", &HalfEdgeMesh::face_loop_vertices)
        .def("face_triangles", &HalfEdgeMesh::face_triangles)

        // Half-edge adjacency (used by M3b push/pull)
        .def("halfedge_origin", &HalfEdgeMesh::halfedge_origin)
        .def("halfedge_next", &HalfEdgeMesh::halfedge_next)
        .def("halfedge_twin", &HalfEdgeMesh::halfedge_twin)
        .def("halfedge_face", &HalfEdgeMesh::halfedge_face)

        // Iteration
        .def("next_live_vertex", &HalfEdgeMesh::next_live_vertex, nb::arg("start") = 0u)
        .def("next_live_edge", &HalfEdgeMesh::next_live_edge, nb::arg("start") = 0u)
        .def("next_live_face", &HalfEdgeMesh::next_live_face, nb::arg("start") = 0u)

        // Buffer projection
        .def("edge_line_buffer", &HalfEdgeMesh::edge_line_buffer)
        .def("face_triangle_buffer", &HalfEdgeMesh::face_triangle_buffer)

        // Dirty flag
        .def("is_dirty", &HalfEdgeMesh::is_dirty)
        .def("mark_clean", &HalfEdgeMesh::mark_clean)

        // Slab introspection (mostly for tests)
        .def("vertex_slab_size", &HalfEdgeMesh::vertex_slab_size)
        .def("halfedge_slab_size", &HalfEdgeMesh::halfedge_slab_size)
        .def("face_slab_size", &HalfEdgeMesh::face_slab_size)

        .def_ro_static("INVALID_ID", &HalfEdgeMesh::INVALID_ID);
```

If the existing `module.cpp` doesn't already `#include <nanobind/stl/vector.h>` and `<nanobind/stl/pair.h>` and `<nanobind/stl/array.h>`, add those — they're needed for the bindings to convert std::vector / std::pair / std::array to/from Python types automatically.

- [ ] **Step 4: Rebuild and run tests**

```bash
pluton-build
pluton-py-tests tests/test_halfedge_python.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full suite**

```bash
pluton-py-tests
```

Expected: 107 passed (101 from M2 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add cpp/bindings/module.cpp tests/test_halfedge_python.py
git commit -m "feat(bindings): expose HalfEdgeMesh to Python via nanobind

All mutators, queries, iteration helpers, buffer projections, half-edge
adjacency helpers, and the INVALID_ID constant. nanobind translates the
C++ exception types: std::out_of_range → IndexError, std::invalid_argument
→ ValueError, std::logic_error → RuntimeError (these mappings are
nanobind defaults). Smoke tests cover construction, add_*, remove_face
double-throw, and buffer projection shape."
```

---

## Task 11: Python Scene refactored as wrapper

This is the **most subtle task** in M3a. The M2 `Scene` class is rewritten internally to delegate every method to the C++ `HalfEdgeMesh`. **All 101 existing M2 tests must continue to pass unchanged.**

**Files:**
- Modify: `python/pluton/scene/scene.py`

- [ ] **Step 1: Read the current `python/pluton/scene/scene.py`** end-to-end (it's about 220 lines after M2 Task 6's regrouping).

- [ ] **Step 2: Replace the entire file content** with the wrapper version below.

```python
"""The editable polygonal scene — thin Python wrapper over the C++ HalfEdgeMesh.

Pure-Python topology is gone. Every public method delegates into the C++
HalfEdgeMesh held in self._mesh, with mapbox-earcut still owning face
triangulation on the Python side.

Idempotent mutators (`add_vertex`; `add_edge` and `add_face_from_loop`
arrive in this same milestone) so tools never have to check existence
before inserting. A single `dirty` flag tracks "has the renderer
seen the current state yet"; the renderer calls `mark_clean()` after
re-uploading buffers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import mapbox_earcut
import numpy as np

from pluton._core import HalfEdgeMesh
from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.vertex import Vertex


class Scene:
    """Editable polygonal scene with stable integer IDs (C++ HalfEdgeMesh backed)."""

    def __init__(self) -> None:
        self._mesh = HalfEdgeMesh()

    # --- Mutators ---------------------------------------------------------

    def add_vertex(self, position: np.ndarray) -> int:
        """Insert a vertex at `position` (float32 (3,)) and return its ID.

        Idempotent on exact equality (delegated to C++ HalfEdgeMesh).
        """
        if position.dtype != np.float32 or position.shape != (3,):
            position = np.asarray(position, dtype=np.float32).reshape(3)
        return self._mesh.add_vertex(float(position[0]), float(position[1]), float(position[2]))

    def add_edge(self, v1_id: int, v2_id: int) -> int:
        """Insert an undirected edge between two existing vertices."""
        if v1_id == v2_id:
            raise ValueError(f"self-loop edge requested at vertex {v1_id}")
        if not self._mesh.vertex_is_live(v1_id):
            raise KeyError(f"add_edge: unknown v1_id={v1_id}")
        if not self._mesh.vertex_is_live(v2_id):
            raise KeyError(f"add_edge: unknown v2_id={v2_id}")
        return self._mesh.add_halfedge_pair(v1_id, v2_id)

    def add_face_from_loop(self, ordered_vertex_ids: Sequence[int]) -> int:
        """Insert a face bounded by the given closed vertex loop.

        Triangulates the loop via mapbox-earcut, then passes both the loop and
        the triangulation into the C++ HalfEdgeMesh.
        """
        loop = tuple(ordered_vertex_ids)
        if len(loop) < 3:
            raise ValueError(f"face needs at least 3 vertices, got {len(loop)}")
        for vid in loop:
            if not self._mesh.vertex_is_live(vid):
                raise KeyError(f"add_face_from_loop: unknown vertex_id={vid}")

        # Build the (N, 2) float32 XY array for earcut.
        xy = np.empty((len(loop), 2), dtype=np.float32)
        for i, vid in enumerate(loop):
            pos = self._mesh.vertex_position(vid)
            xy[i] = (pos[0], pos[1])
        ring_ends = np.array([len(loop)], dtype=np.uint32)
        local_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        # Map local-ring indices to global vertex IDs (flat, length 3*T).
        triangles = [int(loop[i]) for tri in local_indices for i in tri]

        return self._mesh.add_face_from_loop(list(loop), triangles)

    def remove_vertex(self, v_id: int) -> None:
        """Remove a vertex. Raises KeyError if not live, ValueError if still referenced."""
        try:
            self._mesh.remove_vertex(v_id)
        except IndexError as e:
            raise KeyError(str(e)) from None
        except ValueError:
            raise

    def remove_edge(self, e_id: int) -> None:
        try:
            self._mesh.remove_edge(e_id)
        except IndexError as e:
            raise KeyError(str(e)) from None
        except ValueError:
            raise

    def remove_face(self, f_id: int) -> None:
        try:
            self._mesh.remove_face(f_id)
        except IndexError as e:
            raise KeyError(str(e)) from None

    def restore_vertex(self, v_id: int, position: np.ndarray) -> None:
        """Restore a previously-removed vertex with its original ID. Used by undo."""
        position = np.asarray(position, dtype=np.float32).reshape(3)
        self._mesh.restore_vertex(v_id, float(position[0]), float(position[1]), float(position[2]))

    def restore_edge(self, e_id: int, v1_id: int, v2_id: int) -> None:
        """Restore a previously-removed edge with its original ID. Used by undo."""
        self._mesh.restore_edge(e_id, v1_id, v2_id)

    def restore_face(self, f_id: int, ordered_vertex_ids: Sequence[int]) -> None:
        """Restore a previously-removed face with its original ID. Used by undo."""
        loop = tuple(ordered_vertex_ids)
        xy = np.empty((len(loop), 2), dtype=np.float32)
        for i, vid in enumerate(loop):
            pos = self._mesh.vertex_position(vid)
            xy[i] = (pos[0], pos[1])
        ring_ends = np.array([len(loop)], dtype=np.uint32)
        local_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
        local_indices = np.asarray(local_indices, dtype=np.int32).reshape(-1, 3)
        triangles = [int(loop[i]) for tri in local_indices for i in tri]
        self._mesh.restore_face(f_id, list(loop), triangles)

    def clear(self) -> None:
        """Reset the scene to empty. Renderer will re-upload empty buffers."""
        self._mesh.clear()

    # --- Lifecycle (renderer sync) ----------------------------------------

    def mark_clean(self) -> None:
        self._mesh.mark_clean()

    # --- Queries ----------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._mesh.is_dirty()

    def vertex(self, v_id: int) -> Vertex:
        if not self._mesh.vertex_is_live(v_id):
            raise KeyError(f"vertex_id {v_id} is not live")
        pos = self._mesh.vertex_position(v_id)
        return Vertex(id=v_id, position=np.array(pos, dtype=np.float32))

    def edge(self, e_id: int) -> Edge:
        if not self._mesh.edge_is_live(e_id):
            raise KeyError(f"edge_id {e_id} is not live")
        verts = self._mesh.edge_vertices(e_id)
        return Edge(id=e_id, v1_id=verts[0], v2_id=verts[1])

    def face(self, f_id: int) -> Face:
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_id {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        tris = self._mesh.face_triangles(f_id)
        triangles = np.array(tris, dtype=np.int32).reshape(-1, 3)
        return Face(
            id=f_id,
            loop_vertex_ids=tuple(loop),
            plane_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            triangles=triangles,
        )

    def vertices_iter(self) -> Iterable[Vertex]:
        v = self._mesh.next_live_vertex(0)
        while v != HalfEdgeMesh.INVALID_ID:
            yield self.vertex(v)
            v = self._mesh.next_live_vertex(v + 1)

    def edges_iter(self) -> Iterable[Edge]:
        e = self._mesh.next_live_edge(0)
        while e != HalfEdgeMesh.INVALID_ID:
            yield self.edge(e)
            e = self._mesh.next_live_edge(e + 1)

    def faces_iter(self) -> Iterable[Face]:
        f = self._mesh.next_live_face(0)
        while f != HalfEdgeMesh.INVALID_ID:
            yield self.face(f)
            f = self._mesh.next_live_face(f + 1)

    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None:
        """Return the ID of the live vertex closest to `world_xyz` within `tolerance`."""
        best_id: int | None = None
        best_d2 = tolerance * tolerance
        v = self._mesh.next_live_vertex(0)
        while v != HalfEdgeMesh.INVALID_ID:
            pos = self._mesh.vertex_position(v)
            d0 = pos[0] - float(world_xyz[0])
            d1 = pos[1] - float(world_xyz[1])
            d2 = pos[2] - float(world_xyz[2])
            d_sq = d0 * d0 + d1 * d1 + d2 * d2
            if d_sq <= best_d2:
                best_d2 = d_sq
                best_id = v
            v = self._mesh.next_live_vertex(v + 1)
        return best_id

    # --- Render-buffer projection -----------------------------------------

    def edge_line_buffer(self) -> np.ndarray:
        buf = self._mesh.edge_line_buffer()
        if not buf:
            return np.zeros((0, 3), dtype=np.float32)
        return np.asarray(buf, dtype=np.float32).reshape(-1, 3)

    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]:
        positions, normals = self._mesh.face_triangle_buffer()
        if not positions:
            empty = np.zeros((0, 3), dtype=np.float32)
            return empty, empty
        pos = np.asarray(positions, dtype=np.float32).reshape(-1, 3)
        nrm = np.asarray(normals, dtype=np.float32).reshape(-1, 3)
        return pos, nrm
```

- [ ] **Step 3: Run the full M2 test suite — these tests MUST still pass**

```bash
pluton-py-tests
```

Expected: 107 passed (101 M2 + 6 M3a from Task 10). If any M2 test fails, the wrapper has a behavioral mismatch — STOP and report.

Watch for:
- `test_add_edge_returns_new_id` asserts `e == 0` — should still hold because `add_halfedge_pair` allocates `halfedges_` from size 0; `edge_id = halfedge_size / 2 - 1 = 0`.
- `test_clear_resets_dirty_flag_and_removes_everything` — `Scene.mark_clean()` resets dirty; `Scene.clear()` sets it back. Verify.

- [ ] **Step 4: Commit**

```bash
git add python/pluton/scene/scene.py
git commit -m "refactor(scene): Scene becomes a thin wrapper over C++ HalfEdgeMesh

The Python topology dicts (_vertices, _edges, _faces, _position_index,
_edge_index) are replaced with delegation into a single HalfEdgeMesh
instance. Public API is unchanged — every M2 test still passes — but
the underlying storage is now the C++ slab vectors.

Triangulation stays in Python (mapbox-earcut). The C++ HalfEdgeMesh
takes pre-computed triangles as input so M3c can later move earcut to
C++ without changing the binding shape.

Adds remove_vertex / remove_edge / remove_face and restore_* methods
that delegate to HalfEdgeMesh and translate C++ exception types to the
Python convention (IndexError → KeyError; std::logic_error from the
restore-on-live guard surfaces as RuntimeError)."
```

---

## Task 12: Scene.remove_* / restore_* — coverage tests

The methods are already implemented in Task 11. This task adds explicit Python tests for the new behavior.

**Files:**
- Modify: `tests/test_scene.py` (append tests)

- [ ] **Step 1: Append the tests**

```python
def test_remove_face_leaves_verts_and_edges_alive():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    s.add_edge(v0, v1)
    s.add_edge(v1, v2)
    s.add_edge(v2, v0)
    f = s.add_face_from_loop((v0, v1, v2))

    s.remove_face(f)

    assert len(list(s.faces_iter())) == 0
    # Vertices and edges still alive.
    assert len(list(s.vertices_iter())) == 3
    assert len(list(s.edges_iter())) == 3


def test_remove_edge_rejects_if_face_still_uses_it():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    e0 = s.add_edge(v0, v1)
    s.add_edge(v1, v2)
    s.add_edge(v2, v0)
    s.add_face_from_loop((v0, v1, v2))

    with pytest.raises(ValueError):
        s.remove_edge(e0)


def test_remove_vertex_rejects_if_edge_still_uses_it():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    s.add_edge(v0, v1)

    with pytest.raises(ValueError):
        s.remove_vertex(v0)


def test_restore_face_round_trip():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    s.add_edge(v0, v1)
    s.add_edge(v1, v2)
    s.add_edge(v2, v0)
    f = s.add_face_from_loop((v0, v1, v2))
    captured_loop = s.face(f).loop_vertex_ids

    s.remove_face(f)
    assert len(list(s.faces_iter())) == 0

    s.restore_face(f, captured_loop)
    assert len(list(s.faces_iter())) == 1
    restored = s.face(f)
    assert restored.loop_vertex_ids == captured_loop


def test_add_vertex_after_tombstone_at_same_position_allocates_new_id():
    """Position-index only tracks live vertices; tombstoned slots stay tombstoned."""
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([5.0, 5.0, 0.0], dtype=np.float32)
    v0 = s.add_vertex(pos)
    s.remove_vertex(v0)
    v1 = s.add_vertex(pos.copy())
    assert v1 != v0  # new ID; old slot stays tombstoned
```

- [ ] **Step 2: Run the new tests**

```bash
pluton-py-tests tests/test_scene.py -v
```

Expected: all pass (the methods were implemented in Task 11; this just verifies the contract).

- [ ] **Step 3: Run the full suite**

```bash
pluton-py-tests
```

Expected: 112 passed (107 + 5 new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_scene.py
git commit -m "test(scene): cover Scene.remove_* / restore_* contracts

Five behavioral tests: remove_face leaves verts/edges alive; remove_edge
and remove_vertex enforce reject-if-referenced (ValueError); restore_face
round-trips through capture-and-restore; add_vertex with a tombstoned
slot's old position allocates a NEW id rather than resurrecting."
```

---

## Task 13: Command ABC + CompositeCommand

**Files:**
- Create: `python/pluton/commands/__init__.py`
- Create: `python/pluton/commands/command.py`
- Create: `tests/test_command_stack.py` (start the file)

- [ ] **Step 1: Write the failing test** at `tests/test_command_stack.py`

```python
"""Tests for the command framework — Command ABC, CompositeCommand, CommandStack."""

from __future__ import annotations

import numpy as np


class _RecordingCommand:
    """Test helper: records call order without needing a real Scene."""

    def __init__(self, label: str, log: list[str]) -> None:
        self._label = label
        self._log = log

    def do(self, scene) -> None:  # noqa: ANN001
        self._log.append(f"do:{self._label}")

    def undo(self, scene) -> None:  # noqa: ANN001
        self._log.append(f"undo:{self._label}")


def test_composite_do_runs_children_in_order():
    from pluton.commands import CompositeCommand

    log: list[str] = []
    composite = CompositeCommand(
        name="Test",
        children=[_RecordingCommand("a", log), _RecordingCommand("b", log), _RecordingCommand("c", log)],
    )
    composite.do(None)
    assert log == ["do:a", "do:b", "do:c"]


def test_composite_undo_runs_children_in_reverse_order():
    from pluton.commands import CompositeCommand

    log: list[str] = []
    composite = CompositeCommand(
        name="Test",
        children=[_RecordingCommand("a", log), _RecordingCommand("b", log), _RecordingCommand("c", log)],
    )
    composite.undo(None)
    assert log == ["undo:c", "undo:b", "undo:a"]
```

- [ ] **Step 2: Run; verify fails**

```bash
pluton-py-tests tests/test_command_stack.py -v
```

Expected: 2 FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `python/pluton/commands/command.py`**

```python
"""Command framework: Command ABC + CompositeCommand."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class Command(ABC):
    """A reversible operation on the Scene.

    do() executes the operation and may capture state needed by undo().
    undo() reverses the operation exactly. Both must be idempotent on
    re-entry — i.e. `do(); undo(); do(); undo()` leaves the scene in the
    same state as `do(); undo()`.
    """

    name: str = "Command"

    @abstractmethod
    def do(self, scene) -> None: ...  # noqa: ANN001

    @abstractmethod
    def undo(self, scene) -> None: ...  # noqa: ANN001


@dataclass
class CompositeCommand(Command):
    """A sequence of commands executed/undone as one unit (per-gesture grouping)."""

    name: str
    children: list[Command] = field(default_factory=list)

    def do(self, scene) -> None:  # noqa: ANN001
        for c in self.children:
            c.do(scene)

    def undo(self, scene) -> None:  # noqa: ANN001
        for c in reversed(self.children):
            c.undo(scene)
```

- [ ] **Step 4: Create `python/pluton/commands/__init__.py`**

```python
"""Command framework: per-gesture undo/redo via reverse-action commands."""

from __future__ import annotations

from pluton.commands.command import Command, CompositeCommand

__all__ = ["Command", "CompositeCommand"]
```

- [ ] **Step 5: Run; expect 2 pass**

```bash
pluton-py-tests tests/test_command_stack.py -v
```

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/__init__.py python/pluton/commands/command.py tests/test_command_stack.py
git commit -m "feat(commands): add Command ABC + CompositeCommand

Command ABC declares do() and undo() abstract. CompositeCommand groups
children executed in order (do) and reverse order (undo). Used for
per-gesture grouping — one Ctrl+Z undoes a whole tool gesture."
```

---

## Task 14: CommandStack

**Files:**
- Create: `python/pluton/commands/command_stack.py`
- Modify: `python/pluton/commands/__init__.py`
- Modify: `tests/test_command_stack.py` (append tests)

- [ ] **Step 1: Append the failing tests**

```python
def test_command_stack_starts_empty():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert not s.can_undo
    assert not s.can_redo


def test_execute_runs_do_and_pushes_to_undo_stack():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    assert log == ["do:x"]
    assert s.can_undo
    assert not s.can_redo


def test_push_executed_appends_without_calling_do():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.push_executed(cmd)
    assert log == []  # do was NOT called
    assert s.can_undo


def test_undo_calls_command_undo_and_moves_to_redo():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    log.clear()
    assert s.undo(scene=None) is True
    assert log == ["undo:x"]
    assert not s.can_undo
    assert s.can_redo


def test_redo_runs_do_again():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    cmd = CompositeCommand(name="C", children=[_RecordingCommand("x", log)])
    s = CommandStack()
    s.execute(cmd, scene=None)
    s.undo(scene=None)
    log.clear()
    assert s.redo(scene=None) is True
    assert log == ["do:x"]


def test_new_execute_clears_redo_stack():
    from pluton.commands import CommandStack, CompositeCommand

    log: list[str] = []
    s = CommandStack()
    cmd_a = CompositeCommand(name="A", children=[_RecordingCommand("a", log)])
    cmd_b = CompositeCommand(name="B", children=[_RecordingCommand("b", log)])
    s.execute(cmd_a, scene=None)
    s.undo(scene=None)
    assert s.can_redo
    s.execute(cmd_b, scene=None)
    assert not s.can_redo  # new execute cleared redo


def test_undo_on_empty_returns_false():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert s.undo(scene=None) is False


def test_redo_on_empty_returns_false():
    from pluton.commands import CommandStack

    s = CommandStack()
    assert s.redo(scene=None) is False
```

- [ ] **Step 2: Run; verify failure**

```bash
pluton-py-tests tests/test_command_stack.py -v
```

Expected: 8 new FAIL with `ImportError: cannot import name 'CommandStack'`.

- [ ] **Step 3: Create `python/pluton/commands/command_stack.py`**

```python
"""CommandStack: undo + redo with execute / push_executed semantics."""

from __future__ import annotations

from pluton.commands.command import Command


class CommandStack:
    """Owns the undo + redo stacks. Owned by MainWindow."""

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def execute(self, cmd: Command, scene) -> None:  # noqa: ANN001
        """Run cmd.do(scene), push to undo stack, clear redo stack."""
        cmd.do(scene)
        self._undo.append(cmd)
        self._redo.clear()

    def push_executed(self, cmd: Command) -> None:
        """Append a command whose do() was already called incrementally.

        Used by tools that build a CompositeCommand mutating the scene as
        the gesture progresses so the snap engine sees in-progress state.
        At gesture completion the tool calls push_executed(composite) to
        register it for undo without re-executing.
        """
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self, scene) -> bool:  # noqa: ANN001
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo(scene)
        self._redo.append(cmd)
        return True

    def redo(self, scene) -> bool:  # noqa: ANN001
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.do(scene)
        self._undo.append(cmd)
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
```

- [ ] **Step 4: Update `python/pluton/commands/__init__.py`**

Replace:
```python
from pluton.commands.command import Command, CompositeCommand

__all__ = ["Command", "CompositeCommand"]
```
with:
```python
from pluton.commands.command import Command, CompositeCommand
from pluton.commands.command_stack import CommandStack

__all__ = ["Command", "CommandStack", "CompositeCommand"]
```

- [ ] **Step 5: Run; expect 10 pass**

```bash
pluton-py-tests tests/test_command_stack.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/command_stack.py python/pluton/commands/__init__.py tests/test_command_stack.py
git commit -m "feat(commands): add CommandStack with execute / push_executed / undo / redo

Two push-paths: execute(cmd, scene) runs cmd.do() and pushes; push_executed(cmd)
just pushes (tool already ran do() incrementally during gesture). undo() and
redo() return False on empty stacks. New execute clears the redo stack."
```

---

## Task 15: Add-side scene commands

**Files:**
- Create: `python/pluton/commands/scene_commands.py`
- Create: `tests/test_scene_commands.py`

- [ ] **Step 1: Write the failing tests** at `tests/test_scene_commands.py`

```python
"""Tests for AddVertex / AddEdge / AddFace / Remove* / ClearScene commands."""

from __future__ import annotations

import numpy as np


def _three_vertex_scene():
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = s.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    return s, v0, v1, v2


def test_add_vertex_command_round_trip():
    from pluton.commands.scene_commands import AddVertexCommand
    from pluton.scene import Scene

    s = Scene()
    pos = np.array([3.0, 4.0, 0.0], dtype=np.float32)
    cmd = AddVertexCommand(pos)

    cmd.do(s)
    assert len(list(s.vertices_iter())) == 1

    cmd.undo(s)
    assert len(list(s.vertices_iter())) == 0

    cmd.do(s)
    assert len(list(s.vertices_iter())) == 1


def test_add_edge_command_round_trip():
    from pluton.commands.scene_commands import AddEdgeCommand
    from pluton.scene import Scene

    s = Scene()
    v0 = s.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = s.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    cmd = AddEdgeCommand(v0, v1)

    cmd.do(s)
    assert len(list(s.edges_iter())) == 1

    cmd.undo(s)
    assert len(list(s.edges_iter())) == 0


def test_add_face_command_round_trip():
    from pluton.commands.scene_commands import AddFaceCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    cmd = AddFaceCommand((v0, v1, v2))

    cmd.do(s)
    assert len(list(s.faces_iter())) == 1

    cmd.undo(s)
    assert len(list(s.faces_iter())) == 0
```

- [ ] **Step 2: Run; verify failure**

```bash
pluton-py-tests tests/test_scene_commands.py -v
```

- [ ] **Step 3: Create `python/pluton/commands/scene_commands.py`**

```python
"""Concrete commands for Scene mutations."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from pluton.commands.command import Command


class AddVertexCommand(Command):
    name = "Add Vertex"

    def __init__(self, position: np.ndarray) -> None:
        self._position = np.asarray(position, dtype=np.float32).reshape(3).copy()
        self._vertex_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._vertex_id = scene.add_vertex(self._position)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._vertex_id is not None, "AddVertexCommand.undo before do"
        scene.remove_vertex(self._vertex_id)


class AddEdgeCommand(Command):
    name = "Add Edge"

    def __init__(self, v1_id: int, v2_id: int) -> None:
        self._v1, self._v2 = v1_id, v2_id
        self._edge_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._edge_id = scene.add_edge(self._v1, self._v2)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._edge_id is not None, "AddEdgeCommand.undo before do"
        scene.remove_edge(self._edge_id)


class AddFaceCommand(Command):
    name = "Add Face"

    def __init__(self, loop: Sequence[int]) -> None:
        self._loop = tuple(loop)
        self._face_id: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._face_id = scene.add_face_from_loop(self._loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._face_id is not None, "AddFaceCommand.undo before do"
        scene.remove_face(self._face_id)
```

- [ ] **Step 4: Run tests**

```bash
pluton-py-tests tests/test_scene_commands.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full suite**

```bash
pluton-py-tests
```

Expected: 125 passed (112 + 10 from Task 14 + 3 from this task).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_scene_commands.py
git commit -m "feat(commands): add AddVertexCommand / AddEdgeCommand / AddFaceCommand

Each command captures the returned ID in do() so undo() can call the
appropriate Scene.remove_* method. round-trip tests verify do/undo/do
cycles leave the scene at the expected state."
```

---

## Task 16: Remove-side scene commands

**Files:**
- Modify: `python/pluton/commands/scene_commands.py`
- Modify: `tests/test_scene_commands.py`

- [ ] **Step 1: Append failing tests**

```python
def test_remove_face_command_round_trip():
    from pluton.commands.scene_commands import AddFaceCommand, RemoveFaceCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    add = AddFaceCommand((v0, v1, v2))
    add.do(s)
    f = next(iter(s.faces_iter())).id

    remove = RemoveFaceCommand(f)
    remove.do(s)
    assert len(list(s.faces_iter())) == 0

    remove.undo(s)
    assert len(list(s.faces_iter())) == 1
    assert next(iter(s.faces_iter())).id == f


def test_remove_edge_command_round_trip():
    from pluton.commands.scene_commands import AddEdgeCommand, RemoveEdgeCommand
    from pluton.scene import Scene

    s, v0, v1, _ = _three_vertex_scene()
    add = AddEdgeCommand(v0, v1)
    add.do(s)
    e = next(iter(s.edges_iter())).id

    remove = RemoveEdgeCommand(e)
    remove.do(s)
    assert len(list(s.edges_iter())) == 0

    remove.undo(s)
    assert len(list(s.edges_iter())) == 1


def test_remove_vertex_command_round_trip():
    from pluton.commands.scene_commands import RemoveVertexCommand
    from pluton.scene import Scene

    s = Scene()
    v = s.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))

    remove = RemoveVertexCommand(v)
    remove.do(s)
    assert len(list(s.vertices_iter())) == 0

    remove.undo(s)
    assert len(list(s.vertices_iter())) == 1
    restored = next(iter(s.vertices_iter()))
    assert restored.id == v
    np.testing.assert_array_equal(restored.position, np.array([1.0, 2.0, 0.0], dtype=np.float32))
```

- [ ] **Step 2: Run; verify failure**

```bash
pluton-py-tests tests/test_scene_commands.py -v
```

- [ ] **Step 3: Append to `python/pluton/commands/scene_commands.py`**

```python
class RemoveFaceCommand(Command):
    name = "Remove Face"

    def __init__(self, face_id: int) -> None:
        self._face_id = face_id
        self._captured_loop: tuple[int, ...] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._captured_loop = tuple(scene.face(self._face_id).loop_vertex_ids)
        scene.remove_face(self._face_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured_loop is not None, "RemoveFaceCommand.undo before do"
        scene.restore_face(self._face_id, self._captured_loop)


class RemoveEdgeCommand(Command):
    name = "Remove Edge"

    def __init__(self, edge_id: int) -> None:
        self._edge_id = edge_id
        self._captured: tuple[int, int] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        e = scene.edge(self._edge_id)
        self._captured = (e.v1_id, e.v2_id)
        scene.remove_edge(self._edge_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured is not None, "RemoveEdgeCommand.undo before do"
        scene.restore_edge(self._edge_id, self._captured[0], self._captured[1])


class RemoveVertexCommand(Command):
    name = "Remove Vertex"

    def __init__(self, vertex_id: int) -> None:
        self._vertex_id = vertex_id
        self._captured_pos: np.ndarray | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._captured_pos = scene.vertex(self._vertex_id).position.copy()
        scene.remove_vertex(self._vertex_id)

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured_pos is not None, "RemoveVertexCommand.undo before do"
        scene.restore_vertex(self._vertex_id, self._captured_pos)
```

- [ ] **Step 4: Run tests**

```bash
pluton-py-tests
```

Expected: 128 passed (125 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_scene_commands.py
git commit -m "feat(commands): add RemoveVertex / RemoveEdge / RemoveFace commands

Each captures the removed entity's payload during do() so undo() can
call the appropriate Scene.restore_* method. RemoveFaceCommand stores
the boundary loop; RemoveEdgeCommand stores the vertex pair;
RemoveVertexCommand stores the position. Round-trip tests verify
do/undo/do cycles leave the scene at the expected state with stable IDs."
```

---

## Task 17: ClearSceneCommand + _AddVertexAtId / _AddEdgeAtId / _AddFaceAtId helpers

**Files:**
- Modify: `python/pluton/commands/scene_commands.py`
- Modify: `tests/test_scene_commands.py`

- [ ] **Step 1: Append failing tests**

```python
def test_clear_scene_command_captures_and_restores():
    from pluton.commands.scene_commands import ClearSceneCommand
    from pluton.scene import Scene

    s, v0, v1, v2 = _three_vertex_scene()
    s.add_edge(v0, v1); s.add_edge(v1, v2); s.add_edge(v2, v0)
    s.add_face_from_loop((v0, v1, v2))
    assert len(list(s.vertices_iter())) == 3
    assert len(list(s.edges_iter())) == 3
    assert len(list(s.faces_iter())) == 1

    cmd = ClearSceneCommand()
    cmd.do(s)
    assert len(list(s.vertices_iter())) == 0
    assert len(list(s.edges_iter())) == 0
    assert len(list(s.faces_iter())) == 0

    cmd.undo(s)
    # All IDs restored.
    verts = list(s.vertices_iter())
    edges = list(s.edges_iter())
    faces = list(s.faces_iter())
    assert len(verts) == 3
    assert len(edges) == 3
    assert len(faces) == 1
    assert {v.id for v in verts} == {v0, v1, v2}
```

- [ ] **Step 2: Run; verify failure**

```bash
pluton-py-tests tests/test_scene_commands.py -v
```

- [ ] **Step 3: Append to `python/pluton/commands/scene_commands.py`**

```python
class _AddVertexAtId(Command):
    """Internal: restores a vertex at a specific ID. Used by ClearSceneCommand.undo."""

    def __init__(self, v_id: int, position: np.ndarray) -> None:
        self._v_id = v_id
        self._position = np.asarray(position, dtype=np.float32).reshape(3).copy()

    def do(self, scene) -> None:  # noqa: ANN001
        scene.restore_vertex(self._v_id, self._position)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_vertex(self._v_id)


class _AddEdgeAtId(Command):
    """Internal: restores an edge at a specific ID."""

    def __init__(self, e_id: int, v1_id: int, v2_id: int) -> None:
        self._e_id = e_id
        self._v1, self._v2 = v1_id, v2_id

    def do(self, scene) -> None:  # noqa: ANN001
        scene.restore_edge(self._e_id, self._v1, self._v2)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_edge(self._e_id)


class _AddFaceAtId(Command):
    """Internal: restores a face at a specific ID."""

    def __init__(self, f_id: int, loop: Sequence[int]) -> None:
        self._f_id = f_id
        self._loop = tuple(loop)

    def do(self, scene) -> None:  # noqa: ANN001
        scene.restore_face(self._f_id, self._loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        scene.remove_face(self._f_id)


class ClearSceneCommand(Command):
    """do() captures every live entity and clears; undo() replays Add*AtId children."""

    name = "Clear Scene"

    def __init__(self) -> None:
        self._captured: list[Command] | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        captured: list[Command] = []
        for v in scene.vertices_iter():
            captured.append(_AddVertexAtId(v.id, v.position))
        for e in scene.edges_iter():
            captured.append(_AddEdgeAtId(e.id, e.v1_id, e.v2_id))
        for f in scene.faces_iter():
            captured.append(_AddFaceAtId(f.id, f.loop_vertex_ids))
        self._captured = captured
        scene.clear()

    def undo(self, scene) -> None:  # noqa: ANN001
        assert self._captured is not None, "ClearSceneCommand.undo before do"
        for cmd in self._captured:
            cmd.do(scene)
```

- [ ] **Step 4: Run; expect pass**

```bash
pluton-py-tests
```

Expected: 129 passed (128 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_scene_commands.py
git commit -m "feat(commands): ClearSceneCommand + _AddVertexAtId helpers

ClearSceneCommand.do() captures every live vertex, edge, and face as
_AddVertexAtId / _AddEdgeAtId / _AddFaceAtId child commands, then
calls scene.clear(). undo() replays the captured children, restoring
the scene with original IDs intact. Test verifies the 3-vertex /
3-edge / 1-face round-trip preserves all IDs."
```

---

## Task 18: RectangleTool refactor — use composite + command stack

**Files:**
- Modify: `python/pluton/tools/tool.py` (extend ToolContext)
- Modify: `python/pluton/tools/rectangle_tool.py`
- Modify: `tests/test_rectangle_tool.py`

- [ ] **Step 1: Extend `ToolContext` to carry the command stack**

Edit `python/pluton/tools/tool.py`. Find the `ToolContext` dataclass and replace with:

```python
@dataclass(frozen=True, slots=True)
class ToolContext:
    """Handed to Tool.activate(); gives the tool a handle to the live Scene and CommandStack."""

    scene: object
    command_stack: object = None  # M3a-introduced — pluton.commands.CommandStack
```

(Keep `command_stack` defaulted to `None` so legacy test code that constructs `ToolContext(scene=Scene())` still works.)

- [ ] **Step 2: Update `RectangleTool` to build a composite + push at gesture completion**

Edit `python/pluton/tools/rectangle_tool.py`. Two places change: imports + `on_mouse_press` commit path + `on_key_press` ESC rollback.

Replace the imports block at the top with:

```python
from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
```

In `__init__`, add the following fields after the existing ones:
```python
        self._composite: CompositeCommand | None = None
        self._command_stack = None  # populated in activate()
```

Replace `activate` with:
```python
    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._reset_gesture()
```

Replace the `# DRAGGING — commit or drop` block in `on_mouse_press` with:

```python
        # DRAGGING — commit or drop
        assert self._first_corner is not None
        second = snap.world_position
        if np.array_equal(second, self._first_corner):
            self._reset_gesture()
            return

        x0, y0 = float(self._first_corner[0]), float(self._first_corner[1])
        x1, y1 = float(second[0]), float(second[1])

        composite = CompositeCommand(name="Draw Rectangle")
        s = self._scene  # type: ignore[assignment]
        v_cmds = [
            AddVertexCommand(np.array([x0, y0, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([x1, y0, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([x1, y1, 0.0], dtype=np.float32)),
            AddVertexCommand(np.array([x0, y1, 0.0], dtype=np.float32)),
        ]
        for c in v_cmds:
            c.do(s)
            composite.children.append(c)
        vids = [c._vertex_id for c in v_cmds]  # type: ignore[attr-defined]
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            e_cmd = AddEdgeCommand(vids[a], vids[b])
            e_cmd.do(s)
            composite.children.append(e_cmd)
        f_cmd = AddFaceCommand(tuple(vids))
        f_cmd.do(s)
        composite.children.append(f_cmd)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()
```

Replace `on_key_press` with:

```python
    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() != Qt.Key.Key_Escape:
            return
        if self._composite is not None:
            # We haven't built a composite mid-drag in Rectangle (it commits
            # atomically on second click), so there is nothing to roll back.
            self._composite = None
        self._reset_gesture()
```

Update `_reset_gesture` to also clear `_composite`:

```python
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._first_corner = None
        self._preview_corner = None
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
        self._composite = None
```

- [ ] **Step 3: Update existing rectangle tool tests to use a command stack**

In `tests/test_rectangle_tool.py`, locate the existing tests that call `tool.activate(ToolContext(scene=scene))`. Update each to pass a `command_stack`:

```python
# Add a helper at the top of the file
def _ctx(scene):
    from pluton.commands import CommandStack
    from pluton.tools import ToolContext
    return ToolContext(scene=scene, command_stack=CommandStack())
```

Update each test that used `tool.activate(ToolContext(scene=scene))` to `tool.activate(_ctx(scene))` — but only the tests where the command-stack behavior is being verified.

Actually, the simpler refactor: keep the existing tests using `ToolContext(scene=scene)` (no command stack). The tool tolerates a None stack (the `if self._command_stack is not None:` guard). Add NEW tests covering the command-stack interaction:

Append to `tests/test_rectangle_tool.py`:

```python
def test_rectangle_tool_pushes_composite_to_command_stack():
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.rectangle_tool import RectangleTool

    scene = Scene()
    stack = CommandStack()
    tool = RectangleTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))
    tool.on_mouse_press(None, _snap_at((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _snap_at((3.0, 2.0, 0.0)))  # type: ignore[arg-type]

    assert stack.can_undo
    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.faces_iter())) == 0

    stack.redo(scene)
    assert len(list(scene.vertices_iter())) == 4
    assert len(list(scene.faces_iter())) == 1
```

- [ ] **Step 4: Run tests**

```bash
pluton-py-tests tests/test_rectangle_tool.py -v
pluton-py-tests
```

Expected: all rectangle tool tests pass, full suite 130 passed.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tool.py python/pluton/tools/rectangle_tool.py tests/test_rectangle_tool.py
git commit -m "feat(tools): RectangleTool pushes CompositeCommand at gesture completion

RectangleTool builds a CompositeCommand named 'Draw Rectangle' with 4
AddVertexCommand + 4 AddEdgeCommand + 1 AddFaceCommand children, executes
each immediately (so the scene reflects current state), then calls
command_stack.push_executed() to register the composite for undo.

ToolContext gains a command_stack field (defaulted to None for backward
compat with tests that don't care about undo)."
```

---

## Task 19: LineTool refactor — composite + ESC rollback

**Files:**
- Modify: `python/pluton/tools/line_tool.py`
- Modify: `tests/test_line_tool.py`

- [ ] **Step 1: Update `LineTool` for composite + push_executed + ESC rollback**

Edit `python/pluton/tools/line_tool.py`. Replace the imports block:

```python
from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
)
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
```

In `__init__`, after the existing fields, add:
```python
        self._composite: CompositeCommand | None = None
        self._command_stack = None
```

Replace `activate`:
```python
    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene  # type: ignore[assignment]
        self._command_stack = ctx.command_stack
        self._reset_gesture()
```

Replace `on_mouse_press` ENTIRELY with the new composite-aware version:

```python
    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return

        s = self._scene  # type: ignore[assignment]
        if self._state == _State.IDLE:
            # First click — seed the gesture.
            self._composite = CompositeCommand(name="Draw Line")
            if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
                vid = snap.vertex_id  # reuse existing vertex; no command added
            else:
                cmd = AddVertexCommand(snap.world_position)
                cmd.do(s)
                self._composite.children.append(cmd)
                vid = cmd._vertex_id  # type: ignore[attr-defined]
            self._gesture_vertex_ids = [vid]
            self._state = _State.DRAWING
            self._preview_tip = snap.world_position.copy()
            return

        # DRAWING — branch 1, 2, or 3
        assert self._composite is not None
        tip_vid = self._gesture_vertex_ids[-1]
        first_vid = self._gesture_vertex_ids[0]

        if (
            snap.kind == SnapKind.ENDPOINT
            and snap.vertex_id == first_vid
            and len(self._gesture_vertex_ids) >= 3
        ):
            # Branch 1 — loop closure
            e_cmd = AddEdgeCommand(tip_vid, first_vid)
            e_cmd.do(s)
            self._composite.children.append(e_cmd)
            f_cmd = AddFaceCommand(tuple(self._gesture_vertex_ids))
            f_cmd.do(s)
            self._composite.children.append(f_cmd)
            if self._command_stack is not None:
                self._command_stack.push_executed(self._composite)
            self._reset_gesture()
            return

        if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
            if snap.vertex_id == tip_vid:
                return
            e_cmd = AddEdgeCommand(tip_vid, snap.vertex_id)
            e_cmd.do(s)
            self._composite.children.append(e_cmd)
            self._gesture_vertex_ids.append(snap.vertex_id)
            return

        # Branch 3 — new vertex
        v_cmd = AddVertexCommand(snap.world_position)
        v_cmd.do(s)
        new_vid = v_cmd._vertex_id  # type: ignore[attr-defined]
        if new_vid == tip_vid:
            # degenerate: drop the just-added vertex by undoing
            v_cmd.undo(s)
            return
        self._composite.children.append(v_cmd)
        e_cmd = AddEdgeCommand(tip_vid, new_vid)
        e_cmd.do(s)
        self._composite.children.append(e_cmd)
        self._gesture_vertex_ids.append(new_vid)
```

Replace `on_key_press`:

```python
    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() != Qt.Key.Key_Escape:
            return
        # ESC mid-gesture: roll back the in-progress composite.
        if self._composite is not None:
            s = self._scene  # type: ignore[assignment]
            self._composite.undo(s)
            self._composite = None
        self._reset_gesture()
```

Update `_reset_gesture`:

```python
    def _reset_gesture(self) -> None:
        self._state = _State.IDLE
        self._gesture_vertex_ids = []
        self._preview_tip = None
        self._rubber_band_color = _NEUTRAL_COLOR
        self._snap_marker_pos = None
        self._snap_marker_kind = 0
        self._composite = None
```

- [ ] **Step 2: Add new tests** — append to `tests/test_line_tool.py`

```python
def test_line_tool_pushes_composite_at_loop_close():
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    stack = CommandStack()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))

    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    first_vid = next(iter(scene.vertices_iter())).id
    tool.on_mouse_press(None, _grid_snap((2.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((2.0, 2.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _endpoint_snap((0.0, 0.0, 0.0), vertex_id=first_vid))  # type: ignore[arg-type]

    assert stack.can_undo
    assert len(list(scene.faces_iter())) == 1

    stack.undo(scene)
    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.edges_iter())) == 0
    assert len(list(scene.faces_iter())) == 0


def test_line_tool_esc_mid_gesture_rolls_back_committed_geometry():
    """The M2 §5.6 #3 elimination test — ESC fully reverses in-progress mutations."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools import ToolContext
    from pluton.tools.line_tool import LineTool

    scene = Scene()
    stack = CommandStack()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack))

    # 3 clicks — verts + edges committed to scene as the gesture progresses.
    tool.on_mouse_press(None, _grid_snap((0.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((1.0, 0.0, 0.0)))  # type: ignore[arg-type]
    tool.on_mouse_press(None, _grid_snap((1.0, 1.0, 0.0)))  # type: ignore[arg-type]
    assert len(list(scene.vertices_iter())) == 3
    assert len(list(scene.edges_iter())) == 2

    # ESC mid-gesture rolls back everything committed during this gesture.
    ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    tool.on_key_press(ev)

    assert len(list(scene.vertices_iter())) == 0
    assert len(list(scene.edges_iter())) == 0
    # Nothing pushed to undo stack (the composite was discarded, not committed).
    assert not stack.can_undo
```

- [ ] **Step 3: Run tests**

```bash
pluton-py-tests tests/test_line_tool.py -v
pluton-py-tests
```

Expected: all line tool tests pass, full suite 132 passed.

- [ ] **Step 4: Commit**

```bash
git add python/pluton/tools/line_tool.py tests/test_line_tool.py
git commit -m "feat(tools): LineTool composite + ESC mid-gesture rollback

LineTool now builds a CompositeCommand during the gesture, executing
each child as it goes (so the snap engine sees in-progress state on
subsequent clicks). At loop-close, push_executed() registers the
composite for undo.

ESC mid-gesture calls composite.undo() walking children in reverse,
which removes every vertex and edge committed during the gesture —
including the branch-2 'extend to existing vertex' case where the
M2 implementation could leak. This eliminates the M2 §5.6 #3 carve-out.

New test test_line_tool_esc_mid_gesture_rolls_back_committed_geometry
locks in the elimination."
```

---

## Task 20: MainWindow integration

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Modify: `tests/test_viewport.py`

- [ ] **Step 1: Rewrite `MainWindow`**

Replace the entire `python/pluton/ui/main_window.py`:

```python
"""The main application window — hosts the viewport, status bar, ToolManager, and CommandStack."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.commands import CommandStack
from pluton.commands.scene_commands import ClearSceneCommand
from pluton.scene import Scene
from pluton.tools import LineTool, RectangleTool, ToolContext, ToolManager
from pluton.ui.status_bar import StatusBar
from pluton.viewport.viewport_widget import ViewportWidget


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Scene + tool manager + command stack
        self._scene = Scene()
        self._command_stack = CommandStack()
        self._tool_manager = ToolManager()
        self._tool_manager.set_context(
            ToolContext(scene=self._scene, command_stack=self._command_stack)
        )
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())

        # Viewport + status bar
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._status_bar = StatusBar()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewport, stretch=1)
        layout.addWidget(self._status_bar, stretch=0)
        self.setCentralWidget(container)

        self._viewport.set_status_bar(self._status_bar)

        # Keyboard shortcuts
        QShortcut(QKeySequence("L"), self, activated=lambda: self._activate("L"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self._activate("R"))
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_clear_scene)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._on_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._on_redo)

    # --- Slots -----------------------------------------------------------

    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._viewport.update()

    def _on_escape(self) -> None:
        active = self._tool_manager.active
        if active is None:
            return
        if active.has_active_gesture:
            from PySide6.QtGui import QKeyEvent

            ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            active.on_key_press(ev)
        else:
            self._tool_manager.deactivate_current()
            self._status_bar.set_tool("")
            self._status_bar.set_snap("")
        self._viewport.update()

    def _on_clear_scene(self) -> None:
        self._command_stack.execute(ClearSceneCommand(), self._scene)
        self._viewport.update()

    def _on_undo(self) -> None:
        if self._command_stack.undo(self._scene):
            self._viewport.update()

    def _on_redo(self) -> None:
        if self._command_stack.redo(self._scene):
            self._viewport.update()
```

- [ ] **Step 2: Append qtbot integration tests** to `tests/test_viewport.py`

```python
def test_ctrl_z_undoes_completed_rectangle(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # Activate Rectangle, simulate two clicks via the tool directly.
    qtbot.keyClick(window, Qt.Key.Key_R)
    from pluton.viewport.snap_engine import SnapKind, SnapResult
    active = window._tool_manager.active

    def snap_at(x, y):
        return SnapResult(
            kind=SnapKind.GRID,
            world_position=np.array([x, y, 0.0], dtype=np.float32),
            axis=None,
            vertex_id=None,
            label="Grid",
        )

    active.on_mouse_press(None, snap_at(0.0, 0.0))  # type: ignore[arg-type]
    active.on_mouse_press(None, snap_at(3.0, 2.0))  # type: ignore[arg-type]
    assert len(list(window._scene.faces_iter())) == 1

    qtbot.keyClick(window, Qt.Key.Key_Z, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.faces_iter())) == 0

    qtbot.keyClick(window, Qt.Key.Key_Y, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.faces_iter())) == 1


def test_ctrl_n_is_undoable(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    qtbot.wait(50)

    # Seed the scene with two vertices.
    window._scene.add_vertex(np.array([1.0, 2.0, 0.0], dtype=np.float32))
    window._scene.add_vertex(np.array([3.0, 4.0, 0.0], dtype=np.float32))
    assert len(list(window._scene.vertices_iter())) == 2

    qtbot.keyClick(window, Qt.Key.Key_N, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 0

    qtbot.keyClick(window, Qt.Key.Key_Z, modifier=Qt.KeyboardModifier.ControlModifier)
    assert len(list(window._scene.vertices_iter())) == 2
```

- [ ] **Step 3: Run; expect pass**

```bash
pluton-py-tests
```

Expected: 134 passed (132 + 2 new).

- [ ] **Step 4: Commit**

```bash
git add python/pluton/ui/main_window.py tests/test_viewport.py
git commit -m "feat(ui): wire CommandStack into MainWindow; Ctrl+Z / Ctrl+Y / undoable Ctrl+N

MainWindow owns a CommandStack alongside the Scene. The ToolContext
passed to tools carries both. Ctrl+Z and Ctrl+Y (plus Ctrl+Shift+Z)
bind to the stack's undo/redo. Ctrl+N becomes a ClearSceneCommand
that's pushed via execute() — restoring the scene with original IDs
when undone."
```

---

## Task 21: Manual visual verification

**Files:**
- (None — this is a manual smoke test by the human at the keyboard.)

- [ ] **Step 1: Rebuild and launch**

```bash
pluton-build
.venv/Scripts/python.exe -m pluton
```

(If your venv is missing scikit-build-core or mapbox-earcut, install them first: `.venv/Scripts/pip.exe install scikit-build-core nanobind mapbox-earcut`.)

- [ ] **Step 2: Baseline (M2 behavior)**

- Window opens; grid + colored axes visible; no cube; empty status bar.
- Camera: MMB orbit, Shift+MMB pan, wheel zoom-toward-cursor (pure zoom).
- Rectangle (`R`), Line (`L`) draw as before. Snap markers (triangle for midpoint, square for endpoint/grid) appear.

- [ ] **Step 3: Undo / Redo of completed gestures**

- Press **R**, draw a rectangle. Press **Ctrl+Z** → rectangle disappears. Press **Ctrl+Y** → reappears with the same edges/face.
- Press **L**, draw a closed quadrilateral. Press **Ctrl+Z** → polyline + face disappear together (one composite).
- Repeat with multiple gestures. Each Ctrl+Z undoes one whole gesture.

- [ ] **Step 4: M2 §5.6 #3 elimination — ESC mid-gesture rollback**

- Press **L**. Click out 2 or 3 vertices of a polyline (don't close it).
- Press **Esc**. The vertices and edges of the in-progress polyline disappear from the scene.
- This is the M3a improvement over M2.

- [ ] **Step 5: Undoable Ctrl+N**

- Draw several shapes.
- Press **Ctrl+N** → scene clears back to grid + axes.
- Press **Ctrl+Z** → entire scene returns. Hover near a restored vertex with the Line tool active — endpoint snap should fire correctly (proving IDs are restored, not freshly allocated).

- [ ] **Step 6: Redo stack clearing**

- Draw a rectangle.
- Press Ctrl+Z (undo).
- Draw a new rectangle (different position).
- Press **Ctrl+Y** → redo does nothing (the original rectangle does NOT reappear). The redo stack was cleared by the new execute.

- [ ] **Step 7: Camera and tool actions are NOT undoable**

- Orbit / pan / zoom the camera. Press Ctrl+Z → does nothing (no scene mutations to undo, and camera is out of scope).
- Press R then L (switching tools). Ctrl+Z → does nothing.

- [ ] **Step 8: No commit for this task**

Report any issues; otherwise proceed to Task 22.

---

## Task 22: Push, verify CI, tag, open carry-over issues

**Files:**
- Modify: `pyproject.toml`
- Modify: `CMakeLists.txt`
- Modify: `cpp/src/version.cpp`

- [ ] **Step 1: Push the implementation to origin**

```bash
git push origin main
```

- [ ] **Step 2: Watch CI**

```bash
gh run watch --exit-status
```

Expected: both Windows and Linux runners green. If CI fails, fix locally, push, and rerun. Confirm via `gh run view <run_id>` per the M1 lesson.

- [ ] **Step 3: Bump version**

`pyproject.toml`: change `version = "0.0.3"` to `version = "0.0.4"`.

`CMakeLists.txt` (top-level): change `VERSION 0.0.3` to `VERSION 0.0.4`.

`cpp/src/version.cpp`: change `return "0.0.3";` to `return "0.0.4";`.

- [ ] **Step 4: Rebuild and re-run tests**

```bash
pluton-build
pluton-cpp-tests
pluton-py-tests
```

Expected: all green; version test asserts `pluton.version() == "0.0.4"`.

- [ ] **Step 5: Commit the bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp
git commit -m "chore: bump version to 0.0.4 for M3a release"
```

- [ ] **Step 6: Tag**

```bash
git tag -a v0.0.4-m3a -m "M3a — Topology & Undo

C++ HalfEdgeMesh as the geometric source of truth; Python Scene becomes
a thin wrapper. Scene.remove_* / restore_* with stable IDs across remove
and undo. Command-pattern undo/redo: per-gesture + reverse-action +
scene-only. Tools (Rectangle, Line) build CompositeCommands and push
at gesture completion.

ESC mid-gesture now does a clean rollback — eliminates M2 §5.6 #3.

No new C++ deps (CGAL waits for M3c). No new tools.

First of three M3 sub-milestones. M3b (push/pull basic) and M3c
(CGAL booleans + inferencing) follow."
```

- [ ] **Step 7: Push commit + tag**

```bash
git push origin main
git push origin v0.0.4-m3a
```

- [ ] **Step 8: Confirm the tag on GitHub**

```bash
gh api repos/parrow-horrizon-studio/pluton/git/refs/tags/v0.0.4-m3a --jq '{ref, object: .object | {sha, type}}'
```

Expected: `object.type == "tag"` (annotated, not lightweight).

- [ ] **Step 9: Open carry-over GitHub issues**

For each entry in spec §5.4 (Known limitations):

```bash
gh issue create --title "M3a tracker: edge-ID instability after the implicit-edge refactor" \
  --label enhancement \
  --body "Per M3a spec \`docs/2026-05-22-M3a-topology-and-undo-design.md\` §5.4 #1.

After M3a, Scene.add_edge returns edge IDs derived from half-edge pair
indices (edge_id = halfedges_.size() / 2 - 1 at the time of allocation)
rather than M2's dict-counter. The numeric values may differ from what
M2 returned for the same operation sequence.

Acceptance:
- Spot-check any tooling, scripts, or documentation that pins specific
  numeric edge IDs.
- Update or remove such pins as needed.
- Tests should treat IDs as opaque tokens unless verifying ID stability
  across undo/redo cycles (which is a real contract).

Milestone: M3a follow-up sweep (or whenever a brittle ID-pin shows up)."

gh issue create --title "M10 perf: HalfEdgeMesh slab compaction (tombstone reclamation)" \
  --label enhancement \
  --body "Per M3a spec §5.4 #2.

The HalfEdgeMesh slab vectors grow linearly with cumulative mutations
in a session. Tombstoned slots are never reused or compacted. Fine for
M3a/M3b/M3c modest workloads; M4+ long editing sessions may benefit.

Acceptance:
- Add a HalfEdgeMesh::compact() method that re-numbers live entities to
  the front of the slab vectors and updates all back-references.
- Trigger heuristically (e.g. when tombstone density exceeds 50%) or
  expose as an explicit API.
- Stable IDs become invalidated by compaction; document the contract
  and decide whether app-level command history persists across compaction.

Milestone: M10 (perf migration)."

gh issue create --title "M4+: RemoveFaceCommand captured-loop memory" \
  --label enhancement \
  --body "Per M3a spec §5.4 #3.

RemoveFaceCommand.do() captures the removed face's boundary loop so
undo() can call scene.restore_face(...). For M3a's 4-vertex rects this
is trivial. For M4+ faces with hundreds of boundary vertices, command
payloads can grow.

Acceptance:
- Profile typical M4 editing workflows and measure command stack memory.
- If meaningful, consider alternative encodings (delta against the
  previous face state; shared references to immutable loop tuples).

Milestone: M4+ (perf, deferred)."

gh issue create --title "M12+: C++ direct access to HalfEdgeMesh from the native render engine" \
  --label documentation \
  --body "Per M3a spec §5.4 #4.

When Phase 5 introduces the in-house render engine (M12+), the render
pass may want to read HalfEdgeMesh directly rather than through the
Python Scene wrapper. The current API surface is Python-only by design;
revisit the boundary then.

Architectural note. No code action required in M3a-M11.

Milestone: M12 (real-time PBR viewport)."
```

- [ ] **Step 10: Verify M3a is fully shipped**

```bash
gh release view v0.0.4-m3a 2>/dev/null || gh api repos/parrow-horrizon-studio/pluton/git/refs/tags/v0.0.4-m3a
```

---

## Self-Review Checklist (for the plan author)

After the plan is written, verify:

- [ ] **Spec §1 (Purpose)** — covered by plan goal + each task's commit message.
- [ ] **Spec §2 (End State)** — covered by §"Definition of Done for M3a".
- [ ] **Spec §3.1 (Decisions table)** — each row implemented in a specific task. Half-edge in C++ (Task 1-9), Python wrapper (Task 11), per-gesture composite (Task 18-19), reject-if-referenced (Task 6 + Task 12), stable IDs via tombstoning (Task 5-7), unbounded history (Task 14).
- [ ] **Spec §3.2 (File map)** — exactly mirrored in the plan's File Map section.
- [ ] **Spec §3.3 (Dependencies)** — no new C++ deps; mapbox-earcut stays. Confirmed.
- [ ] **Spec §3.4 (Data flow — gesture with undo+redo)** — Task 18-19 + Task 20 integration test.
- [ ] **Spec §3.5 (ESC mid-gesture rollback)** — Task 19's `test_line_tool_esc_mid_gesture_rolls_back_committed_geometry`.
- [ ] **Spec §3.6 (C++ ↔ Python boundary)** — Task 10 (bindings) + Task 11 (Scene wrapper).
- [ ] **Spec §4.1 (HalfEdgeMesh)** — Tasks 1-9.
- [ ] **Spec §4.2 (Scene)** — Task 11 + Task 12.
- [ ] **Spec §4.3 (Command framework)** — Tasks 13-17.
- [ ] **Spec §4.4 (Tool integration)** — Tasks 18-19.
- [ ] **Spec §4.5 (MainWindow integration)** — Task 20.
- [ ] **Spec §5 (Edge cases)** — covered in test cases across Tasks 6, 7, 11, 12, 19.
- [ ] **Spec §5.4 (Known limitations)** — opened as carry-over issues in Task 22 step 9.
- [ ] **Spec §6 (Out of scope)** — no plan task needed.
- [ ] **Spec §7 (M3a → M3b/M3c contract)** — exposed by Task 10's binding (halfedge adjacency).
- [ ] **Spec §8 (Testing)** — every row mapped to one or more tasks.
- [ ] **Spec §9 (Implementation order)** — this plan's task numbering matches.

If any row is unticked, the missing coverage was added inline before commit.

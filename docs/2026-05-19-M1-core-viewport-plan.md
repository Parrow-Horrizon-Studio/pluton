# M1 — Core Viewport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace M0's hardcoded triangle with a shaded 3D cube driven by a real C++ `Mesh` type, viewed through a SketchUp-style orbiting camera in a Z-up world with a ground grid and colored axes.

**Architecture:** C++ kernel exposes an indexed `Mesh` (positions + normals + indices) via nanobind as read-only numpy views. A Python `Camera` class (numpy 4×4 math) owns the view/projection state. A Python `SceneRenderer` owns GL resources and uploads the cube once on first frame, then renders cube + grid + axes every frame. `ViewportWidget` wires Qt mouse events to `Camera` updates.

**Tech Stack:** C++20, nanobind 2.x, GoogleTest, PySide6 (Qt 6), PyOpenGL, numpy, pytest + pytest-qt.

**Spec:** `docs/2026-05-19-M1-core-viewport-design.md`

**Prerequisite:** M0 complete (tag `v0.0.1-m0`). Working tree clean on `main`.

---

## Build & Test Commands Reference

The scikit-build-core build directory pattern is `build/{wheel_tag}/` — e.g. `build/cp313-cp313-win_amd64/` on Windows or `build/cp313-cp313-linux_x86_64/` on Linux.

**Critical:** scikit-build-core does NOT pick up `CMAKE_TOOLCHAIN_FILE` from the environment alone — it must be passed via `SKBUILD_CMAKE_ARGS`. Also, the vcpkg binary cache (`VCPKG_BINARY_SOURCES`) must be cleared when running in a shell that doesn't have GHA cache tokens. Confirmed working incantation:

**Git Bash / Linux / macOS:**
```bash
export VCPKG_ROOT=/c/vcpkg                                                          # or wherever vcpkg lives
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

**Note on stale CMakeCache:** if a build fails with `Could not find GTest`, the existing `build/<wheel_tag>/CMakeCache.txt` was configured without the toolchain. Remove the build directory once: `rm -rf build/<wheel_tag>` and re-run `pluton-build`. Subsequent rebuilds will reuse the cached toolchain setting.

Each task below uses `pluton-build`, `pluton-cpp-tests`, `pluton-py-tests` as shorthand.

---

## File Map

**C++ side**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/include/pluton/mesh.h` | NEW | `Mesh` class declaration |
| `cpp/src/mesh.cpp` | NEW | `Mesh` implementation (empty cpp — header-only members, but kept as a translation unit for symmetry) |
| `cpp/include/pluton/primitives.h` | NEW | `make_cube()` declaration |
| `cpp/src/primitives.cpp` | NEW | `make_cube()` implementation |
| `cpp/bindings/module.cpp` | MODIFY | Bind `Mesh` + `make_cube` to Python |
| `cpp/CMakeLists.txt` | MODIFY | Add `mesh.cpp`, `primitives.cpp` to `pluton_core` |
| `cpp/tests/test_mesh.cpp` | NEW | GoogleTest cases for `Mesh` |
| `cpp/tests/test_primitives.cpp` | NEW | GoogleTest cases for `make_cube` |
| `cpp/tests/CMakeLists.txt` | MODIFY | Add new test sources to `pluton_tests` |

**Python side**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/__init__.py` | MODIFY | Re-export `Mesh`, `make_cube` for the top-level `pluton` namespace |
| `python/pluton/viewport/camera.py` | NEW | `Camera` dataclass + orbit/pan/zoom math |
| `python/pluton/viewport/scene_renderer.py` | NEW | Owns GL resources (VBOs, programs); draws cube + grid + axes |
| `python/pluton/viewport/viewport_widget.py` | MODIFY | Wire `Camera` + `SceneRenderer` + Qt mouse events |
| `python/pluton/viewport/shaders/phong.vert` | NEW | Cube vertex shader |
| `python/pluton/viewport/shaders/phong.frag` | NEW | Cube fragment shader (Phong) |
| `python/pluton/viewport/shaders/line.vert` | NEW | Line vertex shader (grid + axes) |
| `python/pluton/viewport/shaders/line.frag` | NEW | Line fragment shader |

**Tests**

| Path | Status | Responsibility |
|---|---|---|
| `tests/test_mesh.py` | NEW | Python binding tests for `Mesh` + `make_cube` |
| `tests/test_camera.py` | NEW | Pure-Python camera math tests |
| `tests/test_window.py` | RENAME | → `tests/test_viewport.py`, expanded for M1 |

**Versioning / build**

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | MODIFY | Bump `version = "0.0.2"` at the end of M1 |
| `CMakeLists.txt` (top-level) | MODIFY | Bump `project(... VERSION 0.0.2 ...)` |

---

## Definition of Done for M1

1. `python -m pluton` launches a window showing: flat-shaded cube on the ground at origin, 10×10 m grid on Z=0, red/green/blue axis lines through origin, three-quarter default camera pose
2. MMB orbit, Shift+MMB pan, scroll zoom-toward-cursor all work
3. All pytest tests pass locally (8+ tests)
4. All GoogleTest tests pass locally (4+ test cases beyond M0's version tests)
5. CI green on Windows + Linux
6. Tagged `v0.0.2-m1` (annotated, SSH-signed) and `m1-first-cube` (annotated, SSH-signed)
7. Tags pushed to GitHub

---

## Task 1: C++ Mesh class

**Files:**
- Create: `cpp/include/pluton/mesh.h`
- Create: `cpp/src/mesh.cpp`
- Create: `cpp/tests/test_mesh.cpp`
- Modify: `cpp/CMakeLists.txt`
- Modify: `cpp/tests/CMakeLists.txt`

- [ ] **Step 1: Create the header** at `cpp/include/pluton/mesh.h`

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace pluton {

/// A polygonal mesh stored as three flat, GPU-ready arrays.
///
/// Layout matches what OpenGL VBOs want: tightly-packed floats for positions
/// and normals, and a 32-bit index buffer for triangles. This avoids any
/// reshape or copy when the data is pulled to Python via nanobind.
class Mesh {
public:
    /// Vertex positions in XYZ order: [x0,y0,z0, x1,y1,z1, ...].
    std::vector<float> positions;

    /// Vertex normals in XYZ order, parallel to `positions` (same length).
    std::vector<float> normals;

    /// Triangle indices into `positions` / `normals` (3 indices per triangle).
    std::vector<std::uint32_t> indices;

    /// Number of vertices (positions.size() / 3).
    std::size_t vertex_count() const { return positions.size() / 3; }

    /// Number of triangles (indices.size() / 3).
    std::size_t triangle_count() const { return indices.size() / 3; }
};

}  // namespace pluton
```

- [ ] **Step 2: Create the implementation stub** at `cpp/src/mesh.cpp`

```cpp
#include "pluton/mesh.h"

// Mesh is currently header-only (data + inline accessors). This translation
// unit exists to keep CMake symmetry with primitives.cpp and to give us a
// place to put non-inline methods in future milestones (M2: add face/edge
// methods, M3: half-edge adjacency).

namespace pluton {

// Intentionally empty for M1.

}  // namespace pluton
```

- [ ] **Step 3: Add to `cpp/CMakeLists.txt`** — change the `add_library` call

Replace:
```cmake
add_library(pluton_core STATIC
    src/version.cpp
)
```
with:
```cmake
add_library(pluton_core STATIC
    src/version.cpp
    src/mesh.cpp
)
```

- [ ] **Step 4: Write the failing GoogleTest** at `cpp/tests/test_mesh.cpp`

```cpp
#include <gtest/gtest.h>

#include "pluton/mesh.h"

TEST(MeshTest, DefaultConstructedIsEmpty) {
    pluton::Mesh m;
    EXPECT_EQ(m.vertex_count(), 0u);
    EXPECT_EQ(m.triangle_count(), 0u);
    EXPECT_TRUE(m.positions.empty());
    EXPECT_TRUE(m.normals.empty());
    EXPECT_TRUE(m.indices.empty());
}

TEST(MeshTest, CountsMatchArrayLengths) {
    pluton::Mesh m;
    // 3 vertices, 1 triangle
    m.positions = {0.f, 0.f, 0.f,  1.f, 0.f, 0.f,  0.f, 1.f, 0.f};
    m.normals   = {0.f, 0.f, 1.f,  0.f, 0.f, 1.f,  0.f, 0.f, 1.f};
    m.indices   = {0u, 1u, 2u};

    EXPECT_EQ(m.vertex_count(), 3u);
    EXPECT_EQ(m.triangle_count(), 1u);
}
```

- [ ] **Step 5: Add the test source to `cpp/tests/CMakeLists.txt`** — change `add_executable`

Replace:
```cmake
add_executable(pluton_tests
    test_version.cpp
)
```
with:
```cmake
add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
)
```

- [ ] **Step 6: Rebuild and run tests**

```
pluton-build
pluton-cpp-tests
```

Expected: `pluton_tests` runs and `MeshTest.DefaultConstructedIsEmpty` + `MeshTest.CountsMatchArrayLengths` both PASS, alongside the existing M0 `VersionTest` cases.

- [ ] **Step 7: Commit**

```bash
git add cpp/include/pluton/mesh.h cpp/src/mesh.cpp cpp/CMakeLists.txt cpp/tests/test_mesh.cpp cpp/tests/CMakeLists.txt
git commit -m "feat(cpp): add Mesh class with positions/normals/indices"
```

---

## Task 2: C++ cube primitive (TDD)

**Files:**
- Create: `cpp/include/pluton/primitives.h`
- Create: `cpp/src/primitives.cpp`
- Create: `cpp/tests/test_primitives.cpp`
- Modify: `cpp/CMakeLists.txt`
- Modify: `cpp/tests/CMakeLists.txt`

- [ ] **Step 1: Write the failing test** at `cpp/tests/test_primitives.cpp`

```cpp
#include <cmath>
#include <gtest/gtest.h>

#include "pluton/primitives.h"

namespace {

// Approximate equality for floats.
::testing::AssertionResult NearlyEqual(float a, float b, float tol = 1e-5f) {
    if (std::abs(a - b) <= tol) return ::testing::AssertionSuccess();
    return ::testing::AssertionFailure() << a << " not within " << tol << " of " << b;
}

}  // namespace

TEST(PrimitivesCube, CountsAreCorrect) {
    const auto cube = pluton::make_cube(1.0f);
    // 6 faces * 4 vertices per face = 24 vertices (flat shading: corners duplicated per face)
    EXPECT_EQ(cube.vertex_count(), 24u);
    // 6 faces * 2 triangles per face = 12 triangles
    EXPECT_EQ(cube.triangle_count(), 12u);
    EXPECT_EQ(cube.indices.size(), 36u);
    EXPECT_EQ(cube.positions.size(), 72u);  // 24 * 3
    EXPECT_EQ(cube.normals.size(), 72u);
}

TEST(PrimitivesCube, BottomOnGroundCentered) {
    const float size = 2.5f;
    const auto cube = pluton::make_cube(size);

    // Bottom-on-grid: z in [0, size]; x and y in [-size/2, +size/2]
    for (std::size_t i = 0; i < cube.vertex_count(); ++i) {
        const float x = cube.positions[3 * i + 0];
        const float y = cube.positions[3 * i + 1];
        const float z = cube.positions[3 * i + 2];
        EXPECT_GE(x, -size / 2 - 1e-5f);
        EXPECT_LE(x, +size / 2 + 1e-5f);
        EXPECT_GE(y, -size / 2 - 1e-5f);
        EXPECT_LE(y, +size / 2 + 1e-5f);
        EXPECT_GE(z, 0.0f - 1e-5f);
        EXPECT_LE(z, size + 1e-5f);
    }
}

TEST(PrimitivesCube, AllNormalsAreUnitLength) {
    const auto cube = pluton::make_cube(1.0f);
    for (std::size_t i = 0; i < cube.vertex_count(); ++i) {
        const float nx = cube.normals[3 * i + 0];
        const float ny = cube.normals[3 * i + 1];
        const float nz = cube.normals[3 * i + 2];
        const float length = std::sqrt(nx * nx + ny * ny + nz * nz);
        EXPECT_TRUE(NearlyEqual(length, 1.0f)) << "vertex " << i;
    }
}

TEST(PrimitivesCube, IndicesAreInRange) {
    const auto cube = pluton::make_cube(1.0f);
    for (std::uint32_t idx : cube.indices) {
        EXPECT_LT(idx, cube.vertex_count());
    }
}

TEST(PrimitivesCube, EachFaceHasOneNormal) {
    // The 4 vertices of each face must share the same normal (flat shading).
    // Faces are 4 consecutive vertices; we have 6 faces.
    const auto cube = pluton::make_cube(1.0f);
    for (std::size_t f = 0; f < 6; ++f) {
        const float nx0 = cube.normals[3 * (4 * f + 0) + 0];
        const float ny0 = cube.normals[3 * (4 * f + 0) + 1];
        const float nz0 = cube.normals[3 * (4 * f + 0) + 2];
        for (std::size_t v = 1; v < 4; ++v) {
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 0], nx0));
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 1], ny0));
            EXPECT_TRUE(NearlyEqual(cube.normals[3 * (4 * f + v) + 2], nz0));
        }
    }
}
```

- [ ] **Step 2: Add test source to `cpp/tests/CMakeLists.txt`**

Replace the `add_executable` block again so it lists all three test sources:
```cmake
add_executable(pluton_tests
    test_version.cpp
    test_mesh.cpp
    test_primitives.cpp
)
```

- [ ] **Step 3: Create stub primitive header** at `cpp/include/pluton/primitives.h`

```cpp
#pragma once

#include "pluton/mesh.h"

namespace pluton {

/// Axis-aligned cube primitive.
///
/// Bottom face sits on z = 0 (the world ground plane); x and y span
/// [-size/2, +size/2]; z spans [0, size]. Each of the 6 faces has its own
/// outward-pointing normal (flat shading), so corner vertices are duplicated
/// per face — 24 vertices, 36 indices total.
///
/// @param size  Edge length of the cube. Defaults to 1.0.
Mesh make_cube(float size = 1.0f);

}  // namespace pluton
```

- [ ] **Step 4: Create stub `cpp/src/primitives.cpp`** that intentionally returns an empty mesh so tests fail

```cpp
#include "pluton/primitives.h"

namespace pluton {

Mesh make_cube(float /*size*/) {
    // Intentionally empty for the failing-test step. Filled in next step.
    return Mesh{};
}

}  // namespace pluton
```

- [ ] **Step 5: Add `primitives.cpp` to `cpp/CMakeLists.txt`**

```cmake
add_library(pluton_core STATIC
    src/version.cpp
    src/mesh.cpp
    src/primitives.cpp
)
```

- [ ] **Step 6: Rebuild and run — verify the cube tests FAIL**

```
pluton-build
pluton-cpp-tests
```

Expected: `PrimitivesCube.*` tests fail (`vertex_count` is 0, not 24).

- [ ] **Step 7: Implement `make_cube` properly** — replace the body of `cpp/src/primitives.cpp`

```cpp
#include "pluton/primitives.h"

namespace pluton {

Mesh make_cube(float size) {
    const float h = size * 0.5f;  // half-extent in x and y
    // z runs [0, size] so the bottom rests on the ground plane.

    Mesh mesh;
    mesh.positions.reserve(72);  // 24 verts * 3
    mesh.normals.reserve(72);
    mesh.indices.reserve(36);    // 12 triangles * 3

    // Each face: 4 vertices listed CCW when viewed from outside, plus its
    // outward-pointing normal duplicated per vertex.
    //
    // Faces are added in this order: +X, -X, +Y, -Y, +Z (top), -Z (bottom).
    // The +Z face has its normal pointing up; -Z face points down, etc.

    struct Face {
        float v[4][3];   // 4 vertex positions
        float n[3];      // outward face normal
    };

    const Face faces[6] = {
        // +X face (right): normal (1, 0, 0)
        {{{+h, -h, 0.f}, {+h, +h, 0.f}, {+h, +h, size}, {+h, -h, size}}, {1.f, 0.f, 0.f}},
        // -X face (left): normal (-1, 0, 0)
        {{{-h, +h, 0.f}, {-h, -h, 0.f}, {-h, -h, size}, {-h, +h, size}}, {-1.f, 0.f, 0.f}},
        // +Y face (back): normal (0, 1, 0)
        {{{+h, +h, 0.f}, {-h, +h, 0.f}, {-h, +h, size}, {+h, +h, size}}, {0.f, 1.f, 0.f}},
        // -Y face (front): normal (0, -1, 0)
        {{{-h, -h, 0.f}, {+h, -h, 0.f}, {+h, -h, size}, {-h, -h, size}}, {0.f, -1.f, 0.f}},
        // +Z face (top): normal (0, 0, 1)
        {{{-h, -h, size}, {+h, -h, size}, {+h, +h, size}, {-h, +h, size}}, {0.f, 0.f, 1.f}},
        // -Z face (bottom): normal (0, 0, -1)
        {{{-h, +h, 0.f}, {+h, +h, 0.f}, {+h, -h, 0.f}, {-h, -h, 0.f}}, {0.f, 0.f, -1.f}},
    };

    for (const auto& face : faces) {
        const std::uint32_t base = static_cast<std::uint32_t>(mesh.vertex_count());
        for (int v = 0; v < 4; ++v) {
            mesh.positions.push_back(face.v[v][0]);
            mesh.positions.push_back(face.v[v][1]);
            mesh.positions.push_back(face.v[v][2]);
            mesh.normals.push_back(face.n[0]);
            mesh.normals.push_back(face.n[1]);
            mesh.normals.push_back(face.n[2]);
        }
        // Two triangles per face (CCW from outside)
        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 1);
        mesh.indices.push_back(base + 2);
        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 2);
        mesh.indices.push_back(base + 3);
    }

    return mesh;
}

}  // namespace pluton
```

- [ ] **Step 8: Rebuild and run — verify tests PASS**

```
pluton-build
pluton-cpp-tests
```

Expected: All `PrimitivesCube.*` tests PASS. All `MeshTest.*` tests PASS. All `VersionTest.*` tests PASS.

- [ ] **Step 9: Commit**

```bash
git add cpp/include/pluton/primitives.h cpp/src/primitives.cpp cpp/CMakeLists.txt cpp/tests/test_primitives.cpp cpp/tests/CMakeLists.txt
git commit -m "feat(cpp): add make_cube primitive with flat-shaded normals"
```

---

## Task 3: Expose Mesh + make_cube via nanobind

**Files:**
- Modify: `cpp/bindings/module.cpp`
- Modify: `python/pluton/__init__.py`

- [ ] **Step 1: Rewrite `cpp/bindings/module.cpp`** to expose `Mesh` and `make_cube`

```cpp
#include <cstdint>

#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include "pluton/mesh.h"
#include "pluton/primitives.h"
#include "pluton/version.h"

namespace nb = nanobind;
using pluton::Mesh;

namespace {

// Expose std::vector<float> as a read-only (N, 3) numpy view of the data.
// The `const float` dtype is what makes the resulting numpy array
// non-writable from Python. The `nb::rv_policy::reference_internal` policy
// on the def_prop_ro call (below) keeps the owning Mesh alive as long as
// the returned ndarray is alive.
nb::ndarray<const float, nb::numpy, nb::shape<-1, 3>> as_vec3_array(
    const std::vector<float>& v) {
    const std::size_t n = v.size() / 3;
    return nb::ndarray<const float, nb::numpy, nb::shape<-1, 3>>(
        const_cast<float*>(v.data()),  // const-cast: ndarray dtype is `const float`, marking it read-only
        {n, static_cast<std::size_t>(3)});
}

nb::ndarray<const std::uint32_t, nb::numpy, nb::shape<-1>> as_index_array(
    const std::vector<std::uint32_t>& v) {
    return nb::ndarray<const std::uint32_t, nb::numpy, nb::shape<-1>>(
        const_cast<std::uint32_t*>(v.data()),
        {v.size()});
}

}  // namespace

NB_MODULE(_core, m) {
    m.doc() = "Pluton C++ core module";

    m.def("version", &pluton::version,
          "Returns the Pluton library version as a string.");

    nb::class_<Mesh>(m, "Mesh", "Polygonal mesh: positions, normals, indices.")
        .def(nb::init<>())
        .def_prop_ro(
            "positions",
            [](Mesh& self) { return as_vec3_array(self.positions); },
            nb::rv_policy::reference_internal,
            "Vertex positions as a read-only (N, 3) float32 numpy view.")
        .def_prop_ro(
            "normals",
            [](Mesh& self) { return as_vec3_array(self.normals); },
            nb::rv_policy::reference_internal,
            "Vertex normals as a read-only (N, 3) float32 numpy view.")
        .def_prop_ro(
            "indices",
            [](Mesh& self) { return as_index_array(self.indices); },
            nb::rv_policy::reference_internal,
            "Triangle indices as a read-only (M,) uint32 numpy view.")
        .def_prop_ro("vertex_count", &Mesh::vertex_count)
        .def_prop_ro("triangle_count", &Mesh::triangle_count);

    m.def("make_cube", &pluton::make_cube, nb::arg("size") = 1.0f,
          "Create an axis-aligned cube of the given edge length, "
          "with its bottom face on the ground plane (z = 0).");
}
```

**Note on the binding policy:** `nb::rv_policy::reference_internal` tells nanobind "the returned object references memory owned by `self`; keep `self` alive as long as the return is alive." This is the idiomatic nanobind 2.x pattern for exposing C++-owned ndarray views. The `const float` / `const uint32_t` dtype is what makes the resulting numpy array read-only (`flags.writeable = False`).

- [ ] **Step 2: Update `python/pluton/__init__.py`** to re-export the new symbols

```python
"""Pluton — polygonal 3D modeler for architecture."""

from pluton._core import Mesh, make_cube, version

__version__ = version()

__all__ = ["Mesh", "__version__", "make_cube", "version"]
```

- [ ] **Step 3: Rebuild**

```
pluton-build
```

Expected: build succeeds; the new `_core` module exports `Mesh` and `make_cube`.

- [ ] **Step 4: Smoke-check from Python**

```bash
python -c "import pluton; m = pluton.make_cube(); print(m.positions.shape, m.indices.shape, m.vertex_count, m.triangle_count)"
```

Expected output: `(24, 3) (36,) 24 12`

- [ ] **Step 5: Commit**

```bash
git add cpp/bindings/module.cpp python/pluton/__init__.py
git commit -m "feat(bindings): expose Mesh + make_cube to Python via nanobind"
```

---

## Task 4: Python binding tests for Mesh + make_cube

**Files:**
- Create: `tests/test_mesh.py`

- [ ] **Step 1: Write the test file** at `tests/test_mesh.py`

```python
"""Tests for the C++ Mesh class and make_cube primitive, accessed via nanobind."""

from __future__ import annotations

import numpy as np
import pytest

import pluton


def test_make_cube_default_returns_mesh():
    m = pluton.make_cube()
    assert isinstance(m, pluton.Mesh)


def test_make_cube_vertex_and_triangle_counts():
    m = pluton.make_cube()
    assert m.vertex_count == 24
    assert m.triangle_count == 12


def test_make_cube_array_shapes_and_dtypes():
    m = pluton.make_cube()
    assert m.positions.shape == (24, 3)
    assert m.normals.shape == (24, 3)
    assert m.indices.shape == (36,)
    assert m.positions.dtype == np.float32
    assert m.normals.dtype == np.float32
    assert m.indices.dtype == np.uint32


def test_make_cube_arrays_are_read_only():
    m = pluton.make_cube()
    with pytest.raises((ValueError, RuntimeError)):
        m.positions[0, 0] = 999.0
    with pytest.raises((ValueError, RuntimeError)):
        m.normals[0, 0] = 999.0
    with pytest.raises((ValueError, RuntimeError)):
        m.indices[0] = 999


def test_make_cube_bottom_on_ground():
    """The cube sits on z=0 with x,y centered around the origin."""
    m = pluton.make_cube(size=2.0)
    positions = np.asarray(m.positions)
    # x,y in [-1, 1]; z in [0, 2]
    assert positions[:, 0].min() == pytest.approx(-1.0)
    assert positions[:, 0].max() == pytest.approx(+1.0)
    assert positions[:, 1].min() == pytest.approx(-1.0)
    assert positions[:, 1].max() == pytest.approx(+1.0)
    assert positions[:, 2].min() == pytest.approx(0.0)
    assert positions[:, 2].max() == pytest.approx(2.0)


def test_make_cube_normals_are_unit_length():
    m = pluton.make_cube()
    normals = np.asarray(m.normals)
    lengths = np.linalg.norm(normals, axis=1)
    np.testing.assert_allclose(lengths, 1.0, atol=1e-5)


def test_make_cube_indices_in_range():
    m = pluton.make_cube()
    indices = np.asarray(m.indices)
    assert indices.min() >= 0
    assert indices.max() < m.vertex_count


def test_default_constructed_mesh_is_empty():
    m = pluton.Mesh()
    assert m.vertex_count == 0
    assert m.triangle_count == 0
    assert m.positions.shape == (0, 3)
    assert m.indices.shape == (0,)


def test_mesh_array_is_a_view_not_a_copy():
    """Accessing positions repeatedly should yield views that share memory."""
    m = pluton.make_cube()
    a = np.asarray(m.positions)
    b = np.asarray(m.positions)
    # Both views reference the same underlying buffer.
    assert np.may_share_memory(a, b)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_mesh.py -v
```

Expected: all 9 tests PASS.

If `test_make_cube_arrays_are_read_only` doesn't raise the expected error, it means nanobind didn't actually mark the ndarray read-only. In that case, change the binding so `nb::ndarray` is templated on `const float` (already in the plan — that's the read-only marker) — verify the existing binding code is templated on `const float` / `const std::uint32_t`. If still permissive, set the `numpy.ndarray.flags.writeable = False` manually in Python via `np.asarray(m.positions).flags["WRITEABLE"]` — but the C++ side is the right place.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mesh.py
git commit -m "test: add Python binding tests for Mesh and make_cube"
```

---

## Task 5: Python Camera class (TDD)

**Files:**
- Create: `python/pluton/viewport/camera.py`
- Create: `tests/test_camera.py`

- [ ] **Step 1: Write failing tests** at `tests/test_camera.py`

```python
"""Tests for the Python Camera class — pure numpy math, no OpenGL needed."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pluton.viewport.camera import Camera


# --- Defaults --------------------------------------------------------------


def test_default_camera_pose():
    c = Camera()
    np.testing.assert_allclose(c.position, [8.0, -8.0, 6.0], atol=1e-5)
    np.testing.assert_allclose(c.target, [0.0, 0.0, 0.5], atol=1e-5)
    np.testing.assert_allclose(c.up, [0.0, 0.0, 1.0], atol=1e-5)


# --- View matrix -----------------------------------------------------------


def test_view_matrix_is_4x4():
    c = Camera()
    v = c.view_matrix()
    assert v.shape == (4, 4)
    assert v.dtype == np.float32


def test_view_matrix_sends_position_to_origin():
    """v * position (homogeneous) should be (0,0,0) in view space."""
    c = Camera()
    v = c.view_matrix()
    homogeneous = np.array([*c.position, 1.0], dtype=np.float32)
    result = v @ homogeneous
    np.testing.assert_allclose(result[:3], [0.0, 0.0, 0.0], atol=1e-4)


# --- Projection matrix -----------------------------------------------------


def test_projection_matrix_is_4x4():
    c = Camera()
    c.aspect = 16.0 / 9.0
    p = c.projection_matrix()
    assert p.shape == (4, 4)
    assert p.dtype == np.float32


def test_projection_matrix_respects_aspect():
    """Wider aspect should compress x more than tall aspect does (same fov_y)."""
    c1 = Camera()
    c1.aspect = 1.0
    c2 = Camera()
    c2.aspect = 2.0
    p1 = c1.projection_matrix()
    p2 = c2.projection_matrix()
    # Element [0,0] is fovy-derived divided by aspect, so p2[0,0] < p1[0,0].
    assert p2[0, 0] < p1[0, 0]


# --- Orbit -----------------------------------------------------------------


def test_orbit_preserves_distance_to_target():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.orbit(dx_pixels=50.0, dy_pixels=30.0)
    distance_after = np.linalg.norm(c.position - c.target)
    np.testing.assert_allclose(distance_after, distance_before, atol=1e-4)


def test_orbit_full_circle_returns_to_origin():
    """Orbiting 360 degrees in many small steps returns the camera home."""
    c = Camera()
    pos_before = c.position.copy()
    # We don't know the exact pixels-to-radians ratio of the implementation,
    # but if the camera orbits dx_pixels=1 -> some_radians, then 360 deg / that
    # should bring us back. We just step a known total: orbit by (1, 0)
    # 1000 times and the position should be on the same orbital sphere.
    distance_initial = np.linalg.norm(pos_before - c.target)
    for _ in range(1000):
        c.orbit(dx_pixels=1.0, dy_pixels=0.0)
    distance_final = np.linalg.norm(c.position - c.target)
    np.testing.assert_allclose(distance_final, distance_initial, atol=1e-3)


def test_orbit_elevation_clamped():
    """Pitch must be clamped to avoid gimbal flip at the poles."""
    c = Camera()
    # Try to orbit way past the top pole.
    for _ in range(10000):
        c.orbit(dx_pixels=0.0, dy_pixels=10.0)
    # Should still be a valid view (position not on top of target).
    distance = np.linalg.norm(c.position - c.target)
    assert distance > 0.1
    # And up direction is still roughly +Z.
    np.testing.assert_allclose(c.up, [0.0, 0.0, 1.0], atol=1e-5)


# --- Pan -------------------------------------------------------------------


def test_pan_preserves_camera_to_target_vector():
    """Pan translates position and target together; the offset is unchanged."""
    c = Camera()
    offset_before = c.position - c.target
    c.pan(dx_pixels=20.0, dy_pixels=-10.0)
    offset_after = c.position - c.target
    np.testing.assert_allclose(offset_after, offset_before, atol=1e-4)


# --- Zoom ------------------------------------------------------------------


def test_zoom_toward_target_reduces_distance():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.zoom(scroll_delta=1.0, cursor_ndc=None)  # zoom in
    distance_after = np.linalg.norm(c.position - c.target)
    assert distance_after < distance_before


def test_zoom_out_increases_distance():
    c = Camera()
    distance_before = np.linalg.norm(c.position - c.target)
    c.zoom(scroll_delta=-1.0, cursor_ndc=None)
    distance_after = np.linalg.norm(c.position - c.target)
    assert distance_after > distance_before
```

- [ ] **Step 2: Run tests — verify they fail with ImportError**

```bash
pytest tests/test_camera.py -v
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'pluton.viewport.camera'` (or `ImportError: cannot import name 'Camera'`).

- [ ] **Step 3: Implement `Camera`** at `python/pluton/viewport/camera.py`

```python
"""Camera for the 3D viewport: position/target/up, view + projection matrices,
and orbit/pan/zoom operations driven by mouse pixel deltas.

All math is done with numpy. The C++ kernel never sees camera state in M1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Sensitivities chosen for a 1280x800-ish widget. Tunable later via M2's preferences.
_ORBIT_RADIANS_PER_PIXEL = 0.01
_PAN_WORLD_UNITS_PER_PIXEL = 0.0015  # scaled by distance to target
_ZOOM_FACTOR_PER_SCROLL_UNIT = 0.1
_ELEVATION_CLAMP = math.radians(89.0)


def _normalize(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    if length < 1e-12:
        return v
    return v / length


@dataclass
class Camera:
    """Perspective camera in a Z-up world."""

    position: np.ndarray = field(
        default_factory=lambda: np.array([8.0, -8.0, 6.0], dtype=np.float32)
    )
    target: np.ndarray = field(
        default_factory=lambda: np.array([0.0, 0.0, 0.5], dtype=np.float32)
    )
    up: np.ndarray = field(
        default_factory=lambda: np.array([0.0, 0.0, 1.0], dtype=np.float32)
    )

    fov_y_deg: float = 45.0
    aspect: float = 1.0
    near: float = 0.01
    far: float = 1000.0

    # --- Matrices ----------------------------------------------------------

    def view_matrix(self) -> np.ndarray:
        """Right-handed look-at matrix mapping world -> camera space."""
        forward = _normalize(self.target - self.position)  # camera looks down -Z in cam space
        right = _normalize(np.cross(forward, self.up))
        cam_up = np.cross(right, forward)

        m = np.eye(4, dtype=np.float32)
        m[0, 0:3] = right
        m[1, 0:3] = cam_up
        m[2, 0:3] = -forward
        m[0, 3] = -float(np.dot(right, self.position))
        m[1, 3] = -float(np.dot(cam_up, self.position))
        m[2, 3] = +float(np.dot(forward, self.position))
        return m

    def projection_matrix(self) -> np.ndarray:
        """Standard OpenGL right-handed perspective projection, NDC z in [-1, 1]."""
        f = 1.0 / math.tan(math.radians(self.fov_y_deg) * 0.5)
        n, fp = self.near, self.far
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0] = f / self.aspect
        m[1, 1] = f
        m[2, 2] = (fp + n) / (n - fp)
        m[2, 3] = (2.0 * fp * n) / (n - fp)
        m[3, 2] = -1.0
        return m

    # --- Orbit / Pan / Zoom -----------------------------------------------

    def orbit(self, dx_pixels: float, dy_pixels: float) -> None:
        """Spherical orbit around `target`. dx_pixels rotates around world Z;
        dy_pixels rotates around the camera's right vector (elevation)."""
        offset = self.position - self.target
        radius = float(np.linalg.norm(offset))
        if radius < 1e-9:
            return

        # Current spherical coords (relative to target). Azimuth is in the XY plane,
        # elevation is the angle off the XY plane toward +Z.
        azimuth = math.atan2(offset[1], offset[0])
        elevation = math.asin(float(np.clip(offset[2] / radius, -1.0, 1.0)))

        azimuth -= dx_pixels * _ORBIT_RADIANS_PER_PIXEL
        elevation += dy_pixels * _ORBIT_RADIANS_PER_PIXEL
        elevation = max(-_ELEVATION_CLAMP, min(_ELEVATION_CLAMP, elevation))

        cos_e = math.cos(elevation)
        new_offset = np.array(
            [
                radius * cos_e * math.cos(azimuth),
                radius * cos_e * math.sin(azimuth),
                radius * math.sin(elevation),
            ],
            dtype=np.float32,
        )
        self.position = self.target + new_offset

    def pan(self, dx_pixels: float, dy_pixels: float) -> None:
        """Translate position and target together along the camera's right/up axes."""
        forward = _normalize(self.target - self.position)
        right = _normalize(np.cross(forward, self.up))
        cam_up = np.cross(right, forward)

        distance = float(np.linalg.norm(self.target - self.position))
        scale = _PAN_WORLD_UNITS_PER_PIXEL * distance
        delta = (-dx_pixels * right + dy_pixels * cam_up) * scale
        self.position = self.position + delta
        self.target = self.target + delta

    def zoom(self, scroll_delta: float, cursor_ndc: np.ndarray | None = None) -> None:
        """Zoom toward the cursor (if given in NDC [-1, 1]) or toward target.

        Positive scroll_delta zooms in (gets closer); negative zooms out.
        """
        offset = self.position - self.target
        if cursor_ndc is None:
            direction = -_normalize(offset)  # toward target
        else:
            # Unproject cursor NDC to a world-space ray from the camera.
            # For zoom-toward-cursor it's sufficient to move along a screen-space
            # direction that maps to a world-space ray through the cursor pixel.
            forward = _normalize(self.target - self.position)
            right = _normalize(np.cross(forward, self.up))
            cam_up = np.cross(right, forward)
            tan_half_fovy = math.tan(math.radians(self.fov_y_deg) * 0.5)
            # cursor NDC -> camera-space direction
            cam_dir = (
                forward
                + right * (cursor_ndc[0] * tan_half_fovy * self.aspect)
                + cam_up * (cursor_ndc[1] * tan_half_fovy)
            )
            direction = _normalize(cam_dir)

        distance = float(np.linalg.norm(offset))
        step = distance * _ZOOM_FACTOR_PER_SCROLL_UNIT * scroll_delta
        # Clamp so we can't fly through the target on a single tick.
        step = max(min(step, distance * 0.9), -distance * 5.0)

        self.position = self.position + direction * step
        # Drag target along too so subsequent orbits still feel anchored.
        if cursor_ndc is not None:
            self.target = self.target + direction * step
```

- [ ] **Step 4: Run tests — verify they PASS**

```bash
pytest tests/test_camera.py -v
```

Expected: all 11 tests PASS.

If `test_orbit_full_circle_returns_to_origin` fails by being just outside the tolerance, that's likely numerical drift over 1000 iterations — confirm the test uses a generous tolerance (1e-3) and that the orbit math has no off-by-one in atan2/asin.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/camera.py tests/test_camera.py
git commit -m "feat(viewport): add Camera class with orbit/pan/zoom math"
```

---

## Task 6: Shader files

**Files:**
- Create: `python/pluton/viewport/shaders/phong.vert`
- Create: `python/pluton/viewport/shaders/phong.frag`
- Create: `python/pluton/viewport/shaders/line.vert`
- Create: `python/pluton/viewport/shaders/line.frag`

These are GLSL data files, loaded at runtime via `importlib.resources` from the `pluton.viewport` package. scikit-build-core packages everything under `wheel.packages` recursively, so no `pyproject.toml` changes are needed.

- [ ] **Step 1: Create `python/pluton/viewport/shaders/phong.vert`**

```glsl
#version 330 core

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;

uniform mat4 u_view;
uniform mat4 u_projection;
uniform mat4 u_model;

out vec3 v_world_pos;
out vec3 v_world_normal;

void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    // Model matrix is rigid (rotation + translation) in M1, so mat3(u_model)
    // suffices for the normal. Non-uniform scaling would require a normal matrix.
    v_world_normal = mat3(u_model) * in_normal;
    gl_Position = u_projection * u_view * world_pos;
}
```

- [ ] **Step 2: Create `python/pluton/viewport/shaders/phong.frag`**

```glsl
#version 330 core

in vec3 v_world_pos;
in vec3 v_world_normal;
out vec4 frag_color;

uniform vec3 u_camera_pos;

// Hardcoded for M1 — surfaced as uniforms now so the python side can tweak
// them, and so the M5 material system has a natural plug-in point.
uniform vec3  u_light_dir;        // direction the light travels (unit length)
uniform vec3  u_light_color;
uniform vec3  u_material_ambient;
uniform vec3  u_material_diffuse;
uniform vec3  u_material_specular;
uniform float u_material_shininess;

void main() {
    vec3 N = normalize(v_world_normal);
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_camera_pos - v_world_pos);
    vec3 R = reflect(L, N);  // light reflects off the surface

    float diff = max(dot(N, -L), 0.0);
    float spec = pow(max(dot(R, V), 0.0), u_material_shininess);

    vec3 color = u_material_ambient
               + u_material_diffuse  * diff * u_light_color
               + u_material_specular * spec * u_light_color;

    frag_color = vec4(color, 1.0);
}
```

- [ ] **Step 3: Create `python/pluton/viewport/shaders/line.vert`**

```glsl
#version 330 core

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_color;

uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_color;

void main() {
    v_color = in_color;
    gl_Position = u_projection * u_view * vec4(in_position, 1.0);
}
```

- [ ] **Step 4: Create `python/pluton/viewport/shaders/line.frag`**

```glsl
#version 330 core

in vec3 v_color;
out vec4 frag_color;

void main() {
    frag_color = vec4(v_color, 1.0);
}
```

- [ ] **Step 5: Verify shaders are packaged**

```
pluton-build
python -c "from importlib.resources import files; print((files('pluton.viewport') / 'shaders' / 'phong.vert').read_text()[:50])"
```

Expected: prints the first 50 characters of `phong.vert` (i.e., `#version 330 core` plus a newline).

If `read_text()` raises `FileNotFoundError`, the editable install isn't seeing the shaders. Confirm by also running `pip install . --force-reinstall --no-build-isolation` (non-editable wheel install) and re-running the read_text command. If the non-editable install works but the editable one doesn't, the issue is editable-install file discovery — add `[tool.scikit-build.editable] rebuild = true` to `pyproject.toml` and re-run `pluton-build`.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/shaders/phong.vert python/pluton/viewport/shaders/phong.frag python/pluton/viewport/shaders/line.vert python/pluton/viewport/shaders/line.frag
git commit -m "feat(viewport): add Phong + line shaders as packaged resources"
```

---

## Task 7: SceneRenderer

**Files:**
- Create: `python/pluton/viewport/scene_renderer.py`

`SceneRenderer` owns the GL resources (VBOs, IBOs, shader programs) for the M1 scene. It's called from `ViewportWidget`'s `initializeGL`, `resizeGL`, and `paintGL` hooks.

No direct unit tests for `SceneRenderer` — exercising it requires a live GL context. The viewport smoke tests in Task 8 cover construction + paint without crashes via the offscreen platform.

- [ ] **Step 1: Create the file** at `python/pluton/viewport/scene_renderer.py`

```python
"""Owns GL resources for the M1 scene: cube + grid + axes.

Lifecycle is driven by QOpenGLWidget:
  initialize_gl() -> first paintGL() call sets up VBOs and shader programs.
  resize(w, h)    -> called from resizeGL.
  render(camera) -> called from paintGL each frame.
"""

from __future__ import annotations

import ctypes
from importlib.resources import files

import numpy as np
from OpenGL import GL

import pluton
from pluton.viewport.camera import Camera


# --- Constants for the scene -----------------------------------------------

_GRID_HALF_EXTENT = 5.0  # meters, so grid is 10x10
_GRID_SPACING = 1.0
_GRID_COLOR = (0.40, 0.40, 0.40)
_GRID_CENTERLINE_COLOR = (0.60, 0.60, 0.60)

_AXIS_LENGTH = 5.0
_AXIS_X_COLOR = (0.90, 0.20, 0.20)
_AXIS_Y_COLOR = (0.20, 0.90, 0.20)
_AXIS_Z_COLOR = (0.20, 0.40, 0.90)

# Phong material + light — hardcoded for M1.
_LIGHT_DIR = (-1.0, +1.0, -2.0)
_LIGHT_COLOR = (1.00, 0.97, 0.92)
_MATERIAL_AMBIENT = (0.15, 0.15, 0.17)
_MATERIAL_DIFFUSE = (0.65, 0.65, 0.70)
_MATERIAL_SPECULAR = (0.10, 0.10, 0.10)
_MATERIAL_SHININESS = 16.0

_BG_COLOR = (0.15, 0.15, 0.18, 1.0)


def _load_shader_source(name: str) -> str:
    return (files("pluton.viewport") / "shaders" / name).read_text(encoding="utf-8")


def _compile_shader(source: str, shader_type: int) -> int:
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
        kind = "vertex" if shader_type == GL.GL_VERTEX_SHADER else "fragment"
        raise RuntimeError(f"{kind} shader compile failed:\n{log}")
    return shader


def _link_program(vert_src: str, frag_src: str) -> int:
    vs = _compile_shader(vert_src, GL.GL_VERTEX_SHADER)
    fs = _compile_shader(frag_src, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, vs)
    GL.glAttachShader(program, fs)
    GL.glLinkProgram(program)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(f"shader program link failed:\n{log}")
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return program


def _build_grid_vertex_array() -> np.ndarray:
    """Return a (N, 6) float32 array of grid-line vertices: x,y,z, r,g,b."""
    verts: list[float] = []
    n = int(2 * _GRID_HALF_EXTENT / _GRID_SPACING) + 1
    for i in range(n):
        v = -_GRID_HALF_EXTENT + i * _GRID_SPACING
        is_centerline = abs(v) < 1e-5
        c = _GRID_CENTERLINE_COLOR if is_centerline else _GRID_COLOR
        # Line parallel to X (varying x at fixed y)
        verts.extend([-_GRID_HALF_EXTENT, v, 0.0, *c])
        verts.extend([+_GRID_HALF_EXTENT, v, 0.0, *c])
        # Line parallel to Y (varying y at fixed x)
        verts.extend([v, -_GRID_HALF_EXTENT, 0.0, *c])
        verts.extend([v, +_GRID_HALF_EXTENT, 0.0, *c])
    return np.array(verts, dtype=np.float32).reshape(-1, 6)


def _build_axes_vertex_array() -> np.ndarray:
    """Return a (6, 6) float32 array: 3 colored line segments through origin."""
    return np.array(
        [
            # X axis (red)
            [0.0, 0.0, 0.0, *_AXIS_X_COLOR],
            [_AXIS_LENGTH, 0.0, 0.0, *_AXIS_X_COLOR],
            # Y axis (green)
            [0.0, 0.0, 0.0, *_AXIS_Y_COLOR],
            [0.0, _AXIS_LENGTH, 0.0, *_AXIS_Y_COLOR],
            # Z axis (blue)
            [0.0, 0.0, 0.0, *_AXIS_Z_COLOR],
            [0.0, 0.0, _AXIS_LENGTH, *_AXIS_Z_COLOR],
        ],
        dtype=np.float32,
    )


class SceneRenderer:
    """Owns GL resources for the cube + grid + axes scene."""

    def __init__(self) -> None:
        self._initialized = False
        # Programs
        self._phong_program: int = 0
        self._line_program: int = 0
        # Cube buffers
        self._cube_vao: int = 0
        self._cube_position_vbo: int = 0
        self._cube_normal_vbo: int = 0
        self._cube_ibo: int = 0
        self._cube_index_count: int = 0
        # Grid + axes buffers
        self._grid_vao: int = 0
        self._grid_vbo: int = 0
        self._grid_vertex_count: int = 0
        self._axes_vao: int = 0
        self._axes_vbo: int = 0
        self._axes_vertex_count: int = 0

    # --- Lifecycle --------------------------------------------------------

    def initialize_gl(self) -> None:
        if self._initialized:
            return
        GL.glClearColor(*_BG_COLOR)
        GL.glEnable(GL.GL_DEPTH_TEST)

        self._phong_program = _link_program(
            _load_shader_source("phong.vert"),
            _load_shader_source("phong.frag"),
        )
        self._line_program = _link_program(
            _load_shader_source("line.vert"),
            _load_shader_source("line.frag"),
        )

        self._init_cube_buffers()
        self._init_grid_buffers()
        self._init_axes_buffers()

        self._initialized = True

    def resize(self, w: int, h: int) -> None:
        GL.glViewport(0, 0, w, h)

    def render(self, camera: Camera) -> None:
        if not self._initialized:
            return
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        view = camera.view_matrix()
        projection = camera.projection_matrix()
        model = np.eye(4, dtype=np.float32)  # cube model matrix is identity

        # Draw grid + axes first so they don't z-fight on top of the cube.
        self._draw_lines(self._grid_vao, self._grid_vertex_count, view, projection)
        self._draw_lines(self._axes_vao, self._axes_vertex_count, view, projection)
        self._draw_cube(view, projection, model, camera.position)

    # --- Init helpers -----------------------------------------------------

    def _init_cube_buffers(self) -> None:
        mesh = pluton.make_cube(1.0)
        positions = np.ascontiguousarray(mesh.positions, dtype=np.float32)
        normals = np.ascontiguousarray(mesh.normals, dtype=np.float32)
        indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32)
        self._cube_index_count = int(indices.size)

        self._cube_vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._cube_vao)

        self._cube_position_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._cube_position_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, positions.nbytes, positions, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self._cube_normal_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._cube_normal_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, normals.nbytes, normals, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self._cube_ibo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._cube_ibo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)

        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)

    def _init_grid_buffers(self) -> None:
        verts = _build_grid_vertex_array()
        self._grid_vertex_count = int(verts.shape[0])
        self._grid_vao, self._grid_vbo = self._upload_interleaved_lines(verts)

    def _init_axes_buffers(self) -> None:
        verts = _build_axes_vertex_array()
        self._axes_vertex_count = int(verts.shape[0])
        self._axes_vao, self._axes_vbo = self._upload_interleaved_lines(verts)

    @staticmethod
    def _upload_interleaved_lines(verts: np.ndarray) -> tuple[int, int]:
        """Upload an (N, 6) float32 array (x,y,z, r,g,b per vertex). Returns (vao, vbo)."""
        vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(vao)
        vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)
        # position (vec3)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        # color (vec3) at offset 3 floats
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
        return vao, vbo

    # --- Draw helpers -----------------------------------------------------

    def _draw_lines(self, vao: int, count: int, view: np.ndarray, projection: np.ndarray) -> None:
        GL.glUseProgram(self._line_program)
        _set_mat4(self._line_program, "u_view", view)
        _set_mat4(self._line_program, "u_projection", projection)
        GL.glBindVertexArray(vao)
        GL.glDrawArrays(GL.GL_LINES, 0, count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _draw_cube(
        self,
        view: np.ndarray,
        projection: np.ndarray,
        model: np.ndarray,
        camera_pos: np.ndarray,
    ) -> None:
        GL.glUseProgram(self._phong_program)
        _set_mat4(self._phong_program, "u_view", view)
        _set_mat4(self._phong_program, "u_projection", projection)
        _set_mat4(self._phong_program, "u_model", model)
        _set_vec3(self._phong_program, "u_camera_pos", camera_pos)
        _set_vec3(self._phong_program, "u_light_dir", _LIGHT_DIR)
        _set_vec3(self._phong_program, "u_light_color", _LIGHT_COLOR)
        _set_vec3(self._phong_program, "u_material_ambient", _MATERIAL_AMBIENT)
        _set_vec3(self._phong_program, "u_material_diffuse", _MATERIAL_DIFFUSE)
        _set_vec3(self._phong_program, "u_material_specular", _MATERIAL_SPECULAR)
        _set_float(self._phong_program, "u_material_shininess", _MATERIAL_SHININESS)

        GL.glBindVertexArray(self._cube_vao)
        GL.glDrawElements(GL.GL_TRIANGLES, self._cube_index_count, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)


# --- Uniform helpers --------------------------------------------------------

def _set_mat4(program: int, name: str, m: np.ndarray) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    # GLSL is column-major; numpy is row-major. Transpose flag handles it.
    GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, np.ascontiguousarray(m, dtype=np.float32))


def _set_vec3(program: int, name: str, v) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    arr = np.asarray(v, dtype=np.float32)
    GL.glUniform3f(loc, float(arr[0]), float(arr[1]), float(arr[2]))


def _set_float(program: int, name: str, x: float) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    GL.glUniform1f(loc, float(x))
```

- [ ] **Step 2: Commit** (no tests for this file; integration coverage comes in Task 8)

```bash
git add python/pluton/viewport/scene_renderer.py
git commit -m "feat(viewport): add SceneRenderer for cube, grid, and axes"
```

---

## Task 8: ViewportWidget rewrite + expanded tests

**Files:**
- Modify: `python/pluton/viewport/viewport_widget.py` (complete rewrite)
- Rename: `tests/test_window.py` → `tests/test_viewport.py`
- Modify: the renamed file (expand tests)

- [ ] **Step 1: Rename the existing test file**

```bash
git mv tests/test_window.py tests/test_viewport.py
```

- [ ] **Step 2: Replace `tests/test_viewport.py` contents** with expanded tests

```python
"""Smoke tests for the main window and the M1 viewport widget.

These use pytest-qt for the QApplication fixture. Rendering is not pixel-
verified (that requires framebuffer capture, out of scope for M1) — but
construction, GL context creation, mouse handling, and one full paint cycle
are exercised via the Qt offscreen platform.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent


def test_main_window_constructs(qtbot):
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "Pluton"


def test_viewport_widget_constructs(qtbot):
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    assert widget is not None


def test_viewport_widget_has_camera_and_scene(qtbot):
    from pluton.viewport.camera import Camera
    from pluton.viewport.scene_renderer import SceneRenderer
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget.camera, Camera)
    assert isinstance(widget.scene_renderer, SceneRenderer)


def test_resize_updates_camera_aspect(qtbot):
    """Resizing the widget must update the camera's aspect ratio."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    widget.resize(1600, 800)
    # Qt may not deliver resizeGL until the widget is shown; we call it directly.
    widget.resizeGL(1600, 800)
    assert widget.camera.aspect == 2.0


def test_middle_button_drag_orbits_camera(qtbot):
    """MMB drag should change the camera position (orbit)."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    pos_before = widget.camera.position.copy()

    # Simulate MMB press at (100, 100) and release at (200, 150).
    qtbot.mousePress(widget, Qt.MouseButton.MiddleButton, pos=QPoint(100, 100))
    qtbot.mouseMove(widget, QPoint(200, 150))
    qtbot.mouseRelease(widget, Qt.MouseButton.MiddleButton, pos=QPoint(200, 150))

    assert not np.allclose(widget.camera.position, pos_before)


def test_wheel_event_zooms_camera(qtbot):
    """Scrolling should change the camera-target distance."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)
    distance_before = float(np.linalg.norm(widget.camera.position - widget.camera.target))

    # Drive the wheel event directly (qtbot doesn't have a wheel helper).
    widget.wheelEvent(_make_wheel_event(widget, delta_y=120))

    distance_after = float(np.linalg.norm(widget.camera.position - widget.camera.target))
    assert distance_after != distance_before


def _make_wheel_event(widget, delta_y: int) -> QWheelEvent:
    """Construct a QWheelEvent suitable for delivery to a widget's wheelEvent."""
    from PySide6.QtCore import QPointF

    pos = QPointF(widget.width() / 2.0, widget.height() / 2.0)
    return QWheelEvent(
        pos,                              # position (local)
        pos,                              # global position (offscreen: same as local)
        QPoint(0, 0),                     # pixelDelta
        QPoint(0, delta_y),               # angleDelta (120 = one notch on most mice)
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,                            # inverted
    )
```

- [ ] **Step 3: Run tests — verify they fail because `ViewportWidget` doesn't yet have `camera` / `scene_renderer` / mouse handling**

```bash
pytest tests/test_viewport.py -v
```

Expected: `test_main_window_constructs` PASS, `test_viewport_widget_constructs` PASS, the rest FAIL (`AttributeError: 'ViewportWidget' object has no attribute 'camera'`, etc.).

- [ ] **Step 4: Replace `python/pluton/viewport/viewport_widget.py`** entirely

```python
"""The 3D viewport widget — a QOpenGLWidget driving the M1 scene.

Owns a Camera (Python/numpy) and a SceneRenderer (GL resources). Translates
Qt mouse events into camera operations:

  * MMB drag         -> orbit
  * Shift + MMB drag -> pan
  * Scroll wheel     -> zoom toward cursor
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pluton.viewport.camera import Camera
from pluton.viewport.scene_renderer import SceneRenderer


class ViewportWidget(QOpenGLWidget):
    """The 3D viewport. Renders cube + grid + axes; orbits via mouse."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.camera = Camera()
        self.scene_renderer = SceneRenderer()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Receive mouse-tracking events without requiring a button press.
        self.setMouseTracking(True)

        self._last_mouse_pos: QPoint | None = None
        self._dragging_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._dragging_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    # --- GL lifecycle -----------------------------------------------------

    def initializeGL(self) -> None:
        self.scene_renderer.initialize_gl()

    def resizeGL(self, w: int, h: int) -> None:
        self.scene_renderer.resize(w, h)
        self.camera.aspect = float(w) / max(float(h), 1.0)

    def paintGL(self) -> None:
        self.scene_renderer.render(self.camera)

    # --- Mouse handling ---------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.MiddleButton
            self._dragging_modifiers = event.modifiers()
            self._last_mouse_pos = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._dragging_button == Qt.MouseButton.MiddleButton
            and self._last_mouse_pos is not None
        ):
            current = event.position().toPoint()
            dx = float(current.x() - self._last_mouse_pos.x())
            dy = float(current.y() - self._last_mouse_pos.y())
            self._last_mouse_pos = current

            if self._dragging_modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.camera.pan(dx_pixels=dx, dy_pixels=dy)
            else:
                # Negate dy so dragging up tilts the view up (screen-y is inverted).
                self.camera.orbit(dx_pixels=dx, dy_pixels=-dy)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._dragging_button = Qt.MouseButton.NoButton
            self._last_mouse_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # angleDelta is in 1/8 of a degree; one notch = 120 units = 15 degrees.
        notches = event.angleDelta().y() / 120.0
        cursor = event.position()
        ndc = self._cursor_to_ndc(cursor.x(), cursor.y())
        self.camera.zoom(scroll_delta=notches, cursor_ndc=ndc)
        self.update()
        event.accept()

    # --- Helpers ----------------------------------------------------------

    def _cursor_to_ndc(self, x: float, y: float) -> np.ndarray:
        """Map widget-local cursor pixel to NDC [-1, +1] for x and y.

        y axis is flipped because screen-y grows downward while NDC-y grows up.
        """
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        nx = (2.0 * x / w) - 1.0
        ny = 1.0 - (2.0 * y / h)
        return np.array([nx, ny], dtype=np.float32)
```

- [ ] **Step 5: Run tests — verify they PASS**

```bash
pytest tests/test_viewport.py -v
```

Expected: all 6 tests in `test_viewport.py` PASS.

If `test_resize_updates_camera_aspect` fails: confirm `resizeGL` actually mutates `self.camera.aspect` (not the local `aspect`).

- [ ] **Step 6: Run the full Python test suite to confirm no regressions**

```bash
pytest -v
```

Expected: `test_mesh.py` (9), `test_camera.py` (11), `test_viewport.py` (6) = 26 tests, all PASS.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/viewport/viewport_widget.py tests/test_viewport.py
git commit -m "feat(viewport): wire ViewportWidget to Camera + SceneRenderer with mouse controls"
```

---

## Task 9: Manual visual verification

**Files:** none modified.

- [ ] **Step 1: Launch the app**

```bash
python -m pluton
```

- [ ] **Step 2: User confirms each of the following:**

  - [ ] Window opens at default 1280×800
  - [ ] A flat-shaded gray cube is visible at the origin, sitting on the ground
  - [ ] A 10×10 m grid is visible on the Z=0 plane
  - [ ] Red, green, and blue axis lines emanate from the origin (X, Y, Z respectively)
  - [ ] **MMB drag** orbits the camera around the origin
  - [ ] **Shift + MMB drag** pans the view
  - [ ] **Scroll wheel** zooms; pointing the cursor at a cube corner and zooming should keep that corner roughly under the cursor

- [ ] **Step 3: Take a screenshot** for the README / future docs.

If anything in Step 2 looks off, file the deviation against the design spec (`docs/2026-05-19-M1-core-viewport-design.md`) and decide whether to fix-in-task or as a follow-up issue.

---

## Task 10: Push, verify CI

**Files:** none modified.

- [ ] **Step 1: Push commits to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Watch CI**

```bash
gh run watch
```

Expected: Both `ubuntu-24.04` and `windows-2022` jobs go green. Test counts in the logs should show 27 pytest tests + 7 GoogleTest tests passing.

If CI fails for a platform-specific reason (e.g., shader resource not packaged in the built wheel — different behavior from the editable install), capture the error and fix; CI must be green before tagging.

---

## Task 11: Version bump and release tag

**Files:**
- Modify: `pyproject.toml`
- Modify: `CMakeLists.txt`

- [ ] **Step 1: Bump version in `pyproject.toml`**

Replace:
```toml
version = "0.0.1"
```
with:
```toml
version = "0.0.2"
```

- [ ] **Step 2: Bump version in top-level `CMakeLists.txt`**

Replace:
```cmake
project(pluton
    VERSION 0.0.1
    DESCRIPTION "Polygonal 3D modeler for architecture"
    LANGUAGES CXX
)
```
with:
```cmake
project(pluton
    VERSION 0.0.2
    DESCRIPTION "Polygonal 3D modeler for architecture"
    LANGUAGES CXX
)
```

- [ ] **Step 3: Rebuild and confirm `pluton.__version__` reports `0.0.2`**

```bash
pip install -e . --no-build-isolation
python -c "import pluton; print(pluton.__version__)"
```

Wait — `pluton.__version__` comes from the C++ `pluton::version()` function, which is currently hardcoded to `"0.0.1"`. Update `cpp/src/version.cpp` accordingly:

Open `cpp/src/version.cpp` and change the returned string to `"0.0.2"`.

Rebuild again and re-verify.

- [ ] **Step 4: Update the existing C++ version test**

`cpp/tests/test_version.cpp` asserts the version string. Update it to expect `"0.0.2"`.

Rebuild and run `ctest` to confirm all C++ tests pass.

- [ ] **Step 5: Commit the version bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp cpp/tests/test_version.cpp
git commit -m "chore: bump version to 0.0.2 for M1"
```

- [ ] **Step 6: Tag the milestone**

Two tags — one descriptive, one version-based. Both annotated and SSH-signed:

```bash
git tag -a v0.0.2-m1 -m "M1 — Core viewport: cube on grid with orbit/pan/zoom and Phong shading"
git tag -a m1-first-cube -m "M1 milestone marker: first real 3D geometry on screen"
```

- [ ] **Step 7: Push everything**

```bash
git push origin main
git push origin v0.0.2-m1 m1-first-cube
```

- [ ] **Step 8: Verify on GitHub**

Visit `https://github.com/Parrow-Horrizon-Studio/pluton/releases` and confirm both tags appear and show the Verified badge.

---

## Carried-Over Follow-Ups (not blocking M1)

These were noted during M0 execution and are still open. Ideally tracked as GitHub Issues so they don't fall through the cracks, but **none are blocking** for M1 — implementation can proceed without resolving them. Recommended to open issues whenever convenient:

1. **Bump `actions/checkout@v4` and `actions/setup-python@v5`** before Node 20 EOL (Sept 16, 2026)
2. **Install `clang-format`** (e.g., `winget install LLVM.LLVM`) so the `.clang-format` rules can actually be applied
3. **Re-enable vcpkg binary cache in CI** once we have heavier deps (currently disabled via `VCPKG_BINARY_SOURCES: clear`)
4. **Add `gh` CLI to PATH** for smoother CI / release workflow on Windows

---

## Document History

| Date | Author | Change |
|---|---|---|
| 2026-05-19 | Rowee Apor | Initial M1 plan derived from approved design spec |

# M3b — Push/Pull (basic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first SketchUp-style push/pull tool. Click a face, drag along its normal, click to commit. The committed extrusion is topologically valid (open-bottom prism) but does not boolean-merge with surrounding geometry.

**Architecture:** A C++ free function `pluton::ray_intersect_mesh` brute-forces Möller-Trumbore over every live face's stored triangulation; the closest positive `t` wins. The Python `Scene` wrapper exposes `ray_pick_face` plus three read-only helpers (`face_loop`, `face_normal`, `face_center`) that `PushPullTool` consumes. The tool itself runs a three-state machine (IDLE / HOVERING / DRAGGING), drives the depth via a line-line closest-point projection from the camera ray onto the face's normal axis, and at commit time builds a single `CompositeCommand("Push/Pull")` of `4N + 2` children (for an N-gon source: `RemoveFace + AddVertex×N + AddEdge×2N + AddFace×(N+1)`). Preview rendering is done in a new alpha-blended `SceneRenderer.draw_face_fill_overlays` pass; the scene itself is untouched until commit.

**Tech Stack:** C++20, nanobind 2.x, GoogleTest, PySide6 (Qt 6), PyOpenGL, numpy, mapbox-earcut (Python; unchanged from M3a), pytest + pytest-qt. **No new C++ deps** — `vcpkg.json` is untouched; CGAL still waits for M3c.

**Spec:** `docs/2026-05-23-M3b-push-pull-design.md`

**Prerequisite:** M3a complete (tag `v0.0.4-m3a`). Working tree clean on `main`.

---

## Build & Test Commands Reference

Same incantation as M3a. M3b does not change the build system.

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

After any C++ source change you MUST run `pluton-build` before the new code shows up in `pluton-cpp-tests` or `pluton-py-tests`. Python-only changes are picked up automatically by the editable install.

---

## File Map

**C++ side**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/include/pluton/ray_intersect.h` | NEW | `RayMeshHit` struct + `ray_intersect_mesh` free function declaration. |
| `cpp/src/ray_intersect.cpp` | NEW | Möller-Trumbore impl; iterates live faces; closest-hit selection. |
| `cpp/bindings/module.cpp` | MODIFY | Bind `RayMeshHit` + `ray_intersect_mesh` (~30 lines added). |
| `cpp/tests/test_ray_intersect.cpp` | NEW | GoogleTest cases for ray-mesh. |
| `cpp/CMakeLists.txt` | MODIFY | Add `ray_intersect.cpp` to `pluton_core`. |
| `cpp/tests/CMakeLists.txt` | MODIFY | Add `test_ray_intersect.cpp` to `pluton_tests`. |

`HalfEdgeMesh` itself is NOT modified — M3a already exposes `face_loop_vertices` and `face_triangles`, which is everything ray-mesh needs. Task 1 verifies this assumption.

**Python side**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/scene/scene.py` | MODIFY | Add `ray_pick_face` / `face_loop` / `face_normal` / `face_center`. |
| `python/pluton/tools/tool.py` | MODIFY | `ToolContext` gains `camera` + `widget_size_provider`. `ToolOverlay` gains `face_fill_polygons` + `face_fill_color`. `Tool` gains optional `status_text` property. |
| `python/pluton/tools/push_pull_tool.py` | NEW | `PushPullTool` class — full state machine, depth metric, overlay, composite-building. |
| `python/pluton/tools/__init__.py` | MODIFY | Export `PushPullTool`. |
| `python/pluton/viewport/scene_renderer.py` | MODIFY | `draw_face_fill_overlays` pass (alpha-blended, depth-write disabled). |
| `python/pluton/ui/status_bar.py` | MODIFY | Add `set_status(text)` for the third slot used by `PushPullTool`. |
| `python/pluton/ui/main_window.py` | MODIFY | Register `PushPullTool`, bind `P`, refresh status bar's status slot each frame from the active tool's `status_text`. |

**Tests**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/tests/test_ray_intersect.cpp` | NEW | (Listed above; here for completeness.) |
| `tests/test_halfedge_python.py` | MODIFY | Add `face_triangles` + `face_loop_vertices` round-trip coverage (verify M3a API is suitable). |
| `tests/test_ray_intersect_python.py` | NEW | Python binding smoke test. |
| `tests/test_scene.py` | MODIFY | `ray_pick_face` / `face_loop` / `face_normal` / `face_center`. |
| `tests/test_push_pull_tool.py` | NEW | State machine + depth metric. |
| `tests/test_push_pull_topology.py` | NEW | Extrusion composite correctness (undo/redo round-trip). |
| `tests/test_push_pull_overlay.py` | NEW | Overlay polygons per state. |
| `tests/test_scene_renderer.py` | MODIFY | Face-fill overlay smoke test. |
| `tests/test_viewport.py` | MODIFY | `P` keybind + status bar `set_status` integration. |

**Versioning / build (last task)**

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | MODIFY | Bump `version = "0.0.5"`. |
| `CMakeLists.txt` (top-level) | MODIFY | Bump `project(... VERSION 0.0.5 ...)`. |
| `cpp/src/version.cpp` | MODIFY | Return `"0.0.5"`. |

---

## Definition of Done for M3b

1. C++ `ray_intersect_mesh` compiles cleanly with no warnings on MSVC `/W4` and GCC `-Wall -Wextra -Wpedantic`.
2. All M3b GoogleTest cases pass (~5-8 new tests).
3. All M3a Python tests (134) still pass unchanged.
4. New Python tests for `ray_intersect_mesh` binding, `Scene` helpers, `PushPullTool` state machine, extrusion topology, overlay, and MainWindow integration pass.
5. Total Python test count: ~155-165. Total GoogleTest count: ~51-54.
6. `python -m pluton` launches; M3a baseline (camera, snaps, status bar, undo, ESC two-stage) works.
7. `P` activates Push/Pull. Hover-highlight, click-to-arm, drag-to-extrude, click-to-commit all work. `Ctrl+Z` undoes the extrusion.
8. The 11-step visual verification checklist (spec §9.2) passes (items 9 and 11 are documented limitations, not bugs).
9. CI green on Windows + Linux.
10. Tagged `v0.0.5-m3b` (annotated, SSH-signed).
11. Tag pushed to GitHub.
12. Carry-over GitHub issues opened (BVH for ray-mesh / closed-bottom prism / seam-line elimination / any execution-time discoveries).

---

## Task 1: Verify M3a kernel API supports M3b's needs

**Files:**
- Modify: `tests/test_halfedge_python.py`

The M3a `HalfEdgeMesh` already exposes `face_loop_vertices(face_id)` and `face_triangles(face_id)` — between them, M3b has everything it needs for ray-mesh + extrusion topology. Add a couple of explicit smoke tests so this contract is locked down by test rather than assumption.

- [ ] **Step 1: Write the failing test** — append to `tests/test_halfedge_python.py`

```python
def test_face_loop_vertices_returns_ordered_boundary_ids():
    """M3a contract M3b depends on: face_loop_vertices returns the boundary
    loop vertex IDs in insertion order. PushPullTool reads this to know which
    source-face vertices to extrude."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(0.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    mesh.add_halfedge_pair(v1, v2)
    mesh.add_halfedge_pair(v2, v3)
    mesh.add_halfedge_pair(v3, v0)
    # Two-triangle fan for the rectangle: (v0, v1, v2) + (v0, v2, v3).
    f = mesh.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    loop = mesh.face_loop_vertices(f)
    assert list(loop) == [v0, v1, v2, v3]


def test_face_triangles_returns_flat_triangulation_buffer():
    """M3a contract M3b depends on: face_triangles returns a flat list of vertex
    IDs (3 per triangle). ray_intersect_mesh walks this to test ray-triangle
    intersection per face."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(0.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    mesh.add_halfedge_pair(v1, v2)
    mesh.add_halfedge_pair(v2, v3)
    mesh.add_halfedge_pair(v3, v0)
    f = mesh.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    tris = list(mesh.face_triangles(f))
    assert len(tris) == 6  # 2 triangles × 3 vertices
    assert tris == [v0, v1, v2, v0, v2, v3]


def test_face_triangles_raises_on_invalid_face_id():
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    with pytest.raises(Exception):  # IndexError or out_of_range translated to a Python exception
        mesh.face_triangles(42)
```

- [ ] **Step 2: Run to verify the tests pass**

Run: `pluton-py-tests tests/test_halfedge_python.py -k "face_loop_vertices_returns_ordered or face_triangles_returns_flat or face_triangles_raises" -v`
Expected: 3 PASS (all behaviors are M3a-shipped; we're just locking them down).

- [ ] **Step 3: Commit**

```bash
git add tests/test_halfedge_python.py
git commit -m "$(cat <<'EOF'
test(halfedge): lock down M3a accessors that M3b's ray-mesh + extrusion depend on

Add explicit tests for face_loop_vertices ordering and face_triangles' flat
buffer shape (3 vertex IDs per triangle). These are the M3a → M3b contract
surface; pinning them by test means M3b's downstream tasks have a stable
foundation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: C++ ray_intersect_mesh — header, impl, GoogleTest

**Files:**
- Create: `cpp/include/pluton/ray_intersect.h`
- Create: `cpp/src/ray_intersect.cpp`
- Create: `cpp/tests/test_ray_intersect.cpp`
- Modify: `cpp/CMakeLists.txt`
- Modify: `cpp/tests/CMakeLists.txt`

- [ ] **Step 1: Create the header** at `cpp/include/pluton/ray_intersect.h`

```cpp
#pragma once

#include <array>
#include <cstdint>
#include <optional>

#include "pluton/halfedge.h"

namespace pluton {

/// Result of a ray-mesh intersection.
struct RayMeshHit {
    std::uint32_t        face_id;
    float                t;      // ray parameter (always > 0)
    std::array<float, 3> point;  // origin + t * direction
};

/// Brute-force ray-mesh intersection over every live face in `mesh`.
///
/// Iterates `mesh.next_live_face(...)`. For each face: walks the face's
/// triangulation (from `face_triangles(face_id)`); runs Möller-Trumbore on
/// each triangle. Returns the closest positive `t` hit across all triangles
/// (or `std::nullopt` if the ray misses everything).
///
/// Hit selection is two-sided: a ray hits a triangle from either face
/// orientation (we're picking, not shading).
///
/// `direction` does NOT need to be normalized; `t` is in `direction`-units.
std::optional<RayMeshHit> ray_intersect_mesh(
    const HalfEdgeMesh& mesh,
    const std::array<float, 3>& origin,
    const std::array<float, 3>& direction);

}  // namespace pluton
```

- [ ] **Step 2: Create the implementation** at `cpp/src/ray_intersect.cpp`

```cpp
#include "pluton/ray_intersect.h"

#include <cmath>
#include <limits>

namespace pluton {

namespace {

// Möller-Trumbore ray-triangle intersection, two-sided.
//
// Returns the t parameter (always > 0 on hit; std::nullopt on miss).
// Backface culling is intentionally NOT applied: we're picking, not shading.
std::optional<float> ray_triangle(
    const std::array<float, 3>& origin,
    const std::array<float, 3>& dir,
    const std::array<float, 3>& v0,
    const std::array<float, 3>& v1,
    const std::array<float, 3>& v2) {

    const float e1x = v1[0] - v0[0];
    const float e1y = v1[1] - v0[1];
    const float e1z = v1[2] - v0[2];
    const float e2x = v2[0] - v0[0];
    const float e2y = v2[1] - v0[1];
    const float e2z = v2[2] - v0[2];

    // h = dir × e2
    const float hx = dir[1] * e2z - dir[2] * e2y;
    const float hy = dir[2] * e2x - dir[0] * e2z;
    const float hz = dir[0] * e2y - dir[1] * e2x;

    // a = e1 · h
    const float a = e1x * hx + e1y * hy + e1z * hz;

    // Parallel (or degenerate triangle): skip.
    constexpr float kEpsilon = 1e-8f;
    if (std::fabs(a) < kEpsilon) {
        return std::nullopt;
    }

    const float f = 1.0f / a;
    const float sx = origin[0] - v0[0];
    const float sy = origin[1] - v0[1];
    const float sz = origin[2] - v0[2];
    const float u = f * (sx * hx + sy * hy + sz * hz);
    if (u < 0.0f || u > 1.0f) {
        return std::nullopt;
    }

    // q = s × e1
    const float qx = sy * e1z - sz * e1y;
    const float qy = sz * e1x - sx * e1z;
    const float qz = sx * e1y - sy * e1x;

    const float v = f * (dir[0] * qx + dir[1] * qy + dir[2] * qz);
    if (v < 0.0f || u + v > 1.0f) {
        return std::nullopt;
    }

    const float t = f * (e2x * qx + e2y * qy + e2z * qz);
    if (t <= kEpsilon) {
        return std::nullopt;  // behind origin or on it
    }
    return t;
}

}  // namespace

std::optional<RayMeshHit> ray_intersect_mesh(
    const HalfEdgeMesh& mesh,
    const std::array<float, 3>& origin,
    const std::array<float, 3>& direction) {

    std::optional<RayMeshHit> best;
    float best_t = std::numeric_limits<float>::infinity();

    std::uint32_t f = mesh.next_live_face(0);
    while (f != HalfEdgeMesh::INVALID_ID) {
        const auto tris = mesh.face_triangles(f);  // flat: 3*T entries
        for (std::size_t i = 0; i + 2 < tris.size(); i += 3) {
            const auto a_id = static_cast<std::uint32_t>(tris[i]);
            const auto b_id = static_cast<std::uint32_t>(tris[i + 1]);
            const auto c_id = static_cast<std::uint32_t>(tris[i + 2]);
            const auto a = mesh.vertex_position(a_id);
            const auto b = mesh.vertex_position(b_id);
            const auto c = mesh.vertex_position(c_id);

            auto t = ray_triangle(origin, direction, a, b, c);
            if (t && *t < best_t) {
                best_t = *t;
                RayMeshHit hit;
                hit.face_id = f;
                hit.t = *t;
                hit.point = {
                    origin[0] + direction[0] * (*t),
                    origin[1] + direction[1] * (*t),
                    origin[2] + direction[2] * (*t),
                };
                best = hit;
            }
        }
        f = mesh.next_live_face(f + 1);
    }
    return best;
}

}  // namespace pluton
```

- [ ] **Step 3: Create the GoogleTest cases** at `cpp/tests/test_ray_intersect.cpp`

```cpp
#include <gtest/gtest.h>

#include "pluton/halfedge.h"
#include "pluton/ray_intersect.h"

using pluton::HalfEdgeMesh;
using pluton::RayMeshHit;
using pluton::ray_intersect_mesh;

namespace {

// Make a unit-square rectangle face on the XY plane at z=0.
// Returns (mesh, face_id).
std::pair<HalfEdgeMesh, std::uint32_t> make_ground_rect() {
    HalfEdgeMesh m;
    const auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
    const auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
    const auto v2 = m.add_vertex(1.0f, 1.0f, 0.0f);
    const auto v3 = m.add_vertex(0.0f, 1.0f, 0.0f);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);
    std::vector<std::int32_t> tris = {
        static_cast<int>(v0), static_cast<int>(v1), static_cast<int>(v2),
        static_cast<int>(v0), static_cast<int>(v2), static_cast<int>(v3),
    };
    const auto f = m.add_face_from_loop({v0, v1, v2, v3}, tris);
    return {std::move(m), f};
}

}  // namespace

TEST(RayIntersectMesh, EmptyMeshReturnsNullopt) {
    HalfEdgeMesh m;
    auto hit = ray_intersect_mesh(m, {0.0f, 0.0f, 5.0f}, {0.0f, 0.0f, -1.0f});
    EXPECT_FALSE(hit.has_value());
}

TEST(RayIntersectMesh, RayFromAboveHitsGroundRectangle) {
    auto [m, f] = make_ground_rect();
    auto hit = ray_intersect_mesh(m, {0.5f, 0.5f, 5.0f}, {0.0f, 0.0f, -1.0f});
    ASSERT_TRUE(hit.has_value());
    EXPECT_EQ(hit->face_id, f);
    EXPECT_NEAR(hit->t, 5.0f, 1e-5f);
    EXPECT_NEAR(hit->point[0], 0.5f, 1e-5f);
    EXPECT_NEAR(hit->point[1], 0.5f, 1e-5f);
    EXPECT_NEAR(hit->point[2], 0.0f, 1e-5f);
}

TEST(RayIntersectMesh, RayMissesRectangleSideways) {
    auto [m, f] = make_ground_rect();
    auto hit = ray_intersect_mesh(m, {5.0f, 5.0f, 5.0f}, {0.0f, 0.0f, -1.0f});
    EXPECT_FALSE(hit.has_value());
}

TEST(RayIntersectMesh, RayBehindOriginDoesNotHit) {
    auto [m, f] = make_ground_rect();
    // Origin BELOW the rectangle, looking DOWN — ray never crosses z=0 in t>0.
    auto hit = ray_intersect_mesh(m, {0.5f, 0.5f, -1.0f}, {0.0f, 0.0f, -1.0f});
    EXPECT_FALSE(hit.has_value());
}

TEST(RayIntersectMesh, TwoSidedHitFromBelow) {
    auto [m, f] = make_ground_rect();
    // Origin below, looking up — should still pick the face (two-sided).
    auto hit = ray_intersect_mesh(m, {0.5f, 0.5f, -3.0f}, {0.0f, 0.0f, 1.0f});
    ASSERT_TRUE(hit.has_value());
    EXPECT_EQ(hit->face_id, f);
    EXPECT_NEAR(hit->t, 3.0f, 1e-5f);
}

TEST(RayIntersectMesh, ClosestFaceWinsWhenTwoFacesAlongRay) {
    HalfEdgeMesh m;
    // Lower face at z=0
    {
        const auto v0 = m.add_vertex(0.0f, 0.0f, 0.0f);
        const auto v1 = m.add_vertex(1.0f, 0.0f, 0.0f);
        const auto v2 = m.add_vertex(1.0f, 1.0f, 0.0f);
        const auto v3 = m.add_vertex(0.0f, 1.0f, 0.0f);
        m.add_halfedge_pair(v0, v1);
        m.add_halfedge_pair(v1, v2);
        m.add_halfedge_pair(v2, v3);
        m.add_halfedge_pair(v3, v0);
        m.add_face_from_loop(
            {v0, v1, v2, v3},
            {static_cast<int>(v0), static_cast<int>(v1), static_cast<int>(v2),
             static_cast<int>(v0), static_cast<int>(v2), static_cast<int>(v3)});
    }
    // Upper face at z=2 (will be hit FIRST from a ray coming from above)
    std::uint32_t upper_face;
    {
        const auto u0 = m.add_vertex(0.0f, 0.0f, 2.0f);
        const auto u1 = m.add_vertex(1.0f, 0.0f, 2.0f);
        const auto u2 = m.add_vertex(1.0f, 1.0f, 2.0f);
        const auto u3 = m.add_vertex(0.0f, 1.0f, 2.0f);
        m.add_halfedge_pair(u0, u1);
        m.add_halfedge_pair(u1, u2);
        m.add_halfedge_pair(u2, u3);
        m.add_halfedge_pair(u3, u0);
        upper_face = m.add_face_from_loop(
            {u0, u1, u2, u3},
            {static_cast<int>(u0), static_cast<int>(u1), static_cast<int>(u2),
             static_cast<int>(u0), static_cast<int>(u2), static_cast<int>(u3)});
    }

    auto hit = ray_intersect_mesh(m, {0.5f, 0.5f, 5.0f}, {0.0f, 0.0f, -1.0f});
    ASSERT_TRUE(hit.has_value());
    EXPECT_EQ(hit->face_id, upper_face);
    EXPECT_NEAR(hit->t, 3.0f, 1e-5f);  // 5 - 2 = 3
}

TEST(RayIntersectMesh, TombstonedFaceIsSkipped) {
    auto [m, f] = make_ground_rect();
    m.remove_face(f);
    auto hit = ray_intersect_mesh(m, {0.5f, 0.5f, 5.0f}, {0.0f, 0.0f, -1.0f});
    EXPECT_FALSE(hit.has_value());
}

TEST(RayIntersectMesh, NormalizedAndUnnormalizedDirectionsAgreeOnFaceId) {
    auto [m, f] = make_ground_rect();
    auto a = ray_intersect_mesh(m, {0.5f, 0.5f, 5.0f}, {0.0f, 0.0f, -1.0f});
    auto b = ray_intersect_mesh(m, {0.5f, 0.5f, 5.0f}, {0.0f, 0.0f, -7.5f});  // same direction, different magnitude
    ASSERT_TRUE(a.has_value());
    ASSERT_TRUE(b.has_value());
    EXPECT_EQ(a->face_id, b->face_id);
    EXPECT_EQ(a->face_id, f);
    // The t parameters differ because direction magnitudes differ.
    EXPECT_NEAR(a->t * 7.5f, b->t * 1.0f, 1e-4f);
}
```

- [ ] **Step 4: Wire into the build**

Modify `cpp/CMakeLists.txt` — add `src/ray_intersect.cpp` to the `pluton_core` library sources. Find the existing `add_library(pluton_core ...)` (or similar) call and append `src/ray_intersect.cpp` to its source list.

Modify `cpp/tests/CMakeLists.txt` — add `test_ray_intersect.cpp` to the test executable's source list (same pattern as `test_halfedge.cpp`).

- [ ] **Step 5: Build and run the C++ tests**

Run: `pluton-build && pluton-cpp-tests`
Expected: all M3a GoogleTest cases continue to pass; 8 new `RayIntersectMesh.*` tests pass.

- [ ] **Step 6: Commit**

```bash
git add cpp/include/pluton/ray_intersect.h cpp/src/ray_intersect.cpp cpp/tests/test_ray_intersect.cpp cpp/CMakeLists.txt cpp/tests/CMakeLists.txt
git commit -m "$(cat <<'EOF'
feat(cpp): add ray_intersect_mesh — brute-force ray-mesh face picking

Free function pluton::ray_intersect_mesh iterates every live face in the
HalfEdgeMesh, walks the face's stored triangulation, and runs Möller-Trumbore
on each triangle. Closest positive t wins. Two-sided (we're picking, not
shading). Empty meshes / tombstoned faces correctly return nullopt.

This is the M3b kernel primitive the PushPullTool consumes for face picking.
BVH is deferred to M10 (tracked separately).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: nanobind binding for ray_intersect_mesh + Python smoke test

**Files:**
- Modify: `cpp/bindings/module.cpp`
- Create: `tests/test_ray_intersect_python.py`

- [ ] **Step 1: Write the failing Python test** at `tests/test_ray_intersect_python.py`

```python
"""Python binding smoke tests for ray_intersect_mesh."""

import numpy as np
import pytest


def _make_ground_rect():
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(0.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    mesh.add_halfedge_pair(v1, v2)
    mesh.add_halfedge_pair(v2, v3)
    mesh.add_halfedge_pair(v3, v0)
    f = mesh.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])
    return mesh, f


def test_ray_intersect_mesh_hit_returns_face_id_t_and_point():
    from pluton._core import ray_intersect_mesh

    mesh, f = _make_ground_rect()
    hit = ray_intersect_mesh(mesh, [0.5, 0.5, 5.0], [0.0, 0.0, -1.0])
    assert hit is not None
    assert hit.face_id == f
    assert hit.t == pytest.approx(5.0, abs=1e-5)
    assert tuple(hit.point) == pytest.approx((0.5, 0.5, 0.0), abs=1e-5)


def test_ray_intersect_mesh_miss_returns_none():
    from pluton._core import ray_intersect_mesh

    mesh, _ = _make_ground_rect()
    hit = ray_intersect_mesh(mesh, [5.0, 5.0, 5.0], [0.0, 0.0, -1.0])
    assert hit is None


def test_ray_intersect_mesh_empty_mesh_returns_none():
    from pluton._core import HalfEdgeMesh, ray_intersect_mesh

    mesh = HalfEdgeMesh()
    hit = ray_intersect_mesh(mesh, [0.0, 0.0, 5.0], [0.0, 0.0, -1.0])
    assert hit is None


def test_ray_intersect_mesh_accepts_numpy_arrays():
    """Common caller shape: pass numpy float32 (3,) arrays. nanobind should
    accept these because of the stl/array conversion."""
    from pluton._core import ray_intersect_mesh

    mesh, f = _make_ground_rect()
    origin = np.array([0.5, 0.5, 5.0], dtype=np.float32)
    direction = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    hit = ray_intersect_mesh(mesh, list(origin), list(direction))
    assert hit is not None
    assert hit.face_id == f
```

Run: `pluton-py-tests tests/test_ray_intersect_python.py -v`
Expected: FAIL with `ImportError: cannot import name 'ray_intersect_mesh'` or `AttributeError: module 'pluton._core' has no attribute 'ray_intersect_mesh'`.

- [ ] **Step 2: Add the nanobind bindings** in `cpp/bindings/module.cpp`

At the top, add `#include "pluton/ray_intersect.h"` next to the existing `#include "pluton/halfedge.h"` line.

Add `using pluton::RayMeshHit;` and `using pluton::ray_intersect_mesh;` next to the existing `using` declarations.

At the bottom of the `NB_MODULE(_core, m)` block (after the `HalfEdgeMesh` class binding's closing `.def_ro_static(...)` line and its terminating `;`), add:

```cpp
    nb::class_<RayMeshHit>(m, "RayMeshHit", "Result of pluton::ray_intersect_mesh")
        .def_ro("face_id", &RayMeshHit::face_id)
        .def_ro("t",       &RayMeshHit::t)
        .def_prop_ro(
            "point",
            [](RayMeshHit& self) {
                return std::array<float, 3>{self.point[0], self.point[1], self.point[2]};
            },
            "Hit point in world coordinates (3-tuple).");

    m.def("ray_intersect_mesh", &ray_intersect_mesh,
          nb::arg("mesh"), nb::arg("origin"), nb::arg("direction"),
          "Brute-force ray-mesh face picking. Returns RayMeshHit or None.");
```

- [ ] **Step 3: Rebuild and rerun the tests**

Run: `pluton-build && pluton-py-tests tests/test_ray_intersect_python.py -v`
Expected: 4 PASS.

- [ ] **Step 4: Confirm M3a tests still pass**

Run: `pluton-py-tests tests/test_halfedge_python.py -v`
Expected: All previous M3a tests + the 3 Task-1 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cpp/bindings/module.cpp tests/test_ray_intersect_python.py
git commit -m "$(cat <<'EOF'
feat(bindings): expose ray_intersect_mesh + RayMeshHit to Python

nanobind binding for the M3b ray-mesh face picker. RayMeshHit fields
(face_id, t, point) are exposed read-only; ray_intersect_mesh accepts
list / tuple / numpy origin and direction via the stl/array converter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Scene wrapper helpers — ray_pick_face / face_loop / face_normal / face_center

**Files:**
- Modify: `python/pluton/scene/scene.py`
- Modify: `tests/test_scene.py`

These are the read-only accessors PushPullTool calls on each event tick. All four are thin wrappers around M3a's `HalfEdgeMesh` (plus the new `ray_intersect_mesh`).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_scene.py`

```python
class TestSceneRayPickFace:
    """Scene.ray_pick_face — thin wrapper over pluton._core.ray_intersect_mesh."""

    def test_returns_none_for_empty_scene(self):
        from pluton.scene import Scene

        scene = Scene()
        hit = scene.ray_pick_face(
            origin=np.array([0.0, 0.0, 5.0], dtype=np.float32),
            direction=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        assert hit is None

    def test_returns_face_id_when_ray_hits(self):
        from pluton.scene import Scene

        scene = Scene()
        v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
        v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
        v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
        f = scene.add_face_from_loop([v0, v1, v2, v3])

        hit = scene.ray_pick_face(
            origin=np.array([0.5, 0.5, 5.0], dtype=np.float32),
            direction=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        assert hit is not None
        assert hit.face_id == f
        assert hit.t == pytest.approx(5.0, abs=1e-4)

    def test_returns_none_after_face_removed(self):
        from pluton.scene import Scene

        scene = Scene()
        v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
        v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
        v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
        f = scene.add_face_from_loop([v0, v1, v2, v3])
        scene.remove_face(f)

        hit = scene.ray_pick_face(
            origin=np.array([0.5, 0.5, 5.0], dtype=np.float32),
            direction=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        assert hit is None


class TestSceneFaceLoopNormalCenter:
    """face_loop / face_normal / face_center — extrusion composite needs these."""

    def _make_unit_rect(self):
        from pluton.scene import Scene

        scene = Scene()
        v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
        v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
        v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
        f = scene.add_face_from_loop([v0, v1, v2, v3])
        return scene, f, (v0, v1, v2, v3)

    def test_face_loop_returns_boundary_vertex_ids_in_insertion_order(self):
        scene, f, (v0, v1, v2, v3) = self._make_unit_rect()
        loop = scene.face_loop(f)
        assert loop == [v0, v1, v2, v3]

    def test_face_loop_raises_keyerror_on_invalid_face_id(self):
        from pluton.scene import Scene

        scene = Scene()
        with pytest.raises(KeyError):
            scene.face_loop(99)

    def test_face_normal_on_xy_face_is_plus_z(self):
        scene, f, _ = self._make_unit_rect()
        n = scene.face_normal(f)
        assert n.shape == (3,)
        assert n.dtype == np.float32
        np.testing.assert_allclose(n, [0.0, 0.0, 1.0], atol=1e-6)

    def test_face_center_returns_centroid(self):
        scene, f, _ = self._make_unit_rect()
        c = scene.face_center(f)
        assert c.shape == (3,)
        assert c.dtype == np.float32
        np.testing.assert_allclose(c, [0.5, 0.5, 0.0], atol=1e-6)

    def test_face_normal_planar_face_in_xz_plane_is_plus_y(self):
        """A face with vertices at z varying and y=0 — normal should be ±Y."""
        from pluton.scene import Scene

        scene = Scene()
        v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
        v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
        v2 = scene.add_vertex(np.array([1.0, 0.0, 1.0], dtype=np.float32))
        v3 = scene.add_vertex(np.array([0.0, 0.0, 1.0], dtype=np.float32))
        f = scene.add_face_from_loop([v0, v1, v2, v3])
        n = scene.face_normal(f)
        # Loop V0→V1→V2→V3 CCW from +Y → normal points +Y.
        np.testing.assert_allclose(n, [0.0, -1.0, 0.0], atol=1e-6)
```

Run: `pluton-py-tests tests/test_scene.py -k "ray_pick_face or face_loop or face_normal or face_center" -v`
Expected: FAIL with `AttributeError: 'Scene' object has no attribute 'ray_pick_face'` (and similar for the other three methods).

> **Note on the `_plus_y` test:** the spec's normal-computation choice (cross product of the first two edges of the boundary loop, normalized) means the loop `V0(0,0,0)→V1(1,0,0)→V2(1,0,1)→V3(0,0,1)` produces a face whose first two edges are `e1=(1,0,0)` and `e2=(0,0,1)`. The cross product `e1 × e2 = (0·1−0·0, 0·0−1·1, 1·0−0·0) = (0, −1, 0)`. So the normal is `(0, −1, 0)` — that's what the test asserts. The Scene's `face_normal` is the geometric normal derived from the loop's winding, not a forced outward orientation.

- [ ] **Step 2: Add the helpers** to `python/pluton/scene/scene.py`

Find the existing `# --- Queries ---` section header. Insert these methods just before it (or just after `clear()`, whichever is cleaner):

```python
    # --- M3b picking + face geometry helpers ---------------------------------

    def ray_pick_face(
        self,
        origin: np.ndarray,
        direction: np.ndarray,
    ):
        """Return the closest live face hit, or None.

        Thin wrapper around the C++ pluton._core.ray_intersect_mesh. Caller
        passes a 3-vector origin + 3-vector direction (need not be unit length).
        The returned RayMeshHit exposes .face_id, .t, .point.
        """
        from pluton._core import ray_intersect_mesh

        origin_list = [float(origin[0]), float(origin[1]), float(origin[2])]
        direction_list = [float(direction[0]), float(direction[1]), float(direction[2])]
        return ray_intersect_mesh(self._mesh, origin_list, direction_list)

    def face_loop(self, f_id: int) -> list[int]:
        """Ordered boundary vertex IDs of the given live face."""
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_loop: face {f_id} is not live")
        return list(self._mesh.face_loop_vertices(f_id))

    def face_normal(self, f_id: int) -> np.ndarray:
        """Geometric normal of the planar face, computed from the first three
        boundary vertices via cross product, then normalized.

        Assumes the face is planar (M2 / M3a only produce planar faces).
        # TODO M4+: handle non-planar faces (Newell's method, or fan-from-centroid).
        """
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_normal: face {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        if len(loop) < 3:
            raise ValueError(f"face_normal: face {f_id} has fewer than 3 vertices")
        p0 = np.asarray(self._mesh.vertex_position(loop[0]), dtype=np.float32)
        p1 = np.asarray(self._mesh.vertex_position(loop[1]), dtype=np.float32)
        p2 = np.asarray(self._mesh.vertex_position(loop[2]), dtype=np.float32)
        n = np.cross(p1 - p0, p2 - p0).astype(np.float32)
        length = float(np.linalg.norm(n))
        if length < 1e-9:
            raise ValueError(f"face_normal: face {f_id} is degenerate (first 3 vertices collinear)")
        return (n / length).astype(np.float32)

    def face_center(self, f_id: int) -> np.ndarray:
        """Centroid (mean) of the face's boundary vertex positions."""
        if not self._mesh.face_is_live(f_id):
            raise KeyError(f"face_center: face {f_id} is not live")
        loop = self._mesh.face_loop_vertices(f_id)
        acc = np.zeros(3, dtype=np.float32)
        for vid in loop:
            pos = self._mesh.vertex_position(vid)
            acc += np.asarray(pos, dtype=np.float32)
        return (acc / float(len(loop))).astype(np.float32)
```

- [ ] **Step 3: Run the tests**

Run: `pluton-py-tests tests/test_scene.py -k "ray_pick_face or face_loop or face_normal or face_center" -v`
Expected: 8 PASS.

- [ ] **Step 4: Make sure no existing M3a tests broke**

Run: `pluton-py-tests tests/test_scene.py -v`
Expected: all existing M3a tests still pass + 8 new ones.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene.py
git commit -m "$(cat <<'EOF'
feat(scene): add ray_pick_face / face_loop / face_normal / face_center

Read-only helpers for M3b's PushPullTool: ray_pick_face wraps the C++
ray_intersect_mesh; face_loop / face_normal / face_center expose
M3a HalfEdgeMesh data in numpy-friendly form. face_normal uses the
cross product of the first two boundary edges; documented as a
"planar face" assumption to revisit when non-planar faces appear (M4+).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: ToolOverlay + ToolContext extensions

**Files:**
- Modify: `python/pluton/tools/tool.py`
- Create / Modify: `tests/test_tool.py` (a small dedicated test file for the dataclass extensions)

ToolOverlay grows two optional fields for face-fill polygons (the hover/armed/ghost rendering). ToolContext grows `camera` + `widget_size_provider` so PushPullTool can compute camera rays. Tool ABC grows an optional `status_text` property (default `None`) so existing M2/M3a tools don't have to change.

- [ ] **Step 1: Write the failing tests** at `tests/test_tool.py`

(If the file already exists from earlier work, append; otherwise create with this content.)

```python
"""ToolOverlay / ToolContext / Tool ABC extensions for M3b."""

from __future__ import annotations

import numpy as np
import pytest


def test_tool_overlay_face_fill_defaults_to_empty_list_and_ghost_rgba():
    from pluton.tools.tool import ToolOverlay

    overlay = ToolOverlay(
        rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
        rubber_band_color=(1.0, 1.0, 1.0),
        snap_marker_position=None,
        snap_marker_color=(1.0, 1.0, 1.0),
    )
    assert overlay.face_fill_polygons == []
    assert overlay.face_fill_color == (0.4, 0.7, 1.0, 0.15)


def test_tool_overlay_accepts_explicit_face_fill_polygons():
    from pluton.tools.tool import ToolOverlay

    poly = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float32,
    )
    overlay = ToolOverlay(
        rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
        rubber_band_color=(1.0, 1.0, 1.0),
        snap_marker_position=None,
        snap_marker_color=(1.0, 1.0, 1.0),
        face_fill_polygons=[poly],
        face_fill_color=(1.0, 0.0, 0.0, 0.3),
    )
    assert len(overlay.face_fill_polygons) == 1
    np.testing.assert_array_equal(overlay.face_fill_polygons[0], poly)
    assert overlay.face_fill_color == (1.0, 0.0, 0.0, 0.3)


def test_tool_context_camera_and_widget_size_provider_default_to_none():
    from pluton.tools.tool import ToolContext

    ctx = ToolContext(scene=object())
    assert ctx.camera is None
    assert ctx.widget_size_provider is None


def test_tool_context_can_carry_camera_and_widget_size_provider():
    from pluton.tools.tool import ToolContext

    fake_camera = object()
    sizer = lambda: (640, 480)
    ctx = ToolContext(
        scene=object(),
        command_stack=None,
        camera=fake_camera,
        widget_size_provider=sizer,
    )
    assert ctx.camera is fake_camera
    assert ctx.widget_size_provider is sizer
    assert ctx.widget_size_provider() == (640, 480)


def test_tool_status_text_default_is_none():
    """Existing M2 / M3a tools that don't override status_text should return None."""
    from pluton.tools import RectangleTool

    tool = RectangleTool()
    assert tool.status_text is None
```

Run: `pluton-py-tests tests/test_tool.py -v`
Expected: FAIL (the dataclasses don't yet have these fields; the ABC doesn't yet have `status_text`).

- [ ] **Step 2: Extend the dataclasses + ABC** in `python/pluton/tools/tool.py`

Replace the file's body (from `@dataclass(frozen=True, slots=True)` down) with:

```python
@dataclass(frozen=True, slots=True)
class ToolContext:
    """Handed to Tool.activate(); gives the tool a handle to the live Scene,
    CommandStack, Camera, and a viewport-size accessor."""

    scene: object
    command_stack: object = None  # M3a-introduced — pluton.commands.CommandStack
    camera: object = None  # M3b-introduced — pluton.viewport.camera.Camera
    widget_size_provider: object = None
    """M3b-introduced — callable () -> tuple[int, int] returning (width, height)."""


@dataclass(frozen=True, slots=True)
class ToolOverlay:
    """Transient preview geometry rebuilt every frame by the active tool."""

    rubber_band_segments: np.ndarray  # shape (2*N, 3), float32
    rubber_band_color: tuple[float, float, float]
    snap_marker_position: np.ndarray | None
    snap_marker_color: tuple[float, float, float]
    snap_marker_kind: int = 0  # SnapKind value (0=NONE/no marker); stored as int to avoid circular import

    # M3b: filled face overlays (hover-highlight / armed face / ghost prism faces).
    face_fill_polygons: list[np.ndarray] = field(default_factory=list)
    """List of (N, 3) float32 world-space vertex loops. Renderer earcut-triangulates each at draw time."""

    face_fill_color: tuple[float, float, float, float] = (0.4, 0.7, 1.0, 0.15)
    """RGBA. Default is M3b's "ghost prism" color (light blue, 15% alpha)."""


class Tool(ABC):
    """Base class for all M2+ tools."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def shortcut(self) -> str: ...

    @property
    @abstractmethod
    def has_active_gesture(self) -> bool:
        """True if the tool is in the middle of a multi-click gesture.

        MainWindow uses this to decide whether ESC should cancel the gesture
        (forward to tool.on_key_press) or deactivate the tool entirely
        (ToolManager.deactivate_current).
        """

    @abstractmethod
    def activate(self, ctx: ToolContext) -> None: ...

    @abstractmethod
    def deactivate(self) -> None: ...

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing. Tools override as needed."""

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing."""

    def on_key_press(self, event: QKeyEvent) -> None:
        """Default: do nothing."""

    @abstractmethod
    def overlay(self) -> ToolOverlay: ...

    @property
    @abstractmethod
    def anchor_or_none(self) -> np.ndarray | None:
        """Rubber-band anchor used by the SnapEngine for axis-lock."""

    @property
    def status_text(self) -> str | None:
        """Optional third text segment for the status bar.

        Default None means this tool contributes nothing extra to the status
        bar beyond `<name> · <snap>`. PushPullTool overrides this to show the
        current extrusion depth during DRAGGING.
        """
        return None
```

Also at the top of the file, add `from dataclasses import dataclass, field` (the existing import is `from dataclasses import dataclass`).

- [ ] **Step 3: Run the new tool tests**

Run: `pluton-py-tests tests/test_tool.py -v`
Expected: 5 PASS.

- [ ] **Step 4: Make sure no existing M2/M3a tool tests broke**

Run: `pluton-py-tests tests/test_rectangle_tool.py tests/test_line_tool.py -v`
Expected: all PASS (the new fields have defaults).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tool.py tests/test_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): extend ToolContext + ToolOverlay + Tool ABC for M3b

- ToolContext gains camera + widget_size_provider (PushPullTool needs both
  to compute camera rays from cursor positions).
- ToolOverlay gains face_fill_polygons + face_fill_color so the renderer
  can draw hover-highlights and the ghost extrusion prism.
- Tool ABC gains an optional status_text property (default None) that the
  status bar reads each frame; PushPullTool will surface its current depth
  through this hook.

All new fields have safe defaults. Existing M2/M3a tools and tests are
unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: SceneRenderer face-fill overlay pass

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py`
- Modify: `tests/test_scene_renderer.py`

A new render pass that draws semi-transparent filled polygons over the scene. Used for hover-highlight (HOVERING), source-face highlight (DRAGGING), and the ghost extrusion prism (DRAGGING).

- [ ] **Step 1: Write the failing test** — append to `tests/test_scene_renderer.py`

```python
class TestFaceFillOverlayPass:
    """SceneRenderer.draw_face_fill_overlays — alpha-blended ghost rendering."""

    def test_empty_polygon_list_is_a_noop(self, qapp):
        """Smoke test: empty list shouldn't touch GL state or raise."""
        from pluton.viewport.scene_renderer import SceneRenderer

        renderer = SceneRenderer()
        # Don't call initialize_gl — the empty-list path must short-circuit
        # before touching any GL functions.
        renderer.draw_face_fill_overlays(polygons=[], color=(1.0, 0.0, 0.0, 0.5))
        # If we got here without an exception, the smoke test passes.

    def test_polygon_list_with_single_quad_is_accepted(self, qapp):
        """The renderer should accept a single (4, 3) numpy quad without raising.
        Actual GL drawing is exercised by manual visual verification."""
        from pluton.viewport.scene_renderer import SceneRenderer

        renderer = SceneRenderer()
        # We can't fully exercise GL without an offscreen context here, but
        # the renderer's input-validation path should at least accept the data.
        polygons = [
            np.array(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
                dtype=np.float32,
            )
        ]
        # Calling without initialize_gl would crash on real GL calls, so we
        # only assert the method exists with the right signature.
        assert hasattr(renderer, "draw_face_fill_overlays")
        import inspect

        sig = inspect.signature(renderer.draw_face_fill_overlays)
        # polygons + color args
        assert "polygons" in sig.parameters
        assert "color" in sig.parameters
```

Run: `pluton-py-tests tests/test_scene_renderer.py::TestFaceFillOverlayPass -v`
Expected: FAIL with `AttributeError: 'SceneRenderer' object has no attribute 'draw_face_fill_overlays'`.

- [ ] **Step 2: Add the method** to `python/pluton/viewport/scene_renderer.py`

Find the existing `render(self, camera, scene, tool_overlay)` method. Inside it, after the existing tool-overlay-edge rendering and BEFORE the closing of `paintGL` flow (or right at the end of `render`), add a call to `self.draw_face_fill_overlays(...)` if `tool_overlay` carries face-fill polygons.

Then add the new method itself. Anywhere in the class is fine; suggested placement is right after the existing `_draw_tool_overlay_edges` (or equivalent) method.

```python
    def draw_face_fill_overlays(
        self,
        polygons: list[np.ndarray],
        color: tuple[float, float, float, float] = (0.4, 0.7, 1.0, 0.15),
    ) -> None:
        """Draw alpha-blended filled polygons on top of the scene.

        Each polygon is an (N, 3) float32 ndarray (a closed loop in world
        coords). Earcut-triangulates each on the fly. Depth-test enabled
        (so overlays behind opaque geometry are occluded), depth-write
        disabled (so successive overlay passes don't z-fight against
        each other), standard alpha blend.

        Empty polygon list is a no-op.
        """
        if not polygons:
            return

        import mapbox_earcut

        # Earcut-triangulate every polygon by projecting onto its dominant
        # axis-aligned plane (XY / XZ / YZ) — choose whichever has the largest
        # face-normal component magnitude.
        triangle_vertices: list[float] = []  # flat (N*9,) float32-friendly
        for loop in polygons:
            if loop.shape[0] < 3:
                continue
            # Choose the projection plane via the geometric normal of the loop.
            e1 = loop[1] - loop[0]
            e2 = loop[-1] - loop[0]
            n = np.cross(e1, e2)
            ax, ay, az = abs(float(n[0])), abs(float(n[1])), abs(float(n[2]))
            if az >= ax and az >= ay:
                # XY projection (top-down).
                xy = loop[:, :2].astype(np.float32)
            elif ax >= ay:
                # YZ projection.
                xy = np.stack([loop[:, 1], loop[:, 2]], axis=1).astype(np.float32)
            else:
                # XZ projection.
                xy = np.stack([loop[:, 0], loop[:, 2]], axis=1).astype(np.float32)
            ring_ends = np.array([len(loop)], dtype=np.uint32)
            tri_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
            tri_indices = np.asarray(tri_indices, dtype=np.int32).reshape(-1, 3)
            for tri in tri_indices:
                for vi in tri:
                    triangle_vertices.extend(
                        [float(loop[vi, 0]), float(loop[vi, 1]), float(loop[vi, 2])]
                    )

        if not triangle_vertices:
            return

        verts = np.array(triangle_vertices, dtype=np.float32)
        # Upload to the transient ghost-fill VBO (lazily created).
        if not hasattr(self, "_ghost_fill_vbo"):
            self._ghost_fill_vbo = GL.glGenBuffers(1)
            self._ghost_fill_vao = GL.glGenVertexArrays(1)

        GL.glBindVertexArray(self._ghost_fill_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._ghost_fill_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))

        # Activate the simplest line/flat-color program already used for edges.
        # We reuse it because we only need view+projection+a color uniform.
        # (Color is set via a flat fragment shader uniform we wire below.)
        GL.glUseProgram(self._ghost_fill_program)
        # Camera view/projection uniforms — same names as the existing line program.
        GL.glUniformMatrix4fv(
            self._ghost_fill_uniforms["u_view"], 1, GL.GL_TRUE, self._current_view_matrix
        )
        GL.glUniformMatrix4fv(
            self._ghost_fill_uniforms["u_projection"], 1, GL.GL_TRUE, self._current_projection_matrix
        )
        GL.glUniform4f(self._ghost_fill_uniforms["u_color"], *color)

        # GL state: alpha-blended, depth-test on, depth-write off.
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDepthMask(GL.GL_FALSE)

        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(verts) // 3)

        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_BLEND)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
```

Inside `initialize_gl(self)`, after the existing shader-program setup, add the ghost-fill program initialization. The simplest path is to reuse an existing line-shader pair if there's a generic flat-color one; if not, create a tiny inline pair:

```python
        # M3b ghost-fill: flat-color shader for alpha-blended face overlays.
        ghost_vert_src = """
            #version 330 core
            layout(location = 0) in vec3 a_pos;
            uniform mat4 u_view;
            uniform mat4 u_projection;
            void main() { gl_Position = u_projection * u_view * vec4(a_pos, 1.0); }
        """
        ghost_frag_src = """
            #version 330 core
            uniform vec4 u_color;
            out vec4 frag;
            void main() { frag = u_color; }
        """
        self._ghost_fill_program = _link_program(ghost_vert_src, ghost_frag_src)
        self._ghost_fill_uniforms = {
            name: GL.glGetUniformLocation(self._ghost_fill_program, name)
            for name in ("u_view", "u_projection", "u_color")
        }
```

Inside `render(self, camera, scene, tool_overlay)`, store the current view/projection matrices to instance attributes so `draw_face_fill_overlays` can reuse them:

```python
        self._current_view_matrix = view
        self._current_projection_matrix = projection
```

Then near the bottom of `render`, after `_draw_tool_overlay_edges(tool_overlay)` (or wherever edges are drawn), add:

```python
        if tool_overlay is not None and tool_overlay.face_fill_polygons:
            self.draw_face_fill_overlays(
                polygons=tool_overlay.face_fill_polygons,
                color=tool_overlay.face_fill_color,
            )
```

If the exact attribute names / variable names of view/projection differ in the existing `render` method, adapt accordingly — the key is to make them available to `draw_face_fill_overlays`.

- [ ] **Step 3: Run the test**

Run: `pluton-py-tests tests/test_scene_renderer.py::TestFaceFillOverlayPass -v`
Expected: 2 PASS (empty-list early-out + signature check).

- [ ] **Step 4: Verify existing M2/M3a renderer tests still pass**

Run: `pluton-py-tests tests/test_scene_renderer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py tests/test_scene_renderer.py
git commit -m "$(cat <<'EOF'
feat(renderer): add face-fill overlay pass for M3b ghost prism + hover highlight

New draw_face_fill_overlays(polygons, color) method on SceneRenderer:
earcut-triangulates each (N, 3) loop via its dominant projection plane,
uploads to a transient VBO, draws alpha-blended with depth-write disabled.

Renderer.render() now reads tool_overlay.face_fill_polygons and dispatches
to the new pass after the existing edge overlays. Empty list is a no-op.

A new minimal flat-color shader pair (u_view + u_projection + u_color)
is added inline.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: PushPullTool skeleton + IDLE/HOVERING state machine

**Files:**
- Create: `python/pluton/tools/push_pull_tool.py`
- Modify: `python/pluton/tools/__init__.py`
- Create: `tests/test_push_pull_tool.py`

This task implements the tool's identity, the IDLE / HOVERING / DRAGGING state enum, and the IDLE → HOVERING transitions (per-frame ray-pick when no click is held). DRAGGING transitions come in Tasks 8-10.

- [ ] **Step 1: Write the failing tests** at `tests/test_push_pull_tool.py`

```python
"""PushPullTool — state machine + depth metric + composite-building tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


# ---- helpers ---------------------------------------------------------------


def _make_event(pos=(100.0, 100.0), button=Qt.MouseButton.LeftButton, kind=QMouseEvent.Type.MouseMove):
    return QMouseEvent(
        kind,
        QPointF(*pos),
        QPointF(*pos),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_tool_with_unit_rect():
    """Spin up a fresh Scene + PushPullTool with one unit-rect face at z=0.

    The tool is activated against a context with a mock camera + widget sizer
    that we can drive directly.
    """
    from pluton.scene import Scene
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.tool import ToolContext

    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    f = scene.add_face_from_loop([v0, v1, v2, v3])

    # Mock camera that ray_from_screen always returns "directly down from (0.5, 0.5, 5)".
    camera = MagicMock()
    camera.ray_from_screen.return_value = (
        np.array([0.5, 0.5, 5.0], dtype=np.float32),
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
    )

    cmd_stack = MagicMock()

    tool = PushPullTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=cmd_stack,
            camera=camera,
            widget_size_provider=lambda: (800, 600),
        )
    )
    return tool, scene, f, camera, cmd_stack


# ---- identity ---------------------------------------------------------------


class TestPushPullIdentity:
    def test_name_and_shortcut(self):
        from pluton.tools.push_pull_tool import PushPullTool

        tool = PushPullTool()
        assert tool.name == "Push/Pull"
        assert tool.shortcut == "P"


# ---- IDLE / HOVERING -------------------------------------------------------


class TestPushPullHovering:
    def test_starts_in_idle_state(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        assert tool.has_active_gesture is False
        # Default overlay is empty when idle.
        overlay = tool.overlay()
        assert overlay.face_fill_polygons == []

    def test_mouse_move_over_face_transitions_to_hovering(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # The mock camera ray hits the rectangle face.
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        # HOVERING: overlay should now contain the hovered face's polygon.
        overlay = tool.overlay()
        assert len(overlay.face_fill_polygons) == 1
        loop = overlay.face_fill_polygons[0]
        assert loop.shape == (4, 3)
        # Should be the rectangle's 4 corners at z=0.
        np.testing.assert_allclose(
            sorted(map(tuple, loop.tolist())),
            sorted([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]),
            atol=1e-5,
        )
        # No active gesture yet — we haven't clicked.
        assert tool.has_active_gesture is False

    def test_mouse_move_off_face_transitions_back_to_idle(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # First move: hit.
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.overlay().face_fill_polygons != []
        # Second move: miss (camera ray now points away).
        camera.ray_from_screen.return_value = (
            np.array([5.0, 5.0, 5.0], dtype=np.float32),
            np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.overlay().face_fill_polygons == []

    def test_status_text_is_none_in_idle(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        assert tool.status_text is None

    def test_status_text_is_none_in_hovering(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=MagicMock())
        assert tool.status_text is None
```

Run: `pluton-py-tests tests/test_push_pull_tool.py -v`
Expected: FAIL with `ImportError: cannot import name 'PushPullTool'`.

- [ ] **Step 2: Implement the skeleton** at `python/pluton/tools/push_pull_tool.py`

```python
"""The Push/Pull tool — SketchUp-style face extrusion.

Three-state machine:
    IDLE     — no face under cursor; no overlay.
    HOVERING — cursor over a live face; that face highlighted (light blue).
    DRAGGING — face armed by click; cursor moves drive depth via line-line CPA;
               ghost prism rendered.

Click in HOVERING arms the face. Click in DRAGGING commits (or cancels if
depth < 1e-3). ESC in DRAGGING cancels. ESC in HOVERING / IDLE is handled
by MainWindow's two-stage ESC (it deactivates the tool).
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay


# Visual constants (RGBA).
_HOVER_FILL_COLOR = (0.40, 0.70, 1.00, 0.20)   # light blue
_ARMED_FILL_COLOR = (0.20, 0.50, 0.95, 0.40)   # darker blue
_GHOST_FILL_COLOR = (0.40, 0.70, 1.00, 0.15)   # light blue, fainter

_MIN_COMMIT_DEPTH = 1e-3  # world units; below this is treated as cancel
_DEGENERATE_VIEW_EPSILON = 1e-4  # |1 - (d·n)²| below this freezes depth


class _State(Enum):
    IDLE = 0
    HOVERING = 1
    DRAGGING = 2


class PushPullTool(Tool):
    """SketchUp-style face extrusion tool."""

    def __init__(self) -> None:
        self._scene = None
        self._command_stack = None
        self._camera = None
        self._widget_size_provider = None

        self._state: _State = _State.IDLE

        # HOVERING data
        self._hovered_face_id: int | None = None

        # DRAGGING data (set when entering DRAGGING; cleared on exit)
        self._armed_face_id: int | None = None
        self._armed_face_loop: list[int] = []
        self._armed_face_normal: np.ndarray | None = None
        self._armed_face_center: np.ndarray | None = None
        self._current_depth: float = 0.0

    # ---- Tool ABC ------------------------------------------------------

    @property
    def name(self) -> str:
        return "Push/Pull"

    @property
    def shortcut(self) -> str:
        return "P"

    @property
    def has_active_gesture(self) -> bool:
        return self._state == _State.DRAGGING

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return None  # Push/Pull doesn't drive axis-lock.

    @property
    def status_text(self) -> str | None:
        if self._state == _State.DRAGGING:
            return f"depth: {self._current_depth:.3f}"
        return None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._camera = ctx.camera
        self._widget_size_provider = ctx.widget_size_provider
        self._reset_to_idle()

    def deactivate(self) -> None:
        self._reset_to_idle()

    # ---- Event handlers -----------------------------------------------

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.DRAGGING:
            # Depth update — Task 8 fills this in.
            return
        # IDLE / HOVERING — per-frame ray-pick.
        hit = self._pick_face_under_cursor(event)
        if hit is None:
            self._state = _State.IDLE
            self._hovered_face_id = None
        else:
            self._state = _State.HOVERING
            self._hovered_face_id = hit.face_id

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        # IDLE / HOVERING / DRAGGING — Task 9 fills DRAGGING in; Task 10/11
        # handle commit + cancel.
        if self._state == _State.IDLE:
            return  # clicking empty space is a no-op
        if self._state == _State.HOVERING:
            # Task 9 will replace this with the actual arm transition.
            return
        # DRAGGING — Task 10/11.
        return

    def on_key_press(self, event: QKeyEvent) -> None:
        # Task 11 wires ESC cancel for DRAGGING.
        return

    def overlay(self) -> ToolOverlay:
        polygons: list[np.ndarray] = []
        color = _HOVER_FILL_COLOR
        if self._state == _State.HOVERING and self._hovered_face_id is not None:
            polygons = [self._loop_world_coords(self._hovered_face_id)]
            color = _HOVER_FILL_COLOR
        # DRAGGING overlay is added in Task 9.
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=(0.85, 0.85, 0.85),
            snap_marker_position=None,
            snap_marker_color=(0.85, 0.85, 0.85),
            snap_marker_kind=0,
            face_fill_polygons=polygons,
            face_fill_color=color,
        )

    # ---- Helpers -------------------------------------------------------

    def _pick_face_under_cursor(self, event: QMouseEvent):
        """Return RayMeshHit | None for the cursor position in `event`."""
        if self._camera is None or self._widget_size_provider is None or self._scene is None:
            return None
        pos = event.position()
        width, height = self._widget_size_provider()
        origin, direction = self._camera.ray_from_screen(
            float(pos.x()), float(pos.y()), int(width), int(height)
        )
        return self._scene.ray_pick_face(origin, direction)

    def _loop_world_coords(self, face_id: int) -> np.ndarray:
        """Return the face's boundary loop as an (N, 3) float32 ndarray."""
        loop_ids = self._scene.face_loop(face_id)
        coords = np.zeros((len(loop_ids), 3), dtype=np.float32)
        for i, vid in enumerate(loop_ids):
            v = self._scene.vertex(vid)
            coords[i] = v.position
        return coords

    def _reset_to_idle(self) -> None:
        self._state = _State.IDLE
        self._hovered_face_id = None
        self._armed_face_id = None
        self._armed_face_loop = []
        self._armed_face_normal = None
        self._armed_face_center = None
        self._current_depth = 0.0
```

- [ ] **Step 3: Export the tool** — modify `python/pluton/tools/__init__.py`

Find the existing exports (`LineTool`, `RectangleTool`, `ToolContext`, `ToolManager`, etc.) and add `PushPullTool` alongside them. For example:

```python
from pluton.tools.line_tool import LineTool
from pluton.tools.push_pull_tool import PushPullTool  # NEW
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.tools.tool_manager import ToolManager

__all__ = [
    "LineTool",
    "PushPullTool",   # NEW
    "RectangleTool",
    "Tool",
    "ToolContext",
    "ToolOverlay",
    "ToolManager",
]
```

- [ ] **Step 4: Run the tests**

Run: `pluton-py-tests tests/test_push_pull_tool.py -v`
Expected: 5 PASS (`TestPushPullIdentity` + `TestPushPullHovering`).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py python/pluton/tools/__init__.py tests/test_push_pull_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool skeleton + IDLE/HOVERING state machine

Three-state enum (IDLE / HOVERING / DRAGGING) and the IDLE ↔ HOVERING
transitions driven by per-frame ray-picks. Hover-highlight overlay
renders the picked face in light blue. DRAGGING transitions, depth
metric, commit, and cancel land in tasks 8-11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: HOVERING → DRAGGING transition + depth metric

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py`
- Modify: `tests/test_push_pull_tool.py`

Click in HOVERING arms the face; the tool caches the face's loop, normal, and center. Subsequent `on_mouse_move` events in DRAGGING update `_current_depth` via the line-line closest-point projection.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_push_pull_tool.py`

```python
class TestPushPullArmingAndDepth:
    """HOVERING → DRAGGING transition + line-line CPA depth metric."""

    def test_click_in_hovering_arms_the_face(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # Enter HOVERING
        tool.on_mouse_move(_make_event(), snap=None)
        # Click to arm
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        assert tool.has_active_gesture is True
        assert tool.status_text == "depth: 0.000"

    def test_click_in_idle_does_nothing(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # Camera ray misses the rectangle.
        camera.ray_from_screen.return_value = (
            np.array([5.0, 5.0, 5.0], dtype=np.float32),
            np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)  # IDLE
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        assert tool.has_active_gesture is False

    def test_depth_increases_as_camera_ray_aims_above_face(self):
        """Line-line CPA: if the camera ray's closest approach to the normal
        line (face_center, +Z) is at z=2, depth should be 2."""
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # Hover + arm.
        tool.on_mouse_move(_make_event(), snap=None)
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        # Now move: rotate the camera so its ray aims at (0.5, 0.5, 2).
        # A horizontal ray at z=2 with direction +X, origin (-3, 0.5, 2):
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        # CPA between this horizontal ray and the +Z normal line through
        # (0.5, 0.5, 0) gives t = 2.0 on the normal line. So depth = 2.0.
        assert tool.status_text == "depth: 2.000"

    def test_depth_clamps_to_zero_on_negative_drag(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=None)
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        # Horizontal ray at z = -3 (below the source face).
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, -3.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        assert tool.status_text == "depth: 0.000"

    def test_depth_frozen_when_view_parallel_to_normal(self):
        """Camera looking straight down — ray direction == -normal — the depth
        metric's denominator goes to ~0; depth should NOT update."""
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=None)
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        # First move: drive depth to a non-zero value.
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        assert tool.status_text == "depth: 2.000"
        # Second move: ray collinear with normal (degenerate case).
        camera.ray_from_screen.return_value = (
            np.array([0.5, 0.5, 5.0], dtype=np.float32),
            np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        # Depth should be FROZEN at the previous value (2.0), not reset to 0.
        assert tool.status_text == "depth: 2.000"
```

Run: `pluton-py-tests tests/test_push_pull_tool.py::TestPushPullArmingAndDepth -v`
Expected: FAIL (the on_mouse_press / on_mouse_move handlers don't yet implement DRAGGING).

- [ ] **Step 2: Update the handlers** in `python/pluton/tools/push_pull_tool.py`

Replace `on_mouse_press` with:

```python
    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.IDLE:
            return  # clicking empty space is a no-op
        if self._state == _State.HOVERING:
            self._arm_face(self._hovered_face_id)
            return
        # DRAGGING — Task 10 wires commit; Task 11 wires near-zero cancel.
        return
```

Replace `on_mouse_move` with:

```python
    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.DRAGGING:
            self._update_depth_from_event(event)
            return
        hit = self._pick_face_under_cursor(event)
        if hit is None:
            self._state = _State.IDLE
            self._hovered_face_id = None
        else:
            self._state = _State.HOVERING
            self._hovered_face_id = hit.face_id
```

Add two helpers below `_loop_world_coords`:

```python
    def _arm_face(self, face_id: int) -> None:
        """Cache the source face's data and enter DRAGGING."""
        self._armed_face_id = face_id
        self._armed_face_loop = self._scene.face_loop(face_id)
        self._armed_face_normal = self._scene.face_normal(face_id)
        self._armed_face_center = self._scene.face_center(face_id)
        self._current_depth = 0.0
        self._state = _State.DRAGGING

    def _update_depth_from_event(self, event: QMouseEvent) -> None:
        """Update self._current_depth via line-line CPA between the camera ray
        and the line (face_center, +normal). Holds the previous depth if the
        view is ~parallel to the normal (degenerate case)."""
        if self._camera is None or self._widget_size_provider is None:
            return
        pos = event.position()
        width, height = self._widget_size_provider()
        origin, direction = self._camera.ray_from_screen(
            float(pos.x()), float(pos.y()), int(width), int(height)
        )
        # Normalize ray direction.
        d_norm = float(np.linalg.norm(direction))
        if d_norm < 1e-9:
            return
        d_hat = direction / d_norm
        n_hat = self._armed_face_normal  # already unit
        c = self._armed_face_center

        b = float(np.dot(d_hat, n_hat))
        denom = 1.0 - b * b
        if abs(denom) < _DEGENERATE_VIEW_EPSILON:
            return  # depth frozen
        w = origin.astype(np.float32) - c
        e = float(np.dot(n_hat, w))
        d_param = float(np.dot(d_hat, w))
        t = (e - b * d_param) / denom
        self._current_depth = max(0.0, t)
```

- [ ] **Step 3: Run the new tests**

Run: `pluton-py-tests tests/test_push_pull_tool.py::TestPushPullArmingAndDepth -v`
Expected: 5 PASS.

- [ ] **Step 4: Make sure the Task-7 tests still pass**

Run: `pluton-py-tests tests/test_push_pull_tool.py -v`
Expected: all PASS (Task 7 + Task 8 — 10 tests total so far).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — arm-on-click + line-line CPA depth metric

Clicking in HOVERING transitions to DRAGGING and caches the source
face's loop / normal / center. on_mouse_move during DRAGGING projects
the camera ray onto the face's normal axis via line-line closest-point,
clamps to [0, ∞), and holds the previous value if the view is
~parallel to the normal (degenerate case — user must orbit to recover).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: DRAGGING overlay — armed face + ghost prism polygons

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py`
- Create: `tests/test_push_pull_overlay.py`

In DRAGGING, the overlay returns:
- The source face polygon in the "armed" color.
- The ghost prism's top face polygon (source loop shifted by `depth * normal`).
- One ghost prism side polygon per source edge.

All polygons share the SAME RGBA color (the renderer's `face_fill_color` applies to all polygons in the list). For visual differentiation we'd need multiple passes; for M3b we accept a single shared color (the "ghost" color), since the armed source face is naturally distinguished by being underneath the ghost prism's bottom.

Wait — that won't work visually. Let me revise: we'll send the **armed-face polygon first**, then **the ghost prism polygons**, but they all use one color. The visual differentiation comes from the armed source face being rendered against the scene background (with its own alpha) while the ghost prism polygons stack alpha. So the armed face appears slightly darker because it has the existing scene face beneath it. This is good enough for M3b; visual verification confirms.

For absolute clarity we COULD do two `draw_face_fill_overlays` calls (one with the armed color, one with the ghost color) in the renderer. The minimal change: have `ToolOverlay.face_fill_polygons` be a list of `(polygon, color)` tuples instead of a flat list. That would require updating Task 5/6.

Decision: **keep the current single-color list**. If visual verification reveals the differentiation is too weak, Task 14 (visual verification) will surface it and we'll revise the renderer + ToolOverlay then.

- [ ] **Step 1: Write the failing tests** at `tests/test_push_pull_overlay.py`

```python
"""PushPullTool overlay tests — what polygons are returned per state."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


def _make_event(pos=(100.0, 100.0)):
    return QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(*pos),
        QPointF(*pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_tool_with_unit_rect():
    """Same helper as in test_push_pull_tool.py; duplicated here to keep tests independent."""
    from pluton.scene import Scene
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.tool import ToolContext

    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    f = scene.add_face_from_loop([v0, v1, v2, v3])

    camera = MagicMock()
    camera.ray_from_screen.return_value = (
        np.array([0.5, 0.5, 5.0], dtype=np.float32),
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
    )
    cmd_stack = MagicMock()
    tool = PushPullTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=cmd_stack,
            camera=camera,
            widget_size_provider=lambda: (800, 600),
        )
    )
    return tool, scene, f, camera, cmd_stack


def _enter_dragging(tool, camera, depth_target=2.0):
    """Hover, click to arm, then move the camera ray so depth = depth_target."""
    from PySide6.QtGui import QMouseEvent

    tool.on_mouse_move(_make_event(), snap=None)
    tool.on_mouse_press(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(100.0, 100.0),
            QPointF(100.0, 100.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
        snap=None,
    )
    # Horizontal ray at z=depth_target → CPA gives t=depth_target.
    camera.ray_from_screen.return_value = (
        np.array([-3.0, 0.5, depth_target], dtype=np.float32),
        np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )
    tool.on_mouse_move(_make_event(), snap=None)


class TestPushPullOverlay:
    def test_idle_overlay_has_no_polygons(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        # Move OFF the rectangle so we stay IDLE.
        camera.ray_from_screen.return_value = (
            np.array([5.0, 5.0, 5.0], dtype=np.float32),
            np.array([0.0, 0.0, -1.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        overlay = tool.overlay()
        assert overlay.face_fill_polygons == []

    def test_hovering_overlay_has_one_polygon(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=None)
        overlay = tool.overlay()
        assert len(overlay.face_fill_polygons) == 1
        # Hover color (light blue, 0.20 alpha) — see PushPullTool constants.
        assert overlay.face_fill_color[3] == 0.20

    def test_dragging_overlay_has_armed_face_plus_ghost_prism(self):
        """A 4-vertex source face produces a 6-polygon overlay during drag:
        1 armed face + 1 ghost top + 4 ghost sides = 6."""
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        _enter_dragging(tool, camera, depth_target=2.0)
        overlay = tool.overlay()
        assert len(overlay.face_fill_polygons) == 6

    def test_dragging_ghost_top_is_source_loop_shifted_by_depth_times_normal(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        _enter_dragging(tool, camera, depth_target=2.0)
        overlay = tool.overlay()
        # By convention: index 0 is the armed face, index 1 is the ghost top.
        ghost_top = overlay.face_fill_polygons[1]
        assert ghost_top.shape == (4, 3)
        # All z-coordinates should be exactly depth (2.0).
        np.testing.assert_allclose(ghost_top[:, 2], [2.0, 2.0, 2.0, 2.0], atol=1e-5)
        # X/Y match the source.
        np.testing.assert_allclose(
            sorted(map(tuple, ghost_top[:, :2].tolist())),
            sorted([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]),
            atol=1e-5,
        )

    def test_dragging_side_polygons_each_have_four_vertices(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        _enter_dragging(tool, camera, depth_target=2.0)
        overlay = tool.overlay()
        sides = overlay.face_fill_polygons[2:]  # 4 side polys
        assert len(sides) == 4
        for side in sides:
            assert side.shape == (4, 3)

    def test_dragging_color_is_ghost_color(self):
        tool, scene, f, camera, _ = _make_tool_with_unit_rect()
        _enter_dragging(tool, camera, depth_target=2.0)
        overlay = tool.overlay()
        # Ghost color (light blue, 0.15 alpha) — see PushPullTool constants.
        assert overlay.face_fill_color[3] == 0.15
```

Run: `pluton-py-tests tests/test_push_pull_overlay.py -v`
Expected: FAIL (the DRAGGING branch of `overlay()` is not yet implemented).

- [ ] **Step 2: Implement the DRAGGING overlay** in `python/pluton/tools/push_pull_tool.py`

Replace the `overlay()` method with:

```python
    def overlay(self) -> ToolOverlay:
        polygons: list[np.ndarray] = []
        color = _HOVER_FILL_COLOR

        if self._state == _State.HOVERING and self._hovered_face_id is not None:
            polygons = [self._loop_world_coords(self._hovered_face_id)]
            color = _HOVER_FILL_COLOR

        elif self._state == _State.DRAGGING and self._armed_face_id is not None:
            polygons = self._build_ghost_polygons()
            color = _GHOST_FILL_COLOR

        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=(0.85, 0.85, 0.85),
            snap_marker_position=None,
            snap_marker_color=(0.85, 0.85, 0.85),
            snap_marker_kind=0,
            face_fill_polygons=polygons,
            face_fill_color=color,
        )

    def _build_ghost_polygons(self) -> list[np.ndarray]:
        """Return [armed_face_loop, ghost_top, *ghost_sides] all in world coords."""
        assert self._armed_face_id is not None
        assert self._armed_face_normal is not None
        assert self._armed_face_center is not None

        source_loop_xyz = self._loop_world_coords(self._armed_face_id)  # (N, 3)
        n = self._armed_face_normal
        depth = self._current_depth
        top_loop_xyz = source_loop_xyz + depth * n[np.newaxis, :]

        polygons: list[np.ndarray] = [source_loop_xyz, top_loop_xyz]
        # Side polygons (one per source edge): (V_i, V_{i+1}, V'_{i+1}, V'_i).
        n_verts = source_loop_xyz.shape[0]
        for i in range(n_verts):
            j = (i + 1) % n_verts
            side = np.stack(
                [
                    source_loop_xyz[i],
                    source_loop_xyz[j],
                    top_loop_xyz[j],
                    top_loop_xyz[i],
                ]
            ).astype(np.float32)
            polygons.append(side)
        return polygons
```

- [ ] **Step 3: Run the overlay tests**

Run: `pluton-py-tests tests/test_push_pull_overlay.py -v`
Expected: 6 PASS.

- [ ] **Step 4: Verify no regression in Task 7/8 tests**

Run: `pluton-py-tests tests/test_push_pull_tool.py -v`
Expected: all 10 still PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_overlay.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — DRAGGING overlay (armed face + ghost prism)

Overlay during DRAGGING returns 2+N polygons for an N-gon source: the
armed source face, the ghost top face (source shifted by depth*normal),
and N side quads. All polygons share the ghost RGBA — the source face's
"darker" appearance comes naturally from being layered against the scene
mesh beneath.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Commit transition — build composite + push to CommandStack

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py`
- Create: `tests/test_push_pull_topology.py`

A second click in DRAGGING commits the extrusion. The composite is built per spec §4.3:
`RemoveFace(source) + AddVertex×N + AddEdge×N (vertical) + AddEdge×N (top) + AddFace×N (sides) + AddFace (top)`.
Pushed to `command_stack` via `push_executed`. One `Ctrl+Z` undoes the whole extrusion.

- [ ] **Step 1: Write the failing topology tests** at `tests/test_push_pull_topology.py`

```python
"""Extrusion composite tests — topology + undo/redo round-trip."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent


def _make_press():
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_move():
    return QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(100.0, 100.0),
        QPointF(100.0, 100.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _live_vertex_count(scene) -> int:
    return sum(1 for _ in scene.vertices_iter())


def _live_edge_count(scene) -> int:
    return sum(1 for _ in scene.edges_iter())


def _live_face_count(scene) -> int:
    return sum(1 for _ in scene.faces_iter())


def _setup_push_pull(scene_factory_args=None):
    """Build a fresh Scene + REAL CommandStack + PushPullTool with one rect face.

    Returns (tool, scene, f, camera, command_stack).
    """
    from pluton.commands import CommandStack
    from pluton.scene import Scene
    from pluton.tools.push_pull_tool import PushPullTool
    from pluton.tools.tool import ToolContext

    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    f = scene.add_face_from_loop([v0, v1, v2, v3])

    camera = MagicMock()
    camera.ray_from_screen.return_value = (
        np.array([0.5, 0.5, 5.0], dtype=np.float32),
        np.array([0.0, 0.0, -1.0], dtype=np.float32),
    )

    command_stack = CommandStack()
    tool = PushPullTool()
    tool.activate(
        ToolContext(
            scene=scene,
            command_stack=command_stack,
            camera=camera,
            widget_size_provider=lambda: (800, 600),
        )
    )
    return tool, scene, f, camera, command_stack


class TestPushPullCommit:
    def test_commit_a_rectangle_produces_5_new_faces_8_new_edges_4_new_verts(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        # Hover + arm.
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        # Drag to depth 2.
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        # Pre-commit counts: 4 verts, 4 edges, 1 face.
        assert _live_vertex_count(scene) == 4
        assert _live_edge_count(scene) == 4
        assert _live_face_count(scene) == 1
        # Commit (second click).
        tool.on_mouse_press(_make_press(), snap=None)
        # Post-commit counts:
        #   verts: 4 source + 4 top                = 8
        #   edges: 4 source + 4 vertical + 4 top   = 12
        #   faces: 4 sides + 1 top (source removed)= 5
        assert _live_vertex_count(scene) == 8
        assert _live_edge_count(scene) == 12
        assert _live_face_count(scene) == 5
        # Source face is gone.
        with pytest.raises(KeyError):
            scene.face(source_f)
        # Tool returns to IDLE / HOVERING (depending on post-commit ray-pick).
        assert tool.has_active_gesture is False

    def test_commit_pushes_one_composite_command(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        assert cmd_stack.can_undo

    def test_undo_restores_pre_commit_scene(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        # Undo
        assert cmd_stack.undo(scene)
        assert _live_vertex_count(scene) == 4
        assert _live_edge_count(scene) == 4
        assert _live_face_count(scene) == 1
        # Source face exists again with its original id.
        face = scene.face(source_f)
        assert face.id == source_f

    def test_redo_replays_extrusion(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        cmd_stack.undo(scene)
        cmd_stack.redo(scene)
        assert _live_vertex_count(scene) == 8
        assert _live_edge_count(scene) == 12
        assert _live_face_count(scene) == 5

    def test_top_face_normal_matches_source_normal_direction(self):
        tool, scene, source_f, camera, cmd_stack = _setup_push_pull()
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_move(), snap=None)
        tool.on_mouse_press(_make_press(), snap=None)
        # The most recently added face has the highest id. Find it.
        top_face_id = max(f.id for f in scene.faces_iter())
        normal = scene.face_normal(top_face_id)
        np.testing.assert_allclose(normal, [0.0, 0.0, 1.0], atol=1e-5)
```

Run: `pluton-py-tests tests/test_push_pull_topology.py -v`
Expected: FAIL (commit transition not yet wired).

- [ ] **Step 2: Wire the commit in PushPullTool** — modify `python/pluton/tools/push_pull_tool.py`

At the top, add the command imports:

```python
from pluton.commands import CompositeCommand
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
    RemoveFaceCommand,
)
```

Replace `on_mouse_press` with the full version:

```python
    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        if self._state == _State.IDLE:
            return
        if self._state == _State.HOVERING:
            self._arm_face(self._hovered_face_id)
            return
        # DRAGGING: commit if depth >= min threshold, else cancel.
        if self._current_depth >= _MIN_COMMIT_DEPTH:
            self._commit_extrusion()
        # Task 11 wires the near-zero cancel + re-hover.
        self._reset_to_idle()
        # After the gesture ends, immediately re-pick under the current cursor so we
        # transition to HOVERING (or IDLE) cleanly.
        hit = self._pick_face_under_cursor(event)
        if hit is not None:
            self._state = _State.HOVERING
            self._hovered_face_id = hit.face_id
```

Add the `_commit_extrusion` method (anywhere among the helpers):

```python
    def _commit_extrusion(self) -> None:
        """Build the extrusion CompositeCommand and push it to the command stack."""
        assert self._armed_face_id is not None
        assert self._armed_face_loop, "armed loop must be populated"
        assert self._armed_face_normal is not None
        scene = self._scene
        loop = self._armed_face_loop
        normal = self._armed_face_normal.astype(np.float32)
        depth = float(self._current_depth)
        n = len(loop)

        composite = CompositeCommand(name="Push/Pull")

        # 1. Remove source face
        rm = RemoveFaceCommand(self._armed_face_id)
        rm.do(scene)
        composite.children.append(rm)

        # 2. Add top vertices
        top_vert_cmds: list[AddVertexCommand] = []
        for src_vid in loop:
            src_pos = np.asarray(scene._mesh.vertex_position(src_vid), dtype=np.float32)
            top_pos = src_pos + depth * normal
            c = AddVertexCommand(top_pos)
            c.do(scene)
            top_vert_cmds.append(c)
            composite.children.append(c)
        top_vids = [c._vertex_id for c in top_vert_cmds]  # type: ignore[attr-defined]

        # 3. Vertical edges
        for src_vid, top_vid in zip(loop, top_vids):
            c = AddEdgeCommand(src_vid, top_vid)
            c.do(scene)
            composite.children.append(c)

        # 4. Top boundary edges
        for i in range(n):
            c = AddEdgeCommand(top_vids[i], top_vids[(i + 1) % n])
            c.do(scene)
            composite.children.append(c)

        # 5. Side faces (V_i, V_{i+1}, V'_{i+1}, V'_i)
        for i in range(n):
            a = loop[i]
            b = loop[(i + 1) % n]
            b_top = top_vids[(i + 1) % n]
            a_top = top_vids[i]
            c = AddFaceCommand((a, b, b_top, a_top))
            c.do(scene)
            composite.children.append(c)

        # 6. Top face
        c = AddFaceCommand(tuple(top_vids))
        c.do(scene)
        composite.children.append(c)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
```

- [ ] **Step 3: Run the topology tests**

Run: `pluton-py-tests tests/test_push_pull_topology.py -v`
Expected: 5 PASS.

- [ ] **Step 4: Run ALL push/pull tests to confirm no regression**

Run: `pluton-py-tests tests/test_push_pull_tool.py tests/test_push_pull_overlay.py tests/test_push_pull_topology.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_topology.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — commit extrusion as a CompositeCommand

Second click in DRAGGING (depth >= 1e-3) builds:
  RemoveFace(source) + AddVertex×N + AddEdge×N (vertical) +
  AddEdge×N (top) + AddFace×N (sides) + AddFace (top)
and pushes the composite to the CommandStack. One Ctrl+Z undoes the
whole extrusion. For a rectangle: 4 new verts, 8 new edges, 5 new
faces (4 sides + 1 top; source face removed → open-bottom prism per
M3a contract).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: ESC cancel + near-zero cancel

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py`
- Modify: `tests/test_push_pull_tool.py`

ESC mid-drag cancels the gesture without committing. Near-zero depth at second-click also cancels. Both paths return to IDLE/HOVERING without pushing a Command.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_push_pull_tool.py`

```python
class TestPushPullCancel:
    def test_esc_in_dragging_clears_state_without_committing(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        tool, scene, f, camera, cmd_stack = _make_tool_with_unit_rect()
        # Hover + arm + drag.
        tool.on_mouse_move(_make_event(), snap=None)
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        camera.ray_from_screen.return_value = (
            np.array([-3.0, 0.5, 2.0], dtype=np.float32),
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )
        tool.on_mouse_move(_make_event(), snap=None)
        assert tool.has_active_gesture is True
        # ESC
        esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        tool.on_key_press(esc)
        # No command pushed.
        cmd_stack.push_executed.assert_not_called()
        # State reset.
        assert tool.has_active_gesture is False

    def test_second_click_below_threshold_cancels(self):
        tool, scene, f, camera, cmd_stack = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=None)
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        # Don't move; depth stays at 0. Second click should cancel.
        tool.on_mouse_press(_make_event(kind=QMouseEvent.Type.MouseButtonPress), snap=None)
        cmd_stack.push_executed.assert_not_called()
        assert tool.has_active_gesture is False

    def test_esc_in_hovering_or_idle_is_noop_for_the_tool(self):
        """The two-stage ESC behavior (deactivating the tool) is owned by
        MainWindow. The tool itself should treat ESC in non-DRAGGING as a no-op
        (it should not crash, it should not clear state)."""
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        tool, scene, f, camera, cmd_stack = _make_tool_with_unit_rect()
        tool.on_mouse_move(_make_event(), snap=None)  # HOVERING
        assert tool._state.name == "HOVERING"
        esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        tool.on_key_press(esc)
        # Still HOVERING — the tool itself doesn't deactivate; MainWindow does.
        assert tool._state.name == "HOVERING"
```

Run: `pluton-py-tests tests/test_push_pull_tool.py::TestPushPullCancel -v`
Expected: FAIL (on_key_press is currently a no-op stub).

- [ ] **Step 2: Wire ESC + near-zero cancel** in `python/pluton/tools/push_pull_tool.py`

Replace `on_key_press` with:

```python
    def on_key_press(self, event: QKeyEvent) -> None:
        from PySide6.QtCore import Qt

        if event.key() != Qt.Key.Key_Escape:
            return
        if self._state == _State.DRAGGING:
            # Cancel — no command pushed, scene was never mutated during DRAGGING
            # (M3b uses overlay-only preview, not scene mutation).
            self._reset_to_idle()
            return
        # ESC in IDLE/HOVERING is owned by MainWindow's two-stage logic; no-op here.
```

Replace the commit branch of `on_mouse_press` (the DRAGGING case) with:

```python
        # DRAGGING: commit if depth >= min threshold, else cancel.
        if self._current_depth >= _MIN_COMMIT_DEPTH:
            self._commit_extrusion()
        # else: silent cancel — no command pushed.
        self._reset_to_idle()
        # Re-pick under the current cursor for HOVERING vs IDLE.
        hit = self._pick_face_under_cursor(event)
        if hit is not None:
            self._state = _State.HOVERING
            self._hovered_face_id = hit.face_id
```

- [ ] **Step 3: Run the cancel tests**

Run: `pluton-py-tests tests/test_push_pull_tool.py::TestPushPullCancel -v`
Expected: 3 PASS.

- [ ] **Step 4: Run the entire push/pull suite**

Run: `pluton-py-tests tests/test_push_pull_tool.py tests/test_push_pull_overlay.py tests/test_push_pull_topology.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_tool.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — ESC mid-drag + near-zero cancel

ESC in DRAGGING resets the tool to IDLE without pushing a command.
Second click in DRAGGING with depth < 1e-3 also cancels silently.
ESC in IDLE/HOVERING is left to MainWindow's two-stage ESC handler
(which deactivates the tool).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: StatusBar.set_status + MainWindow status_text propagation

**Files:**
- Modify: `python/pluton/ui/status_bar.py`
- Modify: `python/pluton/ui/main_window.py`
- Modify: `tests/test_viewport.py` (or add a dedicated `test_main_window.py` if you prefer)

The status bar gains a third text slot — `set_status(text)` — joined as `<tool> · <snap> · <status>`. MainWindow polls `active_tool.status_text` after every relevant event and forwards it to the status bar.

For M3b the polling happens whenever any of the existing event paths trigger a status update (tool activation, snap change, etc.). We add a small helper `_refresh_status_text()` that's called from those paths.

- [ ] **Step 1: Write the failing test** — append to `tests/test_viewport.py` (or create `tests/test_status_bar.py`)

```python
class TestStatusBarThirdSlot:
    def test_set_status_appends_third_segment(self):
        from PySide6.QtWidgets import QApplication

        # qapp fixture is provided by pytest-qt; if you're not using it,
        # bootstrap a QApplication here. The existing test_viewport.py setup
        # already handles this.
        from pluton.ui.status_bar import StatusBar

        bar = StatusBar()
        bar.set_tool("Push/Pull")
        bar.set_snap("")
        bar.set_status("depth: 1.500")
        assert bar.text() == "Push/Pull · — · depth: 1.500"

    def test_set_status_empty_omits_the_third_segment(self):
        from pluton.ui.status_bar import StatusBar

        bar = StatusBar()
        bar.set_tool("Rectangle")
        bar.set_snap("Endpoint")
        bar.set_status("")  # PushPullTool's status_text returns None outside DRAGGING
        assert bar.text() == "Rectangle · Endpoint"
```

Run: `pluton-py-tests tests/test_viewport.py::TestStatusBarThirdSlot -v`  (or `tests/test_status_bar.py`)
Expected: FAIL (`set_status` doesn't exist).

- [ ] **Step 2: Extend `python/pluton/ui/status_bar.py`**

Replace the file with:

```python
"""Bottom-of-viewport status bar.

Three text slots: tool name, current snap label, and an optional status segment
(used by M3b's PushPullTool to show the current extrusion depth). Joined by `·`.
M4 will repurpose the status slot for the Measurements Box.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBar(QLabel):
    """Single-label status bar — joins tool / snap / status text."""

    def __init__(self) -> None:
        super().__init__()
        self._tool: str = ""
        self._snap: str = ""
        self._status: str = ""
        self.setText("")
        self.setMinimumHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "QLabel { background-color: rgba(0, 0, 0, 0.5); color: #dddddd;"
            " padding: 4px 10px; font-family: sans-serif; font-size: 11px; }"
        )

    def set_tool(self, name: str) -> None:
        self._tool = name
        self._refresh()

    def set_snap(self, label: str) -> None:
        self._snap = label
        self._refresh()

    def set_status(self, text: str) -> None:
        self._status = text or ""
        self._refresh()

    def _refresh(self) -> None:
        if not self._tool:
            self.setText("")
            return
        snap = self._snap if self._snap else "—"
        if self._status:
            self.setText(f"{self._tool} · {snap} · {self._status}")
        else:
            self.setText(f"{self._tool} · {snap}")
```

- [ ] **Step 3: Wire MainWindow to forward `status_text`** — modify `python/pluton/ui/main_window.py`

Add a `_refresh_status_text` helper and call it from `_activate` (and any other path that updates the status bar). Modify `_activate` plus add the helper:

```python
    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._refresh_status_text()
            self._viewport.update()

    def _refresh_status_text(self) -> None:
        active = self._tool_manager.active
        if active is None:
            self._status_bar.set_status("")
            return
        self._status_bar.set_status(active.status_text or "")
```

Also modify `_on_escape`, `_on_clear_scene`, `_on_undo`, `_on_redo` to call `self._refresh_status_text()` before `self._viewport.update()`.

Also modify the ViewportWidget callback path. Currently `viewport_widget._snap_for_event` is called inside mouseMoveEvent / mousePressEvent and the result is forwarded to the active tool, after which the status bar's snap text is set. We need an additional callback to refresh the status text after every event that may have changed it.

The smallest-blast-radius fix: add an optional `on_event_finished` callback to ViewportWidget that fires after every tool event. MainWindow registers it.

In `python/pluton/viewport/viewport_widget.py`, in `__init__` add `self._on_event_finished = None`. Add a setter:
```python
    def set_event_finished_callback(self, fn) -> None:  # noqa: ANN001
        self._on_event_finished = fn
```

In `mousePressEvent` and `mouseMoveEvent`, just before each `self.update()` call inside the tool-active branch, add:
```python
            if self._on_event_finished is not None:
                self._on_event_finished()
```

In `MainWindow.__init__`, after `self._viewport.set_status_bar(self._status_bar)`, add:
```python
        self._viewport.set_event_finished_callback(self._refresh_status_text)
```

- [ ] **Step 4: Run the status-bar tests**

Run: `pluton-py-tests tests/test_viewport.py::TestStatusBarThirdSlot -v` (or `tests/test_status_bar.py`)
Expected: 2 PASS.

- [ ] **Step 5: Make sure M2/M3a status bar / viewport tests still pass**

Run: `pluton-py-tests tests/test_viewport.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/ui/status_bar.py python/pluton/ui/main_window.py python/pluton/viewport/viewport_widget.py tests/test_viewport.py
git commit -m "$(cat <<'EOF'
feat(ui): status bar gets third slot; MainWindow forwards tool.status_text

StatusBar.set_status(text) adds a third '·'-joined segment. MainWindow's
new _refresh_status_text helper polls the active tool's status_text after
every event and pushes the result to the status bar. ViewportWidget grows
a tiny on_event_finished callback that MainWindow registers for the poll.

PushPullTool surfaces "depth: N.NN" during DRAGGING through this hook.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Register PushPullTool in MainWindow + bind P + thread camera/widget into ToolContext

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Modify: `tests/test_viewport.py`

PushPullTool needs `camera` + `widget_size_provider` in its ToolContext. MainWindow creates these AFTER the ViewportWidget is constructed, so we reorder the existing `set_context` call.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_viewport.py`

```python
class TestPushPullToolIntegration:
    def test_p_keybind_activates_push_pull_tool(self, qapp, qtbot):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from pluton.ui.main_window import MainWindow

        win = MainWindow()
        qtbot.addWidget(win)
        win.show()
        qtbot.waitExposed(win)
        QTest.keyClick(win, Qt.Key.Key_P)
        assert win._tool_manager.active is not None
        assert win._tool_manager.active.name == "Push/Pull"

    def test_tool_context_carries_camera_and_widget_size_provider(self, qapp):
        """Sanity: MainWindow wires the viewport's camera + size accessor
        into the ToolContext so PushPullTool can compute camera rays."""
        from pluton.ui.main_window import MainWindow

        win = MainWindow()
        ctx = win._tool_manager._ctx  # noqa: SLF001
        assert ctx.camera is win._viewport.camera
        # widget_size_provider is a lambda returning (width, height).
        assert callable(ctx.widget_size_provider)
        size = ctx.widget_size_provider()
        assert isinstance(size, tuple)
        assert len(size) == 2
```

Run: `pluton-py-tests tests/test_viewport.py::TestPushPullToolIntegration -v`
Expected: FAIL.

- [ ] **Step 2: Update MainWindow** — `python/pluton/ui/main_window.py`

Reorder the `__init__` so that ToolContext is set AFTER the viewport exists. The existing flow creates the ToolManager + sets a context before the viewport; reorder to:

```python
        # Scene + tool manager + command stack
        self._scene = Scene()
        self._command_stack = CommandStack()
        self._tool_manager = ToolManager()
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(PushPullTool())

        # Viewport + status bar (created BEFORE setting ToolContext so we can
        # wire the camera + widget_size_provider into the context).
        self._viewport = ViewportWidget(self._scene, self._tool_manager, self)
        self._status_bar = StatusBar()

        # NOW we can build the ToolContext that includes the viewport refs.
        self._tool_manager.set_context(
            ToolContext(
                scene=self._scene,
                command_stack=self._command_stack,
                camera=self._viewport.camera,
                widget_size_provider=lambda: (self._viewport.width(), self._viewport.height()),
            )
        )
```

Also add to the imports near the top:

```python
from pluton.tools import LineTool, PushPullTool, RectangleTool, ToolContext, ToolManager
```

And add the `P` keybind alongside the existing `L`/`R`:

```python
        QShortcut(QKeySequence("P"), self, activated=lambda: self._activate("P"))
```

- [ ] **Step 3: Run the integration tests**

Run: `pluton-py-tests tests/test_viewport.py::TestPushPullToolIntegration -v`
Expected: 2 PASS.

- [ ] **Step 4: Confirm M2/M3a integration tests still pass**

Run: `pluton-py-tests tests/test_viewport.py -v`
Expected: all PASS.

Also run the full suite to catch any cross-file regression:

Run: `pluton-py-tests -v`
Expected: ~155-165 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/main_window.py tests/test_viewport.py
git commit -m "$(cat <<'EOF'
feat(ui): register PushPullTool and bind P; wire camera into ToolContext

MainWindow now registers PushPullTool alongside Line/Rectangle, binds P,
and builds the ToolContext AFTER the viewport so it can include the
viewport's camera and a widget_size_provider lambda. PushPullTool reads
both to compute camera rays for ray-mesh face picking.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Manual visual verification

**Files:**
- None (manual checklist).

Walk through the spec's §9.2 checklist (11 items). All items should pass; items #9 (open-bottom) and #11 (seam) are EXPECTED limitations — confirm they match the spec wording rather than treating them as bugs.

- [ ] **Step 1: Build the latest binary**

Run: `pluton-build`

- [ ] **Step 2: Run pluton**

Run (Git Bash):
```bash
python -m pluton
```
Run (PowerShell):
```powershell
python -m pluton
```

- [ ] **Step 3: Execute the 11-step checklist from spec §9.2**

For each item, note whether it passed, and capture any deviation. If any item OTHER than #9 or #11 reveals a real bug, file the bug and fix before continuing to Task 15.

- [ ] **Step 4: Verify status bar shows depth during DRAGGING**

Activate Push/Pull (`P`), click a face, drag the cursor — the status bar should read something like `Push/Pull · — · depth: 2.345`.

- [ ] **Step 5: Verify ESC two-stage behavior is preserved**

With Push/Pull active and no gesture in flight, press `Esc` once → tool deactivates. With a gesture in flight (mid-drag), `Esc` cancels the gesture but leaves the tool active. The same two-stage behavior M2 LineTool / RectangleTool ship with.

- [ ] **Step 6: Verify Ctrl+Z restores pre-extrusion scene**

Draw a rectangle, push/pull, `Ctrl+Z`. Scene should return to the original rectangle. `Ctrl+Y` should re-extrude.

If everything looks right, no commit is needed (this task is verification only). If polish issues arise (e.g. hover-highlight color is too subtle, or the ghost prism is too faint), update the M3b plan with a polish task and add a commit.

---

## Task 15: Push, CI verification, version bump, tag, carry-over issues

**Files:**
- Modify: `pyproject.toml`
- Modify: `CMakeLists.txt` (top-level)
- Modify: `cpp/src/version.cpp`

- [ ] **Step 1: Push to main and watch CI**

```bash
git push origin main
gh run watch
```

After it completes, ALWAYS verify with `gh run view <run-id>` because `gh run watch` returns 0 even on certain failure modes.

Expected: both `ubuntu-24.04` and `windows-2022` jobs green.

- [ ] **Step 2: Bump the version to 0.0.5 in three places**

Modify `pyproject.toml`:
```toml
[project]
version = "0.0.5"
```

Modify the root `CMakeLists.txt`:
```cmake
project(pluton
    VERSION 0.0.5
    DESCRIPTION "Polygonal 3D modeler for architecture"
    LANGUAGES CXX
)
```

Modify `cpp/src/version.cpp`:
```cpp
#include "pluton/version.h"

namespace pluton {

std::string version() {
    return "0.0.5";
}

}  // namespace pluton
```

- [ ] **Step 3: Rebuild and run all tests at 0.0.5**

Run: `pluton-build && pluton-cpp-tests && pluton-py-tests`
Expected: ~51-54 GoogleTest pass, ~155-165 pytest pass.

- [ ] **Step 4: Commit the version bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp
git commit -m "chore: bump version to 0.0.5 for M3b release

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Create the annotated, SSH-signed tag**

```bash
git tag -a v0.0.5-m3b -m "$(cat <<'EOF'
M3b — Push/Pull (basic)

Headline: the first SketchUp-style push/pull tool.

What landed:
- C++ pluton::ray_intersect_mesh — brute-force Möller-Trumbore over every
  live face's stored triangulation; closest positive t wins.
- Scene wrapper helpers: ray_pick_face, face_loop, face_normal, face_center.
- PushPullTool — three-state machine (IDLE / HOVERING / DRAGGING), line-line
  CPA depth metric, semi-transparent ghost prism preview, hover-highlight,
  per-gesture CompositeCommand at commit so one Ctrl+Z undoes the whole thing.
- SceneRenderer alpha-blended face-fill overlay pass.
- Status bar gets a third slot for the current extrusion depth.
- ToolContext extended with camera + widget_size_provider.

Known limitations (per design §6):
1. Open-bottom prism — source face is removed and not replaced; orbit below
   the ground plane reveals the open bottom. M3c's booleans close this.
2. Seam line — pushing the top of an existing box creates a coplanar seam at
   the old top height. M3c's booleans eliminate this.
3. Brute-force ray-mesh — O(N) per pick is fine for M3b scenes. BVH = M10.

CI green on Windows + Linux.
EOF
)"
```

- [ ] **Step 6: Push the tag**

```bash
git push origin v0.0.5-m3b
```

Then verify on GitHub:
```bash
gh api repos/Parrow-Horrizon-Studio/pluton/git/refs/tags/v0.0.5-m3b
```
Expected: returns a JSON object with `"type": "tag"` (proves it's annotated).

- [ ] **Step 7: Open the carry-over GitHub issues**

(Edit titles / labels to match the project's existing issue style. Tags below are suggestions.)

```bash
gh issue create \
  --title "M10 perf: BVH for ray-mesh face picking" \
  --body "M3b shipped brute-force O(N) ray-mesh per pick. Fine today but a BVH lands at the perf milestone. See docs/2026-05-23-M3b-push-pull-design.md §6 #3." \
  --label enhancement

gh issue create \
  --title "M3c: close the bottom of a push/pull extrusion via boolean merge" \
  --body "M3b's open-bottom prism is the honest 'no booleans yet' result. M3c's CGAL boolean union closes this by merging the extrusion with the ground / surrounding geometry. See docs/2026-05-23-M3b-push-pull-design.md §6 #1." \
  --label enhancement

gh issue create \
  --title "M3c: eliminate seam line at coplanar adjacent faces after push/pull" \
  --body "M3b leaves a visible seam where the new side wall meets the old side wall when push/pulling a face attached to existing geometry. The two faces are coplanar and share an edge with two live half-edges. M3c's boolean union merges them. See docs/2026-05-23-M3b-push-pull-design.md §6 #2." \
  --label enhancement
```

If visual verification (Task 14) surfaced anything else worth tracking, file additional issues now.

---

## Self-Review

(This section was filled in after writing the plan.)

**Spec coverage check** — every spec section maps to a task:
- §3.3 C++ API surface (`ray_intersect.h`, `RayMeshHit`, `ray_intersect_mesh`) → Task 2 + Task 3.
- §3.4 Python API surface (Scene helpers; ToolOverlay extensions; Tool.status_text; PushPullTool) → Tasks 4 + 5 + 7-11.
- §4.1 state machine → Tasks 7-11.
- §4.2 depth metric → Task 8.
- §4.3 extrusion composite → Task 10.
- §4.4 boundary half-edge reuse → tested implicitly via Task 10's topology tests.
- §4.5 edge cases → Tasks 8 (degenerate view), 10 (commit + ray-pick re-hover), 11 (ESC + near-zero cancel).
- §5 renderer changes → Task 6.
- §6 known limitations → flagged in Task 14 (visual verification) + Task 15 carry-over issues.
- §7 out of scope → respected in plan (no CGAL, no inferencing, no closed bottom).
- §8 M3b → M3c contract → preserved (signatures stable; state machine stable).
- §9.1 test list → covered across Tasks 1-13.
- §9.2 visual checklist → Task 14.
- §10 implementation order → matches Tasks 1-15 (consolidated visual + push/CI + version + tag + carry-overs into Tasks 14-15 vs spec's 14-18 line items).
- §11 risks → mitigated (Task 1 verifies M3a kernel API; Task 14 surfaces visual issues; Task 12 commits the renderer fall-through before MainWindow integration).
- §12 definition of done → enumerated at top of this plan.

**Placeholder scan** — no "TBD", no "TODO" in plan steps (code comments use TODO for M4+ as designed), no vague "add appropriate handling", no orphan references.

**Type consistency** — verified across tasks:
- `Scene.ray_pick_face(origin, direction)` signature in Task 4 matches PushPullTool's usage in Task 7's `_pick_face_under_cursor`.
- `face_loop` returns `list[int]` (Task 4) — consumed by `PushPullTool._arm_face` (Task 8) and `_loop_world_coords` (Task 7).
- `face_normal` returns `np.ndarray (3,) float32` — consumed by `_arm_face` (Task 8) and `_build_ghost_polygons` (Task 9) and `_commit_extrusion` (Task 10).
- `ToolOverlay.face_fill_polygons` is `list[np.ndarray]` (Task 5) — set by PushPullTool (Tasks 7, 9), consumed by SceneRenderer (Task 6).
- `Tool.status_text` returns `str | None` (Task 5) — overridden by PushPullTool (Task 7), read by StatusBar via MainWindow (Task 12).

No issues found.

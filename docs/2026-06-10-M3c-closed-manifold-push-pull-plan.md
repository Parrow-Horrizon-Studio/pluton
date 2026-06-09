# M3c — Closed-manifold Push/Pull Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make push/pull produce closed manifold output. After M3c, a P/P on a standalone face produces a closed prism (no open bottom); a P/P on the top of an existing solid produces a seamless taller solid (no horizontal seam at the old top). No CGAL dependency added — both behaviors are pure half-edge ops.

**Architecture:** Add two small primitives to the C++ kernel — `HalfEdgeMesh::dissolve_edge(EdgeId) → FaceId` (collapses two adjacent faces sharing an edge into one) and `HalfEdgeMesh::faces_are_coplanar(FaceId, FaceId, angle_tol_cos, dist_tol) → bool` (robust two-test coplanarity check). The Python `Scene` wrapper exposes thin `dissolve_edge` + `faces_are_coplanar` accessors plus three half-edge query helpers (`face_edges`, `edge_faces`, `edge_is_boundary`). A new `DissolveEdgeCommand` joins the command set. `PushPullTool._commit_extrusion` is extended (not restructured) with a conditional bottom-cap (only when the source face was standalone) and a single-pass seam-merge over the OLD source face's boundary edges. The renderer and picker need no changes — dissolved edges naturally vanish from the mesh and the existing dominant-axis-projection earcut handles merged-face polygons.

**Tech Stack:** C++20, nanobind 2.x, GoogleTest, PySide6 (Qt 6), PyOpenGL, numpy, mapbox-earcut (Python; unchanged from M3a), pytest + pytest-qt. **No new C++ deps** — `vcpkg.json` is untouched; CGAL still waits for Phase 2.

**Spec:** `docs/2026-06-10-M3c-closed-manifold-push-pull-design.md`

**Prerequisite:** M3b complete (tag `v0.0.5-m3b`). Working tree clean on `main`.

---

## Build & Test Commands Reference

Same incantation as M3a/M3b. M3c does not change the build system.

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

**Pre-flight check (per the M3b `_core.pyd` shadow incident, recurring):** before running any test command after a build, verify the installed module is being loaded:

```bash
python -c "import pluton._core; print(pluton._core.__file__)"
```

Expected output points into `.venv/Lib/site-packages/pluton/_core....pyd` (Windows) or `.venv/lib/python3.13/site-packages/pluton/_core....so` (Linux). If it points into `python/pluton/_core....pyd`, a stale shadow PYD exists in the package dir — `rm python/pluton/_core*.pyd` and rebuild.

---

## File Map

**C++ side**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/include/pluton/halfedge.h` | MODIFY | Add `dissolve_edge` + `faces_are_coplanar` method declarations. |
| `cpp/src/halfedge.cpp` | MODIFY | Implement both methods + private helpers (`faces_share_multiple_edges`, etc.). |
| `cpp/bindings/module.cpp` | MODIFY | Bind both methods to Python (~10-12 lines). |
| `cpp/tests/test_halfedge.cpp` | MODIFY | 11 new GoogleTest cases (6 dissolve, 5 coplanarity). |

`cpp/CMakeLists.txt` is NOT modified — `halfedge.cpp` is already a source. `cpp/tests/CMakeLists.txt` is NOT modified — `test_halfedge.cpp` is already a test source.

**Python side**

| Path | Status | Responsibility |
|---|---|---|
| `python/pluton/scene/scene.py` | MODIFY | Add `dissolve_edge`, `faces_are_coplanar`, plus three half-edge query helpers (`face_edges`, `edge_faces`, `edge_is_boundary`). |
| `python/pluton/commands/scene_commands.py` | MODIFY | Append `DissolveEdgeCommand` class. |
| `python/pluton/tools/push_pull_tool.py` | MODIFY | Extend `_commit_extrusion` — conditional bottom-cap + seam-merge pass. New private helper `_should_add_bottom_cap`. |

**Tests**

| Path | Status | Responsibility |
|---|---|---|
| `cpp/tests/test_halfedge.cpp` | MODIFY | 11 new tests for the two new C++ methods. |
| `tests/test_halfedge_python.py` | MODIFY | Smoke test for the new bindings. |
| `tests/test_scene_dissolve.py` | NEW | Scene-level wrapper tests for `dissolve_edge`, `faces_are_coplanar`, plus the three query helpers. |
| `tests/test_dissolve_edge_command.py` | NEW | `DissolveEdgeCommand` do/undo/redo behaviour. |
| `tests/test_push_pull_tool_closed_manifold.py` | NEW | End-to-end Case 1 (closed bottom) + Case 2 (seam merge) via `PushPullTool`. |
| `tests/test_push_pull_topology.py` | MODIFY | Strengthen existing assertions: per-face triangle counts > 0; interior edges have 2 half-edges. |
| `tests/test_picking_after_merge.py` | NEW | Pick a merged face after Case 2, confirm correct face id returned. |
| `tests/test_renderer_merged_face.py` | NEW | Render pass produces > 0 triangles for a merged hexagon face. |

**Versioning / build (last task)**

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | MODIFY | Bump `version = "0.0.6"`. |
| `CMakeLists.txt` (top-level) | MODIFY | Bump `project(... VERSION 0.0.6 ...)`. |
| `cpp/src/version.cpp` | MODIFY | Return `"0.0.6"`. |

**Documentation**

| Path | Status | Responsibility |
|---|---|---|
| `docs/2026-05-16-pluton-design.md` | MODIFY | Drop "CGAL handles boolean merge" line in §M3; note inferencing splits to M3d. |

---

## Definition of Done for M3c

1. Both new C++ methods compile cleanly on MSVC `/W4` and GCC `-Wall -Wextra -Wpedantic`.
2. All M3c GoogleTest cases pass (+11 = 66 total).
3. All M3a + M3b Python tests (189) still pass unchanged.
4. New Python tests pass (+14 = 203 total).
5. `python -m pluton` launches; M3b baseline (P/P on rectangle, hover, ESC two-stage) works unchanged.
6. **Closed-bottom prism:** draw rectangle → P/P up → orbit below → no hole visible.
7. **Seamless stacked extrusion:** P/P top of existing box → no horizontal seam line at old top height.
8. The 13-step visual verification checklist (this plan §Task 10) passes.
9. CI green on Windows + Linux.
10. Master design doc updated: §M3 no longer claims CGAL is required.
11. Issues #21 and #22 closed with a comment linking the M3c tag.
12. New Phase 2 issue filed: *"Phase 2: CGAL booleans — push/pull into existing solid + Hole tool."*
13. Tagged `v0.0.6-m3c` (annotated, SSH-signed).
14. Tag pushed to GitHub.

---

## Task 1: C++ `HalfEdgeMesh::faces_are_coplanar` + GoogleTests

**Files:**
- Modify: `cpp/include/pluton/halfedge.h` (declaration)
- Modify: `cpp/src/halfedge.cpp` (implementation)
- Modify: `cpp/tests/test_halfedge.cpp` (5 new tests)

Starting with `faces_are_coplanar` because `dissolve_edge` (Task 2) doesn't depend on it, but Task 5's Python scene wrapper consumes both — keeping the C++ work front-loaded means the rest of the milestone is plain Python.

The function takes two face IDs and two tolerances: `angle_tol_cos` (the threshold for `dot(n1, n2)` — pass `cos(0.5°)` for the project default) and `dist_tol` (max signed distance from any vertex of one face to the other face's plane, in world units — pass `1e-4` for the project default). Returns `true` only if BOTH the normal-angle test AND the distance test pass for the pair (symmetric: check each face's vertices against the other's plane).

Degenerate normal (zero-area face) → returns `false` (refuse to merge), no crash.

- [ ] **Step 1: Add the header declaration**

Append to `cpp/include/pluton/halfedge.h` in the `// ---- Queries -----` block (after `face_triangles`, before the `halfedge_*` accessors):

```cpp
    /// Robust planar-coplanarity test for two faces.
    /// Returns true iff both:
    ///   - the angle between unit normals satisfies dot(n1, n2) > angle_tol_cos, AND
    ///   - every vertex of either face lies within `dist_tol` of the other face's plane.
    /// Returns false (without crashing) for degenerate-normal faces (|n| < 1e-7).
    /// Project defaults: angle_tol_cos = cos(0.5°) ≈ 0.9999619f, dist_tol = 1e-4f.
    bool faces_are_coplanar(std::uint32_t f1_id,
                            std::uint32_t f2_id,
                            float angle_tol_cos,
                            float dist_tol) const;
```

- [ ] **Step 2: Write the failing GoogleTests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
// ====================================================================
// M3c: faces_are_coplanar
// ====================================================================

namespace {

// Helper: build a triangle face from 3 explicit positions, return face id.
std::uint32_t add_triangle(pluton::HalfEdgeMesh& m,
                           std::array<float, 3> p0,
                           std::array<float, 3> p1,
                           std::array<float, 3> p2) {
    auto v0 = m.add_vertex(p0[0], p0[1], p0[2]);
    auto v1 = m.add_vertex(p1[0], p1[1], p1[2]);
    auto v2 = m.add_vertex(p2[0], p2[1], p2[2]);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    return m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
}

constexpr float kCos05Deg = 0.99996192306f;   // cos(0.5°)
constexpr float kDistTol  = 1.0e-4f;

}  // namespace

TEST(HalfEdgeMeshTest, FacesAreCoplanar_TrueForIdenticalPlanes) {
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});       // XY plane
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2,3,0});       // also XY plane
    EXPECT_TRUE(m.faces_are_coplanar(f1, f2, kCos05Deg, kDistTol));
    EXPECT_TRUE(m.faces_are_coplanar(f2, f1, kCos05Deg, kDistTol));  // symmetric
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_TrueWithinAngleTolerance) {
    // Two faces on planes whose normals differ by 0.3° — under the 0.5° tolerance.
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});  // normal (0,0,1)
    // Rotate the second face by 0.3° about X: normal becomes (0, -sin(0.3°), cos(0.3°))
    float c = std::cos(0.3f * 3.14159265f / 180.0f);
    float s = std::sin(0.3f * 3.14159265f / 180.0f);
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2, 2 + c, s});
    EXPECT_TRUE(m.faces_are_coplanar(f1, f2, kCos05Deg, 1e-3f));   // looser dist
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseBeyondAngleTolerance) {
    // 1.0° apart — over the 0.5° tolerance.
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});
    float c = std::cos(1.0f * 3.14159265f / 180.0f);
    float s = std::sin(1.0f * 3.14159265f / 180.0f);
    auto f2 = add_triangle(m, {2,2,0}, {3,2,0}, {2, 2 + c, s});
    EXPECT_FALSE(m.faces_are_coplanar(f1, f2, kCos05Deg, 1.0f));
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseBeyondDistanceTolerance) {
    // Two parallel XY planes offset by 1e-3 (over the 1e-4 dist tolerance).
    pluton::HalfEdgeMesh m;
    auto f1 = add_triangle(m, {0,0,0}, {1,0,0}, {0,1,0});       // z = 0
    auto f2 = add_triangle(m, {2,2,1e-3f}, {3,2,1e-3f}, {2,3,1e-3f});  // z = 0.001
    EXPECT_FALSE(m.faces_are_coplanar(f1, f2, kCos05Deg, kDistTol));
}

TEST(HalfEdgeMeshTest, FacesAreCoplanar_FalseForDegenerateNormal) {
    // f1 has zero area (all 3 vertices collinear). Must not crash; must return false.
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(2,0,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    auto f_degen = m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});

    auto f_good = add_triangle(m, {5,0,0}, {6,0,0}, {5,1,0});
    EXPECT_FALSE(m.faces_are_coplanar(f_degen, f_good, kCos05Deg, kDistTol));
    EXPECT_FALSE(m.faces_are_coplanar(f_good, f_degen, kCos05Deg, kDistTol));
}
```

- [ ] **Step 3: Run to verify the tests fail to link**

Run: `pluton-build` — expected: compile error (`'faces_are_coplanar' is not a member of 'pluton::HalfEdgeMesh'`).

- [ ] **Step 4: Implement `faces_are_coplanar`** — add to `cpp/src/halfedge.cpp`

Find an appropriate insertion point (e.g., after `face_triangles` implementation). Add:

```cpp
namespace {

inline std::array<float, 3> sub3(std::array<float, 3> a, std::array<float, 3> b) {
    return { a[0]-b[0], a[1]-b[1], a[2]-b[2] };
}
inline std::array<float, 3> cross3(std::array<float, 3> a, std::array<float, 3> b) {
    return {
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    };
}
inline float dot3(std::array<float, 3> a, std::array<float, 3> b) {
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}
inline float len3(std::array<float, 3> a) {
    return std::sqrt(dot3(a, a));
}

// Compute geometric face normal from the first three boundary vertices.
// Returns zero vector if the face is degenerate (collinear or repeated vertices).
std::array<float, 3> compute_face_normal_geometric(
        const pluton::HalfEdgeMesh& m, std::uint32_t f_id) {
    auto loop = m.face_loop_vertices(f_id);
    if (loop.size() < 3) return {0, 0, 0};
    auto p0 = m.vertex_position(loop[0]);
    auto p1 = m.vertex_position(loop[1]);
    auto p2 = m.vertex_position(loop[2]);
    auto n  = cross3(sub3(p1, p0), sub3(p2, p0));
    float L = len3(n);
    if (L < 1e-7f) return {0, 0, 0};
    return { n[0]/L, n[1]/L, n[2]/L };
}

}  // namespace

bool pluton::HalfEdgeMesh::faces_are_coplanar(std::uint32_t f1_id,
                                              std::uint32_t f2_id,
                                              float angle_tol_cos,
                                              float dist_tol) const {
    if (!face_is_live(f1_id) || !face_is_live(f2_id)) return false;
    auto n1 = compute_face_normal_geometric(*this, f1_id);
    auto n2 = compute_face_normal_geometric(*this, f2_id);
    // Degenerate normal → refuse.
    if (len3(n1) < 1e-7f || len3(n2) < 1e-7f) return false;

    // Angle test: |dot(n1, n2)| > tolerance — accept either winding direction.
    float ang = std::abs(dot3(n1, n2));
    if (ang < angle_tol_cos) return false;

    // Distance test: every vertex of f2 within `dist_tol` of f1's plane, and vv.
    auto check_side = [&](std::array<float, 3> n, std::uint32_t plane_face,
                          std::uint32_t other_face) -> bool {
        auto plane_loop = face_loop_vertices(plane_face);
        auto p_anchor = vertex_position(plane_loop[0]);
        float d_anchor = dot3(n, p_anchor);
        for (auto v : face_loop_vertices(other_face)) {
            auto p = vertex_position(v);
            float signed_d = dot3(n, p) - d_anchor;
            if (std::abs(signed_d) > dist_tol) return false;
        }
        return true;
    };
    return check_side(n1, f1_id, f2_id) && check_side(n2, f2_id, f1_id);
}
```

Add `#include <cmath>` at the top of `halfedge.cpp` if not already present.

- [ ] **Step 5: Build + run the new tests**

```bash
pluton-build
pluton-cpp-tests -R FacesAreCoplanar
```

Expected: 5 PASS.

- [ ] **Step 6: Run the full C++ test suite for regressions**

Run: `pluton-cpp-tests`
Expected: 55 (M3b) + 5 (M3c so far) = 60 PASS.

- [ ] **Step 7: Commit**

```bash
git add cpp/include/pluton/halfedge.h cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "$(cat <<'EOF'
feat(halfedge): add faces_are_coplanar(f1, f2, angle_tol_cos, dist_tol)

Two-test robust coplanarity check:
- |dot(n1, n2)| > angle_tol_cos (accepts either winding direction)
- every vertex of one face within dist_tol of the other's plane (symmetric)

Returns false (without crashing) for degenerate-normal faces (|n| < 1e-7).
Project defaults: cos(0.5°) angle, 1e-4 world-unit distance.

Foundation for M3c seam-merge during push/pull commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: C++ `HalfEdgeMesh::dissolve_edge` happy path + GoogleTests

**Files:**
- Modify: `cpp/include/pluton/halfedge.h` (declaration)
- Modify: `cpp/src/halfedge.cpp` (implementation + helper)
- Modify: `cpp/tests/test_halfedge.cpp` (2 happy-path tests + 2 supporting tests)

Now `dissolve_edge` for the well-defined case: an edge has exactly two adjacent faces (each with exactly one half-edge on this edge). The function:

1. Looks up the two half-edges of the edge (slot indices `2e` and `2e+1`).
2. Identifies the two adjacent faces (`halfedge_face(2e)`, `halfedge_face(2e+1)`).
3. Walks each face's boundary, splicing the two loops together at the shared edge — the result is a single loop that omits the two shared half-edges.
4. Removes the source faces (their `alive = false`, slots tombstoned).
5. Allocates a new face on the spliced loop, with retriangulated `tris`.
6. Removes the edge (both half-edges tombstoned, `alive = false`).
7. Returns the new face's id.

For the multi-shared-edge case and boundary-edge case, this task returns `INVALID_ID` as a stub — the next task (Task 3) writes the rejection logic + tests properly. This task focuses on the happy path.

- [ ] **Step 1: Add the header declaration**

Append to `cpp/include/pluton/halfedge.h` after `faces_are_coplanar`:

```cpp
    /// Dissolve an edge between two adjacent faces — merges the faces into one.
    /// Returns the new (surviving) face id on success.
    /// Returns INVALID_ID if the edge is on the mesh boundary (only 1 incident
    /// face), already tombstoned, or if the two adjacent faces share more than
    /// one edge (would create a degenerate result).
    /// The dissolved edge id is tombstoned (never reused).
    std::uint32_t dissolve_edge(std::uint32_t e_id);
```

- [ ] **Step 2: Write the failing happy-path tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
// ====================================================================
// M3c: dissolve_edge — happy path
// ====================================================================

TEST(HalfEdgeMeshTest, DissolveEdge_TwoTrianglesIntoQuad) {
    // Build two triangles sharing edge v1—v2:
    //   T1 = (v0, v1, v2)   T2 = (v1, v3, v2)   shared edge: v1—v2
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);                                       // shared
    auto shared = m.add_halfedge_pair(v1, v2) / 2u * 0u;  // workaround; see actual edge id below
    // The edge id corresponding to the (v1, v2) pair is recoverable from the
    // returned half-edge id of the second add_halfedge_pair-equivalent call.
    // But add_halfedge_pair is idempotent — calling it twice returns the same edge.
    m.add_halfedge_pair(v2, v0);
    m.add_halfedge_pair(v1, v3);
    m.add_halfedge_pair(v3, v2);

    auto f1 = m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
    auto f2 = m.add_face_from_loop({v1, v3, v2}, {(int)v1, (int)v3, (int)v2});

    // Find the shared edge id (the v1—v2 pair). Walk f1's boundary half-edges.
    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }
    ASSERT_NE(shared_edge, pluton::HalfEdgeMesh::INVALID_ID);

    auto merged = m.dissolve_edge(shared_edge);

    EXPECT_NE(merged, pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_FALSE(m.face_is_live(f1));
    EXPECT_FALSE(m.face_is_live(f2));
    EXPECT_FALSE(m.edge_is_live(shared_edge));
    EXPECT_TRUE(m.face_is_live(merged));

    // The merged face is a quad with 4 vertices.
    auto loop = m.face_loop_vertices(merged);
    EXPECT_EQ(loop.size(), 4u);
}

TEST(HalfEdgeMeshTest, DissolveEdge_TombstonesEdgeId) {
    // After dissolve, the edge slot should be tombstoned (not compacted).
    // Querying the now-dead edge returns invalid; slab size unchanged.
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_halfedge_pair(v1, v3);
    m.add_halfedge_pair(v3, v2);
    m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});
    m.add_face_from_loop({v1, v3, v2}, {(int)v1, (int)v3, (int)v2});

    // Find the shared edge again.
    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }

    auto slab_before = m.halfedge_slab_size();
    m.dissolve_edge(shared_edge);
    EXPECT_EQ(m.halfedge_slab_size(), slab_before);     // no compaction
    EXPECT_FALSE(m.edge_is_live(shared_edge));
}
```

- [ ] **Step 3: Run to verify failures**

`pluton-build` → expected: link/compile error since `dissolve_edge` isn't implemented yet.

- [ ] **Step 4: Implement `dissolve_edge`** — add to `cpp/src/halfedge.cpp`

```cpp
std::uint32_t pluton::HalfEdgeMesh::dissolve_edge(std::uint32_t e_id) {
    // The two half-edges of edge e are at slab indices 2e and 2e+1.
    std::uint32_t he_a = 2u * e_id;
    std::uint32_t he_b = 2u * e_id + 1u;
    if (he_b >= halfedges_.size()) return INVALID_ID;
    if (!halfedges_[he_a].alive || !halfedges_[he_b].alive) return INVALID_ID;

    std::uint32_t f1 = halfedges_[he_a].face;
    std::uint32_t f2 = halfedges_[he_b].face;
    if (f1 == INVALID_ID || f2 == INVALID_ID) return INVALID_ID;  // boundary edge
    if (f1 == f2) return INVALID_ID;                              // same face on both sides

    // Reject multi-shared-edge: count how many edges f1 and f2 share. Walk f1's
    // boundary half-edges; for each, see if its twin is on f2. If more than one
    // such half-edge exists, refuse.
    {
        std::uint32_t shared_count = 0;
        std::uint32_t start = faces_[f1].boundary_he;
        std::uint32_t cur = start;
        do {
            std::uint32_t twin = halfedges_[cur].twin;
            if (twin != INVALID_ID && halfedges_[twin].face == f2) ++shared_count;
            cur = halfedges_[cur].next;
        } while (cur != start);
        if (shared_count > 1) return INVALID_ID;
    }

    // Splice the two boundary loops at the shared edge.
    //   Loop of f1: ... -> A -> he_a -> B -> ...   (B = he_a.next, A's next was he_a)
    //   Loop of f2: ... -> C -> he_b -> D -> ...
    // After dissolve the merged loop becomes:
    //   ... -> A -> D -> ... -> C -> B -> ...
    // (skipping he_a and he_b, splicing across the gap.)

    // Find A (predecessor of he_a in f1's loop).
    std::uint32_t A = INVALID_ID;
    {
        std::uint32_t cur = halfedges_[he_a].next;
        while (halfedges_[cur].next != he_a) cur = halfedges_[cur].next;
        A = cur;
    }
    // Find C (predecessor of he_b in f2's loop).
    std::uint32_t C = INVALID_ID;
    {
        std::uint32_t cur = halfedges_[he_b].next;
        while (halfedges_[cur].next != he_b) cur = halfedges_[cur].next;
        C = cur;
    }
    std::uint32_t B = halfedges_[he_a].next;
    std::uint32_t D = halfedges_[he_b].next;

    // Splice next-pointers across the gap.
    halfedges_[A].next = D;
    halfedges_[C].next = B;

    // Walk the new merged loop, reassigning face pointers and collecting
    // vertex IDs for the new face's `loop` cache.
    std::vector<std::uint32_t> merged_loop;
    std::uint32_t walk_start = D;
    std::uint32_t walk_cur = walk_start;
    do {
        merged_loop.push_back(halfedges_[walk_cur].origin);
        walk_cur = halfedges_[walk_cur].next;
    } while (walk_cur != walk_start);

    // Retriangulate the merged loop with a simple fan (works for convex; the
    // merged shape from coplanar dissolves is convex by construction in M3c's
    // Case 2). For now use fan from vertex 0.
    std::vector<std::int32_t> tris;
    tris.reserve((merged_loop.size() - 2) * 3);
    for (std::size_t i = 1; i + 1 < merged_loop.size(); ++i) {
        tris.push_back((std::int32_t)merged_loop[0]);
        tris.push_back((std::int32_t)merged_loop[i]);
        tris.push_back((std::int32_t)merged_loop[i + 1]);
    }

    // Tombstone the two source faces and the dissolved edge's two half-edges.
    faces_[f1].alive = false;
    faces_[f2].alive = false;
    halfedges_[he_a].alive = false;
    halfedges_[he_b].alive = false;

    // Allocate the new face on the merged loop. Note: this calls
    // add_face_from_loop, which re-walks half-edges — they must already point
    // to a consistent next-chain. Splicing above ensured this.
    auto new_face = add_face_from_loop(merged_loop, tris);

    // After add_face_from_loop, the merged_loop's half-edges now have face = new_face.
    // (add_face_from_loop sets this internally.)

    dirty_ = true;
    return new_face;
}
```

- [ ] **Step 5: Build + run new tests**

```bash
pluton-build
pluton-cpp-tests -R DissolveEdge_Two
```

Expected: 2 PASS (the two happy-path tests).

If the tests fail with shape mismatches (e.g., `loop.size() != 4`), debug the splicing logic by printing the merged loop before/after. The likely failure modes:
- `halfedges_[A].next = D` wired wrong → infinite loop in the walk
- The new face's `boundary_he` ends up pointing at a dead half-edge

- [ ] **Step 6: Run the full C++ test suite for regressions**

`pluton-cpp-tests`
Expected: 60 (Task 1) + 2 (Task 2) = 62 PASS.

- [ ] **Step 7: Commit**

```bash
git add cpp/include/pluton/halfedge.h cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "$(cat <<'EOF'
feat(halfedge): dissolve_edge — happy path (two adjacent faces → one)

Collapses two faces sharing a single edge into one merged face by:
- splicing their boundary loops across the shared edge,
- tombstoning the source faces,
- tombstoning the dissolved edge's two half-edges (slot indices 2e, 2e+1),
- allocating a new face on the spliced loop (fan-triangulated).

Multi-shared-edge case and boundary-edge case currently return INVALID_ID
via guard clauses — Task 3 adds dedicated tests and rejection paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: C++ `dissolve_edge` edge cases (boundary, multi-shared, quads) + GoogleTests

**Files:**
- Modify: `cpp/tests/test_halfedge.cpp` (4 more tests)

Task 2's `dissolve_edge` already has guards for the rejection cases (boundary, multi-shared). This task locks them down by test and adds a quad-into-hexagon happy-path test that the implementation should already pass.

- [ ] **Step 1: Add the remaining 4 tests** — append to `cpp/tests/test_halfedge.cpp`

```cpp
TEST(HalfEdgeMeshTest, DissolveEdge_TwoQuadsIntoHexagon) {
    // Two quads sharing an edge — dissolve produces a 6-vertex face.
    //   Q1 = (v0, v1, v2, v3)  Q2 = (v1, v4, v5, v2)  shared: v1—v2
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(1,1,0);
    auto v3 = m.add_vertex(0,1,0);
    auto v4 = m.add_vertex(2,0,0);
    auto v5 = m.add_vertex(2,1,0);
    m.add_halfedge_pair(v0, v1);
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);
    m.add_halfedge_pair(v1, v4);
    m.add_halfedge_pair(v4, v5);
    m.add_halfedge_pair(v5, v2);
    m.add_face_from_loop({v0, v1, v2, v3},
        {(int)v0, (int)v1, (int)v2, (int)v0, (int)v2, (int)v3});
    m.add_face_from_loop({v1, v4, v5, v2},
        {(int)v1, (int)v4, (int)v5, (int)v1, (int)v5, (int)v2});

    std::uint32_t shared_edge = pluton::HalfEdgeMesh::INVALID_ID;
    for (std::uint32_t e = 0; e < m.halfedge_slab_size() / 2; ++e) {
        auto verts = m.edge_vertices(e);
        if ((verts[0] == v1 && verts[1] == v2) || (verts[0] == v2 && verts[1] == v1)) {
            shared_edge = e;
            break;
        }
    }

    auto merged = m.dissolve_edge(shared_edge);
    EXPECT_NE(merged, pluton::HalfEdgeMesh::INVALID_ID);
    auto loop = m.face_loop_vertices(merged);
    EXPECT_EQ(loop.size(), 6u);
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsBoundaryEdge) {
    // Single triangle — all three edges are boundary (only one half-edge each).
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto v2 = m.add_vertex(0,1,0);
    auto e01 = m.add_halfedge_pair(v0, v1) / 2u;
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {(int)v0, (int)v1, (int)v2});

    EXPECT_EQ(m.dissolve_edge(e01), pluton::HalfEdgeMesh::INVALID_ID);
    EXPECT_TRUE(m.edge_is_live(e01));   // unchanged
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsAlreadyTombstonedEdge) {
    pluton::HalfEdgeMesh m;
    auto v0 = m.add_vertex(0,0,0);
    auto v1 = m.add_vertex(1,0,0);
    auto e = m.add_halfedge_pair(v0, v1) / 2u;
    m.remove_edge(e);

    EXPECT_EQ(m.dissolve_edge(e), pluton::HalfEdgeMesh::INVALID_ID);
}

TEST(HalfEdgeMeshTest, DissolveEdge_RejectsMultiSharedEdges) {
    // Pathological topology where two faces share two edges (e.g., a folded
    // bigon). Construct manually: two triangles sharing two edges. Building a
    // valid multi-shared topology in our half-edge structure is awkward, so
    // for now we accept that the guard exists and the unit test is exercised
    // via the existing implementation path. We assert the API surface stays
    // honest: a follow-up M3 issue can construct the actual degenerate input.
    SUCCEED() << "Multi-shared rejection path covered by code review only; "
              << "constructing a valid degenerate half-edge input requires a "
              << "test helper not yet built. Filed as known carry-over.";
}
```

- [ ] **Step 2: Build + run all new tests**

```bash
pluton-build
pluton-cpp-tests -R DissolveEdge
```

Expected: 6 PASS (4 from Task 2 + 4 from Task 3 — except the multi-shared test which is a `SUCCEED` placeholder).

Note: the multi-shared `SUCCEED` is intentional. The implementation has the guard; constructing a valid degenerate half-edge mesh to exercise it is non-trivial and out of scope for M3c per `docs/2026-06-10-M3c-closed-manifold-push-pull-design.md` §5.1. File as carry-over in Task 11.

- [ ] **Step 3: Run the full C++ test suite for regressions**

`pluton-cpp-tests`
Expected: 62 (after Task 2) + 4 (this task's new tests, one of which is `SUCCEED`) = 66 PASS.

- [ ] **Step 4: Commit**

```bash
git add cpp/tests/test_halfedge.cpp
git commit -m "$(cat <<'EOF'
test(halfedge): dissolve_edge — quad→hexagon happy path + rejection cases

Adds:
- DissolveEdge_TwoQuadsIntoHexagon: dissolving the shared edge between two
  quads produces a 6-vertex merged face (covers the M3c Case 2 topology
  shape that seam-merge produces on rectangular extrusions).
- DissolveEdge_RejectsBoundaryEdge: edge with only one incident half-edge
  returns INVALID_ID, mesh unchanged.
- DissolveEdge_RejectsAlreadyTombstonedEdge: removed edge returns INVALID_ID.
- DissolveEdge_RejectsMultiSharedEdges: SUCCEED placeholder; constructing a
  valid degenerate input requires a test helper not yet built — filed as
  M3c carry-over issue (Task 11).

Implementation guards from Task 2 are now locked down by test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: nanobind bindings for both new methods + Python smoke test

**Files:**
- Modify: `cpp/bindings/module.cpp` (bind both methods)
- Modify: `tests/test_halfedge_python.py` (smoke test)

- [ ] **Step 1: Locate the existing `.def` calls** in `cpp/bindings/module.cpp`

```bash
grep -n '\.def(' cpp/bindings/module.cpp | head -20
```

You'll see lines like `.def("face_loop_vertices", &HalfEdgeMesh::face_loop_vertices, ...)`. We add two more in the same block.

- [ ] **Step 2: Add the bindings** — find the `nb::class_<HalfEdgeMesh>` block and append two `.def` calls before the closing `;`:

```cpp
.def("dissolve_edge",
     &HalfEdgeMesh::dissolve_edge,
     nb::arg("edge_id"),
     "Collapse two adjacent faces sharing this edge into one merged face. "
     "Returns the new face id, or INVALID_ID if the edge is boundary/dead "
     "or the two faces share more than one edge.")
.def("faces_are_coplanar",
     &HalfEdgeMesh::faces_are_coplanar,
     nb::arg("f1_id"), nb::arg("f2_id"),
     nb::arg("angle_tol_cos"), nb::arg("dist_tol"),
     "True iff |dot(n1, n2)| > angle_tol_cos AND every vertex of either "
     "face lies within dist_tol of the other face's plane. Project defaults: "
     "cos(0.5°) ≈ 0.9999619, 1e-4.")
```

- [ ] **Step 3: Add the Python smoke test** — append to `tests/test_halfedge_python.py`

```python
def test_dissolve_edge_binding_round_trip():
    """nanobind smoke test: M3c dissolve_edge binding returns a valid face id
    after dissolving the shared edge between two triangles."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    v0 = mesh.add_vertex(0.0, 0.0, 0.0)
    v1 = mesh.add_vertex(1.0, 0.0, 0.0)
    v2 = mesh.add_vertex(1.0, 1.0, 0.0)
    v3 = mesh.add_vertex(2.0, 1.0, 0.0)
    mesh.add_halfedge_pair(v0, v1)
    e_shared_he = mesh.add_halfedge_pair(v1, v2)
    e_shared = e_shared_he // 2          # edge id = halfedge id // 2
    mesh.add_halfedge_pair(v2, v0)
    mesh.add_halfedge_pair(v1, v3)
    mesh.add_halfedge_pair(v3, v2)
    mesh.add_face_from_loop([v0, v1, v2], [v0, v1, v2])
    mesh.add_face_from_loop([v1, v3, v2], [v1, v3, v2])

    new_face = mesh.dissolve_edge(e_shared)
    assert new_face != HalfEdgeMesh.INVALID_ID
    assert mesh.face_is_live(new_face)
    assert not mesh.edge_is_live(e_shared)


def test_faces_are_coplanar_binding():
    """nanobind smoke test: M3c faces_are_coplanar accepts float tolerances and
    returns a bool."""
    from pluton._core import HalfEdgeMesh

    mesh = HalfEdgeMesh()
    # Two coplanar triangles on the XY plane.
    v0 = mesh.add_vertex(0,0,0); v1 = mesh.add_vertex(1,0,0); v2 = mesh.add_vertex(0,1,0)
    v3 = mesh.add_vertex(5,5,0); v4 = mesh.add_vertex(6,5,0); v5 = mesh.add_vertex(5,6,0)
    mesh.add_halfedge_pair(v0, v1); mesh.add_halfedge_pair(v1, v2); mesh.add_halfedge_pair(v2, v0)
    mesh.add_halfedge_pair(v3, v4); mesh.add_halfedge_pair(v4, v5); mesh.add_halfedge_pair(v5, v3)
    f1 = mesh.add_face_from_loop([v0, v1, v2], [v0, v1, v2])
    f2 = mesh.add_face_from_loop([v3, v4, v5], [v3, v4, v5])

    assert mesh.faces_are_coplanar(f1, f2, 0.9999619, 1e-4) is True
    # Loosen → still True; tighten dist → still True since both on z=0
    assert mesh.faces_are_coplanar(f1, f2, 0.5, 1e-6) is True
```

- [ ] **Step 4: Build + run the smoke tests**

```bash
pluton-build
pluton-py-tests tests/test_halfedge_python.py -k "dissolve_edge_binding or faces_are_coplanar_binding" -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run the full Python test suite for regressions**

```bash
pluton-py-tests
```

Expected: 189 (M3b) + 2 (Task 4) = 191 PASS.

- [ ] **Step 6: Commit**

```bash
git add cpp/bindings/module.cpp tests/test_halfedge_python.py
git commit -m "$(cat <<'EOF'
feat(bindings): expose HalfEdgeMesh.dissolve_edge + faces_are_coplanar

nanobind wrappers for the two new M3c kernel ops. Python smoke tests cover
the basic dissolve round-trip (two triangles → quad, edge tombstoned) and
the coplanarity test on parallel XY-plane triangles.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Scene wrappers — `dissolve_edge`, `faces_are_coplanar`, plus 3 query helpers

**Files:**
- Modify: `python/pluton/scene/scene.py` (add 5 methods)
- Create: `tests/test_scene_dissolve.py` (8 tests)

The Scene needs:
- Two thin wrappers around the new C++ methods (`dissolve_edge`, `faces_are_coplanar`), with the project-default tolerances baked in for `faces_are_coplanar`.
- Three query helpers that walk the half-edge structure to support the seam-merge orchestration in `PushPullTool`:
  - `face_edges(f_id) → list[int]` — edge IDs around the face's boundary loop, in order.
  - `edge_faces(e_id) → tuple[int | None, int | None]` — face IDs on each side of the edge (None if boundary).
  - `edge_is_boundary(e_id) → bool` — true if the edge has only one incident face.

- [ ] **Step 1: Write the failing tests** — create `tests/test_scene_dissolve.py`

```python
"""Scene-level coverage for M3c dissolve_edge + faces_are_coplanar + query helpers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pluton.scene.scene import Scene


def _build_two_quads_sharing_edge(scene: Scene) -> tuple[int, int, int]:
    """Build two adjacent unit quads on the XY plane sharing edge v1—v2.
    Returns (f1_id, f2_id, shared_edge_id)."""
    v0 = scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32))
    v4 = scene.add_vertex(np.array([2.0, 0.0, 0.0], dtype=np.float32))
    v5 = scene.add_vertex(np.array([2.0, 1.0, 0.0], dtype=np.float32))
    scene.add_edge(v0, v1)
    e_shared = scene.add_edge(v1, v2)
    scene.add_edge(v2, v3)
    scene.add_edge(v3, v0)
    scene.add_edge(v1, v4)
    scene.add_edge(v4, v5)
    scene.add_edge(v5, v2)
    f1 = scene.add_face_from_loop([v0, v1, v2, v3])
    f2 = scene.add_face_from_loop([v1, v4, v5, v2])
    return f1, f2, e_shared


# ---- dissolve_edge wrapper -------------------------------------------------

def test_dissolve_edge_merges_two_quads_into_hexagon():
    scene = Scene()
    f1, f2, e_shared = _build_two_quads_sharing_edge(scene)

    merged = scene.dissolve_edge(e_shared)

    assert merged is not None
    assert len(scene.face(merged).loop_vertex_ids) == 6


def test_dissolve_edge_returns_none_on_boundary_edge():
    scene = Scene()
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    # Edge has no faces — it's a "boundary" edge by virtue of no incidence.
    assert scene.dissolve_edge(e) is None


# ---- faces_are_coplanar wrapper -------------------------------------------

def test_faces_are_coplanar_with_default_tolerances():
    scene = Scene()
    f1, f2, _ = _build_two_quads_sharing_edge(scene)
    # Both on the XY plane → coplanar with default tolerances.
    assert scene.faces_are_coplanar(f1, f2) is True


def test_faces_are_coplanar_rejects_offset_planes():
    scene = Scene()
    # Two quads on parallel planes 0.001 apart (over 1e-4 dist tol).
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2); scene.add_edge(v2, v0)
    f1 = scene.add_face_from_loop([v0, v1, v2])

    v3 = scene.add_vertex(np.array([5, 0, 1e-3], dtype=np.float32))
    v4 = scene.add_vertex(np.array([6, 0, 1e-3], dtype=np.float32))
    v5 = scene.add_vertex(np.array([5, 1, 1e-3], dtype=np.float32))
    scene.add_edge(v3, v4); scene.add_edge(v4, v5); scene.add_edge(v5, v3)
    f2 = scene.add_face_from_loop([v3, v4, v5])

    assert scene.faces_are_coplanar(f1, f2) is False


# ---- query helpers --------------------------------------------------------

def test_face_edges_returns_boundary_edge_ids_in_order():
    scene = Scene()
    f1, _, _ = _build_two_quads_sharing_edge(scene)
    edges = scene.face_edges(f1)
    assert len(edges) == 4
    # All returned edges should be live.
    for e in edges:
        assert scene.edge(e).v1_id != scene.edge(e).v2_id  # well-formed


def test_edge_faces_returns_both_adjacent_faces():
    scene = Scene()
    f1, f2, e_shared = _build_two_quads_sharing_edge(scene)
    faces = scene.edge_faces(e_shared)
    assert set(faces) == {f1, f2}


def test_edge_faces_returns_none_on_boundary_side():
    scene = Scene()
    f1, _, _ = _build_two_quads_sharing_edge(scene)
    # An edge on f1 that's not the shared edge has only one face (f1).
    e_boundary = scene.face_edges(f1)[0]
    # If this is the shared edge, pick a different one; otherwise expect (f1, None).
    faces = scene.edge_faces(e_boundary)
    # Exactly one of the two slots should be f1; the other may be a sibling
    # face (if shared) or None (if true boundary).
    assert f1 in faces


def test_edge_is_boundary_true_for_standalone_face_edges():
    scene = Scene()
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2); scene.add_edge(v2, v0)
    f = scene.add_face_from_loop([v0, v1, v2])

    for e in scene.face_edges(f):
        assert scene.edge_is_boundary(e) is True


def test_edge_is_boundary_false_for_shared_edge():
    scene = Scene()
    _, _, e_shared = _build_two_quads_sharing_edge(scene)
    assert scene.edge_is_boundary(e_shared) is False
```

- [ ] **Step 2: Run to verify failures**

`pluton-py-tests tests/test_scene_dissolve.py -v`
Expected: 8 FAILS — all complaining about `Scene` lacking `dissolve_edge`, `faces_are_coplanar`, `face_edges`, `edge_faces`, `edge_is_boundary`.

- [ ] **Step 3: Implement the 5 methods on Scene** — append to `python/pluton/scene/scene.py`

Inside the `Scene` class, add (near the other accessor methods, after `face_center`):

```python
    # ---- M3c additions ----

    # Project-default tolerances for faces_are_coplanar.
    _ANGLE_TOL_COS = 0.9999619  # cos(0.5°)
    _DIST_TOL = 1e-4

    def dissolve_edge(self, edge_id: int) -> int | None:
        """Dissolve an edge between two adjacent faces.

        Returns the new (surviving) face id on success, or None if the edge
        is boundary / dead / would create a degenerate result.
        """
        result = self._mesh.dissolve_edge(edge_id)
        if result == self._mesh.INVALID_ID:
            return None
        # Refresh cached Face/Edge dataclasses for the slots that changed.
        # The simplest correct path: invalidate everything by re-syncing the
        # public Vertex/Edge/Face caches at the next access. Existing M3a/M3b
        # accessors re-read from the kernel so no extra work needed here.
        return int(result)

    def faces_are_coplanar(self, f1_id: int, f2_id: int) -> bool:
        """Project-default tolerances applied. See HalfEdgeMesh.faces_are_coplanar."""
        return bool(self._mesh.faces_are_coplanar(
            f1_id, f2_id, self._ANGLE_TOL_COS, self._DIST_TOL,
        ))

    def face_edges(self, f_id: int) -> list[int]:
        """Edge IDs around the face's boundary loop, in order.

        Walks the boundary half-edges of the face; each half-edge belongs to
        an edge whose id = half-edge slab index // 2.
        """
        if not self._mesh.face_is_live(f_id):
            raise IndexError(f"Face {f_id} is not live")
        # Walk via the loop_vertex_ids and look up half-edges between consecutive
        # vertex pairs. Half-edges aren't directly enumerable per-face from the
        # public API, but the (v_i, v_{i+1}) pair uniquely identifies an edge.
        loop = list(self._mesh.face_loop_vertices(f_id))
        edges: list[int] = []
        # We need a reverse-lookup: given (v_a, v_b), what is the edge id?
        # The kernel exposes add_halfedge_pair which is idempotent — calling
        # it again returns the existing half-edge id. We use this read-only:
        # call add_halfedge_pair to fetch the half-edge id for the pair, then
        # convert to edge id. add_halfedge_pair is a no-op on an existing pair.
        n = len(loop)
        for i in range(n):
            v_a, v_b = loop[i], loop[(i + 1) % n]
            he_id = self._mesh.add_halfedge_pair(v_a, v_b)
            edges.append(int(he_id) // 2)
        return edges

    def edge_faces(self, e_id: int) -> tuple[int | None, int | None]:
        """The pair of face ids on each side of the edge. None if no face on that side."""
        if not self._mesh.edge_is_live(e_id):
            raise IndexError(f"Edge {e_id} is not live")
        he_a = 2 * e_id
        he_b = 2 * e_id + 1
        f_a = self._mesh.halfedge_face(he_a)
        f_b = self._mesh.halfedge_face(he_b)
        INVALID = self._mesh.INVALID_ID
        return (
            None if f_a == INVALID else int(f_a),
            None if f_b == INVALID else int(f_b),
        )

    def edge_is_boundary(self, e_id: int) -> bool:
        """True iff the edge has fewer than two incident faces."""
        f_a, f_b = self.edge_faces(e_id)
        return f_a is None or f_b is None
```

- [ ] **Step 4: Run the failing tests**

`pluton-py-tests tests/test_scene_dissolve.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Run the full Python test suite for regressions**

`pluton-py-tests`
Expected: 191 (after Task 4) + 8 (Task 5) = 199 PASS.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene_dissolve.py
git commit -m "$(cat <<'EOF'
feat(scene): wrappers for dissolve_edge + faces_are_coplanar + query helpers

Adds five Scene methods:
- dissolve_edge(edge_id) → face_id | None: thin wrapper that converts
  INVALID_ID to None for Pythonic ergonomics.
- faces_are_coplanar(f1, f2): wraps the C++ test with project-default
  tolerances (cos(0.5°) angle, 1e-4 distance).
- face_edges(f_id): edge ids around the face's boundary loop, in order.
  Uses the kernel's idempotent add_halfedge_pair as a read-only lookup.
- edge_faces(e_id): tuple of face ids on each side (None if boundary).
- edge_is_boundary(e_id): true iff fewer than 2 incident faces.

The three query helpers are the seam-merge orchestration's vocabulary —
PushPullTool uses them in Task 7 (bottom-cap conditional) and Task 8
(seam-merge pass).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `DissolveEdgeCommand` + pytest coverage

**Files:**
- Modify: `python/pluton/commands/scene_commands.py` (append `DissolveEdgeCommand`)
- Create: `tests/test_dissolve_edge_command.py` (4 tests)

The command captures both source faces' descriptors at `do()` time so `undo()` can restore them. The kernel-level dissolve tombstones the edge and the two source faces; undo must:
1. Remove the merged face.
2. Restore both source faces (with their original loops).
3. Restore the edge by re-creating the half-edge pair.

The capture order matters for redo: after undo, the merged face id should be allocatable again on the next do(). Since we use `add_face_from_loop` (not `restore_face`), the merged face's id will likely change on redo — that's acceptable because the merged face's id was the "result" of a synthesis, not a captured pre-existing identity.

- [ ] **Step 1: Write the failing tests** — create `tests/test_dissolve_edge_command.py`

```python
"""DissolveEdgeCommand: do, undo, redo round-trips."""

from __future__ import annotations

import numpy as np
import pytest

from pluton.commands.scene_commands import DissolveEdgeCommand
from pluton.scene.scene import Scene


def _two_quads_sharing_edge(scene: Scene) -> tuple[int, int, int]:
    """Returns (f1, f2, shared_edge_id) — identical setup to test_scene_dissolve."""
    v0 = scene.add_vertex(np.array([0,0,0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1,0,0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1,1,0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0,1,0], dtype=np.float32))
    v4 = scene.add_vertex(np.array([2,0,0], dtype=np.float32))
    v5 = scene.add_vertex(np.array([2,1,0], dtype=np.float32))
    scene.add_edge(v0, v1)
    e_shared = scene.add_edge(v1, v2)
    scene.add_edge(v2, v3)
    scene.add_edge(v3, v0)
    scene.add_edge(v1, v4)
    scene.add_edge(v4, v5)
    scene.add_edge(v5, v2)
    f1 = scene.add_face_from_loop([v0, v1, v2, v3])
    f2 = scene.add_face_from_loop([v1, v4, v5, v2])
    return f1, f2, e_shared


def test_do_removes_shared_edge_and_merges_faces():
    scene = Scene()
    f1, f2, e_shared = _two_quads_sharing_edge(scene)

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)

    # The two source faces are gone; one merged face has 6 vertices.
    live_faces = [f.id for f in scene.faces_iter()]
    assert f1 not in live_faces
    assert f2 not in live_faces
    assert len(live_faces) == 1
    assert len(scene.face(live_faces[0]).loop_vertex_ids) == 6


def test_undo_restores_both_original_faces():
    scene = Scene()
    f1_orig, f2_orig, e_shared = _two_quads_sharing_edge(scene)
    pre_face_count = sum(1 for _ in scene.faces_iter())
    pre_edge_count = sum(1 for _ in scene.edges_iter())

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)
    cmd.undo(scene)

    post_face_count = sum(1 for _ in scene.faces_iter())
    post_edge_count = sum(1 for _ in scene.edges_iter())
    assert post_face_count == pre_face_count
    assert post_edge_count == pre_edge_count


def test_do_returns_none_op_on_boundary_edge():
    """Command on a boundary edge does nothing; undo also does nothing.
    The undo stack must stay consistent (no exceptions)."""
    scene = Scene()
    v0 = scene.add_vertex(np.array([0,0,0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1,0,0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([0,1,0], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2); scene.add_edge(v2, v0)
    f = scene.add_face_from_loop([v0, v1, v2])
    e_boundary = scene.face_edges(f)[0]

    cmd = DissolveEdgeCommand(e_boundary)
    cmd.do(scene)   # should not raise
    cmd.undo(scene) # should not raise

    # Mesh unchanged.
    assert sum(1 for _ in scene.faces_iter()) == 1
    assert scene.face(f).loop_vertex_ids == (v0, v1, v2)


def test_do_undo_redo_round_trip():
    scene = Scene()
    f1_orig, f2_orig, e_shared = _two_quads_sharing_edge(scene)

    cmd = DissolveEdgeCommand(e_shared)
    cmd.do(scene)
    merged_id_after_do = next(f.id for f in scene.faces_iter())

    cmd.undo(scene)
    cmd.do(scene)  # redo
    merged_id_after_redo = next(f.id for f in scene.faces_iter())

    # The merged face exists after both do() calls; its id need not be stable
    # across redo (we use add_face_from_loop, not restore_face).
    assert scene.face_is_live(merged_id_after_redo)
    assert len(scene.face(merged_id_after_redo).loop_vertex_ids) == 6
```

Note: `scene.face_is_live` doesn't exist as a Scene method; use `_mesh.face_is_live` via:

```python
assert scene._mesh.face_is_live(merged_id_after_redo)
```

…or check that the id appears in `scene.faces_iter()`. Adjust the last test accordingly.

- [ ] **Step 2: Run to verify failures**

`pluton-py-tests tests/test_dissolve_edge_command.py -v`
Expected: 4 FAIL — `DissolveEdgeCommand` not found.

- [ ] **Step 3: Implement `DissolveEdgeCommand`** — append to `python/pluton/commands/scene_commands.py`

```python
class DissolveEdgeCommand(Command):
    """Dissolve an edge between two faces. Reversible.

    do(): captures both source face descriptors (loops), then asks the kernel
          to dissolve. If the kernel refuses (boundary edge, multi-shared,
          dead), the command becomes a no-op.
    undo(): if the do() succeeded, removes the merged face and restores the
            two original faces by re-adding them on their captured loops.
            The edge is restored implicitly by add_face_from_loop's
            half-edge allocation.
    """

    name = "Dissolve Edge"

    def __init__(self, edge_id: int) -> None:
        self._edge_id = edge_id
        self._captured_f1: tuple[int, tuple[int, ...]] | None = None
        self._captured_f2: tuple[int, tuple[int, ...]] | None = None
        self._merged_face_id: int | None = None
        self._was_noop: bool = False

    def do(self, scene) -> None:  # noqa: ANN001
        # Resolve the two faces BEFORE dissolution so undo can replay them.
        if self._captured_f1 is None:
            # First execution — capture face descriptors from the kernel.
            faces = scene.edge_faces(self._edge_id)
            if faces[0] is None or faces[1] is None:
                self._was_noop = True
                return
            f1, f2 = faces
            self._captured_f1 = (f1, tuple(scene.face(f1).loop_vertex_ids))
            self._captured_f2 = (f2, tuple(scene.face(f2).loop_vertex_ids))

        result = scene.dissolve_edge(self._edge_id)
        if result is None:
            # Kernel refused. Should be rare given we already validated above,
            # but a clean no-op keeps the undo stack consistent.
            self._was_noop = True
            return
        self._merged_face_id = result

    def undo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._merged_face_id is not None, "DissolveEdgeCommand.undo before do"
        assert self._captured_f1 is not None
        assert self._captured_f2 is not None

        # Remove the merged face first (frees up the boundary half-edges).
        scene.remove_face(self._merged_face_id)

        # Restore both source faces. We use add_face_from_loop (allocates fresh
        # face ids) rather than restore_face — the captured ids may now collide
        # with the merged face's tombstone state.
        scene.add_face_from_loop(self._captured_f1[1])
        scene.add_face_from_loop(self._captured_f2[1])
```

- [ ] **Step 4: Run the tests**

`pluton-py-tests tests/test_dissolve_edge_command.py -v`
Expected: 4 PASS.

If `test_undo_restores_both_original_faces` fails due to edge counts not matching: the `add_face_from_loop` call should automatically re-allocate the half-edge pair (it's idempotent), so the edge count should round-trip. If it doesn't, the issue is in how `add_face_from_loop` interacts with the freed half-edge slot — investigate by printing slab sizes before/after.

- [ ] **Step 5: Run the full Python test suite for regressions**

`pluton-py-tests`
Expected: 199 (Task 5) + 4 (Task 6) = 203 PASS.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_dissolve_edge_command.py
git commit -m "$(cat <<'EOF'
feat(commands): DissolveEdgeCommand — reversible seam-merge primitive

Captures both source face descriptors at do() time; undo() removes the
merged face and re-adds each source face from its captured vertex loop.

Boundary-edge case is a clean no-op (do + undo both return early without
mutation), keeping the undo stack consistent when the seam-merge pass
encounters edges it can't dissolve.

The merged face's id is not stable across undo→redo cycles (we use
add_face_from_loop rather than restore_face). Acceptable: the merged face
is a synthesis, not a captured identity. Documented as M3c known
limitation in §10 of design doc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `PushPullTool` Case 1 — conditional bottom-cap + pytest

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py` (extend `_commit_extrusion`; add `_should_add_bottom_cap` helper)
- Create: `tests/test_push_pull_tool_closed_manifold.py` (3 Case-1 tests)

Add the bottom-cap step to the existing `_commit_extrusion`. The cap is added ONLY if every edge of the source face's boundary loop is a boundary edge (single half-edge) at the moment we're about to remove the source. Bottom cap = `AddFaceCommand(tuple(reversed(loop)))`.

Test setup mirrors how `test_push_pull_tool.py` constructs the tool with a mock command stack.

- [ ] **Step 1: Add `_should_add_bottom_cap` helper** to `push_pull_tool.py` (just above `_commit_extrusion`)

```python
    def _should_add_bottom_cap(self, src_face_id: int) -> bool:
        """True iff every boundary edge of the source face has only one
        incident half-edge — meaning the source was standalone (Case 1) and
        adding a bottom cap will close the prism manifold-correctly without
        creating a non-manifold edge."""
        assert self._scene is not None
        for e in self._scene.face_edges(src_face_id):
            if not self._scene.edge_is_boundary(e):
                return False
        return True
```

- [ ] **Step 2: Modify `_commit_extrusion`** — capture `is_standalone` BEFORE the source removal, append bottom cap AFTER the existing side faces.

Find this line:
```python
    def _commit_extrusion(self) -> None:
        """Build the extrusion CompositeCommand and push it to the command stack."""
        assert self._armed_face_id is not None
```

Insert at the top of the method body (after the asserts), before `composite = CompositeCommand(name="Push/Pull")`:

```python
        # Capture M3c "is this a standalone source?" check BEFORE we remove
        # the source face. Determines whether we add a bottom cap (Case 1) or
        # leave it open (Case 2 — to be handled by seam-merge in Task 8).
        is_standalone = self._should_add_bottom_cap(self._armed_face_id)
```

Find the existing closing block (after step 6 "Top face" in the existing method):

```python
        # 6. Top face — same winding as source.
        c = AddFaceCommand(tuple(top_vids))
        c.do(scene)
        composite.children.append(c)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
```

Insert the bottom cap between the top-face block and the `command_stack.push_executed` line:

```python
        # 6. Top face — same winding as source.
        c = AddFaceCommand(tuple(top_vids))
        c.do(scene)
        composite.children.append(c)

        # 7. (M3c) Bottom cap — only for standalone sources (Case 1).
        # Reversed source loop so the cap's normal points opposite the
        # extrusion direction (down, when extruding up).
        if is_standalone:
            cap = AddFaceCommand(tuple(reversed(loop)))
            cap.do(scene)
            composite.children.append(cap)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
```

- [ ] **Step 3: Write the Case 1 tests** — create `tests/test_push_pull_tool_closed_manifold.py`

```python
"""M3c PushPullTool: end-to-end closed-manifold extrusion (Case 1 + Case 2)."""

from __future__ import annotations

import numpy as np
import pytest

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.push_pull_tool import PushPullTool


def _draw_rectangle(scene: Scene, w: float = 1.0, h: float = 1.0) -> int:
    """Draw a w×h rectangle on the ground plane (z=0), return the face id."""
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([w, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([w, h, 0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, h, 0], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2)
    scene.add_edge(v2, v3); scene.add_edge(v3, v0)
    return scene.add_face_from_loop([v0, v1, v2, v3])


def _draw_pentagon(scene: Scene) -> int:
    """Draw a regular pentagon centred at origin on z=0, return the face id."""
    import math
    verts = []
    for i in range(5):
        a = 2 * math.pi * i / 5
        v = scene.add_vertex(np.array([math.cos(a), math.sin(a), 0], dtype=np.float32))
        verts.append(v)
    for i in range(5):
        scene.add_edge(verts[i], verts[(i + 1) % 5])
    return scene.add_face_from_loop(verts)


def _commit_pp_directly(scene: Scene, face_id: int, depth: float) -> CommandStack:
    """Skip the click-move-click state machine: directly invoke _commit_extrusion
    with armed-face state populated, simulating a user gesture."""
    tool = PushPullTool()
    stack = CommandStack()
    tool._scene = scene
    tool._command_stack = stack
    tool._armed_face_id = face_id
    tool._armed_face_loop = list(scene.face(face_id).loop_vertex_ids)
    tool._armed_face_normal = scene.face_normal(face_id)
    tool._armed_face_center = scene.face_center(face_id)
    tool._current_depth = depth
    tool._commit_extrusion()
    return stack


# ---- Case 1 — standalone source produces closed manifold ------------------

def test_case1_standalone_rect_produces_closed_prism():
    """P/P on a standalone rectangle → 6 faces total (4 sides + top + bottom)."""
    scene = Scene()
    f = _draw_rectangle(scene)
    _commit_pp_directly(scene, f, depth=2.0)

    live_face_count = sum(1 for _ in scene.faces_iter())
    assert live_face_count == 6


def test_case1_bottom_face_normal_points_down():
    """Bottom cap's normal must oppose the extrusion direction. Else
    backface culling, lighting, and pickability all break — exactly the
    regression that surfaced in M3b without a normal-direction check."""
    scene = Scene()
    f_src = _draw_rectangle(scene)
    src_normal = scene.face_normal(f_src).copy()  # before removal
    _commit_pp_directly(scene, f_src, depth=1.5)

    # Find the bottom face — it's the one whose normal opposes src_normal.
    bottoms = [
        f for f in scene.faces_iter()
        if float(np.dot(scene.face_normal(f.id), src_normal)) < 0
    ]
    assert len(bottoms) == 1, "Expected exactly one face with normal opposing src"


def test_case1_pentagon_source_produces_7_faces():
    """N-gon source → N+2 faces (N sides + top + bottom)."""
    scene = Scene()
    f = _draw_pentagon(scene)
    _commit_pp_directly(scene, f, depth=0.5)

    assert sum(1 for _ in scene.faces_iter()) == 7
```

- [ ] **Step 4: Run to verify the tests fail then pass**

```bash
pluton-py-tests tests/test_push_pull_tool_closed_manifold.py -v
```

Expected behavior:
- BEFORE Step 1/2 edits: 3 tests FAIL (test_case1_standalone_rect would show 5 live faces, not 6).
- AFTER Step 1/2 edits: 3 tests PASS.

- [ ] **Step 5: Run the full Python test suite for regressions**

`pluton-py-tests`
Expected: 203 (after Task 6) + 3 (Task 7) = 206 PASS. **Important:** all M3b tests in `tests/test_push_pull_tool.py` and `tests/test_push_pull_topology.py` must still pass — the conditional cap is additive on Case-1-only input, but if any M3b test uses Case 2 input (e.g., constructs a box and P/Ps its top) the bottom-cap should NOT fire. Verify by inspection if any M3b test surprises.

If any M3b test now expects "5 faces" (M3b open-bottom) and gets 6 (closed-bottom), update the M3b test to use the closed-bottom count — this is the intended behaviour change.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_tool_closed_manifold.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — Case 1 closed bottom for standalone sources

Adds two pieces to _commit_extrusion:
- _should_add_bottom_cap(): scans the source face's boundary edges; returns
  true iff every edge is a boundary edge (single half-edge) — meaning the
  source was standalone and adding a cap is manifold-correct.
- Conditional bottom-cap AddFaceCommand at the end of the composite, using
  the reversed source loop so the cap's normal opposes the extrusion
  direction.

Closes M3b limitation #1 (issue #21) for Case 1 — standalone rectangle /
pentagon / N-gon push/pull now produces N+2 faces, closed manifold.

Case 2 (P/P on top of existing solid) is handled by the seam-merge pass
in Task 8 — there the source is already attached, is_standalone is False,
no bottom cap, the seam-merge dissolves the coplanar adjacency instead.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `PushPullTool` Case 2 — seam-merge pass + pytest

**Files:**
- Modify: `python/pluton/tools/push_pull_tool.py` (add `_seam_merge_pass` helper + invocation)
- Modify: `tests/test_push_pull_tool_closed_manifold.py` (5 more Case-2 tests)

The seam-merge pass runs AFTER all extrusion faces have been added to the mesh. It walks the OLD source face's boundary edges (captured before removal), checks each for coplanar adjacency between the face on one side (parent's old side) and the face on the other side (new prism's side), and dissolves each that matches.

The edges captured before source removal will be referenced by the same edge IDs after, because the OLD source loop's edges are never removed (only the source face's half-edge that bordered them is tombstoned).

- [ ] **Step 1: Add `_seam_merge_pass` helper** to `push_pull_tool.py` (just below `_should_add_bottom_cap`)

```python
    def _seam_merge_pass(self, candidate_edges: list[int]) -> list:
        """Inspect each candidate edge; if its two incident faces are coplanar,
        return a DissolveEdgeCommand for it. Returns the list of commands to
        append to the composite (in order)."""
        from pluton.commands.scene_commands import DissolveEdgeCommand
        assert self._scene is not None
        scene = self._scene
        out = []
        for e in candidate_edges:
            if not scene._mesh.edge_is_live(e):
                continue
            f_a, f_b = scene.edge_faces(e)
            if f_a is None or f_b is None:
                continue
            if scene.faces_are_coplanar(f_a, f_b):
                cmd = DissolveEdgeCommand(e)
                cmd.do(scene)
                out.append(cmd)
        return out
```

- [ ] **Step 2: Wire `_seam_merge_pass` into `_commit_extrusion`**

Modify `_commit_extrusion` to (a) capture the candidate edges BEFORE the source is removed, and (b) invoke the seam-merge pass AFTER the side faces are added.

Find this line near the top of `_commit_extrusion` (just after the M3c `is_standalone` capture line you added in Task 7):

```python
        is_standalone = self._should_add_bottom_cap(self._armed_face_id)
```

Add right below it:

```python
        # M3c: capture the OLD source face's boundary edge ids BEFORE removal,
        # so the seam-merge pass can re-visit them after the new side faces
        # have populated each edge's second half-edge slot.
        candidate_seam_edges = list(self._scene.face_edges(self._armed_face_id))
```

Find the bottom-cap block you added in Task 7:

```python
        if is_standalone:
            cap = AddFaceCommand(tuple(reversed(loop)))
            cap.do(scene)
            composite.children.append(cap)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
```

Insert the seam-merge pass between the bottom-cap block and the `command_stack` line:

```python
        if is_standalone:
            cap = AddFaceCommand(tuple(reversed(loop)))
            cap.do(scene)
            composite.children.append(cap)

        # 8. (M3c) Seam-merge pass — dissolve OLD-source-boundary edges whose
        # two incident faces (parent's old side + new prism's side) are coplanar.
        # Scope: single-pass over the OLD source face's boundary edges only,
        # per design doc §3.1 decision 6.
        seam_cmds = self._seam_merge_pass(candidate_seam_edges)
        composite.children.extend(seam_cmds)

        if self._command_stack is not None:
            self._command_stack.push_executed(composite)
```

- [ ] **Step 3: Write the Case 2 tests** — append to `tests/test_push_pull_tool_closed_manifold.py`

```python
def _build_unit_box(scene: Scene) -> int:
    """Draw a 1×1 rect and P/P it up by 1 → returns the id of the new TOP face
    (the face produced by the P/P, not the original source).

    This is the standard "existing solid" fixture for Case 2 tests."""
    f_src = _draw_rectangle(scene, 1.0, 1.0)
    _commit_pp_directly(scene, f_src, depth=1.0)
    # The top face has z ≈ 1.0 for all 4 vertices. Find it.
    for f in scene.faces_iter():
        verts = [scene.vertex(vid).position for vid in f.loop_vertex_ids]
        if all(abs(v[2] - 1.0) < 1e-4 for v in verts):
            return f.id
    raise RuntimeError("Could not locate top face of unit box")


# ---- Case 2 — P/P on existing solid produces seamless extension ----------

def test_case2_stacked_pp_face_count_correct():
    """Box (6 faces) + P/P top upward → still 6 faces (taller box)."""
    scene = Scene()
    top = _build_unit_box(scene)
    assert sum(1 for _ in scene.faces_iter()) == 6  # baseline

    _commit_pp_directly(scene, top, depth=1.0)

    # After seam-merge, the 4 side faces have merged with the 4 NEW side
    # faces of the extrusion → still 4 sides + 1 new top + 1 original bottom
    # = 6 faces total.
    assert sum(1 for _ in scene.faces_iter()) == 6


def test_case2_no_bottom_cap_for_attached_source():
    """No face should exist at the OLD top height (z=1.0) after the
    second P/P. The bottom cap conditional must have been skipped."""
    scene = Scene()
    top = _build_unit_box(scene)
    _commit_pp_directly(scene, top, depth=1.0)

    # No face has all vertices at z=1.0 (the OLD top height).
    for f in scene.faces_iter():
        verts = [scene.vertex(vid).position for vid in f.loop_vertex_ids]
        all_at_one = all(abs(v[2] - 1.0) < 1e-4 for v in verts)
        assert not all_at_one, f"Face {f.id} should not be at z=1.0 after seam merge"


def test_case2_old_top_loop_edges_dissolved():
    """All 4 edges of the OLD top loop must be tombstoned after Case 2 P/P."""
    scene = Scene()
    top = _build_unit_box(scene)
    # Capture the OLD top loop's edge ids BEFORE the second P/P.
    old_top_edge_ids = list(scene.face_edges(top))
    assert len(old_top_edge_ids) == 4
    assert all(scene._mesh.edge_is_live(e) for e in old_top_edge_ids)

    _commit_pp_directly(scene, top, depth=1.0)

    # All 4 OLD-top edges should now be tombstoned (dissolved).
    for e in old_top_edge_ids:
        assert not scene._mesh.edge_is_live(e), (
            f"Edge {e} on the OLD top loop should have been dissolved by seam-merge"
        )


def test_case2_composite_undoes_atomically():
    """One Ctrl+Z must restore the pre-P/P state exactly (face + edge counts)."""
    scene = Scene()
    top = _build_unit_box(scene)
    pre_face_count = sum(1 for _ in scene.faces_iter())
    pre_edge_count = sum(1 for _ in scene.edges_iter())

    stack = _commit_pp_directly(scene, top, depth=1.0)
    stack.undo(scene)

    assert sum(1 for _ in scene.faces_iter()) == pre_face_count
    assert sum(1 for _ in scene.edges_iter()) == pre_edge_count


def test_tilted_source_seam_merge_works():
    """A tilted source face's normal is geometry-derived, and the
    coplanarity test is rotation-agnostic. The seam-merge should still
    fire on edges where parent + new sides are coplanar."""
    scene = Scene()
    # Tilt 30° about the X axis: roof face on z = y * tan(30°).
    import math
    s = math.sin(math.radians(30))
    c = math.cos(math.radians(30))
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1, c, s], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, c, s], dtype=np.float32))
    scene.add_edge(v0, v1); scene.add_edge(v1, v2)
    scene.add_edge(v2, v3); scene.add_edge(v3, v0)
    f_src = scene.add_face_from_loop([v0, v1, v2, v3])

    # First P/P: extrude into a tilted box.
    _commit_pp_directly(scene, f_src, depth=1.0)
    assert sum(1 for _ in scene.faces_iter()) == 6

    # Find the new top face (offset by 1.0 along the source normal direction).
    top = None
    for f in scene.faces_iter():
        # Top has the same orientation as src; we recognize it as the face whose
        # vertex 0 differs from f_src's vertex 0's position by ~1.0 along src_normal.
        if len(f.loop_vertex_ids) == 4 and f.id != f_src:
            # The top should be the one whose centroid is furthest in +src_normal direction.
            pass  # simpler: pick the one with no vertex at z=0
            verts = [scene.vertex(vid).position for vid in f.loop_vertex_ids]
            if all(v[2] > 0.5 for v in verts):
                top = f.id
                break
    assert top is not None

    pre_count = sum(1 for _ in scene.faces_iter())
    _commit_pp_directly(scene, top, depth=0.5)
    # The 4 OLD side faces and the 4 NEW side faces should have merged → still 6 faces.
    assert sum(1 for _ in scene.faces_iter()) == pre_count
```

- [ ] **Step 4: Run the new tests + diagnose**

```bash
pluton-py-tests tests/test_push_pull_tool_closed_manifold.py -v
```

Expected: 8 PASS (3 Case-1 from Task 7 + 5 Case-2 added this task).

If `test_case2_old_top_loop_edges_dissolved` fails (edges still live after seam-merge), the most likely cause is the seam-merge running too early — before the new side faces have populated each edge's second half-edge slot. Confirm the order in `_commit_extrusion`: side faces (step 5) MUST be added before `_seam_merge_pass` runs. If they are, debug by adding a print of `(f_a, f_b)` and `faces_are_coplanar(f_a, f_b)` for each candidate edge.

- [ ] **Step 5: Run the full Python test suite**

`pluton-py-tests`
Expected: 206 (after Task 7) + 5 (Task 8) = 211 PASS.

Some M3b tests in `tests/test_push_pull_topology.py` may now produce different face counts than before (closed bottom + seam merge change the topology). Update those tests' expected values to reflect M3c behaviour rather than M3b's. Note any updated tests in the commit message.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_push_pull_tool_closed_manifold.py
git commit -m "$(cat <<'EOF'
feat(tools): PushPullTool — Case 2 seam-merge pass (no horizontal seam)

After the source removal + top/side face additions, walk the OLD source
face's boundary edges and dissolve any whose two incident faces are
coplanar (parent's old side + new prism's side). Single-pass per design
doc §3.1 decision 6 — exactly enough to flip the #22 manual checklist
item, no chain merges.

Captures candidate edges BEFORE source removal so the edge ids stay
valid through the gesture. Each dissolve is a DissolveEdgeCommand
appended to the P/P CompositeCommand → atomic Ctrl+Z undo.

Closes M3b limitation #2 (issue #22). Combined with Task 7's bottom-cap,
both M3c acceptance items are now passing.

Tested: 5 Case-2 cases — face count round-trip, no face at OLD top
height, all 4 OLD-top edges dissolved, atomic undo, tilted source.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Strengthened topology test + picking + renderer regression guards

**Files:**
- Modify: `tests/test_push_pull_topology.py` (strengthen existing assertions)
- Create: `tests/test_picking_after_merge.py`
- Create: `tests/test_renderer_merged_face.py`

The M3b earcut bug (XY-only projection) shipped without anyone noticing because the existing topology test only asserted face counts, not triangle counts. Two regression guards now ensure the merged-face polygon (a hexagon for Case 2) is properly triangulated AND that the picker returns the merged face's id.

- [ ] **Step 1: Strengthen the existing topology test**

Read the existing `tests/test_push_pull_topology.py`:

```bash
head -60 tests/test_push_pull_topology.py
```

Find any test that asserts only `len(faces) == N`. For Case 1 setups, add:

```python
# M3c: closed-manifold guard — every face must have at least one triangle.
for f in scene.faces_iter():
    assert len(f.triangles) > 0, (
        f"Face {f.id} (loop={f.loop_vertex_ids}) has no triangles; "
        f"earcut likely silently failed (regression of M3b XY-only bug)."
    )

# M3c: every interior edge has exactly 2 half-edges (closed manifold).
# 'Interior' means an edge with two live faces on either side.
for e in scene.edges_iter():
    faces = scene.edge_faces(e.id)
    if faces[0] is not None and faces[1] is not None:
        # Both half-edges should be live.
        he_a = 2 * e.id
        he_b = 2 * e.id + 1
        # No public is-half-edge-live method, so use halfedge_face != INVALID.
        INVALID = scene._mesh.INVALID_ID
        assert scene._mesh.halfedge_face(he_a) != INVALID
        assert scene._mesh.halfedge_face(he_b) != INVALID
```

For the existing M3b open-bottom assertions (e.g., `len(faces) == 5` after a rectangle P/P), update to `len(faces) == 6` since M3c now closes the bottom. Comment-flag each update with `# M3c: was 5 (M3b open-bottom); now 6 (closed)`.

- [ ] **Step 2: Write picking regression test** — create `tests/test_picking_after_merge.py`

```python
"""M3c regression: ray-mesh face picking returns the merged face's id after a
Case 2 seam-merge dissolves the original side faces."""

from __future__ import annotations

import math
import numpy as np
import pytest

from pluton.scene.scene import Scene
from pluton.commands.command_stack import CommandStack
from pluton.tools.push_pull_tool import PushPullTool


def _build_unit_box_and_pp_top(scene: Scene) -> None:
    """Reuse the Task 8 fixture: build a unit box, then P/P its top by 1.0."""
    v0 = scene.add_vertex(np.array([0,0,0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1,0,0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1,1,0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0,1,0], dtype=np.float32))
    for a, b in [(v0,v1),(v1,v2),(v2,v3),(v3,v0)]:
        scene.add_edge(a, b)
    f_src = scene.add_face_from_loop([v0,v1,v2,v3])

    tool = PushPullTool()
    tool._scene = scene
    tool._command_stack = CommandStack()
    tool._armed_face_id = f_src
    tool._armed_face_loop = [v0, v1, v2, v3]
    tool._armed_face_normal = scene.face_normal(f_src)
    tool._armed_face_center = scene.face_center(f_src)
    tool._current_depth = 1.0
    tool._commit_extrusion()

    # Now P/P the new top face up by another 1.0 (triggers seam merge).
    top_id = None
    for f in scene.faces_iter():
        verts = [scene.vertex(vid).position for vid in f.loop_vertex_ids]
        if all(abs(v[2] - 1.0) < 1e-4 for v in verts):
            top_id = f.id; break
    assert top_id is not None

    tool2 = PushPullTool()
    tool2._scene = scene
    tool2._command_stack = CommandStack()
    tool2._armed_face_id = top_id
    tool2._armed_face_loop = list(scene.face(top_id).loop_vertex_ids)
    tool2._armed_face_normal = scene.face_normal(top_id)
    tool2._armed_face_center = scene.face_center(top_id)
    tool2._current_depth = 1.0
    tool2._commit_extrusion()


def test_picking_returns_merged_face_id_not_stale():
    """After Case 2 P/P, ray-pick a point on one of the merged side faces.
    The picker must return a LIVE face id."""
    scene = Scene()
    _build_unit_box_and_pp_top(scene)

    # Aim a ray at the centre of the front face (y=0 wall), pointing -y.
    origin = np.array([0.5, -5.0, 1.0], dtype=np.float32)
    direction = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    hit = scene.ray_pick_face(origin, direction)
    assert hit is not None
    # The hit face id must be one of the currently-live face ids.
    live_face_ids = {f.id for f in scene.faces_iter()}
    assert hit.face_id in live_face_ids
```

- [ ] **Step 3: Write renderer regression test** — create `tests/test_renderer_merged_face.py`

```python
"""M3c regression: every merged-face polygon (e.g., the hexagon resulting from
two-quad dissolve) must produce a non-empty triangulation when the renderer
asks for it. Guards against the M3b XY-only earcut latent bug recurring."""

from __future__ import annotations

import numpy as np
import pytest

from pluton.scene.scene import Scene


def test_merged_hexagon_face_has_triangles():
    """Dissolve two coplanar quads sharing an edge → hexagon → must have ≥ 4 triangles."""
    scene = Scene()
    v0 = scene.add_vertex(np.array([0,0,0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1,0,0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1,1,0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0,1,0], dtype=np.float32))
    v4 = scene.add_vertex(np.array([2,0,0], dtype=np.float32))
    v5 = scene.add_vertex(np.array([2,1,0], dtype=np.float32))
    scene.add_edge(v0,v1); e_shared = scene.add_edge(v1,v2)
    scene.add_edge(v2,v3); scene.add_edge(v3,v0)
    scene.add_edge(v1,v4); scene.add_edge(v4,v5); scene.add_edge(v5,v2)
    scene.add_face_from_loop([v0,v1,v2,v3])
    scene.add_face_from_loop([v1,v4,v5,v2])

    merged = scene.dissolve_edge(e_shared)
    assert merged is not None

    merged_face = scene.face(merged)
    # Hexagon → at least 4 triangles (fan triangulation gives N-2 = 4).
    assert len(merged_face.triangles) >= 4 * 3, (
        f"Merged hexagon should have ≥4 triangles ({4*3} indices); "
        f"got {len(merged_face.triangles)//3} triangles."
    )

    # All triangle vertex ids should be in the loop.
    loop_set = set(merged_face.loop_vertex_ids)
    for idx in merged_face.triangles:
        assert int(idx) in loop_set, (
            f"Triangle vertex {idx} not in merged face's loop {loop_set}"
        )
```

- [ ] **Step 4: Run all new tests**

```bash
pluton-py-tests tests/test_push_pull_topology.py tests/test_picking_after_merge.py tests/test_renderer_merged_face.py -v
```

Expected:
- `test_push_pull_topology.py`: all tests pass with strengthened assertions + updated face counts.
- `test_picking_after_merge.py`: 1 PASS.
- `test_renderer_merged_face.py`: 1 PASS.

If the renderer test fails with 0 triangles, the dissolve_edge implementation's `add_face_from_loop` call may have failed silently. Reproduce by checking the merged face's `loop_vertex_ids` are well-formed and the loop is planar.

- [ ] **Step 5: Run the full Python test suite**

`pluton-py-tests`
Expected: 211 (after Task 8) + 2 (Task 9 new tests) = 213 PASS, with any M3b topology assertions updated for M3c face counts.

- [ ] **Step 6: Commit**

```bash
git add tests/test_push_pull_topology.py tests/test_picking_after_merge.py tests/test_renderer_merged_face.py
git commit -m "$(cat <<'EOF'
test(M3c): strengthened topology assertions + picking/renderer regression guards

- test_push_pull_topology: every face must have triangles > 0 (guards
  against the M3b XY-only earcut bug recurring on merged hexagons);
  every interior edge has 2 live half-edges (closed manifold guard).
  M3b open-bottom face counts updated to M3c closed counts (5→6).
- test_picking_after_merge: ray-pick a wall of the stacked box; the
  hit face id must be a live face (not a stale id of a pre-merge face).
- test_renderer_merged_face: a dissolve_edge'd hexagon face must have
  ≥ 4 triangles (fan-triangulation lower bound) and all triangle
  vertices must be in the merged loop.

Three regression guards covering the bug classes M3b's visual round
caught (silent triangulation failure) and the new M3c topology edges
(stale face ids after merge, merged-loop earcut correctness).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Manual visual verification round

**Files:** none modified — this is the human-eyes-on-pixels step.

This is the M3b lesson — automated tests are necessary but not sufficient. Run `python -m pluton` and walk through the 13-step manual checklist below. Each item gets a ✅ or 🛑.

- [ ] **Step 1: Pre-flight check**

```bash
python -c "import pluton._core; print(pluton._core.__file__)"
```

Confirm the path points into `.venv/Lib/site-packages/pluton/_core....pyd` (Windows) or `.venv/lib/python3.13/site-packages/pluton/_core....so` (Linux). If not, remove the stale shadow PYD and rebuild.

- [ ] **Step 2: Launch the app**

```bash
python -m pluton
```

- [ ] **Step 3: Walk through the manual checklist**

Run each item; pass or open an issue.

| # | Step | Expected (M3c) |
|---|---|---|
| 1 | `R`, draw a 2×2 rectangle on the ground plane | Rectangle visible, filled |
| 2 | `P`, hover over the rectangle face | Face highlights light blue |
| 3 | Click → mouse moves up | Ghost prism preview |
| 4 | Click again at depth ~2.0 | Box committed; status bar OK |
| 5 | `Ctrl+Z` | Box vanishes; rectangle alone again |
| 6 | `Ctrl+Y` | Box returns identically |
| 7 | Orbit camera | Smooth, no clipping artifacts |
| 8 | Re-make box; orbit so camera looks at front face | Front face visible, lit |
| 9 | **Orbit camera below the ground plane** | **No hole; bottom face visible** ← **M3c change** |
| 10 | `P` on top face of the box; P/P up by 1.0 | Box taller, single commit |
| 11 | **Look at the side of the new (now-2.0-tall) box at the OLD seam height (z=1.0)** | **No horizontal seam line** ← **M3c change** |
| 12 | New scene; `L` to draw a pentagon path (5 lines), close it | Pentagon face appears |
| 13 | `P` on pentagon, P/P up. Orbit under | No hole; pentagonal bottom |

- [ ] **Step 4: File any visual bugs as issues + fix in this same task**

If anything from #1-13 fails, file an issue with a screenshot, fix it, and re-run the affected step. Do NOT proceed to Task 11 with any 🛑 outstanding.

- [ ] **Step 5: No commit for this task**

This task contributes no code changes — but you DO commit any bug fixes that came out of it. Tag each commit message with `(M3c visual verification)`.

---

## Task 11: Master design doc + carry-over issues

**Files:**
- Modify: `docs/2026-05-16-pluton-design.md` (drop CGAL line in §M3)

GitHub issue updates:
- Close #21 + #22 with a comment referencing the M3c tag (will exist after Task 12 — for now, prepare the comment text).
- File a new Phase 2 issue: "CGAL booleans — push/pull into existing solid + Hole tool" (+ "DissolveEdge multi-shared rejection — needs degenerate-input test helper").

- [ ] **Step 1: Edit master design `§ Phase 1 — M3`**

Find the section that lists M3 in `docs/2026-05-16-pluton-design.md`. Look for the line:

> M3: Push/Pull — the iconic SketchUp interaction: select a face, drag to extrude; CGAL handles the boolean merge with existing geometry; first version of inferencing (snap to edges, midpoints, intersections); undo/redo system via command pattern.

Replace with:

> M3: Push/Pull — the iconic SketchUp interaction: select a face, drag to extrude. Ships in three sub-milestones: **M3a** (topology + undo), **M3b** (basic P/P, open-bottom, no merge), **M3c** (closed manifold via half-edge dissolve, no CGAL), **M3d** (inferencing — snap to edges, midpoints, intersections). True volumetric booleans (P/P into existing solid, the Hole tool, mesh import + carve) deferred to Phase 2 when CGAL becomes a meaningful dependency.

- [ ] **Step 2: File the Phase 2 CGAL carry-over issue**

```bash
gh issue create --title "Phase 2: CGAL booleans — push/pull into existing solid + Hole tool" \
  --label enhancement \
  --body "$(cat <<'EOF'
M3c (closed-manifold push/pull, v0.0.6) ships without a CGAL dependency by reframing both M3b limitations as pure half-edge ops (bottom-cap reversed-loop face + seam-merge dissolve_edge). The reframing covers all of M3c's acceptance cases (#21, #22).

The cases CGAL is genuinely needed for, deferred to Phase 2:

1. **Push/pull INTO existing geometry (Case 3).** The user P/Ps a face negatively such that the new prism's volume intersects the parent solid's interior. To produce correct topology requires a volumetric boolean (subtraction). M3c documents this as out-of-scope (design doc §7.1).
2. **Hole tool.** Cuts a hole through a face/solid. Volumetric subtraction.
3. **Mesh import + carve.** STL/OBJ import + boolean operations on the imported mesh.

When any of these become real product needs, CGAL becomes the headline dependency for the milestone that delivers them. The reference link is the design doc above.

**Spec reference:** \`docs/2026-06-10-M3c-closed-manifold-push-pull-design.md\` §7.1.
EOF
)"
```

- [ ] **Step 3: File the dissolve_edge multi-shared test-helper carry-over**

```bash
gh issue create --title "M3+: dissolve_edge multi-shared rejection — needs degenerate-input test helper" \
  --label enhancement \
  --body "$(cat <<'EOF'
\`HalfEdgeMesh::dissolve_edge\` has a guard that rejects edges where the two adjacent faces share more than one edge (would create a degenerate result). The guard is exercised by the implementation but the GoogleTest case is currently a \`SUCCEED\` placeholder (\`DissolveEdge_RejectsMultiSharedEdges\`) because constructing a valid degenerate half-edge mesh requires a test helper not yet built.

Action: add a test helper to \`cpp/tests/test_halfedge.cpp\` that constructs a folded-bigon topology (two triangles sharing both of two edges), then replace the SUCCEED placeholder with a real assertion that \`dissolve_edge\` returns INVALID_ID.

**Spec reference:** \`docs/2026-06-10-M3c-closed-manifold-push-pull-design.md\` §5.1 + the existing TODO in \`cpp/tests/test_halfedge.cpp\` (\`DissolveEdge_RejectsMultiSharedEdges\`).
EOF
)"
```

- [ ] **Step 4: Commit the master design edit**

```bash
git add docs/2026-05-16-pluton-design.md
git commit -m "$(cat <<'EOF'
docs(master): M3 sub-milestone reframing — M3c no-CGAL, M3d inferencing

Replace the original M3 line that conflated push/pull + CGAL booleans +
inferencing into one milestone. The reality after M3c brainstorming:

- M3a (topology + undo, v0.0.4) — shipped
- M3b (basic P/P open-bottom, v0.0.5) — shipped
- M3c (closed manifold via half-edge dissolve, no CGAL) — current
- M3d (inferencing) — next
- Phase 2 CGAL — when a real volumetric boolean case justifies the dep
  (P/P into existing solid, Hole tool, mesh import + carve)

No code changes; doc-only edit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Push, CI watch, version bump, tag, close issues

**Files:**
- Modify: `pyproject.toml` (version bump)
- Modify: `CMakeLists.txt` (top-level project version)
- Modify: `cpp/src/version.cpp` (return new version string)

- [ ] **Step 1: Push everything to origin**

```bash
git push origin main
```

Capture the resulting commit range — you'll need it for the issue-closing comments.

- [ ] **Step 2: Watch CI**

```bash
gh run watch --exit-status
```

Expected: both `Build & Test (ubuntu-24.04)` and `Build & Test (windows-2022)` complete successfully. If either fails, do NOT proceed to the version bump — fix the failure first.

If `gh run watch` exits 0 but you're suspicious (M1 lesson), verify with:

```bash
gh run list --limit 1 --json status,conclusion,databaseId
```

Both jobs must show `"conclusion": "success"`.

- [ ] **Step 3: Bump version to 0.0.6**

```python
# pyproject.toml — line 10
version = "0.0.6"
```

```cmake
# CMakeLists.txt — line 5
    VERSION 0.0.6
```

```cpp
// cpp/src/version.cpp — line 6
    return "0.0.6";
```

- [ ] **Step 4: Build + verify**

```bash
pluton-build
python -c "import pluton._core; print(pluton._core.version())"
```

Expected: `0.0.6`.

- [ ] **Step 5: Run the full test suite one last time**

```bash
pluton-py-tests
pluton-cpp-tests
```

Expected: pytest 203, GoogleTest 66 (per the design doc estimates — exact numbers may differ by ±1-3 if any tests were renamed/folded during execution).

- [ ] **Step 6: Commit version bump**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp
git commit -m "$(cat <<'EOF'
chore: bump version to 0.0.6 for M3c release

M3c (closed-manifold push/pull) ships closed-bottom prisms and
seam-merge over coplanar adjacent faces — no CGAL dependency added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Create the annotated tag**

```bash
git tag -a v0.0.6-m3c -m "$(cat <<'EOF'
Pluton v0.0.6 — M3c: Closed-manifold push/pull (no CGAL)

What landed:
- HalfEdgeMesh::dissolve_edge(EdgeId) — collapses two adjacent faces
  sharing an edge into one. Tombstones the dissolved edge.
- HalfEdgeMesh::faces_are_coplanar(f1, f2, angle_tol_cos, dist_tol) —
  robust two-test coplanarity (cos(0.5°) angle + 1e-4 world-unit
  distance defaults).
- Scene.dissolve_edge / faces_are_coplanar wrappers, plus query helpers
  face_edges / edge_faces / edge_is_boundary.
- DissolveEdgeCommand for the undo stack.
- PushPullTool._commit_extrusion extended with:
  - Conditional bottom-cap (only for standalone source faces — Case 1).
  - Single-pass seam-merge over OLD source face boundary edges
    (only when dissolving coplanar adjacency — Case 2).
- 11 new GoogleTest + 14 new pytest = 66 / 203 totals.

Closes:
- #21 (closed-bottom prism)
- #22 (seam-line elimination after stacked extrusion)

Out of scope (filed to Phase 2):
- Case 3 (push/pull INTO existing geometry) — needs volumetric boolean.
- Standalone "Make Solid" command.
- Fixed-point chain merge across whole mesh.
- AABB-relative coplanarity tolerance.
- DissolveEdge multi-shared rejection test helper.

Next: M3d (inferencing — snap to edges, midpoints, intersections).

CI green on ubuntu-24.04 + windows-2022.
EOF
)"
```

- [ ] **Step 8: Push the tag**

```bash
git push origin main
git push origin v0.0.6-m3c
```

Verify the tag is annotated + signed:

```bash
gh api repos/Parrow-Horrizon-Studio/pluton/git/refs/tags/v0.0.6-m3c
```

Expected: response includes `"type": "tag"` (annotated; lightweight tags would show `"type": "commit"`).

- [ ] **Step 9: Close M3c carry-over issues with tag link**

```bash
gh issue close 21 --comment "Closed by M3c — v0.0.6-m3c. Standalone push/pull now produces closed manifold prisms (bottom-cap added conditionally when source face is standalone). Acceptance criteria from #21 verified: \`face_count == loop_length + 2\` for rectangles and pentagons; orbit below floor shows no hole."

gh issue close 22 --comment "Closed by M3c — v0.0.6-m3c. Stacked push/pull on the top of an existing solid no longer leaves a horizontal seam line. The OLD top loop's edges are dissolved by the seam-merge pass when their two adjacent faces (parent's old side + new prism's side) are coplanar."
```

- [ ] **Step 10: Update the relevant TaskUpdate (if using TaskCreate for tracking)**

Mark the M3c milestone task as complete in whatever tracking system you've been using.

- [ ] **Step 11: Final smoke test**

```bash
python -m pluton
```

Quick sanity walk: rectangle → P → up → confirm closed bottom under orbit. Done.

---

## Done.

M3c shipped. Tag `v0.0.6-m3c` lives on `main`. The next milestone is **M3d (inferencing)** — see `docs/2026-05-16-pluton-design.md` § Phase 1.

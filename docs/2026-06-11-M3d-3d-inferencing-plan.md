# M3d — 3D Inferencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift Pluton's inferencing from the M2 ground-plane-only `SnapEngine` into full 3D (raycast + screen-space proximity), add the On-Edge / On-Face / Intersection inferences with distinct glyph+color markers, and add a `split_edge` topology op so midpoint/on-edge/intersection snaps build clean manifold geometry.

**Architecture:** A new `Camera.world_to_screen` primitive enables screen-space candidate ranking. The `SnapEngine.snap()` signature changes to derive the cursor *ray* (and ground hit) internally from `(cursor_screen, viewport_size, camera)`, then evaluates 3D candidates and returns the highest-precedence one. A new C++ `split_edge(e, t)` kernel op (returning a `SplitEdgeResult` struct) plus an id-preserving `SplitEdgeCommand` let the Line/Rectangle tools split an edge when a snap lands on its interior.

**Tech Stack:** C++20 half-edge kernel (nanobind bindings) · Python 3.13 · numpy · PySide6/PyOpenGL viewport · GoogleTest (ctest) · pytest.

**Spec:** `docs/2026-06-11-M3d-3d-inferencing-design.md` (Tier 2).

**Clarification vs spec:** D9 said `split_edge` returns `VertexId`; to satisfy D10's id-preserving undo it returns a `SplitEdgeResult { vertex, edge_a, edge_b, face_a, face_b }` struct instead (INVALID_ID for an absent face on a boundary edge).

---

## Conventions for every task

- **Run all commands from the `pluton/` directory.**
- **Interpreter is the venv, explicitly:** `.venv\Scripts\python.exe` (never bare `python` — the bash shell defaults to a different, drifting editable install).
- **Rebuild the C++ extension after any `cpp/` change:** `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation`
- **Build + run C++ (GoogleTest) tests:** `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure`
- **Run a pytest file:** `.venv\Scripts\python.exe -m pytest tests/<file>.py -v`
- **Git:** work on `main`; stage **specific files only** (never `git add -A`/`.`); never `--no-verify`, never `--amend`, never `--no-gpg-sign` (SSH signing is on and must stay on). End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **Do not touch version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) except in Task 14.

---

## File structure

| File | Responsibility | Task |
|------|----------------|------|
| `python/pluton/viewport/camera.py` | + `world_to_screen` (inverse of `ray_from_screen`) | 1 |
| `cpp/include/pluton/halfedge.h` | + `SplitEdgeResult` struct, `split_edge` decl | 2 |
| `cpp/src/halfedge.cpp` | + `split_edge` impl (+ `build_split_face` helper) | 2,3 |
| `cpp/bindings/module.cpp` | bind `SplitEdgeResult` + `split_edge` | 4 |
| `python/pluton/scene/scene.py` | + `split_edge` wrapper, `point_on_edge`, `closest_point_on_edge` | 5 |
| `python/pluton/commands/scene_commands.py` | + `SplitEdgeCommand` (id-preserving do/undo/redo) | 6 |
| `python/pluton/viewport/snap_engine.py` | new `SnapKind`s, ray-based `snap()`, 3D candidate generators, shared marker color map + precedence | 7,8,9,10 |
| `python/pluton/viewport/scene_renderer.py` | per-kind glyph table (triangle / diamond / X / square) | 11 |
| `python/pluton/viewport/viewport_widget.py` | `_snap_for_event` → new `snap()` signature | 8 |
| `python/pluton/tools/line_tool.py`, `rectangle_tool.py` | consume 3D snaps; split-on-edge gesture commit | 12 |
| `tests/*` | GoogleTest + pytest per task | all |

**Task dependency:** 1 is independent. 2→3→4→5→6 is the split_edge chain. 7→8→9→10 is the snap-engine chain (7 also unblocks 11). 12 depends on 6 + 10 + 11. 13 depends on all. 14 is the release.

---

### Task 1: `Camera.world_to_screen`

**Files:**
- Modify: `python/pluton/viewport/camera.py` (add method after `ray_from_screen`, ~line 186)
- Test: `tests/test_camera.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_camera.py`:

```python
# --- world_to_screen -------------------------------------------------------


def test_world_to_screen_roundtrips_with_ray_from_screen():
    """A world point projected to screen, then turned back into a ray, yields a
    ray that passes through the original point."""
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    world = np.array([1.0, 2.0, 0.5], dtype=np.float32)

    sx, sy, depth = cam.world_to_screen(world, 1280, 800)
    assert depth > 0.0  # in front of the camera

    origin, direction = cam.ray_from_screen(sx, sy, 1280, 800)
    # The world point lies on the ray: world == origin + s*direction for some s>0.
    to_point = world - origin
    s = float(np.dot(to_point, direction))
    closest = origin + s * direction
    np.testing.assert_allclose(closest, world, atol=1e-3)


def test_world_to_screen_center_of_target_is_screen_center():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1.0
    sx, sy, _ = cam.world_to_screen(cam.target, 1000, 1000)
    np.testing.assert_allclose([sx, sy], [500.0, 500.0], atol=1.0)


def test_world_to_screen_behind_camera_returns_none():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.position = np.array([0.0, 0.0, 5.0], dtype=np.float32)
    cam.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)  # looking down -Z
    cam.aspect = 1.0
    behind = np.array([0.0, 0.0, 10.0], dtype=np.float32)  # above/behind the camera
    assert cam.world_to_screen(behind, 1280, 800) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_camera.py -k world_to_screen -v`
Expected: FAIL — `AttributeError: 'Camera' object has no attribute 'world_to_screen'`

- [ ] **Step 3: Implement `world_to_screen`**

Add to `python/pluton/viewport/camera.py` immediately after `ray_from_screen` (before `ray_intersect_ground`):

```python
    def world_to_screen(
        self, world_xyz: np.ndarray, width: int, height: int
    ) -> tuple[float, float, float] | None:
        """Project a world point to screen pixels. Inverse of ray_from_screen.

        Returns `(sx, sy, depth)` where (sx, sy) are pixel coordinates (screen-y
        top-down) and `depth` is the positive camera-space distance in front of
        the camera (larger = farther), suitable for depth tie-breaking. Returns
        `None` if the point is at or behind the camera plane.
        """
        w = max(int(width), 1)
        h = max(int(height), 1)
        p = np.array(
            [float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2]), 1.0],
            dtype=np.float32,
        )
        clip = self.projection_matrix() @ (self.view_matrix() @ p)
        clip_w = float(clip[3])
        if clip_w <= 1e-7:
            return None  # at or behind the camera
        ndc_x = float(clip[0]) / clip_w
        ndc_y = float(clip[1]) / clip_w
        sx = (ndc_x + 1.0) * 0.5 * w
        sy = (1.0 - ndc_y) * 0.5 * h
        return (sx, sy, clip_w)  # clip_w == -z_cam, positive in front
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_camera.py -k world_to_screen -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full camera suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_camera.py -v`
Expected: PASS (all existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/camera.py tests/test_camera.py
git commit -m "feat(camera): add world_to_screen projection (inverse of ray_from_screen)

The screen-space proximity model for M3d inferencing needs to project
candidate geometry to pixels. world_to_screen composes view+projection,
perspective-divides to NDC, and maps to screen-y-down pixels; returns
None for points at/behind the camera.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: C++ `split_edge` — happy path (interior edge) + `SplitEdgeResult`

**Files:**
- Modify: `cpp/include/pluton/halfedge.h` (add `#include <optional>`, `SplitEdgeResult` struct, method decl)
- Modify: `cpp/src/halfedge.cpp` (add anonymous-namespace helper + `split_edge` impl near `dissolve_edge`)
- Test: `cpp/tests/test_halfedge.cpp` (append)

- [ ] **Step 1: Declare `SplitEdgeResult` + `split_edge` in the header**

In `cpp/include/pluton/halfedge.h`: add `#include <optional>` to the includes block, then add this struct **above** `class HalfEdgeMesh` (after the file doc comment, before `class`):

```cpp
/// Result of HalfEdgeMesh::split_edge — the ids of the entities it created.
/// face_a / face_b are INVALID_ID for a boundary edge's empty side.
struct SplitEdgeResult {
    std::uint32_t vertex;   // the new vertex w inserted on the edge
    std::uint32_t edge_a;   // new edge (v_min — w)
    std::uint32_t edge_b;   // new edge (w — v_max)
    std::uint32_t face_a;   // rebuilt face on he(2e) side, or INVALID_ID
    std::uint32_t face_b;   // rebuilt face on he(2e+1) side, or INVALID_ID
};
```

Add the method declaration in the `// ---- Mutators ----` section, right after the `dissolve_edge` declaration (~line 73):

```cpp
    /// Split an edge at parameter t ∈ (0,1), inserting a new vertex w at
    /// p(v_min) + t*(p(v_max) - p(v_min)) where (v_min, v_max) = edge_vertices(e_id).
    /// The edge is replaced by two collinear edges and w is inserted into the
    /// boundary loop of each incident face (which is re-triangulated). Manifold
    /// structure is preserved. Returns the created ids, or std::nullopt if e_id
    /// is dead, t ∉ (0,1), or w coincides with an existing endpoint.
    std::optional<SplitEdgeResult> split_edge(std::uint32_t e_id, float t);
```

(Header already includes nothing for optional — that is why Step 1 adds `#include <optional>`.)

- [ ] **Step 2: Write the failing GoogleTest**

Append to `cpp/tests/test_halfedge.cpp` (it already includes `pluton/halfedge.h` and `<gtest/gtest.h>`):

```cpp
// ---- split_edge -------------------------------------------------------------

namespace {
// Build two quads sharing edge (v1,v2): f1=[v0,v1,v2,v3], f2=[v1,v4,v5,v2].
// Returns the shared edge id via out-param. Mirrors the dissolve_edge fixture.
pluton::HalfEdgeMesh make_two_quads(std::uint32_t& shared_edge_out) {
    using pluton::HalfEdgeMesh;
    HalfEdgeMesh m;
    auto v0 = m.add_vertex(0, 0, 0);
    auto v1 = m.add_vertex(1, 0, 0);
    auto v2 = m.add_vertex(1, 1, 0);
    auto v3 = m.add_vertex(0, 1, 0);
    auto v4 = m.add_vertex(2, 0, 0);
    auto v5 = m.add_vertex(2, 1, 0);
    m.add_halfedge_pair(v0, v1);
    shared_edge_out = m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v3);
    m.add_halfedge_pair(v3, v0);
    m.add_halfedge_pair(v1, v4);
    m.add_halfedge_pair(v4, v5);
    m.add_halfedge_pair(v5, v2);
    // Fan triangulations (CCW quads): [0,1,2],[0,2,3].
    m.add_face_from_loop({v0, v1, v2, v3}, {(int)v0,(int)v1,(int)v2, (int)v0,(int)v2,(int)v3});
    m.add_face_from_loop({v1, v4, v5, v2}, {(int)v1,(int)v4,(int)v5, (int)v1,(int)v5,(int)v2});
    return m;
}
}  // namespace

TEST(SplitEdge, InteriorEdgeInsertsVertexAndRebuildsBothFaces) {
    std::uint32_t e_shared = 0;
    auto m = make_two_quads(e_shared);

    auto res = m.split_edge(e_shared, 0.5f);
    ASSERT_TRUE(res.has_value());

    // New vertex sits at the midpoint of (1,0)-(1,1) = (1, 0.5, 0).
    auto wp = m.vertex_position(res->vertex);
    EXPECT_FLOAT_EQ(wp[0], 1.0f);
    EXPECT_FLOAT_EQ(wp[1], 0.5f);
    EXPECT_FLOAT_EQ(wp[2], 0.0f);

    // The original shared edge is dead; two new live edges exist.
    EXPECT_FALSE(m.edge_is_live(e_shared));
    EXPECT_TRUE(m.edge_is_live(res->edge_a));
    EXPECT_TRUE(m.edge_is_live(res->edge_b));

    // Both faces were rebuilt and now each have 5 boundary vertices (4 + w).
    EXPECT_NE(res->face_a, HalfEdgeMesh::INVALID_ID);
    EXPECT_NE(res->face_b, HalfEdgeMesh::INVALID_ID);
    EXPECT_TRUE(m.face_is_live(res->face_a));
    EXPECT_TRUE(m.face_is_live(res->face_b));
    EXPECT_EQ(m.face_loop_vertices(res->face_a).size(), 5u);
    EXPECT_EQ(m.face_loop_vertices(res->face_b).size(), 5u);

    // Exactly two live faces total.
    std::uint32_t live = 0;
    for (auto f = m.next_live_face(0); f != HalfEdgeMesh::INVALID_ID; f = m.next_live_face(f + 1))
        ++live;
    EXPECT_EQ(live, 2u);
}
```

- [ ] **Step 3: Run the test to verify it fails to build**

Run: `cmake --build build/tests`
Expected: FAIL — `'split_edge' is not a member of 'pluton::HalfEdgeMesh'` (decl present but no definition → link/compile error).

- [ ] **Step 4: Implement `split_edge` + helper**

In `cpp/src/halfedge.cpp`, add a helper inside the existing anonymous `namespace { ... }` (the one that already holds `compute_face_normal_geometric`, ~lines 364-398) — add before its closing `}`:

```cpp
// Insert vertex w into `loop` between the adjacent pair (va, vb) (either order),
// returning the new loop. Caller guarantees va,vb are consecutive in loop.
std::vector<std::uint32_t> loop_with_inserted(
        const std::vector<std::uint32_t>& loop,
        std::uint32_t va, std::uint32_t vb, std::uint32_t w) {
    const std::size_t n = loop.size();
    std::vector<std::uint32_t> out;
    out.reserve(n + 1);
    for (std::size_t i = 0; i < n; ++i) {
        out.push_back(loop[i]);
        const std::uint32_t cur = loop[i];
        const std::uint32_t nxt = loop[(i + 1) % n];
        if ((cur == va && nxt == vb) || (cur == vb && nxt == va)) {
            out.push_back(w);
        }
    }
    return out;
}
```

Then add the method definition just **after** `dissolve_edge` (after line 532). It composes the same primitives `dissolve_edge` uses (`remove_face`, `remove_edge`, `add_halfedge_pair`, `add_face_from_loop`):

```cpp
std::optional<pluton::HalfEdgeMesh::SplitEdgeResult>
pluton::HalfEdgeMesh::split_edge(std::uint32_t e_id, float t) {
    if (!edge_is_live(e_id)) return std::nullopt;
    if (!(t > 0.0f && t < 1.0f)) return std::nullopt;

    const std::uint32_t he_a = 2u * e_id;
    const std::uint32_t he_b = 2u * e_id + 1u;
    const std::uint32_t va = halfedges_[he_a].origin;  // v_min
    const std::uint32_t vb = halfedges_[he_b].origin;  // v_max

    const auto pa = vertices_[va].pos;
    const auto pb = vertices_[vb].pos;
    const float wx = pa[0] + t * (pb[0] - pa[0]);
    const float wy = pa[1] + t * (pb[1] - pa[1]);
    const float wz = pa[2] + t * (pb[2] - pa[2]);
    const std::uint32_t w = add_vertex(wx, wy, wz);
    if (w == va || w == vb) return std::nullopt;  // coincident with an endpoint

    // Capture incident faces and their loops before we tombstone them.
    const std::uint32_t fa = halfedges_[he_a].face;
    const std::uint32_t fb = halfedges_[he_b].face;
    std::vector<std::uint32_t> loopA, loopB;
    if (fa != INVALID_ID) loopA = faces_[fa].loop;
    if (fb != INVALID_ID) loopB = faces_[fb].loop;

    // Remove incident faces (clears their boundary half-edges' face = INVALID),
    // which makes the edge unbordered so remove_edge can tombstone it.
    if (fa != INVALID_ID) remove_face(fa);
    if (fb != INVALID_ID) remove_face(fb);
    remove_edge(e_id);

    // Two new collinear edges. add_halfedge_pair allocates fresh ids (the old
    // pair is dead and erased from edge_index_).
    const std::uint32_t edge_a = add_halfedge_pair(va, w);
    const std::uint32_t edge_b = add_halfedge_pair(w, vb);

    auto rebuild = [&](const std::vector<std::uint32_t>& loop) -> std::uint32_t {
        if (loop.empty()) return INVALID_ID;
        std::vector<std::uint32_t> nl = loop_with_inserted(loop, va, vb, w);
        std::vector<std::int32_t> tris;
        tris.reserve((nl.size() - 2) * 3);
        for (std::size_t i = 1; i + 1 < nl.size(); ++i) {
            tris.push_back((std::int32_t)nl[0]);
            tris.push_back((std::int32_t)nl[i]);
            tris.push_back((std::int32_t)nl[i + 1]);
        }
        return add_face_from_loop(nl, tris);
    };
    const std::uint32_t new_fa = rebuild(loopA);
    const std::uint32_t new_fb = rebuild(loopB);

    dirty_ = true;
    return SplitEdgeResult{w, edge_a, edge_b, new_fa, new_fb};
}
```

> Note the qualified return type `pluton::HalfEdgeMesh::SplitEdgeResult` — the struct is nested-adjacent in the header's `pluton` namespace, matching how `dissolve_edge` is defined as `pluton::HalfEdgeMesh::...` in this file.

- [ ] **Step 5: Build and run the test**

Run: `cmake --build build/tests`
Then: `ctest --test-dir build/tests --output-on-failure -R SplitEdge`
Expected: PASS (1 test, `SplitEdge.InteriorEdgeInsertsVertexAndRebuildsBothFaces`)

- [ ] **Step 6: Full C++ suite (no regressions)**

Run: `ctest --test-dir build/tests --output-on-failure`
Expected: PASS (all prior GoogleTests + the new one)

- [ ] **Step 7: Commit**

```bash
git add cpp/include/pluton/halfedge.h cpp/src/halfedge.cpp cpp/tests/test_halfedge.cpp
git commit -m "feat(halfedge): split_edge happy path + SplitEdgeResult

Inserts a vertex at parameter t on an edge, replacing it with two
collinear edges and re-inserting the vertex into each incident face's
loop (re-triangulated). Composes the same primitives dissolve_edge uses;
returns the created ids for the command layer's id-preserving undo.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: C++ `split_edge` — edge cases

**Files:**
- Test: `cpp/tests/test_halfedge.cpp` (append)
- (No production change expected; the Task 2 guards should already pass. If a test fails, fix `split_edge` minimally.)

- [ ] **Step 1: Write the failing edge-case tests**

Append to `cpp/tests/test_halfedge.cpp`:

```cpp
TEST(SplitEdge, BoundaryEdgeSplitsTheSingleIncidentFace) {
    using pluton::HalfEdgeMesh;
    HalfEdgeMesh m;
    auto v0 = m.add_vertex(0, 0, 0);
    auto v1 = m.add_vertex(2, 0, 0);
    auto v2 = m.add_vertex(0, 2, 0);
    m.add_halfedge_pair(v0, v1);
    auto e01 = (m.add_halfedge_pair(v0, v1));  // idempotent → same edge id
    m.add_halfedge_pair(v1, v2);
    m.add_halfedge_pair(v2, v0);
    m.add_face_from_loop({v0, v1, v2}, {(int)v0,(int)v1,(int)v2});

    auto res = m.split_edge(e01, 0.5f);
    ASSERT_TRUE(res.has_value());
    // Only one side had a face: face_a present, face_b absent.
    const bool one_face =
        (res->face_a != HalfEdgeMesh::INVALID_ID) != (res->face_b != HalfEdgeMesh::INVALID_ID);
    EXPECT_TRUE(one_face);
    // The single rebuilt triangle-face is now a quad (3 + w).
    const std::uint32_t live_face =
        res->face_a != HalfEdgeMesh::INVALID_ID ? res->face_a : res->face_b;
    EXPECT_EQ(m.face_loop_vertices(live_face).size(), 4u);
}

TEST(SplitEdge, RejectsParameterOutOfRange) {
    std::uint32_t e = 0;
    auto m = make_two_quads(e);
    EXPECT_FALSE(m.split_edge(e, 0.0f).has_value());
    EXPECT_FALSE(m.split_edge(e, 1.0f).has_value());
    EXPECT_FALSE(m.split_edge(e, -0.2f).has_value());
    EXPECT_FALSE(m.split_edge(e, 1.5f).has_value());
}

TEST(SplitEdge, RejectsDeadEdge) {
    std::uint32_t e = 0;
    auto m = make_two_quads(e);
    auto first = m.split_edge(e, 0.5f);
    ASSERT_TRUE(first.has_value());
    // e is now dead; splitting it again must refuse.
    EXPECT_FALSE(m.split_edge(e, 0.5f).has_value());
}

TEST(SplitEdge, PreservesManifoldTwinsOnNewEdges) {
    std::uint32_t e = 0;
    auto m = make_two_quads(e);
    auto res = m.split_edge(e, 0.5f);
    ASSERT_TRUE(res.has_value());
    // Each new edge's two half-edges must reference each other as twins, and
    // (since this was an interior edge) both must border a live face.
    for (std::uint32_t ne : {res->edge_a, res->edge_b}) {
        std::uint32_t ha = 2u * ne, hb = 2u * ne + 1u;
        EXPECT_EQ(m.halfedge_twin(ha), hb);
        EXPECT_EQ(m.halfedge_twin(hb), ha);
        EXPECT_NE(m.halfedge_face(ha), HalfEdgeMesh::INVALID_ID);
        EXPECT_NE(m.halfedge_face(hb), HalfEdgeMesh::INVALID_ID);
    }
}
```

- [ ] **Step 2: Build and run**

Run: `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure -R SplitEdge`
Expected: PASS (5 SplitEdge tests). If `BoundaryEdgeSplitsTheSingleIncidentFace` or `PreservesManifoldTwins` fails, fix `split_edge` minimally (most likely the boundary branch where `fb == INVALID_ID`).

- [ ] **Step 3: Full C++ suite**

Run: `ctest --test-dir build/tests --output-on-failure`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add cpp/tests/test_halfedge.cpp cpp/src/halfedge.cpp cpp/include/pluton/halfedge.h
git commit -m "test(halfedge): split_edge edge cases (boundary, bad t, dead edge, twins)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: nanobind bindings — `split_edge` + `SplitEdgeResult`

**Files:**
- Modify: `cpp/bindings/module.cpp`
- Test: `tests/test_halfedge_python.py` (append a smoke test)

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_halfedge_python.py`:

```python
def test_split_edge_binding_smoke():
    from pluton._core import HalfEdgeMesh

    m = HalfEdgeMesh()
    v0 = m.add_vertex(0.0, 0.0, 0.0)
    v1 = m.add_vertex(1.0, 0.0, 0.0)
    v2 = m.add_vertex(1.0, 1.0, 0.0)
    v3 = m.add_vertex(0.0, 1.0, 0.0)
    m.add_halfedge_pair(v0, v1)
    e = m.add_halfedge_pair(v1, v2)
    m.add_halfedge_pair(v2, v3)
    m.add_halfedge_pair(v3, v0)
    m.add_face_from_loop([v0, v1, v2, v3], [v0, v1, v2, v0, v2, v3])

    res = m.split_edge(e, 0.5)
    assert res is not None
    assert m.vertex_is_live(res.vertex)
    assert m.edge_is_live(res.edge_a)
    assert m.edge_is_live(res.edge_b)
    # Boundary quad → single incident face rebuilt to 5 vertices.
    live = res.face_a if res.face_a != HalfEdgeMesh.INVALID_ID else res.face_b
    assert len(m.face_loop_vertices(live)) == 5
    # Out-of-range t → None.
    assert m.split_edge(res.edge_a, 1.0) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_halfedge_python.py -k split_edge_binding -v`
Expected: FAIL — `AttributeError: ... has no attribute 'split_edge'`

- [ ] **Step 3: Bind the struct + method**

In `cpp/bindings/module.cpp`, add the `SplitEdgeResult` class binding right after the `HalfEdgeMesh` class chain closes (after the `.def_ro_static("INVALID_ID", ...)` line ~140, before the `RayMeshHit` binding). First add the using-declaration near the top with the others (~line 18):

```cpp
using pluton::SplitEdgeResult;
```

Then add the method into the `HalfEdgeMesh` chain, right after the `dissolve_edge` def (~line 107):

```cpp
        .def("split_edge",
             &HalfEdgeMesh::split_edge,
             nb::arg("edge_id"), nb::arg("t"),
             "Split an edge at parameter t in (0,1), inserting a vertex and "
             "rebuilding incident faces. Returns a SplitEdgeResult, or None if "
             "the edge is dead, t is out of range, or w coincides with an endpoint.")
```

And after the `HalfEdgeMesh` chain's terminating `;`, add:

```cpp
    nb::class_<SplitEdgeResult>(m, "SplitEdgeResult", "Result of HalfEdgeMesh.split_edge")
        .def_ro("vertex", &SplitEdgeResult::vertex)
        .def_ro("edge_a", &SplitEdgeResult::edge_a)
        .def_ro("edge_b", &SplitEdgeResult::edge_b)
        .def_ro("face_a", &SplitEdgeResult::face_a)
        .def_ro("face_b", &SplitEdgeResult::face_b);
```

(`std::optional<SplitEdgeResult>` → Python `None`/object conversion is already enabled by the `#include <nanobind/stl/optional.h>` at the top of this file.)

- [ ] **Step 4: Rebuild the extension**

Run: `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation`
Expected: `Successfully installed pluton-0.0.6`

- [ ] **Step 5: Run the smoke test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_halfedge_python.py -k split_edge_binding -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cpp/bindings/module.cpp tests/test_halfedge_python.py
git commit -m "feat(bindings): expose split_edge + SplitEdgeResult to Python

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `Scene.split_edge` wrapper + edge geometry helpers

**Files:**
- Modify: `python/pluton/scene/scene.py` (add to the "M3c additions" region; add `SplitResult` namedtuple near the top)
- Test: `tests/test_scene_split.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scene_split.py`:

```python
"""Scene-level split_edge wrapper + edge geometry helpers."""

from __future__ import annotations

import numpy as np
from pluton.scene.scene import Scene


def _quad(scene: Scene):
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([2, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([2, 2, 0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, 2, 0], dtype=np.float32))
    for a, b in [(v0, v1), (v1, v2), (v2, v3), (v3, v0)]:
        scene.add_edge(a, b)
    f = scene.add_face_from_loop([v0, v1, v2, v3])
    e01 = scene.add_edge(v0, v1)  # idempotent → existing edge id
    return f, e01, (v0, v1, v2, v3)


def test_point_on_edge_midpoint():
    scene = Scene()
    _, e01, _ = _quad(scene)
    p = scene.point_on_edge(e01, 0.5)
    np.testing.assert_allclose(p, [1.0, 0.0, 0.0], atol=1e-6)


def test_closest_point_on_edge_clamps_to_segment():
    scene = Scene()
    _, e01, _ = _quad(scene)
    # Ray-independent helper form: closest point to an arbitrary world point.
    # A point beyond v1 clamps to v1 (t=1 → (2,0,0)).
    p, t = scene.closest_point_on_edge(e01, np.array([5.0, 0.0, 0.0], dtype=np.float32))
    np.testing.assert_allclose(p, [2.0, 0.0, 0.0], atol=1e-6)
    assert t == 1.0


def test_split_edge_returns_result_and_inserts_vertex():
    scene = Scene()
    f, e01, (v0, v1, v2, v3) = _quad(scene)
    res = scene.split_edge(e01, 0.5)
    assert res is not None
    np.testing.assert_allclose(scene.vertex(res.vertex).position, [1.0, 0.0, 0.0], atol=1e-6)
    # Boundary edge → one rebuilt face (face_a), other side None.
    assert (res.face_a is None) != (res.face_b is None)
    live_face = res.face_a if res.face_a is not None else res.face_b
    assert len(scene.face(live_face).loop_vertex_ids) == 5


def test_split_edge_invalid_returns_none():
    scene = Scene()
    _, e01, _ = _quad(scene)
    assert scene.split_edge(e01, 0.0) is None
    assert scene.split_edge(e01, 1.0) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scene_split.py -v`
Expected: FAIL — `AttributeError: 'Scene' object has no attribute 'point_on_edge'`

- [ ] **Step 3: Implement the wrapper + helpers**

In `python/pluton/scene/scene.py`, add a namedtuple import + type near the top imports:

```python
from collections import namedtuple
```

and after the imports (module scope, before `class Scene`):

```python
SplitResult = namedtuple("SplitResult", "vertex edge_a edge_b face_a face_b")
```

Then add these methods inside the `# ---- M3c additions ----` region (after `edge_is_boundary`, ~line 296):

```python
    # ---- M3d additions ----

    def point_on_edge(self, e_id: int, t: float) -> np.ndarray:
        """World point at parameter t along edge e (t measured v1→v2 of edge())."""
        e = self.edge(e_id)
        pa = self.vertex(e.v1_id).position
        pb = self.vertex(e.v2_id).position
        return (pa + float(t) * (pb - pa)).astype(np.float32)

    def closest_point_on_edge(
        self, e_id: int, world_point: np.ndarray
    ) -> tuple[np.ndarray, float]:
        """Closest point on edge segment to `world_point`, plus its clamped t∈[0,1]."""
        e = self.edge(e_id)
        pa = self.vertex(e.v1_id).position
        pb = self.vertex(e.v2_id).position
        ab = pb - pa
        denom = float(np.dot(ab, ab))
        if denom < 1e-18:
            return pa.astype(np.float32), 0.0
        t = float(np.dot(np.asarray(world_point, dtype=np.float32) - pa, ab) / denom)
        t = max(0.0, min(1.0, t))
        return (pa + t * ab).astype(np.float32), t

    def split_edge(self, e_id: int, t: float) -> "SplitResult | None":
        """Split edge e at parameter t. Returns a SplitResult (face_* None for a
        boundary edge's empty side), or None if the split is invalid."""
        res = self._mesh.split_edge(int(e_id), float(t))
        if res is None:
            return None
        invalid = self._mesh.INVALID_ID
        return SplitResult(
            vertex=int(res.vertex),
            edge_a=int(res.edge_a),
            edge_b=int(res.edge_b),
            face_a=None if res.face_a == invalid else int(res.face_a),
            face_b=None if res.face_b == invalid else int(res.face_b),
        )
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scene_split.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add python/pluton/scene/scene.py tests/test_scene_split.py
git commit -m "feat(scene): split_edge wrapper + point_on_edge/closest_point_on_edge

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `SplitEdgeCommand` (id-preserving do / undo / redo)

**Files:**
- Modify: `python/pluton/commands/scene_commands.py` (append `SplitEdgeCommand`)
- Test: `tests/test_split_edge_command.py` (new)

The command mirrors `DissolveEdgeCommand`'s id-preserving discipline, but because a split *creates* a vertex + two edges + (up to) two faces, redo must restore **all** of them to their first-run ids (so a sibling `AddEdgeCommand` that cached the new vertex id stays valid inside a gesture composite — the same atomic-undo concern M3c fixed).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_split_edge_command.py`:

```python
"""SplitEdgeCommand: do, undo, redo round-trips + composite-sibling safety."""

from __future__ import annotations

import numpy as np
from pluton.commands.command import CompositeCommand
from pluton.commands.scene_commands import AddEdgeCommand, SplitEdgeCommand
from pluton.scene.scene import Scene


def _two_quads(scene: Scene):
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1, 1, 0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, 1, 0], dtype=np.float32))
    v4 = scene.add_vertex(np.array([2, 0, 0], dtype=np.float32))
    v5 = scene.add_vertex(np.array([2, 1, 0], dtype=np.float32))
    for a, b in [(v0, v1), (v1, v2), (v2, v3), (v3, v0), (v1, v4), (v4, v5), (v5, v2)]:
        scene.add_edge(a, b)
    scene.add_face_from_loop([v0, v1, v2, v3])
    scene.add_face_from_loop([v1, v4, v5, v2])
    e_shared = scene.add_edge(v1, v2)  # idempotent → existing id
    return e_shared, (v1, v2)


def test_do_splits_and_grows_both_faces():
    scene = Scene()
    e, _ = _two_quads(scene)
    cmd = SplitEdgeCommand(e, 0.5)
    cmd.do(scene)
    faces = list(scene.faces_iter())
    assert len(faces) == 2
    assert all(len(f.loop_vertex_ids) == 5 for f in faces)


def test_undo_restores_counts():
    scene = Scene()
    e, _ = _two_quads(scene)
    pf = sum(1 for _ in scene.faces_iter())
    pe = sum(1 for _ in scene.edges_iter())
    pv = sum(1 for _ in scene.vertices_iter())
    cmd = SplitEdgeCommand(e, 0.5)
    cmd.do(scene)
    cmd.undo(scene)
    assert sum(1 for _ in scene.faces_iter()) == pf
    assert sum(1 for _ in scene.edges_iter()) == pe
    assert sum(1 for _ in scene.vertices_iter()) == pv


def test_do_undo_redo_double_cycle():
    scene = Scene()
    e, _ = _two_quads(scene)
    pf = sum(1 for _ in scene.faces_iter())
    pe = sum(1 for _ in scene.edges_iter())
    cmd = SplitEdgeCommand(e, 0.5)
    cmd.do(scene)
    cmd.undo(scene)
    cmd.do(scene)    # redo
    cmd.undo(scene)  # undo again
    assert sum(1 for _ in scene.faces_iter()) == pf
    assert sum(1 for _ in scene.edges_iter()) == pe


def test_invalid_t_is_noop():
    scene = Scene()
    e, _ = _two_quads(scene)
    cmd = SplitEdgeCommand(e, 0.0)
    cmd.do(scene)    # no-op, must not raise
    cmd.undo(scene)  # no-op, must not raise
    assert sum(1 for _ in scene.faces_iter()) == 2


def test_redo_keeps_new_vertex_id_stable_for_sibling():
    """A sibling AddEdgeCommand that connects to the new vertex must survive an
    undo/redo of the whole composite — i.e. redo must restore the SAME vertex id."""
    scene = Scene()
    e, (v1, v2) = _two_quads(scene)
    anchor = scene.add_vertex(np.array([0.5, -1.0, 0.0], dtype=np.float32))

    comp = CompositeCommand(name="line-onto-edge")
    split = SplitEdgeCommand(e, 0.5)
    split.do(scene)
    comp.children.append(split)
    w = split.new_vertex_id
    assert w is not None
    e_cmd = AddEdgeCommand(anchor, w)
    e_cmd.do(scene)
    comp.children.append(e_cmd)

    # Undo the whole gesture, then redo. The connecting edge must reference a
    # live vertex (the same w) afterwards — no dangling reference.
    comp.undo(scene)
    comp.do(scene)  # redo
    assert scene._mesh.vertex_is_live(w)
    # The connecting edge (anchor—w) is live again.
    reconnected = scene.add_edge(anchor, w)  # idempotent lookup
    assert scene._mesh.edge_is_live(reconnected)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_split_edge_command.py -v`
Expected: FAIL — `ImportError: cannot import name 'SplitEdgeCommand'`

- [ ] **Step 3: Implement `SplitEdgeCommand`**

Append to `python/pluton/commands/scene_commands.py`:

```python
class SplitEdgeCommand(Command):
    """Split an edge at parameter t, inserting a vertex. Reversible.

    do(): first call performs the split via scene.split_edge and captures BOTH
          the originals (edge endpoints, incident face ids+loops) and the created
          ids (vertex w, two edges, up to two faces) plus the rebuilt loops.
          Redo restores every created entity to its FIRST-RUN id (id-preserving),
          so a sibling command in the same gesture composite that cached the new
          vertex id stays valid across undo/redo (the M3c atomic-undo concern).
    undo(): removes the created faces/edges/vertex, then restores the original
            edge and faces to their ORIGINAL ids (restore_edge before restore_face).
    Invalid/degenerate splits make the command a clean no-op.
    """

    name = "Split Edge"

    def __init__(self, edge_id: int, t: float) -> None:
        self._edge_id = edge_id
        self._t = float(t)
        self._was_noop = False
        self._done_once = False
        # originals
        self._orig_verts: tuple[int, int] | None = None  # (va, vb) = edge endpoints
        self._orig_faces: list[tuple[int, tuple[int, ...]]] = []  # (id, loop) captured
        self._w_pos: np.ndarray | None = None
        # created (first-run ids, reused on redo)
        self.new_vertex_id: int | None = None
        self._e1: int | None = None
        self._e2: int | None = None
        self._new_faces: list[tuple[int, tuple[int, ...]]] = []  # (id, loop-with-w)

    def do(self, scene) -> None:  # noqa: ANN001
        if not self._done_once:
            self._first_do(scene)
        else:
            self._redo(scene)

    def _first_do(self, scene) -> None:  # noqa: ANN001
        try:
            e = scene.edge(self._edge_id)
        except KeyError:
            self._was_noop = True
            self._done_once = True
            return
        va, vb = e.v1_id, e.v2_id
        # Capture incident faces + loops before the split tombstones them.
        fa, fb = scene.edge_faces(self._edge_id)
        captured_faces: list[tuple[int, tuple[int, ...]]] = []
        for fid in (fa, fb):
            if fid is not None:
                captured_faces.append((fid, tuple(scene.face(fid).loop_vertex_ids)))

        res = scene.split_edge(self._edge_id, self._t)
        if res is None:
            self._was_noop = True
            self._done_once = True
            return

        self._orig_verts = (va, vb)
        self._orig_faces = captured_faces
        self._w_pos = scene.vertex(res.vertex).position.copy()
        self.new_vertex_id = res.vertex
        self._e1, self._e2 = res.edge_a, res.edge_b
        # Capture the rebuilt loops (loop-with-w) for id-preserving redo.
        self._new_faces = []
        for fid in (res.face_a, res.face_b):
            if fid is not None:
                self._new_faces.append((fid, tuple(scene.face(fid).loop_vertex_ids)))
        self._done_once = True
        self._was_noop = False

    def _redo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._orig_verts is not None and self._w_pos is not None
        assert self.new_vertex_id is not None and self._e1 is not None and self._e2 is not None
        va, vb = self._orig_verts
        w = self.new_vertex_id
        # Re-create the new vertex at its original id.
        scene.restore_vertex(w, self._w_pos)
        # Tombstone the incident faces + original edge again (they are live after undo).
        for fid, _loop in self._orig_faces:
            scene.remove_face(fid)
        scene.remove_edge(self._edge_id)
        # Re-create the two split edges at their original ids.
        scene.restore_edge(self._e1, va, w)
        scene.restore_edge(self._e2, w, vb)
        # Re-create the rebuilt faces at their original ids.
        for fid, loop in self._new_faces:
            scene.restore_face(fid, loop)

    def undo(self, scene) -> None:  # noqa: ANN001
        if self._was_noop:
            return
        assert self._orig_verts is not None
        assert self.new_vertex_id is not None and self._e1 is not None and self._e2 is not None
        # Remove created faces, then created edges, then the new vertex.
        for fid, _loop in self._new_faces:
            scene.remove_face(fid)
        scene.remove_edge(self._e1)
        scene.remove_edge(self._e2)
        scene.remove_vertex(self.new_vertex_id)
        # Restore the original edge (first — faces reference it), then faces.
        va, vb = self._orig_verts
        scene.restore_edge(self._edge_id, va, vb)
        for fid, loop in self._orig_faces:
            scene.restore_face(fid, loop)
```

Add `import numpy as np` if not already present at the top of `scene_commands.py` (it is — used by `AddVertexCommand`).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_split_edge_command.py -v`
Expected: PASS (5 passed). The `test_redo_keeps_new_vertex_id_stable_for_sibling` case is the critical regression guard.

- [ ] **Step 5: Run the full command suite (no regressions)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scene_commands.py tests/test_dissolve_edge_command.py tests/test_split_edge_command.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/scene_commands.py tests/test_split_edge_command.py
git commit -m "feat(commands): SplitEdgeCommand with id-preserving do/undo/redo

Redo restores the created vertex/edges/faces to their first-run ids so a
sibling AddEdgeCommand that cached the new vertex survives an undo/redo of
the gesture composite (the M3c atomic-undo pattern).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Snap scaffolding — new kinds, result fields, color map, precedence, math helpers

**Files:**
- Modify: `python/pluton/viewport/snap_engine.py` (additive only — `snap()` is untouched here, so all existing snap tests stay green)
- Test: `tests/test_snap_engine.py` (append helper-math tests)

- [ ] **Step 1: Write the failing math-helper tests**

Append to `tests/test_snap_engine.py`:

```python
def test_closest_points_two_lines_perpendicular_crossing():
    from pluton.viewport.snap_engine import _closest_points_two_lines

    # Line 1 along X through origin; line 2 along Y through (3, 0, 1). They are
    # skew: closest points are (3,0,0) on L1 and (3,0,1) on L2, distance 1.
    p1 = np.array([0, 0, 0], np.float32); d1 = np.array([1, 0, 0], np.float32)
    p2 = np.array([3, 0, 1], np.float32); d2 = np.array([0, 1, 0], np.float32)
    _, _, c1, c2 = _closest_points_two_lines(p1, d1, p2, d2)
    np.testing.assert_allclose(c1, [3, 0, 0], atol=1e-5)
    np.testing.assert_allclose(c2, [3, 0, 1], atol=1e-5)


def test_closest_point_on_segment_to_ray_clamps():
    from pluton.viewport.snap_engine import _closest_point_on_segment_to_ray

    # Ray looking down -Z from above (5,0,10); segment along X from (0,0,0)-(2,0,0).
    ro = np.array([5, 0, 10], np.float32); rd = np.array([0, 0, -1], np.float32)
    a = np.array([0, 0, 0], np.float32); b = np.array([2, 0, 0], np.float32)
    pt, t = _closest_point_on_segment_to_ray(ro, rd, a, b)
    np.testing.assert_allclose(pt, [2, 0, 0], atol=1e-5)  # clamped to far endpoint
    assert t == 1.0


def test_precedence_rank_orders_endpoint_above_on_face():
    from pluton.viewport.snap_engine import SnapKind, _PRECEDENCE_RANK

    assert _PRECEDENCE_RANK[SnapKind.ENDPOINT] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]
    assert _PRECEDENCE_RANK[SnapKind.MIDPOINT] < _PRECEDENCE_RANK[SnapKind.ON_EDGE]
    assert _PRECEDENCE_RANK[SnapKind.ON_EDGE] < _PRECEDENCE_RANK[SnapKind.ON_FACE]
    assert _PRECEDENCE_RANK[SnapKind.ON_FACE] < _PRECEDENCE_RANK[SnapKind.GRID]
    assert _PRECEDENCE_RANK[SnapKind.INTERSECTION] < _PRECEDENCE_RANK[SnapKind.MIDPOINT]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -k "closest or precedence_rank" -v`
Expected: FAIL — `ImportError: cannot import name '_closest_points_two_lines'`

- [ ] **Step 3: Add the scaffolding**

In `python/pluton/viewport/snap_engine.py`:

(a) Extend the enum (append the three new members):

```python
class SnapKind(IntEnum):
    """Snap kinds. Integer values are stable wire ids (used by the renderer +
    tool overlays). Precedence is a SEPARATE explicit ordering — see _PRECEDENCE."""

    NONE = 0
    GRID = 1
    AXIS_LOCK = 2
    MIDPOINT = 3
    ENDPOINT = 4
    ON_FACE = 5
    ON_EDGE = 6
    INTERSECTION = 7
```

(b) Extend `SnapResult` with three optional fields:

```python
@dataclass(frozen=True, slots=True)
class SnapResult:
    """The chosen snap for one cursor position."""

    kind: SnapKind
    world_position: np.ndarray
    axis: int | None  # 0=X (red), 1=Y (green), 2=Z (blue); only AXIS_LOCK
    vertex_id: int | None  # only ENDPOINT
    label: str
    edge_id: int | None = None  # MIDPOINT / ON_EDGE / INTERSECTION
    face_id: int | None = None  # ON_FACE
    edge_t: float | None = None  # parameter along edge_id (drives split_edge)
```

(c) Add module-level constants after `_AXIS_NAMES`:

```python
# Snap-marker colors, keyed by kind. Shared by tools (overlay color) and the
# renderer is shape-only. AXIS_LOCK has no marker color (the rubber-band shows
# the axis color instead).
MARKER_COLOR_BY_KIND = {
    SnapKind.GRID: (0.70, 0.70, 0.70),
    SnapKind.MIDPOINT: (0.13, 0.77, 0.84),       # cyan
    SnapKind.ENDPOINT: (0.15, 0.75, 0.26),       # green
    SnapKind.ON_EDGE: (0.89, 0.23, 0.18),        # red
    SnapKind.ON_FACE: (0.18, 0.42, 0.88),        # blue
    SnapKind.INTERSECTION: (0.82, 0.23, 0.82),   # magenta
}

# Precedence, highest first. Decoupled from the enum's integer values.
_PRECEDENCE = [
    SnapKind.ENDPOINT,
    SnapKind.INTERSECTION,
    SnapKind.MIDPOINT,
    SnapKind.ON_EDGE,
    SnapKind.ON_FACE,
    SnapKind.AXIS_LOCK,
    SnapKind.GRID,
]
_PRECEDENCE_RANK = {k: i for i, k in enumerate(_PRECEDENCE)}  # lower = higher precedence
```

(d) Add a `_Candidate` dataclass after the constants:

```python
@dataclass
class _Candidate:
    """One in-tolerance snap candidate, before precedence selection."""

    kind: SnapKind
    world_position: np.ndarray
    screen_dist: float
    depth: float
    label: str
    vertex_id: int | None = None
    edge_id: int | None = None
    face_id: int | None = None
    axis: int | None = None
    edge_t: float | None = None
```

(e) Add the two vector-math module functions at the end of the file:

```python
def _closest_points_two_lines(p1, d1, p2, d2):
    """Closest points between two infinite lines L1=p1+s*d1, L2=p2+t*d2.

    Returns (s, t, c1, c2). For parallel lines s=0 (and t follows). All inputs
    are float32 (3,) numpy arrays; d1/d2 need not be unit length.
    """
    r = p1 - p2
    a = float(np.dot(d1, d1))
    e = float(np.dot(d2, d2))
    f = float(np.dot(d2, r))
    b = float(np.dot(d1, d2))
    c = float(np.dot(d1, r))
    denom = a * e - b * b
    s = 0.0 if abs(denom) < 1e-12 else (b * f - c * e) / denom
    t = (b * s + f) / e if e > 1e-12 else 0.0
    c1 = p1 + s * d1
    c2 = p2 + t * d2
    return s, t, c1.astype(np.float32), c2.astype(np.float32)


def _closest_point_on_segment_to_ray(ray_origin, ray_dir, a, b):
    """Closest point ON segment [a, b] to the (infinite) ray line. Returns
    (point, t) with t clamped to [0, 1]."""
    d2 = b - a
    _, t, _, _ = _closest_points_two_lines(ray_origin, ray_dir, a, d2)
    t = max(0.0, min(1.0, t))
    return (a + t * d2).astype(np.float32), float(t)
```

- [ ] **Step 4: Run to verify pass + no regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -v`
Expected: PASS — the new math/precedence tests pass AND all 8 pre-existing snap tests still pass (snap() is untouched in this task).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/snap_engine.py tests/test_snap_engine.py
git commit -m "feat(snap): scaffolding for 3D inferencing (kinds, precedence, math helpers)

Adds ON_FACE/ON_EDGE/INTERSECTION kinds, edge_id/face_id/edge_t result
fields, a shared marker color map, an explicit precedence ordering, the
_Candidate record, and line/segment closest-point helpers. snap() itself
is unchanged here, so existing behavior is intact.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Ray-based `snap()` core (endpoint + midpoint + grid) + viewport wiring

This task changes the `snap()` signature from a ground-point input to a screen-cursor input, derives the cursor ray and ground hit internally, and ranks candidates in **screen space**. It implements the **endpoint, midpoint, and grid** candidates plus the precedence/depth selection. On-Edge/On-Face (Task 9) and Axis/Intersection (Task 10) plug into the same `snap()` afterward.

**Files:**
- Modify: `python/pluton/viewport/snap_engine.py` (rewrite `snap()`; add generators + selection)
- Modify: `python/pluton/viewport/viewport_widget.py` (`_snap_for_event` → new signature)
- Test: `tests/test_snap_engine.py` (**rewrite** — the signature changed)

- [ ] **Step 1: Rewrite the snap-engine tests for the new signature**

Replace the body of `tests/test_snap_engine.py` **above** the Task 7 math tests (i.e. the 8 original `snap(...)` tests) with these. Keep the Task 7 math/precedence tests at the bottom.

```python
"""Unit tests for the snap & inference engine (3D, screen-space)."""

from __future__ import annotations

import numpy as np


def _camera_at_default():
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = 1280.0 / 800.0
    return cam


def _screen_of(cam, world):
    """Pixel coords that project onto `world` in a 1280x800 viewport."""
    sx, sy, _ = cam.world_to_screen(np.asarray(world, dtype=np.float32), 1280, 800)
    return (sx, sy)


def test_endpoint_snap_in_3d_off_the_ground():
    """The headline M3d capability: snap to a vertex ABOVE the ground plane."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    vid = scene.add_vertex(np.array([1.0, 2.0, 3.0], dtype=np.float32))  # off-ground
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 2.0, 3.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ENDPOINT
    assert res.vertex_id == vid
    np.testing.assert_allclose(res.world_position, scene.vertex(vid).position, atol=1e-4)


def test_midpoint_snap_in_3d():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([0.0, 4.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 2.0, 2.0])  # the midpoint
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.MIDPOINT
    assert res.edge_id == e
    assert abs(res.edge_t - 0.5) < 1e-3
    np.testing.assert_allclose(res.world_position, [0.0, 2.0, 2.0], atol=1e-3)


def test_grid_fallback_on_empty_ground():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    cursor = _screen_of(cam, [2.3, -1.4, 0.0])
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.GRID
    np.testing.assert_allclose(res.world_position, [2.0, -1.0, 0.0], atol=1e-3)


def test_none_when_scene_is_none():
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    cam = _camera_at_default()
    res = eng.snap((640.0, 400.0), (1280, 800), cam, None)  # type: ignore[arg-type]
    assert res.kind == SnapKind.NONE


def test_selection_prefers_precedence_then_depth():
    """Unit-test the selection directly with synthetic candidates."""
    from pluton.viewport.snap_engine import SnapEngine, SnapKind, _Candidate

    eng = SnapEngine()
    near = np.zeros(3, dtype=np.float32)
    cands = [
        _Candidate(SnapKind.ON_FACE, near, screen_dist=1.0, depth=5.0, label="f"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=3.0, depth=9.0, label="e"),
        _Candidate(SnapKind.MIDPOINT, near, screen_dist=2.0, depth=1.0, label="m"),
    ]
    chosen = eng._select(cands)
    assert chosen.kind == SnapKind.ENDPOINT  # precedence beats smaller screen_dist

    # Depth tie-break within the same kind: nearer (smaller depth) wins.
    two = [
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=9.0, label="far"),
        _Candidate(SnapKind.ENDPOINT, near, screen_dist=2.0, depth=2.0, label="near"),
    ]
    assert eng._select(two).label == "near"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -v`
Expected: FAIL — `snap()` rejects the new positional args / `_select` missing.

- [ ] **Step 3: Rewrite `snap()` + add generators + selection**

In `python/pluton/viewport/snap_engine.py`, replace the entire `snap(...)` method on `SnapEngine` with the following, and add the helper methods below it:

```python
    PIXEL_TOLERANCE = 8.0  # screen-space proximity for point/edge inferences
    AXIS_DEG_TOLERANCE = 5.0
    GRID_SIZE_WORLD = 1.0

    def snap(self, cursor_screen, viewport_size, camera, scene, anchor=None) -> SnapResult:
        """Return the chosen 3D snap for the given cursor.

        cursor_screen: (px, py) pixel coords. viewport_size: (width, height).
        The cursor ray and ground hit are derived internally from the camera.
        """
        if cursor_screen is None or camera is None or scene is None:
            return self._none()
        px, py = float(cursor_screen[0]), float(cursor_screen[1])
        width = int(viewport_size[0])
        height = int(viewport_size[1])
        ray_origin, ray_dir = camera.ray_from_screen(px, py, width, height)
        ground_hit = camera.ray_intersect_ground(px, py, width, height)

        cands: list[_Candidate] = []
        cands += self._endpoint_candidates(px, py, width, height, camera, scene)
        cands += self._edge_point_candidates(
            px, py, width, height, camera, scene, ray_origin, ray_dir
        )
        # On-Edge / On-Face plug in here (Task 9); Axis / Intersection (Task 10).

        within = [c for c in cands if c.screen_dist <= self.PIXEL_TOLERANCE]
        if within:
            return self._to_result(self._select(within))

        # Fallback: snap to the integer grid on the ground plane.
        if ground_hit is not None:
            gx = round(float(ground_hit[0]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            gy = round(float(ground_hit[1]) / self.GRID_SIZE_WORLD) * self.GRID_SIZE_WORLD
            return SnapResult(
                kind=SnapKind.GRID,
                world_position=np.array([gx, gy, 0.0], dtype=np.float32),
                axis=None, vertex_id=None, label="Grid",
            )
        return self._none()

    # --- selection --------------------------------------------------------

    def _select(self, candidates: list[_Candidate]) -> _Candidate:
        return min(candidates, key=lambda c: (_PRECEDENCE_RANK[c.kind], c.depth))

    def _to_result(self, c: _Candidate) -> SnapResult:
        return SnapResult(
            kind=c.kind,
            world_position=np.asarray(c.world_position, dtype=np.float32),
            axis=c.axis,
            vertex_id=c.vertex_id,
            label=c.label,
            edge_id=c.edge_id,
            face_id=c.face_id,
            edge_t=c.edge_t,
        )

    def _none(self) -> SnapResult:
        return SnapResult(
            kind=SnapKind.NONE,
            world_position=np.zeros(3, dtype=np.float32),
            axis=None, vertex_id=None, label="—",
        )

    # --- candidate generators --------------------------------------------

    def _endpoint_candidates(self, px, py, width, height, camera, scene):
        out: list[_Candidate] = []
        for v in scene.vertices_iter():
            proj = camera.world_to_screen(v.position, width, height)
            if proj is None:
                continue
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= self.PIXEL_TOLERANCE:
                out.append(_Candidate(
                    kind=SnapKind.ENDPOINT, world_position=v.position.copy(),
                    screen_dist=d, depth=depth, label="Endpoint", vertex_id=v.id,
                ))
        return out

    def _edge_point_candidates(self, px, py, width, height, camera, scene, ray_origin, ray_dir):
        """Midpoint candidates (On-Edge is added in Task 9 into this method)."""
        out: list[_Candidate] = []
        for e in scene.edges_iter():
            p1 = scene.vertex(e.v1_id).position
            p2 = scene.vertex(e.v2_id).position
            mid = (p1 + p2) * 0.5
            proj = camera.world_to_screen(mid, width, height)
            if proj is not None:
                sx, sy, depth = proj
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.MIDPOINT, world_position=mid.astype(np.float32),
                        screen_dist=d, depth=depth, label="Midpoint",
                        edge_id=e.id, edge_t=0.5,
                    ))
        return out
```

Also delete the now-unused `_AXIS_NAMES` reference inside the old method if the rewrite removed it (keep the module-level `_AXIS_NAMES` dict — Task 10 uses it).

- [ ] **Step 4: Update the viewport call site**

In `python/pluton/viewport/viewport_widget.py`, replace `_snap_for_event` (lines 147-160) with:

```python
    def _snap_for_event(self, event: QMouseEvent):
        pos = event.position()
        active = self.tool_manager.active if self.tool_manager is not None else None
        anchor = active.anchor_or_none if active is not None else None
        return self.snap_engine.snap(
            (float(pos.x()), float(pos.y())),
            (self.width(), self.height()),
            self.camera,
            self.scene,
            anchor=anchor,
        )
```

- [ ] **Step 5: Run the snap + viewport tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py tests/test_viewport.py -v`
Expected: PASS. If `test_viewport.py` references the old `snap(cursor_world, ...)` form, update those call sites to the new signature (same pattern as Step 4).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/snap_engine.py python/pluton/viewport/viewport_widget.py tests/test_snap_engine.py
git commit -m "feat(snap): ray-based 3D snap() core (endpoint + midpoint + grid)

snap() now takes (cursor_screen, viewport_size, camera, scene, anchor),
derives the cursor ray + ground hit internally, and ranks candidates in
screen space by precedence then depth. Endpoint/midpoint now work on
geometry ABOVE the ground plane. Viewport wired to the new signature.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: On-Edge + On-Face candidates

**Files:**
- Modify: `python/pluton/viewport/snap_engine.py` (extend `_edge_point_candidates`; add `_face_candidate`; call it in `snap()`)
- Test: `tests/test_snap_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_snap_engine.py` (above the Task 7 math tests is fine; order doesn't matter):

```python
def test_on_edge_snap_to_interior_point():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([0.0, 0.0, 2.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([4.0, 0.0, 2.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    cursor = _screen_of(cam, [1.0, 0.0, 2.0])  # quarter point, far from midpoint(2,0,2)
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_EDGE
    assert res.edge_id == e
    assert abs(res.edge_t - 0.25) < 5e-2
    np.testing.assert_allclose(res.world_position, [1.0, 0.0, 2.0], atol=5e-2)


def test_on_face_snap_over_a_face():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    v0 = scene.add_vertex(np.array([-1.0, -1.0, 1.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([1.0, -1.0, 1.0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([-1.0, 1.0, 1.0], dtype=np.float32))
    for a, b in [(v0, v1), (v1, v2), (v2, v3), (v3, v0)]:
        scene.add_edge(a, b)
    f = scene.add_face_from_loop([v0, v1, v2, v3])
    cam = _camera_at_default()
    cursor = _screen_of(cam, [0.0, 0.0, 1.0])  # face center
    res = eng.snap(cursor, (1280, 800), cam, scene)
    assert res.kind == SnapKind.ON_FACE
    assert res.face_id == f
    np.testing.assert_allclose(res.world_position[2], 1.0, atol=1e-3)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -k "on_edge or on_face" -v`
Expected: FAIL — On-Edge resolves as GRID/none; On-Face has no candidate yet.

- [ ] **Step 3: Add On-Edge into `_edge_point_candidates` and add `_face_candidate`**

In `python/pluton/viewport/snap_engine.py`, extend `_edge_point_candidates` — inside the `for e in scene.edges_iter():` loop, **after** the midpoint block, add the On-Edge block:

```python
            # On-Edge: closest point on the 3D segment to the cursor ray.
            on_pt, t = _closest_point_on_segment_to_ray(ray_origin, ray_dir, p1, p2)
            proj_e = camera.world_to_screen(on_pt, width, height)
            if proj_e is not None:
                sx, sy, depth = proj_e
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.ON_EDGE, world_position=on_pt,
                        screen_dist=d, depth=depth, label="On Edge",
                        edge_id=e.id, edge_t=t,
                    ))
```

Add the `_face_candidate` method after `_edge_point_candidates`:

```python
    def _face_candidate(self, ray_origin, ray_dir, scene):
        """On-Face via the C++ ray-mesh pick. Screen distance is 0 (under cursor)."""
        hit = scene.ray_pick_face(ray_origin, ray_dir)
        if hit is None:
            return None
        point = np.array([hit.point[0], hit.point[1], hit.point[2]], dtype=np.float32)
        return _Candidate(
            kind=SnapKind.ON_FACE, world_position=point,
            screen_dist=0.0, depth=float(hit.t), label="On Face",
            face_id=int(hit.face_id),
        )
```

Wire it into `snap()` — after the `cands += self._edge_point_candidates(...)` line, add:

```python
        face_cand = self._face_candidate(ray_origin, ray_dir, scene)
        if face_cand is not None:
            cands.append(face_cand)
```

- [ ] **Step 4: Run to verify pass + full snap suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -v`
Expected: PASS (all). On-Edge yields to Midpoint/Endpoint by precedence where they overlap; On-Face is the lowest-precedence geometry snap.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/snap_engine.py tests/test_snap_engine.py
git commit -m "feat(snap): On-Edge (ray-segment) + On-Face (ray_pick_face) candidates

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 3D Axis-lock + Intersection candidates

**Files:**
- Modify: `python/pluton/viewport/snap_engine.py` (add `_axis_candidates`, `_intersection_candidates`; call them when `anchor` is set; add `_INTERSECTION_EPS`)
- Test: `tests/test_snap_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_snap_engine.py`:

```python
def test_axis_lock_vertical_z_in_3d():
    """Z-axis lock — impossible in M2's ground-only world."""
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cursor = _screen_of(cam, [0.0, 0.0, 3.0])  # straight up the blue axis
    res = eng.snap(cursor, (1280, 800), cam, scene, anchor=anchor)
    assert res.kind == SnapKind.AXIS_LOCK
    assert res.axis == 2  # Z / blue
    np.testing.assert_allclose(res.world_position, [0.0, 0.0, 3.0], atol=5e-2)


def test_intersection_of_axis_line_and_edge():
    from pluton.scene import Scene
    from pluton.viewport.snap_engine import SnapEngine, SnapKind

    eng = SnapEngine()
    scene = Scene()
    # Edge crosses the X axis at (3,0,0) at parameter t=0.25 (NOT its midpoint).
    v0 = scene.add_vertex(np.array([3.0, -1.0, 0.0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([3.0, 3.0, 0.0], dtype=np.float32))
    e = scene.add_edge(v0, v1)
    cam = _camera_at_default()
    anchor = np.array([0.0, 0.0, 0.0], dtype=np.float32)  # draw along +X from origin
    cursor = _screen_of(cam, [3.0, 0.0, 0.0])
    res = eng.snap(cursor, (1280, 800), cam, scene, anchor=anchor)
    assert res.kind == SnapKind.INTERSECTION
    assert res.edge_id == e
    np.testing.assert_allclose(res.world_position, [3.0, 0.0, 0.0], atol=5e-2)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -k "axis_lock_vertical or intersection_of_axis" -v`
Expected: FAIL — axis returns GRID; intersection unhandled.

- [ ] **Step 3: Implement the two anchor-gated generators**

In `python/pluton/viewport/snap_engine.py`, add a module constant near the other tolerances:

```python
_INTERSECTION_EPS = 1e-3  # world-space closest-approach below this = a real crossing
_AXIS_DIRS = {
    0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
    1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
    2: np.array([0.0, 0.0, 1.0], dtype=np.float32),
}
```

Add the two methods to `SnapEngine`:

```python
    def _axis_candidates(self, px, py, width, height, camera, anchor, ray_origin, ray_dir):
        out: list[_Candidate] = []
        for axis_idx, axis_dir in _AXIS_DIRS.items():
            # Point on the infinite axis line (through anchor) nearest the cursor ray.
            _, _, _c_ray, c_axis = _closest_points_two_lines(ray_origin, ray_dir, anchor, axis_dir)
            proj = camera.world_to_screen(c_axis, width, height)
            if proj is None:
                continue
            sx, sy, depth = proj
            d = math.hypot(sx - px, sy - py)
            if d <= self.PIXEL_TOLERANCE:
                out.append(_Candidate(
                    kind=SnapKind.AXIS_LOCK, world_position=c_axis,
                    screen_dist=d, depth=depth,
                    label=f"on {_AXIS_NAMES[axis_idx]} Axis", axis=axis_idx,
                ))
        return out

    def _intersection_candidates(self, px, py, width, height, camera, scene, anchor):
        out: list[_Candidate] = []
        for axis_idx, axis_dir in _AXIS_DIRS.items():
            for e in scene.edges_iter():
                a = scene.vertex(e.v1_id).position
                b = scene.vertex(e.v2_id).position
                seg_dir = b - a
                _, t, c_axis, c_edge = _closest_points_two_lines(anchor, axis_dir, a, seg_dir)
                if t < 0.0 or t > 1.0:
                    continue  # crossing lies outside the edge segment
                if float(np.linalg.norm(c_axis - c_edge)) > _INTERSECTION_EPS:
                    continue  # skew — no genuine 3D crossing
                proj = camera.world_to_screen(c_edge, width, height)
                if proj is None:
                    continue
                sx, sy, depth = proj
                d = math.hypot(sx - px, sy - py)
                if d <= self.PIXEL_TOLERANCE:
                    out.append(_Candidate(
                        kind=SnapKind.INTERSECTION, world_position=c_edge,
                        screen_dist=d, depth=depth, label="Intersection",
                        edge_id=e.id, edge_t=float(t),
                    ))
        return out
```

Wire them into `snap()` — replace the comment line `# On-Edge / On-Face plug in here ... Axis / Intersection (Task 10).` (now that On-Edge/On-Face are in) with:

```python
        if anchor is not None:
            a = np.asarray(anchor, dtype=np.float32)
            cands += self._axis_candidates(px, py, width, height, camera, a, ray_origin, ray_dir)
            cands += self._intersection_candidates(px, py, width, height, camera, scene, a)
```

- [ ] **Step 4: Run to verify pass + full snap suite + the precedence regression**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap_engine.py -v`
Expected: PASS (all). Note Intersection outranks Axis-lock, so a point that is both resolves to Intersection.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/snap_engine.py tests/test_snap_engine.py
git commit -m "feat(snap): 3D axis-lock (incl. Z) + axis x edge intersection

Axis-lock projects the cursor ray onto the axis line through the anchor
(works off-ground, so the blue/Z axis now fires). Intersection finds where
an axis line from the anchor genuinely crosses an edge in 3D.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Renderer per-kind glyph table

The marker shape currently special-cases MIDPOINT→triangle, else square. Generalize to: square (Endpoint/On-Face/Grid/Axis), triangle (Midpoint), diamond (On-Edge), X (Intersection). Extract the shape math into a pure, testable function.

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py` (add `_snap_marker_vertices`; call it in `_draw_tool_overlay`; import `SnapKind`)
- Test: `tests/test_scene_renderer.py` (append a GL-free shape test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scene_renderer.py`:

```python
def test_snap_marker_vertices_shape_per_kind():
    import numpy as np
    from pluton.viewport.scene_renderer import _snap_marker_vertices
    from pluton.viewport.snap_engine import SnapKind

    p = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    # GL_LINES vertex counts: square=8, triangle=6, diamond=8, X=4.
    assert _snap_marker_vertices(int(SnapKind.ENDPOINT), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.ON_FACE), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.MIDPOINT), p).shape == (6, 3)
    assert _snap_marker_vertices(int(SnapKind.ON_EDGE), p).shape == (8, 3)
    assert _snap_marker_vertices(int(SnapKind.INTERSECTION), p).shape == (4, 3)
    # All markers are centered on p (z preserved).
    for kind in (SnapKind.ENDPOINT, SnapKind.MIDPOINT, SnapKind.ON_EDGE, SnapKind.INTERSECTION):
        v = _snap_marker_vertices(int(kind), p)
        assert np.allclose(v[:, 2], 3.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scene_renderer.py -k snap_marker_vertices -v`
Expected: FAIL — `ImportError: cannot import name '_snap_marker_vertices'`

- [ ] **Step 3: Add `_snap_marker_vertices` and use it**

In `python/pluton/viewport/scene_renderer.py`, add the import near the top (with the other pluton imports):

```python
from pluton.viewport.snap_engine import SnapKind
```

Add this module-level function (near the other module helpers, e.g. above the `SceneRenderer` class):

```python
def _snap_marker_vertices(kind: int, p) -> np.ndarray:
    """GL_LINES vertices (N, 3) for a snap marker centered at world point p.

    Shape per kind: triangle (Midpoint), diamond (On-Edge), X (Intersection),
    square (Endpoint / On-Face / Grid / Axis / default). Drawn flat in the XY
    plane at p.z (a billboard approximation, matching M2/M3b markers).
    """
    s = 0.05
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if kind == int(SnapKind.MIDPOINT):
        return np.array(
            [[x - s, y - s, z], [x + s, y - s, z],
             [x + s, y - s, z], [x, y + s, z],
             [x, y + s, z], [x - s, y - s, z]],
            dtype=np.float32,
        )
    if kind == int(SnapKind.ON_EDGE):  # diamond
        return np.array(
            [[x, y + s, z], [x + s, y, z],
             [x + s, y, z], [x, y - s, z],
             [x, y - s, z], [x - s, y, z],
             [x - s, y, z], [x, y + s, z]],
            dtype=np.float32,
        )
    if kind == int(SnapKind.INTERSECTION):  # X
        return np.array(
            [[x - s, y - s, z], [x + s, y + s, z],
             [x - s, y + s, z], [x + s, y - s, z]],
            dtype=np.float32,
        )
    # default: square
    return np.array(
        [[x - s, y - s, z], [x + s, y - s, z],
         [x + s, y - s, z], [x + s, y + s, z],
         [x + s, y + s, z], [x - s, y + s, z],
         [x - s, y + s, z], [x - s, y - s, z]],
        dtype=np.float32,
    )
```

In `_draw_tool_overlay`, replace the inline `if overlay.snap_marker_kind == 3: ... else: ...` shape block (lines ~479-499) with:

```python
                pos = _snap_marker_vertices(overlay.snap_marker_kind, p)
```

(Leave the surrounding color/upload/draw code unchanged.)

- [ ] **Step 4: Run to verify pass + full renderer suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_scene_renderer.py tests/test_renderer_merged_face.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py tests/test_scene_renderer.py
git commit -m "feat(renderer): per-kind snap marker glyphs (diamond on-edge, X intersection)

Extracts marker shape math into a pure _snap_marker_vertices() and adds
the diamond (On-Edge) and X (Intersection) glyphs alongside the existing
square/triangle. Endpoint vs On-Face stay square, color-separated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Tools consume 3D snaps — split-on-edge + shared color map

**Files:**
- Modify: `python/pluton/tools/line_tool.py` (add `_vertex_for_snap`; rewrite `on_mouse_press`; use shared color map; import `SplitEdgeCommand`)
- Modify: `python/pluton/tools/rectangle_tool.py` (use shared color map only — stays ground-plane)
- Test: `tests/test_line_tool_split.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_line_tool_split.py`:

```python
"""LineTool splits an edge when a vertex lands on its interior."""

from __future__ import annotations

import numpy as np
from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.line_tool import LineTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind, SnapResult


class _FakeEvent:
    """LineTool.on_mouse_press never touches the event; a stub suffices."""


def _snap(kind, pos, **kw):
    return SnapResult(
        kind=kind, world_position=np.array(pos, dtype=np.float32),
        axis=kw.get("axis"), vertex_id=kw.get("vertex_id"),
        label=kw.get("label", ""), edge_id=kw.get("edge_id"),
        face_id=kw.get("face_id"), edge_t=kw.get("edge_t"),
    )


def _make_tool(scene):
    stack = CommandStack()
    tool = LineTool()
    tool.activate(ToolContext(scene=scene, command_stack=stack,
                              camera=None, widget_size_provider=None))
    return tool, stack


def test_line_onto_edge_interior_splits_it():
    scene = Scene()
    a = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    b = scene.add_vertex(np.array([4, 0, 0], dtype=np.float32))
    e = scene.add_edge(a, b)
    tool, _ = _make_tool(scene)

    # Click 1: a fresh point off the edge.
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.GRID, [0, 2, 0]))
    # Click 2: onto the edge interior at t=0.5 → must split.
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ON_EDGE, [2, 0, 0], edge_id=e, edge_t=0.5))

    # A vertex now exists at (2,0,0)...
    positions = [tuple(round(float(c), 4) for c in v.position) for v in scene.vertices_iter()]
    assert (2.0, 0.0, 0.0) in positions
    # ...and the original edge was replaced (it is no longer live).
    assert not scene._mesh.edge_is_live(e)


def test_line_endpoint_snap_reuses_vertex():
    scene = Scene()
    a = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    tool, _ = _make_tool(scene)
    before = sum(1 for _ in scene.vertices_iter())
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.GRID, [1, 1, 0]))
    tool.on_mouse_press(_FakeEvent(), _snap(SnapKind.ENDPOINT, [0, 0, 0], vertex_id=a))
    # One new vertex (the grid click); the endpoint click reused vertex a.
    assert sum(1 for _ in scene.vertices_iter()) == before + 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_line_tool_split.py -v`
Expected: FAIL — On-Edge currently falls through to "new vertex" (no split; original edge stays live).

- [ ] **Step 3: Update the Line tool**

In `python/pluton/tools/line_tool.py`:

(a) Update imports:

```python
from pluton.commands.scene_commands import (
    AddEdgeCommand,
    AddFaceCommand,
    AddVertexCommand,
    SplitEdgeCommand,
)
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND
```

(b) Delete the module-level `_MARKER_COLOR_BY_KIND` dict and, in `on_mouse_move`, change the color lookup line to:

```python
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
```

(c) Add the resolver helper to the class (e.g. above `_reset_gesture`):

```python
    def _vertex_for_snap(self, snap, scene):  # noqa: ANN001
        """Resolve a snap to a vertex id. Splits the host edge for interior
        snaps. Returns (vertex_id, command_or_None); caller appends the command."""
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.ENDPOINT and snap.vertex_id is not None:
            return snap.vertex_id, None
        if snap.edge_id is not None and snap.edge_t is not None and snap.kind in (
            SnapKind.MIDPOINT, SnapKind.ON_EDGE, SnapKind.INTERSECTION
        ):
            split = SplitEdgeCommand(snap.edge_id, snap.edge_t)
            split.do(scene)
            if split.new_vertex_id is not None:
                return split.new_vertex_id, split
            # split was a no-op (degenerate t) → fall through to a plain vertex.
        cmd = AddVertexCommand(snap.world_position)
        cmd.do(scene)
        return cmd._vertex_id, cmd  # type: ignore[attr-defined]
```

(d) Replace `on_mouse_press` with the unified version (loop-closure stays special; branches 2/3 fold into the resolver):

```python
    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind

        if snap.kind == SnapKind.NONE:
            return
        s = self._scene  # type: ignore[assignment]

        if self._state == _State.IDLE:
            self._composite = CompositeCommand(name="Draw Line")
            vid, cmd = self._vertex_for_snap(snap, s)
            if cmd is not None:
                self._composite.children.append(cmd)
            self._gesture_vertex_ids = [vid]
            self._state = _State.DRAWING
            self._preview_tip = snap.world_position.copy()
            return

        assert self._composite is not None
        tip_vid = self._gesture_vertex_ids[-1]
        first_vid = self._gesture_vertex_ids[0]

        # Branch 1 — loop closure (snap back onto the first vertex with ≥3 points).
        if (
            snap.kind == SnapKind.ENDPOINT
            and snap.vertex_id == first_vid
            and len(self._gesture_vertex_ids) >= 3
        ):
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

        # Branches 2/3 — extend to a resolved vertex (reuse / split / new).
        vid, cmd = self._vertex_for_snap(snap, s)
        if vid == tip_vid:
            if cmd is not None:
                cmd.undo(s)  # degenerate: clicked the current tip
            return
        if cmd is not None:
            self._composite.children.append(cmd)
        e_cmd = AddEdgeCommand(tip_vid, vid)
        e_cmd.do(s)
        self._composite.children.append(e_cmd)
        self._gesture_vertex_ids.append(vid)
```

- [ ] **Step 4: DRY the Rectangle tool's color map**

In `python/pluton/tools/rectangle_tool.py`: delete the module-level `_MARKER_COLOR_BY_KIND` dict, add `from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND`, and in `on_mouse_move` change the color line to:

```python
        self._snap_marker_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL_COLOR)
```

(Rectangle stays ground-plane: it still builds corners at z=0 from `snap.world_position`'s x/y.)

- [ ] **Step 5: Run the new test + existing tool tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_line_tool_split.py tests/test_line_tool.py tests/test_rectangle_tool.py -v`
Expected: PASS (all). If `test_line_tool.py` asserted the old branch structure, adjust those assertions to the unified behavior (same observable outcome: vertices/edges created, loop closes).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/tools/line_tool.py python/pluton/tools/rectangle_tool.py tests/test_line_tool_split.py
git commit -m "feat(tools): Line tool splits edges on midpoint/on-edge/intersection snaps

Non-endpoint snaps that carry an edge_id now run a SplitEdgeCommand to
materialize a clean vertex (no T-junction) before connecting. Both tools
now share snap_engine.MARKER_COLOR_BY_KIND.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Regression guards + manual visual verification

**Files:** none (verification only; if a regression surfaces, fix it in the owning module + add a guard test there).

- [ ] **Step 1: Full C++ suite**

Run: `cmake --build build/tests` then `ctest --test-dir build/tests --output-on-failure`
Expected: PASS (all, including the new SplitEdge tests).

- [ ] **Step 2: Full Python suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (all). Pay attention to `test_viewport.py`, `test_line_tool.py`, `test_status_bar.py` — the snap signature + tool changes are the likely regression points. Fix any breakage in the owning module.

- [ ] **Step 2b: Lint**

Run: `.venv\Scripts\python.exe -m ruff check python/pluton tests`
Then: `.venv\Scripts\python.exe -m ruff format --check python/pluton tests`
Expected: PASS (no lint errors; formatting clean). Run `ruff format python/pluton tests` to fix formatting if needed, then re-commit the touched files.

- [ ] **Step 3: Manual visual verification (run the app)**

Run: `.venv\Scripts\python.exe -m pluton.app`

Verify each, deterministically:

1. **3D endpoint/edge/face markers.** Draw a rectangle on the ground (`R`, drag), push it up into a box (`P`, drag up). Press `L` (Line). Hover the box's **top corner** → green **square**. Hover the middle of a **top edge** → cyan **triangle**. Hover partway along an edge → red **diamond**. Hover the **top face** interior → blue **square**. (In M2 none of these fired off the ground.)
2. **Vertical (blue/Z) axis-lock.** Start a line at a top corner, move the cursor straight up → the rubber-band turns **blue** and locks to the Z axis. (Impossible in M2.)
3. **Split-on-edge builds clean topology.** Start a line somewhere, then click onto the **interior of an existing edge** → the line ends exactly on the edge and the edge **splits** at that point (a new vertex appears; the box stays solid/manifold). Press **Ctrl+Z** → the split + line are undone together and the edge is whole again. Press **Ctrl+Y** (redo) → reapplied cleanly.
4. **Intersection.** Start a line at the origin corner, move so an axis line from the start crosses another edge → a **magenta X** appears at the crossing.

- [ ] **Step 4: Report results to the controller.**

Summarize what rendered correctly and anything off. Do **not** proceed to Task 14 until the controller confirms the visuals look right. (No commit in this task.)

---

### Task 14: Release — v0.0.7-m3d

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` (version bump — the only task allowed to touch these)
- Modify: `docs/2026-05-16-pluton-design.md` (mark M3d shipped)

- [ ] **Step 1: Bump version 0.0.6 → 0.0.7**

- `pyproject.toml`: `version = "0.0.7"`
- `CMakeLists.txt`: `VERSION 0.0.7`
- `cpp/src/version.cpp`: `return "0.0.7";`

- [ ] **Step 2: Rebuild + verify version + full suites**

```bash
.venv\Scripts\python.exe -m pip install -e . --no-build-isolation
.venv\Scripts\python.exe -c "import pluton._core as c; print(c.version())"   # → 0.0.7
cmake --build build/tests
ctest --test-dir build/tests --output-on-failure
.venv\Scripts\python.exe -m pytest -q
```
Expected: version prints `0.0.7`; all C++ + Python tests PASS.

- [ ] **Step 3: Edit the master design's M3d line**

In `docs/2026-05-16-pluton-design.md`, update the M3d clause (in the M3 bullet) to note it shipped Tier 2 — 3D inferencing (endpoint/midpoint/on-edge/on-face/intersection + 3D axis) with `split_edge`; face-split (Tier 3) deferred to a future milestone.

- [ ] **Step 4: Commit the version bump + design note**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "release: v0.0.7 (M3d — 3D inferencing)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Push + verify CI green**

```bash
git push origin main
```
Then watch the run to completion and confirm BOTH jobs succeed (the M1 lesson — check the conclusion, not just the exit code):
```bash
gh run watch --exit-status
gh run view --json status,conclusion,jobs
```
Expected: `status: completed`, `conclusion: success`, with `Build & Test (windows-2022)` and `Build & Test (ubuntu-24.04)` both `success`.

- [ ] **Step 6: Tag the release (annotated, SSH-signed)**

```bash
git tag -a v0.0.7-m3d -m "Pluton v0.0.7 — M3d 3D inferencing (Tier 2)"
git cat-file -t v0.0.7-m3d        # → tag (annotated)
git push origin v0.0.7-m3d
```
(Signing is automatic via git config — do NOT pass `--no-gpg-sign`. A local `--show-signature` warning about `allowedSignersFile` is cosmetic; the signature is in the tag object. Confirm server-side with `gh api repos/:owner/:repo/git/refs/tags/v0.0.7-m3d`.)

- [ ] **Step 7: File carry-over issues**

Create GitHub issues (via `gh issue create`) for the deferred work:
1. **Face-split (Tier 3)** — let tools place a vertex on a face interior (On-Face drawing), splitting the face; blocked M3d On-Face from being a build target.
2. **Parallel / perpendicular "from point" linear inferences** — the magenta guide lines.
3. **Free edge–edge intersection inference** — beyond the M3d axis×edge case.
4. **Snap candidate spatial index** — replace the per-mouse-move linear scan (rolls into M10 performance).

- [ ] **Step 8: Final report**

Summarize: tag pushed, CI green (both jobs), test counts (C++ + Python), the carry-over issue numbers. M3 is now complete (M3a–M3d all shipped).

---

## Self-review checklist (controller runs before dispatch)

- [ ] **Spec coverage:** every inference in §3 of the design has a task (endpoint/midpoint T8, on-edge/on-face T9, axis/intersection T10); `split_edge` D9 → T2–T4; `SplitEdgeCommand` D10 → T6; `world_to_screen` D2 → T1; renderer glyphs D12 → T11; tool consumption D11 → T12; out-of-scope D + §8 → T14 issues.
- [ ] **No placeholders:** every code step has real code; every run step has an exact command + expected result.
- [ ] **Type/name consistency:** `SplitEdgeResult{vertex,edge_a,edge_b,face_a,face_b}` (C++) ↔ `SplitResult` namedtuple (Python) ↔ `SplitEdgeCommand.new_vertex_id`; `snap(cursor_screen, viewport_size, camera, scene, anchor)` signature used identically in T8 (engine), T8 (viewport), and every snap test; `MARKER_COLOR_BY_KIND` keyed by `SnapKind` in T7/T11/T12.

---

*End of M3d implementation plan.*






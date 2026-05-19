# Pluton M1 — Core Viewport: Design Spec

**Date:** 2026-05-19
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio)
**Milestone:** M1 — Core viewport (Phase 1, Foundation)
**Prerequisite:** M0 complete (tag `v0.0.1-m0`)
**License:** GPL-3.0-or-later

---

## 1. Purpose

M1 takes the M0 scaffold (Qt window with a hardcoded triangle, nanobind pipeline proven) and turns it into a **real 3D viewport**: a shaded cube rendered from a C++ `Mesh` type, orbiting in a Z-up world, with SketchUp-style mouse controls and a ground grid for spatial orientation.

This is Pluton's first **vertical slice**: it exercises the full architectural path C++ kernel → nanobind → Python → OpenGL with actual geometry rather than M0's hardcoded triangle. Everything M2 onward (drawing tools, push/pull, materials) is layered on top of the components built here.

## 2. End State

When M1 is complete, `python -m pluton` opens a window and the user sees:

- A flat-shaded 3D cube (1 m edge) sitting on the ground at the world origin
- A ground grid on the Z=0 plane (10×10 m extent, 1 m spacing)
- Red / green / blue lines through the origin marking the X / Y / Z axes
- Phong shading from a single directional light (above-front), neutral gray material
- **SketchUp-style camera controls:**
  - Middle mouse drag → orbit around the world origin
  - Shift + middle mouse drag → pan
  - Scroll wheel → zoom *toward the cursor*
- Z-up coordinate system everywhere (world up = `(0, 0, 1)`)
- CI green on Windows + Linux, with 6+ pytest tests and 4+ GoogleTest tests passing

## 3. Architecture

### 3.1 Decisions captured from brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Mesh data structure | **Indexed mesh** (positions + indices + normals); half-edge deferred to M3 | Half-edge has no consumer until push/pull. Designing it without one risks getting it wrong. |
| C++ Mesh API | **Real `Mesh` class** exposed via `nb::class_<Mesh>` | Establishes the pattern that M2/M3 geometry plugs into; ~50 extra lines of bindings now vs. a forced refactor in M2. |
| Cube shading | **Flat (per-face) normals** — 24 vertices, 36 indices | Smooth normals on a cube look like a beach ball. |
| Camera controls | **SketchUp-style** — MMB orbit, Shift+MMB pan, scroll zoom-to-cursor | Matches the audience's muscle memory. |
| Camera math placement | **Python with numpy** | One 4×4 matrix per frame is nowhere near a hot path. Adding `glm` to vcpkg would be premature. |
| Orientation aids | **Grid + colored axes** through origin; **no** corner XYZ gizmo | Best legibility-per-line-of-code. Corner gizmo adds a screen-space overlay viewport that's M2 work. |

### 3.2 Files added relative to M0

```
pluton/
├── cpp/
│   ├── include/pluton/
│   │   ├── mesh.h            # NEW
│   │   └── primitives.h      # NEW
│   ├── src/
│   │   ├── mesh.cpp          # NEW
│   │   └── primitives.cpp    # NEW
│   ├── bindings/
│   │   └── module.cpp        # MODIFIED — expose Mesh + make_cube
│   ├── tests/
│   │   ├── test_mesh.cpp         # NEW
│   │   └── test_primitives.cpp   # NEW
│   └── CMakeLists.txt        # MODIFIED — add new sources & test targets
│
└── python/pluton/
    └── viewport/
        ├── camera.py             # NEW
        ├── scene_renderer.py     # NEW
        ├── viewport_widget.py    # MODIFIED — real scene + mouse handling
        └── shaders/              # NEW directory
            ├── phong.vert
            ├── phong.frag
            ├── line.vert
            └── line.frag

└── tests/
    ├── test_mesh.py          # NEW
    ├── test_camera.py        # NEW
    └── test_viewport.py      # RENAMED/EXPANDED from test_window.py
```

### 3.3 Data flow — one rendered frame

```
1. Qt fires QOpenGLWidget.paintGL()
2. viewport_widget asks Camera (Python/numpy) for view + projection matrices
3. viewport_widget asks SceneRenderer to draw, in order:
     a. Grid lines       (line shader)
     b. Colored XYZ axes (line shader, same program as grid)
     c. Cube             (Phong shader, cube VBO + IBO + NBO)
4. SceneRenderer's first-frame init pulled cube vertex / index / normal arrays
   from the C++ Mesh as numpy views (no copy) and uploaded them to GL once.
5. Shaders receive uniforms: view, projection, light_dir, light_color,
   material_ambient, material_diffuse, material_specular, material_shininess
```

Mouse events handled by `viewport_widget`:
- `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent` for MMB and Shift+MMB
- `wheelEvent` for scroll zoom
- Each event mutates the `Camera` object and calls `self.update()`

## 4. Components

### 4.1 C++ Mesh

```cpp
// cpp/include/pluton/mesh.h
#pragma once

#include <cstdint>
#include <vector>

namespace pluton {

class Mesh {
public:
    // Flat, tightly-packed arrays — GPU-ready, zero-copy through nanobind to numpy.
    std::vector<float>    positions;  // [x,y,z, x,y,z, ...]
    std::vector<float>    normals;    // [nx,ny,nz, ...] — same length as positions
    std::vector<uint32_t> indices;    // triangle list

    std::size_t vertex_count()   const { return positions.size() / 3; }
    std::size_t triangle_count() const { return indices.size()   / 3; }
};

}  // namespace pluton
```

**Why flat `std::vector<float>` instead of `std::vector<Vec3>`?** It's the layout the GPU wants. nanobind exposes each member as a `(N, 3)` (or `(M,)`) numpy view with zero copy and zero reshape — the same memory the GPU eventually consumes.

**nanobind exposure:**
- `Mesh` is a class with `positions`, `normals`, `indices` accessible from Python as read-only numpy views (`nb::ndarray` with appropriate shape + dtype)
- Read-only because M1 doesn't mutate meshes; future mutation API is M2/M3 design

### 4.2 C++ primitives — cube

```cpp
// cpp/include/pluton/primitives.h
#pragma once

#include "pluton/mesh.h"

namespace pluton {

// Axis-aligned cube. Bottom face rests on z = 0; centered on x and y.
// Each face has its own normal (flat shading) — 24 vertices, 36 indices.
Mesh make_cube(float size = 1.0f);

}  // namespace pluton
```

Implementation notes:
- 6 faces × 4 vertices each = 24 vertices; corner vertices are duplicated per-face so each face carries its own normal
- 6 faces × 2 triangles each × 3 indices = 36 indices
- Vertex ordering: counterclockwise when viewed from outside (front-face culling-friendly)
- Bottom-on-grid placement: `z` runs `[0, size]`, `x` and `y` run `[-size/2, +size/2]` — matches SketchUp's "geometry sits on the ground" intuition

### 4.3 Python Camera

```python
# python/pluton/viewport/camera.py
from dataclasses import dataclass, field
import numpy as np

@dataclass
class Camera:
    position: np.ndarray = field(default_factory=lambda: np.array([8.0, -8.0, 6.0], dtype=np.float32))
    target:   np.ndarray = field(default_factory=lambda: np.array([0.0,  0.0, 0.5], dtype=np.float32))
    up:       np.ndarray = field(default_factory=lambda: np.array([0.0,  0.0, 1.0], dtype=np.float32))

    fov_y_deg: float = 45.0
    aspect:    float = 1.0     # widget sets this on resize
    near:      float = 0.01
    far:       float = 1000.0

    def view_matrix(self)       -> np.ndarray: ...  # 4×4 look-at
    def projection_matrix(self) -> np.ndarray: ...  # 4×4 perspective

    # Mouse-driven motion
    def orbit(self, dx_pixels: float, dy_pixels: float) -> None: ...
    def pan  (self, dx_pixels: float, dy_pixels: float) -> None: ...
    def zoom (self, scroll_delta: float, cursor_ndc: np.ndarray | None = None) -> None: ...
```

**Orbit:** convert `(position - target)` into spherical coordinates around `target`; advance azimuth by `dx · sensitivity`, elevation by `dy · sensitivity`; clamp elevation to `[-89°, +89°]` to avoid gimbal flip; convert back to Cartesian.

**Pan:** compute the camera's right vector (`(position - target) × up`) and up vector (perpendicular to right and view dir); translate `position` and `target` together by `dx · right + dy · up`, scaled by current distance so pan feels consistent at any zoom.

**Zoom toward cursor:** when `cursor_ndc` is provided, build a ray from the camera through the cursor's NDC position; advance `position` along that ray by a factor proportional to `scroll_delta`. The orbit pivot (`target`) is dragged along proportionally so zoom doesn't make orbit feel weird. When `cursor_ndc` is `None` (e.g., keyboard zoom later), zoom toward `target`.

**Default pose:** three-quarter view of a cube at origin, looking down and forward — matches SketchUp's default "Iso" camera.

### 4.4 SceneRenderer

```python
# python/pluton/viewport/scene_renderer.py
class SceneRenderer:
    """Owns GPU resources for the M1 scene: cube + grid + axes."""

    def initialize_gl(self) -> None: ...   # called once from initializeGL()
    def resize(self, w: int, h: int) -> None: ...
    def render(self, camera: Camera) -> None: ...  # called from paintGL()
    def cleanup_gl(self) -> None: ...
```

Owns:
- The cube's VBO (positions), NBO (normals), IBO (indices)
- The grid's VBO (line vertex positions for the grid lines)
- The axes' VBO (6 vertices: 3 colored line segments through origin)
- Two shader programs: Phong (cube) and line (grid + axes)

Pulls cube data from `pluton.make_cube()` on first frame, uploads once, draws every frame.

### 4.5 Shaders

All shaders use `#version 330 core` (matches M0; no new GL feature requirements).

**`phong.vert`** — transforms position by `proj * view * model`, transforms normal by `mat3(model)` (no scaling so this is correct), passes world-space position and normal to fragment shader.

**`phong.frag`** — single directional light using the standard Phong model:

```
final = ambient
      + diffuse  * max(0, dot(N, -L))
      + specular * pow(max(0, dot(R, V)), shininess)
```

Hardcoded uniforms in M1:
- Light direction (world space, direction the light *travels*): `normalize(vec3(-1, +1, -2))` — light originates above-and-camera-side, illuminating all three faces visible from the default camera pose (+X, -Y, +Z)
- Light color: `vec3(1.0, 0.97, 0.92)` (warm white)
- Material ambient: `vec3(0.15, 0.15, 0.17)`
- Material diffuse: `vec3(0.65, 0.65, 0.70)` (neutral gray)
- Material specular: `vec3(0.10, 0.10, 0.10)`
- Material shininess: `16.0`

**`line.vert` / `line.frag`** — flat color, no lighting. Color is a per-vertex attribute (so grid lines and axis lines can share one shader program).

Grid color: `vec3(0.4, 0.4, 0.4)`, centerline (X=0, Y=0) slightly brighter `vec3(0.6, 0.6, 0.6)`.
Axis colors: X = `(0.9, 0.2, 0.2)`, Y = `(0.2, 0.9, 0.2)`, Z = `(0.2, 0.4, 0.9)`.

### 4.6 viewport_widget changes

Compared to M0, `viewport_widget.py` is rewritten to:

- Construct a `Camera` and a `SceneRenderer` on init
- Forward `initializeGL` / `resizeGL` / `paintGL` to the renderer
- Handle `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` for MMB and Shift+MMB
- Handle `wheelEvent` for zoom (computing NDC of cursor and passing it to `Camera.zoom`)
- Set `setFocusPolicy(Qt.StrongFocus)` so the widget can later receive keyboard events (M2 will need this)

## 5. Testing

### 5.1 C++ (GoogleTest)

**`test_mesh.cpp`**
- Default-constructed Mesh has zero counts
- Mesh built from explicit data has correct `vertex_count` and `triangle_count`
- Arrays survive round-trip through copy

**`test_primitives.cpp`**
- `make_cube()` returns exactly 24 vertices and 36 indices
- `triangle_count()` == 12
- Every position lies within the expected AABB
- Every face's centroid lies at distance `size/2` from the cube's center along its normal
- Every face normal is unit-length within tolerance
- Indices are all in range `[0, 24)`

### 5.2 Python (pytest)

**`test_mesh.py`**
- `pluton.make_cube()` returns an object whose `positions` is a `(24, 3) float32` numpy view, `normals` is `(24, 3) float32`, `indices` is `(36,) uint32`
- Read-only enforcement: writing to the view raises
- Buffer is a view, not a copy (verifiable via `np.may_share_memory` or by checking the array's base pointer)

**`test_camera.py`**
- View matrix maps `position` to origin (within tolerance)
- Projection matrix maps a point on the near plane to NDC `z = -1` (or `0` depending on convention — pick one and stick with it)
- Orbit by 360° (in many small steps) returns position within 1e-4 of original
- Pan preserves `(position - target)` (distance to target unchanged)
- Zoom toward `target` (cursor=None) reduces `|position - target|`
- Zoom toward cursor keeps the world point under the cursor at (approximately) the same screen position

**`test_viewport.py`** (renamed from `test_window.py`, expanded)
- Widget constructs without raising
- `resizeGL(800, 600)` sets camera aspect to `800/600`
- One `paintGL` call doesn't raise (headless via `QT_QPA_PLATFORM=offscreen`)
- Sending a Qt middle-button press + drag + release rotates the camera (orbit took effect)
- Sending a wheel event changes the camera distance

### 5.3 Visual verification (manual)

User launches `python -m pluton` and confirms:
- Cube + grid + colored axes are visible
- Camera default pose looks like the screenshot in the M1 implementation plan (will be captured during execution)
- MMB orbit feels right
- Shift+MMB pan feels right
- Scroll zoom toward cursor feels right

Same handoff pattern as M0's triangle verification.

## 6. Out of Scope for M1 (Non-Goals)

- Selection / picking (M2)
- Drawing tools (Line, Rectangle) (M2)
- Multiple meshes in the scene (M2)
- Configurable materials beyond hardcoded Phong (M5)
- Orthographic projection (M4 — part of viewport styles)
- Corner XYZ axis gizmo overlay (M2 — needs a separate viewport region)
- Half-edge connectivity / adjacency queries (M3)
- File save/load (M6)
- Snapping / inferencing (M3)
- "Zoom extents", "Look around", any other camera modes beyond orbit/pan/zoom (M4)

## 7. Open Questions / Deferred Decisions

- **Orbit pivot smarter than world origin** — SketchUp orbits around the point under the cursor. Requires ray-mesh hit-testing. Deferred to M2 or M3 (once we have a BVH or at least multiple objects to hit-test against).
- **`glm` in C++** — revisit when M10 (performance) or M12 (native renderer) actually need C++-side per-frame math.
- **Camera animation / "zoom extents" / "fit selection"** — useful UX but not foundational. Punt to M4 (modeling polish).
- **NDC convention** — OpenGL traditional `[-1, 1]` z vs. reverse-Z. Pick during plan writing; M1 has no precision-sensitive math, so the simpler `[-1, 1]` is the default unless there's a reason to deviate.
- **Read-only numpy enforcement mechanism** — nanobind's exact incantation for read-only `nb::ndarray` is decided during plan writing.

## 8. Dependencies and Tooling Impact

- **No new vcpkg dependencies** — Mesh is plain `std::vector<float>`, primitives are plain math, GoogleTest is already in
- **No new Python runtime dependencies** — PySide6, PyOpenGL, numpy (transitively via nanobind) are already present
- **Same CMake / scikit-build-core / nanobind versions** as M0
- **clang-format** still pending install (carried over from M0 follow-ups) — not blocking; M1 source can be hand-formatted to the existing `.clang-format` rules

## 9. References

- M0 design + plan: `docs/2026-05-16-pluton-design.md`, `docs/2026-05-17-M0-foundation-plan.md`
- nanobind ndarray docs: <https://nanobind.readthedocs.io/en/latest/ndarray.html>
- Phong reflection model (Wikipedia): <https://en.wikipedia.org/wiki/Phong_reflection_model>
- SketchUp camera reference behaviour: SketchUp Pro user guide, "Orbiting, Panning, and Zooming"

## 10. Document History

| Date | Author | Change |
|---|---|---|
| 2026-05-19 | Rowee Apor | Initial M1 design from brainstorming session |

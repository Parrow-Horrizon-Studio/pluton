# Pluton M2 — Basic Drawing: Design Spec

**Date:** 2026-05-22
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio)
**Milestone:** M2 — Basic drawing (Phase 1, Foundation)
**Prerequisite:** M1 complete (tag `v0.0.2-m1`)
**License:** GPL-3.0-or-later

---

## 1. Purpose

M2 takes the M1 viewport (shaded cube, Z-up world, SketchUp-style camera) and turns it into a **drawing surface**: the user can interactively create geometry on the ground plane with a Line tool and a Rectangle tool, with SketchUp-style snapping and axis-locking, and closed planar loops become filled faces.

This is the milestone where Pluton begins to feel like a modeler rather than a viewer. It establishes:

- The **Python scene data model** (vertices, edges, faces) that the rest of Phase 1 and 2 builds on.
- The **tool framework** (`Tool` ABC + `ToolManager`) that M3's Push/Pull and M4's full tool roster plug into without rework.
- The **snap & inference engine** that grows in scope across M3 (snap-to-edge / intersections) and M4 (on-edge with edge-splitting, parallel/perpendicular).
- The **bottom status bar** that the M4 Measurements Box will reuse.

M3 (Push/Pull) needs *faces* to operate on — M2 produces them.

## 2. End State

When M2 is complete, `python -m pluton` opens a window and the user can:

- See the **grid + colored axes** (no cube — the empty ground plane is the starting canvas; `make_cube` survives as a C++ primitive for tests and fixtures).
- See an empty **status bar** along the bottom of the viewport showing `<tool> · <snap>` text.
- Press **`L`** to activate the Line tool, **`R`** for Rectangle, **`Esc`** to cancel any in-progress drawing gesture or to deactivate the current tool. **`Ctrl+N`** clears the entire scene back to grid + axes. At startup, no tool is active and the viewport is camera-only (orbit / pan / zoom from M1 still work).
- With **Rectangle** active: click → drag → click. A filled, flat-shaded face appears on the ground plane between the two corners, with its four edges around it.
- With **Line** active: click → click → click → … draws a polyline. When a click endpoint-snaps onto the *first vertex of the current polyline*, the loop closes and the enclosed planar region becomes a filled face (convex *or* concave, via earcut triangulation). When a click endpoint-snaps onto *some other existing vertex*, the polyline extends to it and the gesture continues.
- During drawing, snaps are active in precedence **endpoint > midpoint > axis-lock > grid**. Hovering over a snap target shows a type-coloured marker (green = endpoint, cyan = midpoint, axis-RGB = axis-lock, gray = grid). When axis-locked, the rubber-band line is drawn in the locked axis colour (red / green / blue).
- CI green on Windows + Linux, with the existing ~32 pytest + 14 GoogleTest tests still passing plus ~25–30 new pytest tests covering the scene model, snap engine, tool state machines, and the integrated flow.

## 3. Architecture

### 3.1 Decisions captured from brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Geometry produced | **Faces** auto-created on closed planar loop | M3 push/pull needs faces; producing them in M2 keeps M3 focused on extrusion + boolean. |
| Snap targets in M2 | **Grid, Endpoint, Midpoint, Axis-lock (R/G/B)** | Mandatory pair (Grid + Endpoint) plus the two that make drawing actually feel like SketchUp. |
| Snap precedence | **endpoint > midpoint > axis-lock > grid** | Deterministic tie-breaks when multiple snaps are within tolerance. |
| On-edge / intersection / parallel inference | **Deferred to M4** | Require splitting an existing edge mid-segment — a topology operation that belongs with the M3 half-edge structure. |
| Numeric input (Measurements Box) | **Deferred to M4** | Belongs with the per-document units work; building half of it in M2 means reworking the UX in M4. |
| Editable scene location | **Pure Python** (`Vertex`, `Edge`, `Face` objects) | Half-edge stays deferred to M3 per the M1 design doc; drawing is not a perf hot path. |
| Face triangulation | **`mapbox-earcut`** Python dep for non-convex; convex case uses a fan internally | Battle-tested triangulator; Line tool with concave loops works correctly. |
| Tool system | **Generic `Tool` base + `ToolManager`** | Same framework absorbs M3 Push/Pull and M4's full roster without rework. |
| Tool switching UI | **Keyboard only** (`L`, `R`, `Esc`); no toolbar | Toolbar widget lands in M4 alongside the rest of the tool roster. |
| Undo / redo | **None in M2**; `Ctrl+N` "Clear scene" as escape hatch | Command-pattern undo is M3 charter. Stubbing would create UX expectations M3 has to honour. |
| Snap & rubber-band visuals | **Hybrid** (option C from brainstorming) | Type-coloured markers; axis-coloured rubber-band; permanent bottom status bar (reusable in M4 for the Measurements Box). |
| Default scene at app start | **Grid + colored axes only** (M1 cube removed) | Empty canvas matches the "user creates geometry" framing; `make_cube` survives as a primitive for tests. |
| Default active tool at startup | **None** (camera-only) | Avoids a "Select" placeholder we don't have. User presses `L` / `R` to start drawing. |
| Self-intersecting Line polylines | **Allowed**; documented as known M2 limitation | Detection requires planar segment-intersection logic that belongs with M4. |
| C++ code changes | **None expected in M2** | First Python-only milestone. The nanobind boundary is exercised through the existing `Mesh` + `make_cube`. |

### 3.2 Files added relative to M1

```
pluton/
├── python/pluton/
│   ├── scene/                       # NEW PACKAGE
│   │   ├── __init__.py
│   │   ├── vertex.py                # NEW — Vertex(id, position)
│   │   ├── edge.py                  # NEW — Edge(id, v1_id, v2_id)
│   │   ├── face.py                  # NEW — Face(id, loop_vertex_ids, plane_normal, triangles)
│   │   └── scene.py                 # NEW — Scene: holds entities, IDs, close-loop detection
│   │
│   ├── viewport/
│   │   ├── snap_engine.py           # NEW — SnapKind enum, SnapResult, SnapEngine
│   │   ├── camera.py                # MODIFIED — adds ray_from_screen + ray_intersect_ground
│   │   ├── scene_renderer.py        # MODIFIED — render user edges + user faces + tool overlay; M1 hardcoded cube removed from default render path
│   │   ├── viewport_widget.py       # MODIFIED — delegate events to active tool; snap evaluation
│   │   └── shaders/                 # (no new shaders; line + phong reused)
│   │
│   ├── tools/                       # NEW PACKAGE
│   │   ├── __init__.py
│   │   ├── tool.py                  # NEW — Tool ABC + ToolOverlay dataclass + ToolContext
│   │   ├── tool_manager.py          # NEW — one active tool at a time
│   │   ├── line_tool.py             # NEW
│   │   └── rectangle_tool.py        # NEW
│   │
│   └── ui/
│       ├── main_window.py           # MODIFIED — hosts status bar; binds L / R / Esc / Ctrl+N
│       └── status_bar.py            # NEW — bottom widget showing tool + snap text
│
└── tests/
    ├── test_scene.py                # NEW
    ├── test_snap_engine.py          # NEW
    ├── test_line_tool.py            # NEW
    ├── test_rectangle_tool.py       # NEW
    ├── test_tool_manager.py         # NEW
    ├── test_camera.py               # MODIFIED — adds ray_from_screen tests
    └── test_viewport.py             # MODIFIED — keyboard bindings, status bar, full gestures
```

### 3.3 Dependencies added

- `mapbox-earcut` (Python wheel — small, no compile required).
  Declared in `pyproject.toml` alongside `numpy>=2.0`.

No new C++ libraries. `vcpkg.json` is untouched. `CMakeLists.txt` is untouched.

### 3.4 Data flow — one rendered frame

```
Qt fires QOpenGLWidget.paintGL()
  → ViewportWidget asks Camera for view + projection matrices
  → ViewportWidget asks active tool (if any) for ToolOverlay
  → ViewportWidget asks SceneRenderer to render(camera, scene, tool_overlay)
       1. Grid lines             (line shader, M1)
       2. Colored XYZ axes       (line shader, M1)
       3. User faces             (Phong shader, M1)         ← NEW pass
       4. User edges             (line shader)              ← NEW pass
       5. Tool overlay           (line shader, depth off)   ← NEW pass
            5a. Rubber-band segments (axis-coloured or neutral)
            5b. Snap marker (small screen-space quad, billboarded)
```

If `scene.dirty` is set, the user-face and user-edge VBOs are re-uploaded before the pass. Tool overlay is rebuilt and uploaded every frame.

### 3.5 Data flow — mouse move with active tool

```
Qt fires mouseMoveEvent → ViewportWidget.mouseMoveEvent(event)
  → existing MMB / Shift+MMB logic handles camera drag (M1, unchanged)
  → if no MMB drag in progress and a tool is active:
       cursor_screen = event.position()
       cursor_world  = Camera.ray_intersect_ground(cursor_screen, width, height)
       snap = SnapEngine.snap(cursor_world, cursor_screen, camera, scene, anchor=tool.anchor_or_none)
       active_tool.on_mouse_move(event, snap)
       status_bar.update(tool=tool.name, snap=snap.label)
       widget.update()       # triggers paintGL
```

`Camera.ray_intersect_ground` is a thin convenience built on `Camera.ray_from_screen(x, y, width, height)` (the lower-level helper M4 will reuse for drawing on faces).

## 4. Components

### 4.1 Scene data model

```python
# python/pluton/scene/vertex.py
@dataclass(frozen=True, slots=True)
class Vertex:
    id: int
    position: np.ndarray  # shape (3,), dtype=float32, Z-up world coords

# python/pluton/scene/edge.py
@dataclass(frozen=True, slots=True)
class Edge:
    id: int
    v1_id: int
    v2_id: int  # undirected; v1_id < v2_id is the canonical order
```

```python
# python/pluton/scene/face.py
@dataclass(frozen=True, slots=True)
class Face:
    id: int
    loop_vertex_ids: tuple[int, ...]   # ordered around the loop, CCW from +Z (ground-plane convention)
    plane_normal: np.ndarray            # shape (3,), unit; (0, 0, 1) for ground faces in M2
    triangles: np.ndarray               # shape (N, 3), int32 — vertex IDs per triangle
```

Faces store their triangulation eagerly. Recomputing earcut on every paint would be wasted work; recomputing on every edit is fine — faces are small (a handful of vertices) and edits are infrequent.

```python
# python/pluton/scene/scene.py
class Scene:
    """Editable polygonal scene. Owns vertex/edge/face IDs and adjacency."""

    # Mutators
    def add_vertex(self, position: np.ndarray) -> int: ...         # idempotent on exact match
    def add_edge(self, v1_id: int, v2_id: int) -> int: ...         # idempotent on unordered pair; rejects self-loops
    def add_face_from_loop(self, ordered_vertex_ids: Sequence[int]) -> int: ...
    def clear(self) -> None: ...

    # Queries used by tools / snap engine
    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None: ...
    def edges_iter(self) -> Iterable[Edge]: ...
    def faces_iter(self) -> Iterable[Face]: ...

    # Render-buffer projection (rebuilt on edit, cached otherwise)
    def edge_line_buffer(self) -> np.ndarray: ...                  # shape (2*E, 3), float32
    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]: ...  # (positions, normals)

    @property
    def dirty(self) -> bool: ...
```

### 4.2 Snap engine

```python
# python/pluton/viewport/snap_engine.py
class SnapKind(IntEnum):
    NONE      = 0
    GRID      = 1
    AXIS_LOCK = 2
    MIDPOINT  = 3
    ENDPOINT  = 4   # numeric order encodes precedence (higher wins)

@dataclass(frozen=True, slots=True)
class SnapResult:
    kind: SnapKind
    world_position: np.ndarray   # snapped world point (Z = 0 in M2)
    axis: int | None             # 0 = X (red), 1 = Y (green), 2 = Z (blue); only set when kind == AXIS_LOCK
    vertex_id: int | None        # only set when kind == ENDPOINT
    label: str                   # for the status bar, e.g. "Endpoint", "on Green Axis"

class SnapEngine:
    PIXEL_TOLERANCE = 8.0        # screen-space, endpoint & midpoint
    AXIS_DEG_TOLERANCE = 5.0     # angular tolerance for axis-lock
    GRID_SIZE_WORLD = 1.0        # 1 m grid spacing matches M1 grid

    def snap(self,
             cursor_world_on_ground: np.ndarray | None,
             cursor_screen: tuple[float, float],
             camera: Camera,
             scene: Scene,
             anchor: np.ndarray | None = None,   # set during line-tool's rubber-band phase
             ) -> SnapResult: ...
```

The engine evaluates each candidate snap, keeps the one with the highest precedence within tolerance, and returns it. `Grid` is always available as a floor on the ground plane, so `SnapKind.NONE` is returned only when `cursor_world_on_ground is None` (cursor above the horizon — see §5.3). `axis` is set only for `AXIS_LOCK`; `vertex_id` is set only for `ENDPOINT`.

### 4.3 Tool framework

```python
# python/pluton/tools/tool.py
class Tool(ABC):
    name: str          # "Line", "Rectangle"
    shortcut: str      # "L", "R"

    @abstractmethod
    def activate(self, ctx: ToolContext) -> None: ...
    @abstractmethod
    def deactivate(self) -> None: ...                # also called on ESC mid-gesture or tool switch

    def on_mouse_move(self, event: QMouseEvent, snap: SnapResult) -> None: ...
    def on_mouse_press(self, event: QMouseEvent, snap: SnapResult) -> None: ...
    def on_key_press(self, event: QKeyEvent) -> None: ...

    @abstractmethod
    def overlay(self) -> ToolOverlay: ...            # transient preview geometry

    @property
    def anchor_or_none(self) -> np.ndarray | None: ...  # rubber-band anchor for SnapEngine

@dataclass(frozen=True, slots=True)
class ToolOverlay:
    rubber_band_segments: np.ndarray                 # shape (2*N, 3), float32
    rubber_band_color: tuple[float, float, float]    # axis colour or neutral
    snap_marker_position: np.ndarray | None          # world XYZ, or None
    snap_marker_color: tuple[float, float, float]    # by SnapKind
```

```python
# python/pluton/tools/tool_manager.py
class ToolManager:
    def register(self, tool: Tool) -> None: ...
    def activate_by_shortcut(self, key: str) -> bool: ...
    def deactivate_current(self) -> None: ...        # bound to ESC when no gesture is in progress
    @property
    def active(self) -> Tool | None: ...
```

`LineTool` and `RectangleTool` each own a small internal state machine — see §4.5 below for their click logic.

### 4.4 SceneRenderer extensions

The render contract becomes `SceneRenderer.render(camera, scene, tool_overlay)`. Three new passes are added after M1's grid + axes pass:

1. **User faces** — Phong-shaded, same shader and uniforms as the M1 cube; positions and normals come from `scene.face_triangle_buffer()`.
2. **User edges** — line shader; positions from `scene.edge_line_buffer()`; single neutral color (dark gray, distinguishable from the grid).
3. **Tool overlay** — line shader with depth-test disabled so it draws on top; rubber-band + snap marker from the active tool's `ToolOverlay`. The snap marker is rendered as a small screen-space square billboarded to the camera (4-vertex quad).

The user-face and user-edge VBOs are re-uploaded only when `scene.dirty` is set. The tool overlay is rebuilt every frame (cheap — at most a few segments).

### 4.5 Tool state machines

**RectangleTool** (the simpler one):

```
State: IDLE
  on_mouse_press(snap):
    first_corner = snap.world_position
    state = DRAGGING

State: DRAGGING
  on_mouse_move(snap):
    second_corner_preview = snap.world_position
    overlay.rubber_band = the four segments of the axis-aligned rect
                          between first_corner and second_corner_preview
    overlay.snap_marker = snap.world_position (color by snap.kind)

  on_mouse_press(snap):
    second_corner = snap.world_position
    if second_corner == first_corner: state = IDLE; return       # zero-area: drop
    v0..v3 = scene.add_vertex(...)  for the four corners (CCW)
    scene.add_edge(v0,v1); scene.add_edge(v1,v2); scene.add_edge(v2,v3); scene.add_edge(v3,v0)
    scene.add_face_from_loop((v0,v1,v2,v3))
    state = IDLE

  on_key_press(ESC):
    state = IDLE; overlay cleared (no scene mutation)
```

**LineTool** (three-branch click logic):

```
State: IDLE
  on_mouse_press(snap):
    gesture_vertex_ids = [scene.add_vertex(snap.world_position)]
    state = DRAWING

State: DRAWING
  on_mouse_move(snap):
    anchor = scene.vertex(gesture_vertex_ids[-1]).position
    overlay.rubber_band = single segment from anchor → snap.world_position
    overlay.rubber_band_color = axis color if snap.kind == AXIS_LOCK else neutral
    overlay.snap_marker = snap.world_position (color by snap.kind)

  on_mouse_press(snap):
    IF snap.kind == ENDPOINT and snap.vertex_id == gesture_vertex_ids[0] and len(gesture_vertex_ids) >= 3:
        # branch 1 — loop closure
        scene.add_edge(gesture_vertex_ids[-1], gesture_vertex_ids[0])
        scene.add_face_from_loop(tuple(gesture_vertex_ids))
        state = IDLE
    ELIF snap.kind == ENDPOINT:
        # branch 2 — extend polyline to an existing vertex
        if snap.vertex_id == gesture_vertex_ids[-1]: return       # degenerate: dropped
        scene.add_edge(gesture_vertex_ids[-1], snap.vertex_id)
        gesture_vertex_ids.append(snap.vertex_id)
    ELSE:
        # branch 3 — new vertex
        new_v = scene.add_vertex(snap.world_position)
        if new_v == gesture_vertex_ids[-1]: return                # degenerate: dropped
        scene.add_edge(gesture_vertex_ids[-1], new_v)
        gesture_vertex_ids.append(new_v)

  on_key_press(ESC):
    state = IDLE; gesture_vertex_ids = []; overlay cleared (no scene mutation)
```

Note that ESC mid-gesture **rolls back** the visible gesture state but does **not** un-add the vertices and edges already committed to the `Scene`. Without an undo stack we cannot cleanly distinguish "vertices added this gesture" from "vertices that already existed and were extended-to in branch 2." This is one of the costs of deferring undo to M3 and is acceptable for M2.

### 4.6 Status bar

`StatusBar` is a thin `QWidget` wrapper around two `QLabel`s, docked along the bottom of the central widget in `MainWindow`. Format: `<tool> · <snap>` where each slot is empty when nothing applies.

| State | Bar text |
|---|---|
| No tool active | `(empty)` |
| Line tool active, no snap | `Line · —` |
| Line tool active, hovering near a grid intersection | `Line · Grid` |
| Line tool active, hovering near an existing vertex | `Line · Endpoint` |
| Line tool drawing, rubber-band locked to Y axis | `Line · on Green Axis` |

In M4 a third slot appears: the Measurements Box value. The widget is laid out with that future slot in mind.

## 5. Edge cases & error handling

### 5.1 Degenerate clicks

| Situation | M2 behaviour |
|---|---|
| Line tool: two consecutive clicks snap to the same vertex | Drop the second click; tool stays in DRAWING. |
| Line tool: loop-close attempt with fewer than 3 vertices in the gesture | Ignore the close; tool stays in DRAWING. |
| Rectangle tool: second corner equals first corner | Drop the gesture; nothing added. |
| Anywhere: `Scene.add_edge(v, v)` | `Scene` rejects with `ValueError`. |

### 5.2 Self-intersecting Line polylines

Allowed. Mapbox-earcut produces some triangulation, the resulting face is geometrically invalid (self-overlapping), and the user redraws. Detection requires planar segment-intersection logic and belongs with the M4 on-edge / intersection snap work.

### 5.3 Cursor above the horizon

When the cursor ray from the camera either runs parallel to Z = 0 or hits it behind the camera, `Camera.ray_intersect_ground` returns `None`. The snap engine then returns `SnapKind.NONE`. Tools ignore mouse events with `NONE` snap — no rubber-band update, no click commit. The status bar shows `—` for the snap text.

### 5.4 Tool switching mid-gesture

`L` / `R` pressed while a different tool is mid-gesture:

```
ToolManager.activate_by_shortcut(new):
    if active is not None:
        active.deactivate()         # tool clears its own gesture state, no scene mutation
    new.activate(ctx)
```

The in-progress gesture is silently dropped — same effect as ESC followed by tool switch.

### 5.5 Vertex / edge de-duplication

`Scene.add_vertex` and `Scene.add_edge` are idempotent on exact match:

- `add_vertex` returns the existing vertex ID if any stored vertex has `np.array_equal(position, existing.position)`. No epsilon: the snap engine produces deterministic positions (grid snaps to whole meters; endpoint snap returns the exact stored position), so exact equality is sufficient and prevents accidental tolerance drift. This invariant is documented in the `Scene.add_vertex` docstring and is exercised by `test_scene.py`.
- `add_edge(a, b)` returns the existing edge ID if `(min(a, b), max(a, b))` matches any stored edge. Self-loops (`a == b`) raise.

### 5.6 Known M2 limitations (deferred fixes)

1. **No edge splitting.** A Line drawn through the middle of an existing edge does not split that edge. New geometry and existing geometry share no topology at the crossing point. *Fix: M4, with on-edge / intersection snap.*
2. **No self-intersection detection in Line polylines.** A self-crossing closed polyline produces a geometrically broken face. *Fix: M4, with intersection-aware drawing.*
3. **No undo / redo.** `Ctrl+N` clears the entire scene as the only escape hatch. ESC mid-gesture cancels the visible preview but does not roll back already-committed geometry within the gesture. *Fix: M3, with the command pattern.*
4. **No drawing on existing face surfaces.** Drawing is strictly on the ground plane. *Fix: M4.*
5. **No numeric input.** *Fix: M4, with the units system.*
6. **No `remove_*` operations on `Scene`.** *Fix: M3, with push/pull as the first consumer.*

**Carry-over policy:** at M2 tag time, every entry in §5.6 (Known limitations) and §6 (Out of scope) is opened as a GitHub issue tagged with the milestone it lands in (`M3`, `M4`, …). Same pattern that worked for M1.

## 6. Out of scope for M2

Things people might reasonably expect from a "drawing" milestone but that M2 does **not** ship. Each has a roadmap home.

| Not in M2 | Lands in |
|---|---|
| Push / Pull (extruding a face) | **M3** |
| Undo / redo + command pattern | **M3** |
| `Scene.remove_*` operations | **M3** |
| Half-edge data structure | **M3** |
| First version of inferencing (snap-to-edge, intersections) | **M3** |
| On-edge snap + edge splitting | **M4** |
| Self-intersection detection in Line tool | **M4** |
| Circle / Arc / Polygon tools | **M4** |
| Eraser / Select / Move / Rotate / Scale | **M4** |
| Tape Measure | **M4** |
| User-switchable imperial / metric units | **M4** |
| Measurements Box (numeric input while drawing) | **M4** |
| Groups and Components | **M4** |
| Tool palette / toolbar widget | **M4** |
| Drawing on existing face surfaces | **M4** |
| Materials, viewport styles, layers | **M5** |
| File I/O (saving the scene) | **M6** |

## 7. The M2 → M3 contract

What M3 inherits from M2:

- `pluton.scene.Scene` with `add_vertex` / `add_edge` / `add_face_from_loop` / `clear` / iterators / render-buffer projections.
- `pluton.scene.Face` with `loop_vertex_ids`, `plane_normal`, and `triangles`.
- `pluton.tools.Tool` ABC + `ToolManager` — M3 implements `PushPullTool` against the same framework.
- `SceneRenderer` rendering user faces with Phong, so an extruded face looks consistent with M2's drawn face.
- `SnapEngine` — M3 may extend it with new `SnapKind` values (e.g. on-face hit for push/pull's "drag this face" gesture).
- The bottom status bar widget — M3 plugs into the same slots.

What M3 has to add fresh:

- `Scene.remove_*` operations and the topology mutations push / pull needs.
- The half-edge data structure (M3's central design decision).
- The command pattern + undo / redo stack.
- Ray-mesh intersection (camera ray → which face under cursor).
- CGAL boolean merge (extruded prism ∪ existing geometry).
- First-pass inferencing (snap to existing geometry's edges / intersections).

## 8. Testing strategy

Same TDD discipline as M1: each subagent task writes a failing test first, watches it fail, implements the minimum to pass, watches it pass, then commits.

| File | Test file | Coverage |
|---|---|---|
| `scene/scene.py` | `tests/test_scene.py` | `add_vertex` idempotency; `add_edge` unordered de-dup + self-loop rejection; `add_face_from_loop` rejects < 3 vertices; `clear` resets all dicts; `edge_line_buffer` / `face_triangle_buffer` shapes; `find_vertex_near` returns nearest within tolerance and `None` otherwise; dirty flag toggles correctly. |
| `viewport/snap_engine.py` | `tests/test_snap_engine.py` | Each `SnapKind` fires in isolation; precedence resolution when multiple snaps are within tolerance; `axis` field set only for `AXIS_LOCK`; `vertex_id` set only for `ENDPOINT`; `NONE` returned when the cursor ray misses the ground. |
| `viewport/camera.py` | `tests/test_camera.py` | New: `ray_from_screen` returns a ray with correct origin (= camera position) and direction (unit, points away from camera); `ray_intersect_ground` returns the correct point on Z = 0 for a downward ray and `None` for an upward / parallel ray. |
| `tools/tool.py` + `tool_manager.py` | `tests/test_tool_manager.py` | Register / activate / deactivate / shortcut lookup; switching tools mid-gesture deactivates the old one; no active tool by default. |
| `tools/line_tool.py` | `tests/test_line_tool.py` | State machine; three-branch click logic; ESC cancels the visible gesture without mutating scene-after-the-last-committed-vertex; < 3-vertex close attempt ignored. |
| `tools/rectangle_tool.py` | `tests/test_rectangle_tool.py` | Two-corner gesture produces 4 vertices + 4 edges + 1 face; zero-area gesture rejected; ESC mid-drag cancels. |
| `ui/main_window.py` + `ui/status_bar.py` | `tests/test_viewport.py` (expanded) | Pressing `L` / `R` activates the right tool; ESC cancels gestures or deactivates; `Ctrl+N` clears scene; status bar text updates on tool change and on snap change; full Rectangle gesture via qtbot creates 4 verts / 4 edges / 1 face; full Line loop closure via qtbot creates the expected face. |

**Coverage count targets after M2:**

| Layer | After M2 |
|---|---|
| Pytest | ~57–62 |
| GoogleTest | 14 (unchanged — no C++ touched) |

**Manual visual verification checklist** (the M2 equivalent of M1 Task 9): the implementation plan will spell it out, but in summary — open the app, exercise both tools, exercise each snap kind, exercise ESC and `Ctrl+N`, and confirm orbit / pan / zoom still work and do not trigger tool events.

## 9. Implementation order (preview)

The implementation plan will own the exact task decomposition. Tentative shape — ~12–13 tasks, mirroring M1's cadence:

1. `Scene` core (`Vertex` / `Edge` / `Face` dataclasses + `Scene.add_*` + `clear`) — TDD
2. `Scene.find_vertex_near` + render-buffer projection methods — TDD
3. `Camera.ray_from_screen` + `ray_intersect_ground` — TDD
4. `SnapEngine` (each `SnapKind` + precedence) — TDD
5. `Tool` ABC + `ToolOverlay` + `ToolManager` — TDD
6. `RectangleTool` (simpler state machine, ships first) — TDD
7. `LineTool` (three-branch click logic + ESC cancel) — TDD
8. `SceneRenderer` extensions (user-face pass, user-edge pass, overlay pass) — code + render-test
9. `StatusBar` widget + `MainWindow` integration (`L` / `R` / Esc / `Ctrl+N` bindings) — TDD via qtbot
10. `ViewportWidget` rewrite for tool delegation + per-move snap evaluation — TDD via qtbot
11. Manual visual verification
12. Push and verify CI on both runners
13. Version bump to `0.0.3` and release tag `v0.0.3-m2`

The milestone is Python-only. The build incantation from M1 stays identical.

## 10. References

- M0 design: `docs/2026-05-17-M0-foundation-plan.md`
- M1 design: `docs/2026-05-19-M1-core-viewport-design.md`
- M1 plan: `docs/2026-05-19-M1-core-viewport-plan.md`
- Project design: `docs/2026-05-16-pluton-design.md`
- **mapbox-earcut** (Python wheel): https://pypi.org/project/mapbox-earcut/
- **SketchUp inferencing documentation** (reference for snap behaviours): https://help.sketchup.com/

## 11. Document history

| Date | Author | Change |
|---|---|---|
| 2026-05-22 | Rowee Apor | Initial design from brainstorming session |

# Pluton M3a — Topology & Undo: Design Spec

**Date:** 2026-05-22
**Status:** Approved design, ready for implementation plan
**Author:** Rowee Apor (Parrow Horrizon Studio)
**Milestone:** M3a — Topology & Undo (Phase 1, Foundation; first sub-milestone of M3)
**Prerequisite:** M2 complete (tag `v0.0.3-m2`)
**License:** GPL-3.0-or-later

---

## 1. Purpose

The roadmap's M3 milestone — "Push/Pull" — bundles five substantial pieces of architecture (half-edge data structure, push/pull tool, CGAL booleans, command-pattern undo, first inferencing on existing geometry, `Scene.remove_*`). Treating it as one milestone risks long stalls on the first piece (CGAL build setup) before the headline feature (push/pull) is even verifiable.

M3 is decomposed into three sub-milestones, each with its own design / plan / tag cycle:

- **M3a — Topology & Undo** (this spec): the half-edge data structure in C++, the M2 `Scene` rewired as a thin wrapper, `Scene.remove_*` operations, and a command-pattern undo/redo stack. **No new tools.**
- **M3b — Push/Pull (basic)**: ray-mesh face picking, the `PushPullTool` itself, drag-extrude along the face normal. Extrusion result is topologically valid but does not boolean-merge with existing geometry — overlaps are visually possible.
- **M3c — Booleans & Inferencing**: CGAL integration via vcpkg, mesh-mesh boolean union for push/pull, first inferencing on existing edges (snap-to-edge, midpoints of existing edges, edge-edge intersections projected onto the drawing plane).

M3a is the substrate everything else needs. It establishes the architecture the C++ kernel will use from here forward — `HalfEdgeMesh` is the *geometric source of truth* — without yet exercising the harder geometric operations that depend on it.

## 2. End State

When M3a is complete, `python -m pluton` looks **almost identical** to M2 from the user's perspective. What changes:

- All M2 tools (Line, Rectangle) still work exactly as before. Drawing a rectangle still produces 4 vertices, 4 edges, 1 filled face on the ground.
- **`Ctrl+Z`** undoes the last completed tool gesture. **`Ctrl+Y`** (or `Ctrl+Shift+Z`) redoes. Multiple undo/redo cycles work.
- **`Ctrl+N` (clear scene) is now undo-able.** Pressing `Ctrl+Z` after `Ctrl+N` restores the previous scene with original vertex / edge / face IDs intact.
- **ESC mid-gesture now performs a clean rollback** of any in-progress mutations (a behavior improvement over M2 §5.6 limitation #3, which is eliminated by the command-pattern refactor).
- The status bar communicates the same `<tool> · <snap>` text as M2.
- **No new GL or visual changes.** The renderer continues to draw against `Scene.edge_line_buffer()` / `face_triangle_buffer()` — those return identical output to M2.

Under the hood, the architecture changes substantially:

- The C++ kernel grows a `HalfEdgeMesh` class — vertices, half-edges (with `next` / `twin` / `origin` / `face` pointers), and faces — backed by `std::vector` slabs with tombstoned removal (slots are marked deleted but never reused; IDs stay stable for resurrection by undo).
- The Python `Scene` class becomes a **thin wrapper** that delegates topology operations to the C++ mesh via nanobind. The M2 public API stays exactly the same — every M2 caller continues to compile and pass.
- The Python layer gains a `CommandStack` class with `execute` / `push_executed` / `undo` / `redo` semantics. Concrete commands (`AddVertexCommand`, `AddEdgeCommand`, `AddFaceCommand`, `RemoveFaceCommand`, `RemoveEdgeCommand`, `RemoveVertexCommand`, `CompositeCommand`, `ClearSceneCommand`) plus internal `_AddVertexAtId` / `_AddEdgeAtId` / `_AddFaceAtId` helpers for resurrection during undo.
- Both M2 tools (`RectangleTool` and `LineTool`) update to push a `CompositeCommand` at gesture completion instead of mutating `Scene` directly.

**CI must be green on Windows + Linux**, with **≈ 125-130 pytest tests** and **≈ 26-29 GoogleTest tests** passing. **No new C++ dependencies** in M3a (`vcpkg.json` unchanged); CGAL waits for M3c.

## 3. Architecture

### 3.1 Decisions captured from brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Sub-milestone scope | **M3a only** — topology + remove_* + undo. M3b push/pull and M3c CGAL booleans land later. | De-risks CGAL by isolating it; each sub-milestone CI-verified independently. |
| Half-edge location | **C++ `HalfEdgeMesh`** with Python `Scene` as a thin wrapper. | Matches the project design's long-term plan (§3.1: "C++ — Geometry kernel"). M3b ray-mesh and M3c CGAL want a C++ mesh natively. |
| Storage layout | `std::vector` slabs of `Vertex` / `HalfEdge` / `Face`; **tombstoned removal** (slots marked deleted; IDs never reused). | Stable IDs make undo trivial — restoring a removed face means flipping the tombstone, not allocating a new ID. |
| Edge representation | **Implicit** — every edge is a pair of twin half-edges. M2's `edge_id` becomes `min(he_id, twin_he_id)` for canonical naming. | Half-edge canon. No second source of truth. |
| `Scene` public API | **Unchanged** — same names, same signatures, same return types as M2. | LineTool / RectangleTool / SceneRenderer / tests don't touch. |
| `Scene.remove_*` cascade | **Reject if still referenced.** Caller (push/pull, undo) tears down in order: face → edges → vertices. | Smallest command payloads; composes cleanly with per-gesture pattern. |
| Undo granularity | **Per-gesture** — one `CompositeCommand` per tool gesture; one `Ctrl+Z` undoes the whole rectangle / line. | SketchUp behavior; what users expect. |
| Undo implementation | **Reverse-action** — each command pair stores `do` / `undo` specific to its operation. | Standard pattern; command payload scales with mutation count, not scene size. |
| Undo scope | **Scene mutations only.** Camera orbit/pan/zoom and tool activation are NOT undoable. `Ctrl+N` IS undoable. | SketchUp behavior; matches user expectations. |
| Stack ownership | **`MainWindow`** owns the `CommandStack`. Tools get a handle via the extended `ToolContext`. | Scene doesn't know about commands → clean separation. |
| Gesture boundary | Tools build a `CompositeCommand` during their gesture (executing each child immediately so the snap engine sees the in-progress state) and call `command_stack.push_executed(composite)` at gesture completion. ESC mid-gesture calls `composite.undo()` and discards. | Explicit, simple; no implicit transaction state on `Scene`. Side benefit: ESC mid-gesture now does a clean rollback. |
| History size | **Unbounded** in M3a; settings hook deferred. | Trim later if memory becomes a concern. |
| Earcut triangulation location | **Stays in Python.** `Scene.add_face_from_loop` triangulates via `mapbox-earcut`, passes both the loop and the triangulation into the C++ `HalfEdgeMesh`. | Minimises M3a C++ surface area. Move to C++ if perf matters later. |
| C++ deps added | **None.** `vcpkg.json` unchanged; CGAL waits for M3c. | Smallest M3a build-system change. |
| Exception discipline | **`KeyError`** for "entity doesn't exist / can't find"; **`ValueError`** for "entity exists but operation is invalid"; **`RuntimeError`** for "invariant violated by caller" (e.g. restoring a live slot). | Matches M2's discipline; nanobind translates from corresponding C++ exception types. |

### 3.2 Files added relative to M2

```
pluton/
├── cpp/
│   ├── include/pluton/
│   │   └── halfedge.h               # NEW — HalfEdgeMesh class declaration
│   ├── src/
│   │   └── halfedge.cpp             # NEW — HalfEdgeMesh implementation
│   ├── bindings/
│   │   └── module.cpp               # MODIFIED — expose HalfEdgeMesh
│   ├── tests/
│   │   └── test_halfedge.cpp        # NEW — GoogleTest for the C++ topology
│   └── CMakeLists.txt               # MODIFIED — add halfedge.cpp + test_halfedge.cpp
│
├── python/pluton/
│   ├── scene/
│   │   └── scene.py                 # MODIFIED — delegates to C++ HalfEdgeMesh; adds remove_* / restore_*
│   │
│   ├── commands/                    # NEW PACKAGE
│   │   ├── __init__.py
│   │   ├── command.py               # NEW — Command ABC; CompositeCommand
│   │   ├── command_stack.py         # NEW — CommandStack (execute / push_executed / undo / redo)
│   │   └── scene_commands.py        # NEW — Add* / Remove* / ClearSceneCommand + _AddVertexAtId helpers
│   │
│   ├── tools/
│   │   ├── tool.py                  # MODIFIED — ToolContext gains command_stack handle
│   │   ├── rectangle_tool.py        # MODIFIED — packages mutations into a CompositeCommand
│   │   └── line_tool.py             # MODIFIED — same; ESC mid-gesture rollback
│   │
│   └── ui/
│       └── main_window.py           # MODIFIED — owns CommandStack; binds Ctrl+Z / Ctrl+Y; Ctrl+N is a command
│
└── tests/
    ├── test_halfedge_python.py      # NEW — tests Python bindings for HalfEdgeMesh
    ├── test_scene.py                # MODIFIED — adds remove_* / restore_* / tombstone coverage
    ├── test_command_stack.py        # NEW
    ├── test_scene_commands.py       # NEW
    ├── test_rectangle_tool.py       # MODIFIED — asserts command-stack interaction
    ├── test_line_tool.py            # MODIFIED — ESC rollback test
    └── test_viewport.py             # MODIFIED — Ctrl+Z / Ctrl+Y / undo-of-Ctrl+N integration
```

### 3.3 Dependencies

- No new C++ libraries. `vcpkg.json` unchanged from M2.
- No new Python libraries. `mapbox-earcut>=2.0` (added in M2 Task 1) stays.

### 3.4 Data flow — a complete gesture with undo + redo

```
1. User presses R, drags out a rectangle, second-clicks.

2. RectangleTool builds a CompositeCommand("Draw Rectangle") incrementally
   as the gesture progresses, executing each child immediately so the live
   scene reflects current state (so the snap engine works mid-gesture):
     - AddVertexCommand(corner0).do(scene)
     - AddVertexCommand(corner1).do(scene)
     - AddVertexCommand(corner2).do(scene)
     - AddVertexCommand(corner3).do(scene)
     - AddEdgeCommand(v0, v1).do(scene)  ... etc.
     - AddFaceCommand((v0,v1,v2,v3)).do(scene)

3. At gesture completion, RectangleTool calls:
     command_stack.push_executed(composite)
   — appends the composite to the undo stack, clears the redo stack.

4. Scene now has 4 verts, 4 edges, 1 face. Renderer re-uploads on next frame.

5. User presses Ctrl+Z. MainWindow calls command_stack.undo(scene):
     - Pops composite from undo stack.
     - composite.undo() iterates children in REVERSE order, calling each child's undo().
     - RemoveFaceCommand removes the face (vertices and edges stay).
     - RemoveEdgeCommand removes each edge (vertices stay).
     - RemoveVertexCommand tombstones each vertex.
     - composite is pushed onto the redo stack.

6. Scene is empty. Renderer re-uploads.

7. User presses Ctrl+Y. MainWindow calls command_stack.redo(scene):
     - Pops composite from redo stack.
     - composite.do() runs each child in forward order.
     - Because IDs are stable, vertices return with IDs 0..3, edges with their
       original IDs, face with id 0.
     - composite returns to the undo stack.

8. Scene matches step 4 exactly.
```

The key invariant: **stable IDs let `do()` and `undo()` be exact inverses without any ID renaming.** A face removed and then restored gets its original ID back, so any later command in the stack that references it remains valid.

### 3.5 ESC mid-gesture (improvement over M2)

In M2, tools called `scene.add_vertex` directly during a gesture; ESC could only clear the visible state, not roll back committed entities (§5.6 limitation #3).

In M3a, the same incremental-execution pattern that lets the snap engine see in-progress state also gives clean rollback for free: ESC mid-gesture calls `composite.undo()` on the in-progress composite (walking children in reverse), then discards the composite without ever pushing it onto the undo stack. The scene returns to its pre-gesture state.

This eliminates the M2 §5.6 #3 carve-out. The release notes for `v0.0.4-m3a` should call this out explicitly.

### 3.6 C++ ↔ Python boundary

The Python `Scene` is a thin wrapper. Every method delegates to the C++ `HalfEdgeMesh` instance held internally:

```
Python                                C++
────────────────────────────────────  ───────────────────────────────────────
Scene.add_vertex(pos) ──────────────→ HalfEdgeMesh::add_vertex(x, y, z)
Scene.add_edge(v1, v2) ─────────────→ HalfEdgeMesh::add_halfedge_pair(v1, v2)
Scene.add_face_from_loop(loop) ─────→ (Python earcut) → HalfEdgeMesh::add_face_from_loop(loop, tris)
Scene.remove_vertex(v) ─────────────→ HalfEdgeMesh::remove_vertex(v)
Scene.remove_edge(e) ───────────────→ HalfEdgeMesh::remove_edge(e)
Scene.remove_face(f) ───────────────→ HalfEdgeMesh::remove_face(f)
Scene.restore_vertex(v, pos) ───────→ HalfEdgeMesh::restore_vertex(v, x, y, z)
Scene.restore_edge(e, v1, v2) ──────→ HalfEdgeMesh::restore_edge(e, v1, v2)
Scene.restore_face(f, loop) ────────→ (Python earcut) → HalfEdgeMesh::restore_face(f, loop, tris)
Scene.vertex(id).position ──────────→ numpy view into HalfEdgeMesh vertex positions
Scene.edge_line_buffer() ───────────→ numpy view: flat (2 * E_live, 3) float32
Scene.face_triangle_buffer() ───────→ numpy views: flat (3 * T_live, 3) positions + normals
Scene.dirty ←──────────────────────  HalfEdgeMesh::is_dirty()
Scene.mark_clean() ─────────────────→ HalfEdgeMesh::mark_clean()
```

Buffer projections walk the C++ slabs, **skip tombstoned entities**, and return numpy arrays. `reference_internal` makes them zero-copy views; copies are only made when the buffer is mutated.

The Python `Vertex` / `Edge` / `Face` dataclasses from M2 are kept as **lightweight read-only views** — they're not the source of truth anymore. Their fields populate from the C++ side when the Python code asks. The `__hash__` / `__eq__` by integer ID (M2 Task 3 hardening) carries over unchanged.

## 4. Components

### 4.1 C++ `HalfEdgeMesh`

```cpp
// cpp/include/pluton/halfedge.h
namespace pluton {

class HalfEdgeMesh {
public:
    static constexpr uint32_t INVALID_ID = 0xFFFFFFFFu;

    // ---- Mutators ----------------------------------------------------
    uint32_t add_vertex(float x, float y, float z);
    uint32_t add_halfedge_pair(uint32_t v1_id, uint32_t v2_id);
    uint32_t add_face_from_loop(std::span<const uint32_t> loop,
                                std::span<const int32_t> triangles);

    void remove_vertex(uint32_t v_id);   // throws if any half-edge has v_id as origin
    void remove_edge(uint32_t e_id);     // throws if either half-edge has a face
    void remove_face(uint32_t f_id);     // always works; leaves half-edges + verts alone

    void restore_vertex(uint32_t v_id, float x, float y, float z);
    void restore_edge(uint32_t e_id, uint32_t v1_id, uint32_t v2_id);
    void restore_face(uint32_t f_id, std::span<const uint32_t> loop,
                                     std::span<const int32_t> triangles);

    void clear() noexcept;

    // ---- Queries -----------------------------------------------------
    bool vertex_is_live(uint32_t v_id) const noexcept;
    bool edge_is_live(uint32_t e_id) const noexcept;
    bool face_is_live(uint32_t f_id) const noexcept;

    std::array<float, 3> vertex_position(uint32_t v_id) const;
    std::array<uint32_t, 2> edge_vertices(uint32_t e_id) const;
    std::span<const uint32_t> face_loop_vertices(uint32_t f_id) const;
    std::span<const int32_t>  face_triangles(uint32_t f_id) const;

    // Half-edge adjacency (exposed for M3b push/pull; not driven from Python in M3a)
    uint32_t halfedge_origin(uint32_t he_id) const noexcept;
    uint32_t halfedge_next(uint32_t he_id) const noexcept;
    uint32_t halfedge_twin(uint32_t he_id) const noexcept;
    uint32_t halfedge_face(uint32_t he_id) const noexcept;  // INVALID_ID for boundary

    // ---- Iteration / buffer projection ------------------------------
    uint32_t next_live_vertex(uint32_t start = 0) const noexcept;
    uint32_t next_live_edge(uint32_t start = 0) const noexcept;
    uint32_t next_live_face(uint32_t start = 0) const noexcept;

    std::vector<float> edge_line_buffer() const;
    std::pair<std::vector<float>, std::vector<float>> face_triangle_buffer() const;

    // ---- Dirty flag --------------------------------------------------
    bool is_dirty() const noexcept;
    void mark_clean() noexcept;

private:
    struct Vertex   { float pos[3]; uint32_t outgoing_he; bool alive; };
    struct HalfEdge { uint32_t origin; uint32_t next; uint32_t twin; uint32_t face; bool alive; };
    struct Face     { uint32_t boundary_he; float normal[3]; std::vector<int32_t> tris; bool alive; };

    std::vector<Vertex>   vertices_;
    std::vector<HalfEdge> halfedges_;
    std::vector<Face>     faces_;

    std::unordered_map<uint64_t, uint32_t> position_index_;  // packed float32×3 → live vertex id
    bool dirty_ = false;
};

}  // namespace pluton
```

Tombstoning is one `bool alive;` per record. Iteration helpers (`next_live_*`) skip them. IDs stay mapped to their slot for life. `position_index_` only tracks LIVE vertices — a tombstoned vertex's old position is not eligible for resurrection by position match. (Resurrection requires explicit `restore_vertex(id, x, y, z)`.)

### 4.2 Python `Scene` (wrapper)

```python
class Scene:
    """The editable polygonal scene — thin wrapper over C++ HalfEdgeMesh."""

    def __init__(self) -> None:
        self._mesh = _core.HalfEdgeMesh()

    # ---- Mutators (M2 API + new methods) ------------------------------
    def add_vertex(self, position: np.ndarray) -> int: ...
    def add_edge(self, v1_id: int, v2_id: int) -> int: ...
    def add_face_from_loop(self, ordered_vertex_ids: Sequence[int]) -> int: ...
    def remove_vertex(self, v_id: int) -> None: ...
    def remove_edge(self, e_id: int) -> None: ...
    def remove_face(self, f_id: int) -> None: ...
    def restore_vertex(self, v_id: int, position: np.ndarray) -> None: ...
    def restore_edge(self, e_id: int, v1_id: int, v2_id: int) -> None: ...
    def restore_face(self, f_id: int, ordered_vertex_ids: Sequence[int]) -> None: ...
    def clear(self) -> None: ...
    def mark_clean(self) -> None: ...

    # ---- Queries (M2 API, unchanged) ----------------------------------
    @property
    def dirty(self) -> bool: ...
    def vertex(self, v_id: int) -> Vertex: ...
    def edge(self, e_id: int) -> Edge: ...
    def face(self, f_id: int) -> Face: ...
    def vertices_iter(self) -> Iterable[Vertex]: ...
    def edges_iter(self) -> Iterable[Edge]: ...
    def faces_iter(self) -> Iterable[Face]: ...
    def find_vertex_near(self, world_xyz: np.ndarray, tolerance: float) -> int | None: ...
    def edge_line_buffer(self) -> np.ndarray: ...
    def face_triangle_buffer(self) -> tuple[np.ndarray, np.ndarray]: ...
```

The `restore_*` methods are deliberately separate from the `add_*` methods because they take a **specific ID** to restore (rather than allocating a new one). They're the inverse half of the `remove_*` commands and are only meant to be called by undo logic, not by application code. Their docstrings say so.

### 4.3 Command framework

```python
# python/pluton/commands/command.py
class Command(ABC):
    """A reversible operation on the Scene."""
    name: str

    @abstractmethod
    def do(self, scene: Scene) -> None: ...
    @abstractmethod
    def undo(self, scene: Scene) -> None: ...


@dataclass
class CompositeCommand(Command):
    """A sequence of commands executed/undone as one unit (per-gesture grouping)."""
    name: str
    children: list[Command]

    def do(self, scene: Scene) -> None:
        for c in self.children:
            c.do(scene)

    def undo(self, scene: Scene) -> None:
        for c in reversed(self.children):
            c.undo(scene)
```

```python
# python/pluton/commands/command_stack.py
class CommandStack:
    """Owns the undo + redo stacks. Owned by MainWindow."""

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def execute(self, cmd: Command, scene: Scene) -> None:
        """Run cmd.do(scene), push to undo stack, clear redo stack."""
        cmd.do(scene)
        self._undo.append(cmd)
        self._redo.clear()

    def push_executed(self, cmd: Command) -> None:
        """Append a command whose do() was already called (incremental gestures)."""
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self, scene: Scene) -> bool: ...
    def redo(self, scene: Scene) -> bool: ...

    @property
    def can_undo(self) -> bool: ...
    @property
    def can_redo(self) -> bool: ...
```

`CommandStack` exposes two push-paths:

- `execute(cmd, scene)` — for one-shot commands. Calls `cmd.do(scene)` then appends to the undo stack. Used by `Ctrl+N` and any tool that wants atomic commit (Rectangle could use this, but consistency with Line drives the choice).
- `push_executed(cmd)` — just appends. The tool has already called `cmd.do(scene)` incrementally during the gesture (so the snap engine could see in-progress state). The cleanest path for both Line and Rectangle.

```python
# python/pluton/commands/scene_commands.py
class AddVertexCommand(Command):
    def __init__(self, position: np.ndarray) -> None:
        self._position = position.copy()
        self._vertex_id: int | None = None

    def do(self, scene: Scene) -> None:
        self._vertex_id = scene.add_vertex(self._position)

    def undo(self, scene: Scene) -> None:
        scene.remove_vertex(self._vertex_id)


class RemoveFaceCommand(Command):
    def __init__(self, face_id: int) -> None:
        self._face_id = face_id
        self._captured_loop: tuple[int, ...] | None = None

    def do(self, scene: Scene) -> None:
        self._captured_loop = tuple(scene.face(self._face_id).loop_vertex_ids)
        scene.remove_face(self._face_id)

    def undo(self, scene: Scene) -> None:
        scene.restore_face(self._face_id, self._captured_loop)


class ClearSceneCommand(Command):
    """Special: do() captures the entire scene; undo() replays Add*AtId children."""
    def do(self, scene: Scene) -> None:
        captured: list[Command] = []
        for v in scene.vertices_iter():
            captured.append(_AddVertexAtId(v.id, v.position))
        for e in scene.edges_iter():
            captured.append(_AddEdgeAtId(e.id, e.v1_id, e.v2_id))
        for f in scene.faces_iter():
            captured.append(_AddFaceAtId(f.id, f.loop_vertex_ids))
        self._captured = captured
        scene.clear()

    def undo(self, scene: Scene) -> None:
        for cmd in self._captured:
            cmd.do(scene)
```

The `_AddVertexAtId` / `_AddEdgeAtId` / `_AddFaceAtId` variants are internal commands that assert a specific ID rather than allocating a fresh one — used by `ClearSceneCommand`'s capture-and-restore path. They wrap `Scene.restore_*` internally.

### 4.4 Tool integration

Both `RectangleTool` and `LineTool` change minimally:

- They build a `CompositeCommand` as the gesture progresses, calling `child.do(scene)` on each appended child so the snap engine sees in-progress state.
- At gesture completion, they call `command_stack.push_executed(composite)`.
- ESC mid-gesture calls `composite.undo(scene)` (walks children in reverse) and discards the composite.

The state machines and three-branch click logic stay identical.

### 4.5 `MainWindow` integration

`MainWindow` grows:

- A `CommandStack` instance (`self._command_stack`).
- `Ctrl+Z` `QShortcut` → `self._command_stack.undo(self._scene)` + `self._viewport.update()`.
- `Ctrl+Y` and `Ctrl+Shift+Z` `QShortcut`s → `self._command_stack.redo(self._scene)`.
- `Ctrl+N` becomes `self._command_stack.execute(ClearSceneCommand(), self._scene)` (was `self._scene.clear()`).
- The `ToolContext` passed to tools gains a `command_stack` field so tools can reach the stack without a back-reference to `MainWindow`.

## 5. Edge cases & error handling

### 5.1 Exception discipline

- **`KeyError`** — "entity doesn't exist / can't find." `Scene.vertex(v)` where `v` is tombstoned or never existed. `Scene.remove_vertex(v)` where `v` is already tombstoned.
- **`ValueError`** — "entity exists but operation is invalid." Self-loop edge (`add_edge(v, v)`). Removing an edge that still has a face attached. Removing a vertex that still has an incident edge. Face creation with fewer than 3 vertices.
- **`RuntimeError`** — "caller violated an invariant." Restoring a slot that's currently live (double-undo bug). Restoring a slot whose recorded shape doesn't match (e.g. `restore_edge(e, v1, v2)` where the recorded `v1`/`v2` don't satisfy the canonical ordering).

nanobind translates the C++ counterparts (`std::out_of_range`, `std::invalid_argument`, `std::logic_error`) to these Python types.

### 5.2 ESC mid-gesture rollback

Tools execute their composite's children incrementally during the gesture so the snap engine sees in-progress state. ESC mid-gesture invokes `composite.undo(scene)` then discards the composite without pushing it to the stack. The scene returns to its pre-gesture state. **This eliminates M2 §5.6 limitation #3 — that carve-out is gone.**

### 5.3 Edge cases table

| Situation | Behaviour |
|---|---|
| `remove_vertex(v)` already tombstoned | `KeyError`. Loud bug signal. |
| `remove_edge(e)` while a face still uses it | `ValueError`. Caller must remove the face first. |
| `remove_vertex(v)` while an edge still uses it | `ValueError`. Caller must remove the edge first. |
| `restore_face(f, loop)` where `f` is currently live | `RuntimeError`. Restoration is only valid on a tombstoned slot. |
| `Scene.vertex(v)` where `v` is tombstoned | `KeyError`. Live-or-dead is implementation detail; missing is missing. |
| `vertices_iter()` / `edges_iter()` / `faces_iter()` | Yield only **live** entities. Tombstoned ones are invisible. |
| `add_vertex(pos)` where `pos` matches a tombstoned vertex's old position | Allocates a **new** vertex ID. The position index tracks only live vertices. |
| `command_stack.undo()` when undo stack is empty | Returns `False`. MainWindow's handler ignores the return — no-op is acceptable. |
| `command_stack.redo()` when redo stack is empty | Returns `False`. Same. |
| New `execute` / `push_executed` after a sequence of `undo()` calls | Redo stack clears. Standard behavior. |
| Direct `scene.*` calls (test or one-off scripts) | Don't appear in the undo history. App code goes through the stack; direct calls are an opt-out. |
| Pickling / serializing commands | **Not in scope.** Commands live only in memory. Persisting undo history is M6 file I/O. |

### 5.4 Known limitations (carry-over GitHub issues opened at tag time)

1. **Edge-ID instability after the implicit-edge refactor.** M2's `Scene.add_edge(v1, v2)` returns numeric IDs derived from a dict counter; M3a derives them from half-edge pair indices. Tests using IDs as opaque tokens are fine; tests pinning specific numeric IDs may need updating.
2. **Tombstone memory growth.** Slabs grow linearly with cumulative mutations across a session — tombstoned slots are never reclaimed. Defer compaction to a perf-focused milestone (M10).
3. **`RemoveFaceCommand` captured-loop memory.** Commands that remove geometry capture the removed entity's payload (e.g. the face's boundary loop). For M3a's small faces fine; for M4+ faces with many boundary vertices, command payload grows. Defer.
4. **C++ direct access from the future render engine.** When Phase 5 brings an in-house renderer, it may want to read `HalfEdgeMesh` directly rather than through the Python `Scene` wrapper. Architectural note; no code action in M3a.

## 6. Out of scope for M3a

| Not in M3a | Lands in |
|---|---|
| Push/Pull tool | **M3b** |
| Ray-mesh intersection / face picking | **M3b** |
| CGAL booleans | **M3c** |
| First inferencing on existing geometry (snap to edge / midpoint / intersection) | **M3c** |
| On-edge snap + edge splitting in Line tool ([#9](https://github.com/Parrow-Horrizon-Studio/pluton/issues/9)) | M4 |
| Self-intersection detection in Line tool ([#10](https://github.com/Parrow-Horrizon-Studio/pluton/issues/10)) | M4 |
| Drawing on existing face surfaces ([#12](https://github.com/Parrow-Horrizon-Studio/pluton/issues/12)) | M4 |
| Measurements Box / numeric input ([#13](https://github.com/Parrow-Horrizon-Studio/pluton/issues/13)) | M4 |
| Tombstone slab compaction | M10 (perf) |
| Multi-document undo history persistence (save undo history with the document) | M6 (file I/O) |
| Select tool / "no active tool" visual chrome beyond empty status bar | M4 |
| Toolbar widget | M4 |

## 7. The M3a → M3b / M3c contract

**M3b (Push/Pull basic) inherits:**

- C++ `HalfEdgeMesh` with `next`/`twin`/`origin`/`face` pointers; `halfedge_face` returns `INVALID_ID` for boundary half-edges (M3b uses this to recognize silhouette edges).
- `Scene.remove_face` and its restore counterpart. Push/pull's central transaction is `RemoveFace(source) + AddVertices(top) + AddEdges(sides) + AddFaces(sides + top)`.
- `CommandStack` + per-gesture composite pattern.
- `ToolContext.command_stack` so the `PushPullTool` plugs in.
- All M2 + M3a public APIs unchanged.

**M3b must add fresh:**

- Ray-mesh intersection (face picking from a screen point).
- `PushPullTool` — face-pick on mouse press; drag along face normal to set extrusion depth; release commits a composite.
- Visual preview — semi-transparent ghost prism during drag; source face highlighted.
- Status bar shows current extrusion distance.

**M3c (Booleans & Inferencing) inherits everything above plus M3b's `PushPullTool` and face-pick infrastructure.**

**M3c must add fresh:**

- CGAL dep added to `vcpkg.json` (first vcpkg change since M0).
- `HalfEdgeMesh` ↔ CGAL `Surface_mesh` conversion.
- Boolean merge — when push/pull's extruded prism intersects existing geometry, invoke CGAL boolean union, convert back.
- Inferencing extensions — snap to existing edges, midpoints of existing edges, edge-edge intersections projected onto the drawing plane.

## 8. Testing strategy

Following the M1/M2 TDD discipline.

| Component | Test file | Coverage |
|---|---|---|
| C++ `HalfEdgeMesh` | `cpp/tests/test_halfedge.cpp` (NEW) | `add_vertex` idempotency on exact float match; `add_halfedge_pair` creates twin pair with correct origin/next; `add_face_from_loop` sets boundary half-edge cycle; `remove_face` leaves verts/edges alive; `remove_edge` rejects if any face references it; `remove_vertex` rejects if any edge references it; tombstone iteration via `next_live_*` skips dead slots; `restore_*` rejects non-tombstoned IDs; `clear()` empties everything. |
| nanobind bindings | `tests/test_halfedge_python.py` (NEW) | Python can construct `HalfEdgeMesh`, call mutators, read back vertex positions / edge endpoints / face loops as numpy arrays. Mirrors M1's `test_mesh.py`. |
| Python `Scene` (wrapper) | `tests/test_scene.py` (MODIFIED) | All M2 tests must still pass unchanged. New tests for `remove_*` reject-if-referenced; `restore_*` round-trip; tombstone invisible to iteration; `add_vertex` matching tombstoned position allocates new ID. |
| Command framework | `tests/test_command_stack.py` (NEW) | `CompositeCommand` do/undo ordering; `CommandStack.execute` / `push_executed` / `undo` / `redo` flows; empty-stack returns False; new execute clears redo. |
| Scene commands | `tests/test_scene_commands.py` (NEW) | Each `Add*` / `Remove*` command's do/undo is a perfect inverse — assert scene state matches across `do → undo → do → undo` cycles. `ClearSceneCommand` captures + restores full scene. |
| `RectangleTool` (modified) | `tests/test_rectangle_tool.py` (MODIFIED) | After a completed gesture, command stack has exactly one entry; `Ctrl+Z` undoes the rectangle; `Ctrl+Y` redoes; ESC mid-drag rolls back. |
| `LineTool` (modified) | `tests/test_line_tool.py` (MODIFIED) | After a closed loop, command stack has one entry; multi-click gestures execute incrementally so snap engine sees in-progress state; ESC mid-gesture rolls back all incrementally-added verts/edges (the M2 §5.6 #3 elimination test). |
| MainWindow | `tests/test_viewport.py` (MODIFIED) | `Ctrl+Z` / `Ctrl+Y` bindings via qtbot; `Ctrl+N` is a `ClearSceneCommand`; undo-of-Ctrl+N restores the scene; rapid undo+redo cycles produce identical scene state. |

**Count targets:**

| Layer | After M2 | After M3a |
|---|---|---|
| Pytest | 101 | ≈ 125-130 |
| GoogleTest | 14 | ≈ 26-29 |

**Manual visual verification checklist** (post-implementation, before tag):

1. Baseline: empty scene at startup; camera, snap markers, status bar all behave like M2.
2. Draw a rectangle with `R`. Press `Ctrl+Z` → rectangle disappears. Press `Ctrl+Y` → reappears.
3. Draw a closed polyline with `L`. Multi-click builds visible polyline (snap engine works on the in-progress vertices). Press `Ctrl+Z` → entire polyline + face disappears.
4. **M3a improvement to verify**: during a Line gesture, after 2-3 clicks, press `Esc` → all in-progress vertices and edges disappear (M2 §5.6 #3 elimination).
5. Draw several shapes, press `Ctrl+N` → scene clears. Press `Ctrl+Z` → entire scene returns with original IDs (test: the snap engine's endpoint snap still works on restored vertices).
6. Mix undo and new gestures: undo a rectangle, then draw a new one, then attempt redo → redo stack was cleared (no rectangle returns).

## 9. Implementation order (preview)

The implementation plan will own the exact task decomposition. Tentative shape — ~22 tasks. The C++ work happens first; Python comes second; tool integration and `MainWindow` wiring come last.

1. C++ `HalfEdgeMesh` header skeleton (struct layout, `INVALID_ID`, no method bodies) — TDD.
2. `HalfEdgeMesh::add_vertex` with position index — TDD.
3. `HalfEdgeMesh::add_halfedge_pair` — TDD.
4. `HalfEdgeMesh::add_face_from_loop` (loop + triangulation passed in) — TDD.
5. `HalfEdgeMesh::remove_face` — TDD.
6. `HalfEdgeMesh::remove_edge` + `remove_vertex` (reject-if-referenced) — TDD.
7. `HalfEdgeMesh::restore_face` / `restore_edge` / `restore_vertex` — TDD.
8. `HalfEdgeMesh::next_live_*` + `clear` + `dirty` — TDD.
9. `HalfEdgeMesh::edge_line_buffer` + `face_triangle_buffer` projections — TDD.
10. nanobind bindings + Python smoke tests.
11. Python `Scene` refactored as wrapper; all M2 tests still pass.
12. Python `Scene.remove_*` + `restore_*` — TDD.
13. `Command` ABC + `CompositeCommand` — TDD.
14. `CommandStack` (`execute` / `push_executed` / `undo` / `redo`) — TDD.
15. Add-side commands (`AddVertex`, `AddEdge`, `AddFace`) — TDD.
16. Remove-side commands (`RemoveVertex`, `RemoveEdge`, `RemoveFace`) — TDD.
17. `ClearSceneCommand` + `_AddVertexAtId` / `_AddEdgeAtId` / `_AddFaceAtId` helpers — TDD.
18. `RectangleTool` refactor: incremental composite, gesture completion via `push_executed` — TDD.
19. `LineTool` refactor + ESC mid-gesture rollback — TDD.
20. `MainWindow` integration: own `CommandStack`, bind `Ctrl+Z` / `Ctrl+Y`, `Ctrl+N` becomes a command — TDD + qtbot integration.
21. Manual visual verification (§8 checklist).
22. Push and verify CI; bump to `0.0.4`; tag `v0.0.4-m3a` (annotated, SSH-signed); open carry-over GitHub issues from §5.4.

The C++ kernel does its first real geometric work in tasks 1-9, with nanobind exercising more of the binding surface than M0/M1 did. Tasks 11-12 are the milestone's most subtle step — the Python `Scene` rewires its internals without breaking M2 callers.

## 10. References

- Project design: `docs/2026-05-16-pluton-design.md`
- M0 plan: `docs/2026-05-17-M0-foundation-plan.md`
- M1 design + plan: `docs/2026-05-19-M1-core-viewport-design.md` / `docs/2026-05-19-M1-core-viewport-plan.md`
- M2 design + plan: `docs/2026-05-22-M2-basic-drawing-design.md` / `docs/2026-05-22-M2-basic-drawing-plan.md`
- Half-edge mesh data structure (canonical reference): https://www.openmesh.org/Documentation/OpenMesh-Doc-Latest/a04175.html
- nanobind 2.x: https://nanobind.readthedocs.io/

## 11. Document history

| Date | Author | Change |
|---|---|---|
| 2026-05-22 | Rowee Apor | Initial design from brainstorming session |

# Pluton — Design Document

**Date:** 2026-05-16
**Status:** Initial design, drafted from brainstorming session
**Author:** Rowee Apor (Parrow Horrizon Studio)
**License:** GPL (matches the project license)

---

## 1. Vision

**Pluton is an open-source, long-horizon, polygonal 3D modeler with CAD-like precision, aimed primarily at architectural 3D modeling. It is intended to be a free, self-hostable alternative to SketchUp Pro, following the Blender model of community-supported free software.**

Pluton is not a hobby project in the soft sense. It is a hobby project in the *no commercial deadline* sense: developed without external pressure, but with the serious architectural and engineering rigor required for a tool that aspires to be globally recognized over the course of years.

### 1.1 Inspirations

- **SketchUp Pro** — the modeling paradigm, push/pull workflow, inferencing/snapping, viewport styles, layout/scenes pattern, and architect-first audience.
- **Blender** — the software development and distribution model: free, GPL, native core (C/C++) with a scripting layer (Python), community-funded.

### 1.2 Long-Horizon Ambition

Pluton's eventual destination is a fully self-sufficient architectural modeler:
- Modeling (Phases 1–4)
- Documentation output (Phase 6 — layout-equivalent, BIM-lite)
- Built-in real-time and production rendering (Phase 5)
- Plugin ecosystem (Phase 3 onward)

We expect this to take years. Blender took roughly 25 years to reach its current standing. Pluton's pace will be honest about the constraints of solo development without forcing artificial deadlines.

---

## 2. Modeling Paradigm

Pluton is a **polygonal modeler with CAD-like precision** — not a B-Rep parametric CAD app.

| Property | Value |
|---|---|
| Geometry primitive | Polygon meshes (vertices, edges, faces) |
| Surfaces | Polygonal approximations — no NURBS |
| Boolean operations | Mesh-based booleans (via CGAL) |
| Parametric history | None — direct manipulation, like SketchUp |
| Precision | Exact numerical input + tolerance-based snapping/inferencing |
| Target use case | Architectural 3D modeling (buildings, interiors, urban) |

This distinction matters: it shapes the kernel choice, the data structures, the interaction model, and the renderer requirements. Pluton is closer in architecture to Blender (polygonal) than to Fusion 360 / FreeCAD (B-Rep / NURBS).

---

## 3. Technical Architecture

### 3.1 Language Stack — Hybrid Python + C++

Pluton uses a hybrid architecture matching Blender's general pattern: a native core for performance-critical work, a Python application layer for everything else.

**Python (≈ 80–90% of the codebase by line count):**
- UI shell (PySide6 / Qt)
- Tools (drawing, push/pull, transform, measure, etc.)
- Scene graph, layers, undo/redo, command pattern
- File I/O orchestration
- Plugin system
- High-level application logic

**C++ (≈ 10–20% of the codebase by line count, but performance-critical):**
- Geometry kernel (mesh data structures, half-edge model)
- Boolean / CSG operations
- BVH and spatial indexing
- Robust geometric predicates
- Per-frame CPU work for the viewport (culling, batching) when Python becomes the bottleneck
- Future production renderer (Phase 5)

### 3.2 Key Libraries and Tooling

| Concern | Choice | Rationale |
|---|---|---|
| Binding library | **nanobind** | Modern successor to pybind11 by the same author; leaner, faster compile, cleaner API. Reference: nanobind.readthedocs.io |
| C++ standard | **C++20** | Modern (concepts, ranges, `<=>`, designated init) with rock-solid compiler support across MSVC/GCC/Clang |
| Geometry library | **CGAL** | Mature computational geometry: mesh ops, booleans, BVH, robust predicates. GPL license matches Pluton's. |
| UI framework | **PySide6** (Qt 6) | Industry-standard cross-platform UI; same family Blender uses for its UI through Python |
| Viewport renderer | **QOpenGLWidget + ModernGL** initially, designed as a swappable abstraction | Get on-screen fast; swap to native C++ renderer in Phase 5 without disturbing the rest of the app |
| C++ dependency manager | **vcpkg** | Microsoft-maintained, one-line CMake integration, manifest mode (`vcpkg.json`), Visual Studio integration. CGAL/Eigen/fmt/spdlog all available. (Qt installed separately via Qt installer.) |
| Build orchestration | **scikit-build-core + CMake + Ninja** | Modern Python/C++ build orchestration; `pip install -e .` builds the whole project end-to-end |
| Python tests | **pytest** | De facto Python testing standard |
| C++ tests | TBD between **GoogleTest** and **Catch2** (deferred to implementation plan) | Either is fine; decided when C++ tests are first written |
| Python tooling | **Ruff** (formatter + linter), **mypy** (type checking) | Modern, fast Python tooling |
| C++ tooling | **clang-format** + **clang-tidy** | Standard formatters and linters |
| Documentation | Deferred — likely **MkDocs Material** + **Doxygen** for C++ API | Decided at Phase 3 (when there's something to document publicly) |

### 3.3 Codebase Structure

```
pluton/
├── cpp/                       # All C++ code
│   ├── include/pluton/        # Public headers (Python-facing API)
│   ├── src/                   # Implementation
│   │   ├── mesh/              # Half-edge mesh, geometry kernel
│   │   ├── boolean/           # CSG / boolean ops via CGAL
│   │   ├── spatial/           # BVH, spatial indexing
│   │   └── render/            # Per-frame CPU work for viewport (Phase 4+)
│   ├── bindings/              # nanobind glue
│   │   └── module.cpp         # The Python-visible module definition
│   ├── tests/                 # C++ unit tests
│   └── CMakeLists.txt
│
├── python/pluton/             # All Python code
│   ├── __init__.py            # Imports the compiled C++ module
│   ├── app.py                 # Entry point
│   ├── ui/                    # PySide6/Qt UI
│   ├── tools/                 # Modeling tools
│   ├── scene/                 # Scene graph, layers, undo/redo
│   ├── viewport/              # Renderer abstraction (ModernGL initially)
│   ├── io/                    # File import/export
│   └── plugins/               # Plugin system (Phase 3)
│
├── tests/                     # Python integration tests
├── docs/                      # Design docs, ADRs, user docs
├── vcpkg.json                 # C++ dependency manifest
├── pyproject.toml             # Python project + scikit-build-core config
├── CMakeLists.txt             # Top-level CMake
├── LICENSE                    # GPL
└── README.md
```

### 3.4 The Geometry Kernel Architecture

The C++ kernel exposes a clean Python-facing API designed for binding from day 1:
- Mesh data structures (half-edge, vertex/edge/face)
- Boolean operations (union, intersection, difference) via CGAL
- Spatial queries (ray-mesh intersection, point-in-mesh, nearest face)
- Geometric primitives (cube, plane, cylinder, etc.)
- Robust predicates for snapping/inferencing

Internal design principle: **the kernel knows about geometry, not the application.** No UI concepts, no scene-graph concepts, no Python objects in the public API. The Python layer wraps and composes kernel operations into application-level features.

---

## 4. Conventions

### 4.1 Coordinate System
- **Z-up** (matches SketchUp, matches architect convention — Z is the vertical axis)
- Right-handed coordinate system

### 4.2 Units
- User-switchable per-document **imperial (feet/inches)** or **metric (mm/cm/m)**
- Setting lives in document preferences (not a global app setting), so opening a project preserves the units it was created with
- Internal representation is always in meters (or unitless) — display layer translates to user's chosen units

### 4.3 License
- **GPL** (specifically GPL-3.0 or later, to match the modern open-source standard and align with Blender)
- All contributions are GPL-licensed

### 4.4 Hosting & Branding
- GitHub: `github.com/parrow-horrizon-studio/pluton`
- Website: `pluton3d.org`
- Studio org GitHub is calibrated for security (2FA enforcement, conservative member privileges, secure defaults)

---

## 5. Platforms

| Platform | Status | Phase |
|---|---|---|
| Windows | Primary development platform from day 1 | Phase 1+ |
| Linux | First-class supported platform, shipped from v0.1 | Phase 1+ |
| macOS | Added at Phase 3 (M9), when initial installer pipeline matures | Phase 3 |

**Cross-platform discipline from day 1:** all code uses `std::filesystem`, avoids OS-specific extensions, runs CI on both Windows and Linux from M0. Catching portability bugs early is cheap; fixing accumulated portability debt is expensive.

---

## 6. Roadmap

Pluton's development is organized into **6 Phases**. Phases 1–5 form a linear progression toward a feature-complete v1.0. Phase 6 is explicitly an **exploration tier** where priorities emerge from community needs.

Version numbers are directional anchors, not commitments.

### Phase 1 — Foundation *(v0.0 → v0.1)*

**End state:** A toy version of SketchUp's core push/pull innovation works. Proof that the technology stack is sound.

- **M0: Hello, Window** — project scaffolding (cpp/python layout, CMake, vcpkg, scikit-build-core, pyproject.toml); Qt window with QOpenGLWidget; draw a triangle on screen; nanobind binding pipeline verified end-to-end; CI green on Windows + Linux.
- **M1: Core viewport** — mesh data structure in C++ exposed via nanobind; orbit/pan/zoom camera; basic Phong shading; Z-up coordinate system established; build a single cube.
- **M2: Basic drawing** — Line tool, Rectangle tool, drawing on the ground plane; mouse input with grid snapping; ability to create geometry interactively.
- **M3: Push/Pull** — the iconic SketchUp interaction: select a face, drag to extrude. Delivered in four sub-milestones: **M3a** (half-edge topology + command-pattern undo/redo), **M3b** (basic push/pull — open-bottom prism, no merge), **M3c** (closed-manifold push/pull via half-edge dissolve — closed bottoms + coplanar seam-merge, no CGAL), **M3d** ✅ *(shipped v0.0.7)* — 3D inferencing (Tier 2): endpoint/midpoint/on-edge/on-face/intersection snaps + 3D axis-lock incl. the vertical Z axis, with a `split_edge` half-edge op so interior snaps build clean (T-junction-free) topology; face-split deferred to Phase 2. True volumetric booleans (push/pull *into* existing geometry, the Hole tool, mesh import + carve) are deferred to Phase 2, where CGAL becomes a meaningful dependency — M3c showed the M3-scope merge cases are pure half-edge operations that don't need it.

### Phase 2 — Modeling App *(v0.1 → v0.3)*

**End state:** An architect could use Pluton for simple real projects.

- **M4: Modeling polish** — Circle, Arc, Polygon tools; Eraser tool; Select tool with multi-select; Move/Rotate/Scale transforms; **Tape Measure / point-to-point measurement tool**; **user-switchable imperial/metric units** in document preferences; **Groups and Components** (SketchUp's most important organizational feature). Delivered in five sub-milestones: **M4a** ✅ *(shipped v0.1.0)* — drawing tools (Circle, Polygon, 2-Point Arc) on ground/face planes, snap-driven; **M4b** ✅ *(shipped v0.1.1)* — selection & eraser (edges+faces, box-select, blue highlight, edge-Eraser with face cascade, Delete); **M4c** ✅ *(shipped v0.1.2)* — Move/Rotate/Scale transforms (`set_vertex_position` kernel op; point-to-point Move, auto-tilt Rotate protractor, full corner/edge/face Scale gizmo); **M4d** ✅ *(shipped v0.1.3)* — units & measurement (metric + architectural imperial; the typed-entry VCB / Measurements box across all 9 tools; measure-only Tape Measure with snapping); **M4e** ✅ *(shipped v0.1.4)* — Groups & Components (a Python scene-graph **Definition + Instance** model replacing the single flat mesh; enter-to-edit full isolation with breadcrumb + dimmed surroundings; Make Group / Make Component / Make Unique / Explode; Move-copy via Ctrl-drag; shared-definition edit-propagation across all instances of a component; every editing tool — draw / push-pull / Move / Rotate / Scale / Eraser / select-hover — made transform-aware so editing works correctly inside a moved or rotated context; root-with-identity stays behaviorally identical to the old flat mesh).
- **M5: Materials and viewport styles** — basic materials (color + simple textures); multiple **viewport styles** (Shaded, Hidden Line, Wireframe, Monochrome, X-Ray, Sketchy edges); Layers/Tags for object organization. Delivered in sub-milestones: **M5a** ✅ *(shipped v0.1.5)* — viewport display styles: four mutually-exclusive face styles (Wireframe / Hidden Line / Monochrome / Shaded) plus an orthogonal X-Ray toggle, switchable from a View menu; renderer-only — a pure descriptor table (`resolve_face_pass`) drives the existing phong shader via a new `u_alpha` uniform that also unifies the dim pass, with the Shaded default kept byte-identical to v0.1.4; **M5b** ✅ *(shipped v0.1.6)* — solid-color materials: a `Material`/`MaterialLibrary` palette, a per-face `face_id→material_id` sidecar on `Scene`, and per-material draw batching (a pure `plan_face_batches` → one `glDrawArrays` per material through M5a's unchanged `resolve_face_pass`, so unpainted models stay byte-identical to v0.1.5 with no shader change), plus a Paint tool (B) with Alt-sample + Default un-paint and a dockable Materials palette (reopenable via View ▸ Materials). **Textures/UV mapping deferred to a later milestone**; **M5c** ✅ *(shipped v0.1.7)* — Layers/Tags: a `Tag`/`TagLibrary` (always-visible "Untagged" sentinel) on the `Model`, a `tag_id` on each group/component `Instance`, a visibility-aware `Model.traverse_visible` that prunes hidden-tag instances and their subtrees (with an active-path bypass, byte-identical render when nothing is hidden), an undoable `TagInstancesCommand`, MakeGroup/MakeComponent inheriting the active tag, and a dockable Tags panel (list with show/hide checkboxes, inline rename, a "Selection: <tag>" indicator, Assign-to-Selection; tabbed with Materials, reopenable via View ▸ Tags). Instances-only tagging; loose-geometry tagging, per-tag color, and rename/delete/reorder deferred. **M5 is complete** (M5a + M5b + M5c all shipped).
- **M6: File I/O** — native `.pluton` file format with versioned schema from day 1; import/export OBJ and glTF via Assimp. Delivered in sub-milestones: **M6a** ✅ *(shipped v0.1.8)* — native `.pluton` save / open / new: a zip container (`manifest.json` + compact `document.json`, `schema_version` gate from day 1) round-tripping the whole document — scene graph with component **sharing preserved by identity**, per-face materials + material library, tags + visibility, document units, and the camera view. A pure, headlessly-testable `pluton/io/` package (`document_codec` ↔ `pluton_file`, model classes stay format-agnostic): **index-based** geometry encoding (compacts kernel id gaps, rebuild via `add_vertex`/`add_edge`/`add_face_from_loop`) with structural def/instance ids + counters preserved; **atomic** save (temp + `os.replace`) and atomic in-place adopt on open (`Model.load_from` keeps identity so the viewport/tools keep working; open-failure leaves the session untouched). Full File menu (New/Open/Save/Save As) with dirty-state title marker and a Save/Don't-Save/Cancel guard (`Ctrl+N` repurposed to File ▸ New; the old clear-scene moved to Edit ▸ "Clear Active Context"). **M6b** ✅ *(shipped v0.1.9)* — OBJ import/export: a pure `obj_codec` (a world-space polygon-soup IR ↔ `.obj`/`.mtl` text — n-gons preserved, 1 unit = 1 m, material colors round-tripped, `vn`/`vt` ignored on read) plus an `obj_io` model bridge. Export flattens the scene graph to world space (one `o` group per node with geometry, a sibling `.mtl` when materials are painted, atomic temp+`os.replace` write); **adaptive** import routes a grouped OBJ (`o`/`g`) into one group per object in the active context or merges a flat OBJ into the active scene, **best-effort** (skips + counts faces/materials the kernel or a malformed file rejects — a missing/subdir `.mtl` or bad `Kd` degrades gracefully, never hard-failing the import), delivered as an undoable `ImportObjCommand` and wired to File ▸ Import/Export OBJ (generalized path prompts). **M6c** ✅ *(shipped v0.2.0)* — glTF import/export via **Assimp** (Pluton's first C++ format dependency, statically linked — Windows uses the `x64-windows-static-md` vcpkg triplet so `_core` bundles no runtime DLLs). Import goes through a thin Assimp nanobind bridge that decodes `.glb`/`.gltf` — **including Draco mesh compression** (`KHR_draco_mesh_compression`) — into a neutral plain-data IR, then a pure-Python layer maps it onto Pluton's scene graph: the glTF node tree becomes nested groups (each node → one object, single-mesh childless leaves collapsing to a direct instance), meshes shared across nodes become shared **Components** (real instancing reconstructed), PBR `baseColorFactor` becomes Pluton materials, Y-up→Z-up axis conversion, **best-effort** (skips + counts rejected triangles, never hard-failing) and **undoable** (`ImportGltfCommand`). Export is a pure-Python `.glb`/`.gltf` writer (`gltf_codec` + `gltf_export`): Z-up→Y-up, n-gon fan-triangulation grouped into per-material primitives, mesh-level instancing preserved, atomic write. A permanent, non-skippable CI gate keeps Draco decode from silently regressing. Wired to File ▸ Import/Export glTF. **M6 is complete** (M6a + M6b + M6c all shipped). Recent-files, autosave, and launch-with-file remain deferred.
- **M7: Architecture-specific tools** — Wall tool (auto-thickness); Door/Window placement; Roof tools; Dimensions and annotations; Scenes (saved cameras/views). Delivered in sub-milestones: **M7a** ✅ *(shipped v0.2.1)* — the **Wall tool** (`W`): draws a **chaining polyline of baked solid-box walls**. The first click sets the anchor; each later click commits one **centered** wall segment (thickness/2 to each side of the drawn centerline) as its own `"Wall"` group in the active context, then chains (anchor = endpoint) so a whole floor plan traces in one gesture — Esc/Enter ends the chain (committed segments stay). Walls are ordinary baked geometry, not a parametric object: a pure `wall_box` generator (8 verts / 6 outward-wound quad faces, or empty for a degenerate segment) → an undoable `CreateWallCommand` (Ctrl+Z peels back one segment at a time, mirroring the import command's detach-to-unreachable undo) → a **transform-aware** `WallTool` (world→active-local conversion with the base dropped to the context ground plane, VCB typed segment length) → a unit-aware thickness/height **tool-options row** shown only while the Wall tool is active (defaults 100 mm / 2400 mm). Independent boxes (no corner mitering) and centered justification for now. Python-only — no C++/kernel change (ctest stays 79/79). **M7b** ✅ *(shipped v0.2.2)* — the **Door/Window tool** (`D`): pick a wall face and a **framed door or window Component** is placed **flush** on it — auto-oriented to the face (upright, horizontal follows the cursor), **floor-anchored** (door sill 0, window sill default 900 mm), extending inward by a set depth. The wall is **not cut** (the kernel has no boolean/holes) — the opening sits on the still-solid wall (the accepted tradeoff). Identical `(kind, width, height, depth)` openings **share one Component** `Definition` via a runtime dedup registry (real instancing). Pipeline: a pure `opening_frame` generator (door = jambs + head + panel; window = jambs + head + sill + glazing, from closed outward-wound sub-boxes) → a pure `opening_placement_transform` (horizontalized viewer-facing normal → upright flush basis) → a hierarchical `Model.pick_face_local` (world ray → nearest child-face point + normal in active-local) → an undoable `PlaceOpeningCommand` (dedup-or-create Component, detach-undo keeping the shared Definition) → a `DoorWindowTool` with a Door|Window options row (unit-aware width/height/sill/depth). Python-only (ctest stays 79/79). **M7c** ✅ *(shipped v0.2.3)* — the **Roof tool** (`O`): draw a rectangle footprint on the active drawing plane and a parametric **Gable / Hip / Shed** roof is baked as a closed-solid `"Roof"` group over it — ridge auto-aligned to the footprint's longer edge (Up/Down arrows rotate it 90°), form + slope° from an options row, base following the drawing plane (draw on the ground, or hover a wall-top face to land on the walls). Flush (no overhang); each roof is a unique baked group. Pipeline: a pure `roof_solid(kind, width, depth, angle)` generator (Shed = mono-pitch wedge; Gable = full-depth ridge prism; Hip = equal-pitch ridge-setback, collapsing to a pyramid when `depth ≤ width`; all closed outward-wound manifolds) → an undoable `CreateRoofCommand` (baked `"Roof"` group, `CreateInstanceCommand`-style reuse-on-redo undo, no `defn.instances` leak) → a **transform-aware** `RoofTool` (world footprint → `mat_invert(active_world) @ m_world` local placement; live world-space wireframe preview matching the placement even inside an entered group) → a Gable|Hip|Shed options row (unit-aware slope°). Python-only (ctest stays 79/79). **M7d** ✅ *(shipped v0.2.4)* — the **Dimension tool** (`I`) and **Text tool** (`N`): persistent architectural-style annotations that live **per editing context** (`Definition.annotations`, so they ride along when their group/component moves) and draw as **screen-space `QPainter` overlays** over the GL pass — upright and constant pixel size at any zoom, no glyph atlas or texture support needed. The Dimension tool is a **3-click gesture** (snap `p1`, snap `p2`, click to set the perpendicular offset) drawing an **Architectural** dimension (45° ticks, extension-line gap + overshoot, text above an unbroken line); the Text tool is a **2-click + `QInputDialog`** gesture drawing a **Classic callout** (arrowhead at the anchor, dogleg leader into a horizontal landing, text on the landing, side-flipping to read away from the anchor). The spine is a **pure `plan_annotation` draw plan** (numpy, no Qt) that turns an annotation + camera into screen-space segments, texts and hit-boxes — **shared by both rendering and picking**, so what the user can click is by construction exactly what they see. Measurement text is **derived at draw time** from the geometry and the document's `Units` (never stored — switching metric↔imperial re-labels every dimension instantly). Round-trips through `.pluton` (per-`Definition` `annotations` block, `schema_version` 1→2, older files still open) — deliberately **not** exported to OBJ/glTF. Full lifecycle: click / Shift-toggle / **hover-highlight** select, Eraser + Delete (undoable, composing into a single undo with any co-deleted geometry), double-click a label to **retype** (`EditLabelTextCommand`), and **move** via the existing Move tool (a Dimension's offset or a Label's text_pos shifts, composing into one undo alongside geometry). Additive `main_window.py` (issue #48 finding count held at 9). Python-only (ctest stays 79/79). Remaining sub-milestones: **M7e** Scenes (saved cameras/views).

### Phase 3 — Platform *(v0.3 → v0.5)*

**End state:** Public beta. Cross-platform installers. Plugin ecosystem possible.

- **M8: Plugin system** — Python plugin API; plugin manifest format; plugin loader; sample plugins demonstrating common extension patterns.
- **M9: Mac support and installers** — macOS port (code signing + notarization); polished installers for Windows / Linux / macOS; first formal release announcement; documentation site; basic tutorial materials.

### Phase 4 — Scale and Integration *(v0.5 → v1.0)*

**End state:** v1.0. Handles real architectural projects. Integrates with industry rendering tools.

- **M10: Performance and scale** — profile and migrate geometry hot paths from Python to C++; BVH/spatial indexing for large scenes; multi-threading where applicable; goal is comfortable performance on full-building / neighborhood-scale projects.
- **M11: Industry integration** — additional file formats (FBX, USD, DAE); export pipelines tuned for V-Ray, Twinmotion, Lumion, Enscape workflows; potential "live link" plugin for at least one major external renderer.

### Phase 5 — Self-Sufficient *(v1.0+)*

**End state:** Pluton stands alone — full modeling and full rendering, no need to export.

- **M12: Real-time PBR viewport** — Eevee-style real-time renderer; Vulkan (probably) for forward-compatible performance; physically-based materials; real-time shadows, reflections, ambient occlusion.
- **M13: Production renderer** — Cycles-style path tracer for final renders; GPU-accelerated; architectural-grade rendering quality (interior lighting, glass, materials, global illumination).

### Phase 6 — Architectural Maturity & Open Horizons *(exploration tier)*

**End state:** Pluton becomes a complete architect's tool. Priority within this phase emerges from real user demand.

- **Layout-equivalent (integrated)** — 2D documentation from the 3D model: floor plans, elevations, sections, construction documents, title blocks, dimensions, scales. **Integrated into Pluton** (single install), not a separate companion app like SketchUp's Layout.
- **BIM-lite features** — smart architectural components (walls/doors/windows that know what they are); component properties and basic schedules; intentionally *not* full IFC / Revit-grade BIM (that is a multi-year project in its own right).
- **Open horizons** — animation and walkthrough cameras; VR support; AI-assisted modeling features; anything else the community surfaces as valuable.

---

## 7. Time-Shape Estimate

Honest solo-developer pacing at hobby intensity:

| Phase | Estimated duration |
|---|---|
| Phase 1: Foundation | 6–12 months |
| Phase 2: Modeling App | 12–18 months |
| Phase 3: Platform | 6–12 months |
| Phase 4: Scale and Integration | 12–18 months |
| Phase 5: Self-Sufficient | 2–5 years |
| Phase 6: Exploration | open-ended |

**v1.0: 3–6 years from project start. Phase 5 vision: 5–10+ years.** Blender took roughly 25 years to reach its current standing; Pluton is on a similar honest trajectory. The time-shape is part of the project's identity — sustainable pace beats burnout.

---

## 8. Open Questions / Deferred Decisions

These are flagged for resolution during the implementation plan or at the relevant milestone:

- **C++ test framework** — GoogleTest vs Catch2. Deferred to the M0 implementation plan; either is fine.
- **`.pluton` file format** — binary (e.g., custom binary or SQLite-based) vs JSON-based vs hybrid. Decided in M6 implementation plan; must support schema versioning from day 1.
- **Internationalization (i18n)** — not a concern for v0.x; revisit for Phase 3 / v0.5.
- **Plugin API surface** — detailed design deferred to M8 implementation plan.
- **Specific Python version target** — most recent stable Python at M0 start (probably 3.12 or 3.13); minimum supported version policy TBD.
- **Specific Qt version** — Qt 6.x latest LTS at M0 start.
- **Vulkan vs OpenGL for the eventual native renderer** — decided in M12 planning.
- **Funding model** — not relevant until at least Phase 3. Likely follows Blender's pattern (donations, optional cloud services, no paid features in core software).

---

## 9. References

- **nanobind**: https://nanobind.readthedocs.io/
- **CGAL**: https://www.cgal.org/
- **PySide6 / Qt for Python**: https://doc.qt.io/qtforpython-6/
- **ModernGL**: https://moderngl.readthedocs.io/
- **scikit-build-core**: https://scikit-build-core.readthedocs.io/
- **vcpkg**: https://vcpkg.io/
- **Blender source code** (architectural reference): https://projects.blender.org/blender/blender
- **FreeCAD source code** (Python + C++ + CGAL reference): https://github.com/FreeCAD/FreeCAD
- **SketchUp documentation** (modeling paradigm reference): https://help.sketchup.com/

---

## 10. Document History

| Date | Author | Change |
|---|---|---|
| 2026-05-16 | Rowee Apor | Initial design from brainstorming session |

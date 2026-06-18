# M4e — Groups & Components — Design Spec

- **Milestone:** M4e (fifth and final sub-milestone of M4, Phase 2 "Modeling App")
- **Depends on:** the C++ `HalfEdgeMesh` kernel + `Scene` wrapper (M3a), the command stack (M3a), selection + eraser (M4b), Move/Rotate/Scale transforms (M4c), the snap engine (M3d), the renderer/picking pipeline, the status bar.
- **Target release:** v0.1.4 (Groups + Components together).
- **Date:** 2026-06-19

---

## 1. Overview & Goals

Introduce SketchUp's central organizational feature: **Groups** and **Components**. Both are bundles of geometry that move/transform as a unit, are isolated from surrounding geometry, and can be "entered" for editing. **Components** add reuse: many **instances** share one **definition**, so editing any instance's geometry updates all of them.

This is the largest architectural change since the half-edge kernel itself. Pluton today is **one flat `HalfEdgeMesh`** — all geometry in a single coordinate/selection space (`MainWindow._scene`). M4e replaces that with a **scene graph**: a hierarchy of transformed, geometry-isolated nodes.

**Guiding insight:** in SketchUp's own model, *a group is just a component definition used by a single instance* (flagged "make unique on copy"). So we build **one** unified **Definition + Instance** model; "Group" vs "Component" is a behavior/UX distinction over shared machinery, not two code paths.

**Key property — de-risking:** the C++ kernel is **reused untouched**. A `Scene`/`HalfEdgeMesh` becomes "the geometry of one definition" instead of "the whole model." The root context with an identity transform must be **behaviorally identical to today's single mesh** — that invariant is the safety net the entire milestone leans on (all 417 pytest + 76 ctest stay green).

## 2. Non-goals / Deferrals

- **Component browser / library panel** (in-model thumbnails, re-insert from a list). Re-placing instances in M4e is done via **Move-copy** (§7.4). **Carry-over.**
- **Outliner panel** (a tree view of the model hierarchy). Navigation in M4e is via double-click-to-enter + `Esc`-to-exit + the breadcrumb. **Carry-over.**
- **On-disk component saving / loading** — belongs to the native file format (**M6**). M4e components live only in the in-memory model.
- **Cross-document clipboard copy/paste** (`Ctrl+C`/`Ctrl+V`). Superseded for M4e by Move-copy. **Carry-over.**
- **Move-copy of *loose* geometry** (duplicating raw edges/faces). M4e's Move-copy duplicates **instances**; loose-geometry duplication is a carry-over.
- **Advanced component behaviors:** glue-to-face, cut-opening, insertion axes/origin editing UI, dynamic-component attributes, scale-definition behavior. **Carry-over.**
- **VBO hardware instancing** (one upload, GPU-instanced draws). M4e draws a shared definition N times with N model matrices on the CPU side; the buffer is uploaded once per definition. Hardware instancing is a later perf optimization. **Carry-over.**
- **Rename UI for groups** — groups auto-name (`Group #N`); components get a name at creation (§7.2). A general rename/Entity-Info panel is a carry-over.

## 3. Key decisions

| Decision | Choice |
|---|---|
| Scope | Groups **and** Components in one release (v0.1.4). |
| Architecture | **Python scene graph over per-definition C++ meshes** (Approach ①). Each Definition owns its own `HalfEdgeMesh`; the kernel is untouched. |
| Unified model | One `Definition`+`Instance` model. Group = Definition with one instance (`is_group=True`); Component = Definition shared by ≥1. |
| Nesting | **Recursive / arbitrary depth** (falls out of the model). |
| Editing context | **Full isolation (Option A):** entering a group dims + desaturates the rest of the model; only the active context is pickable/editable. |
| Duplication | **Move-copy** (hold `Ctrl` during Move) → a new instance of the same definition. |
| Object selection | Selecting an instance highlights it as a **bounding box** (selection-blue); hover shows the object **silhouette**. Entity selection unchanged from M4b. |
| Coordinates | Geometry stored **definition-local**; world↔local conversion at the tool/snap/pick boundary via the active path's accumulated transform. Identity at the root. |
| Undo stack | Single, document-global (as today). Commands target an **explicit Definition** so they're context-independent. Entering/exiting a context is **not** undoable (transient, like selection). |
| Kernel changes | **None.** AABB + transform math is Python/numpy. |

## 4. Data model

New package `python/pluton/model/`.

### 4.1 `Instance` — `python/pluton/model/instance.py`

```python
class Instance:
    id: int                      # stable, unique within the Model
    definition: Definition       # the geometry this instance shows
    transform: np.ndarray        # (4,4) float64 model matrix, world-from-local
```

- Lightweight and **non-destructive**: an instance never owns geometry, only a reference + a placement.
- `transform` defaults to identity. Move/Rotate/Scale compose into it.

### 4.2 `Definition` — `python/pluton/model/definition.py`

```python
class Definition:
    id: int
    name: str                    # "Group #3" | "Chair" | "Model"
    is_group: bool               # True => group semantics (make-unique on copy)
    mesh: Scene                  # this definition's OWN geometry (a fresh HalfEdgeMesh)
    children: list[Instance]     # nested instances (recursion)
    instances: list[Instance]    # back-refs: every instance referencing THIS def
```

- `mesh` is the existing `Scene` wrapper — reused verbatim, one per definition.
- `instances` back-refs let us (a) know an edit propagates to N places, (b) detect single-instance (group) vs shared (component), (c) drive Make Unique.
- `local_aabb() -> (min_xyz, max_xyz) | None` — numpy min/max over the mesh's live vertex positions; `None` if empty. Used for bounding boxes.

### 4.3 `Model` — `python/pluton/model/model.py`

```python
class Model:
    root: Definition             # the top-level context ("Model"); is_group=False
    active_path: list[Instance]  # root→…→entered instance; [] means "at root"
    # registries / id counters for instances and definitions
```

Responsibilities:
- **Active context** — `active_context -> Definition` (the def at the tip of `active_path`, or `root` when empty); `active_world_transform -> (4,4)` (product of `active_path` transforms; identity at root); `active_scene -> Scene` (= `active_context.mesh`).
- **Traversal** — `traverse() -> Iterable[(Definition, world_transform)]` depth-first from `root`, accumulating transforms. The same definition reached via two instances is yielded twice with two transforms (this drives instancing).
- **Enter/exit** — `enter(instance)` pushes; `exit_one()` pops; `revalidate_active_path()` pops to the nearest surviving ancestor after an undo/redo destroys the active definition.
- **Picking** — `pick(ray_origin, ray_dir, *, scope)` (§9).
- **Structural mutators** used by commands — create/dissolve definitions, add/remove instances, clone a definition (Make Unique), bake an instance (Explode).

`MainWindow._scene = Scene()` is replaced by `MainWindow._model = Model()`. Everywhere a tool/renderer/picker currently reaches `_scene`, it reaches `_model.active_scene` (tools) or iterates `_model.traverse()` (renderer/picker).

## 5. Editing context & coordinates

- **Tools mutate the active context's mesh.** `ToolContext` exposes the **active context's** `Scene` and the active world↔local transforms through **accessors** (not a value captured once), so they track context changes during a session. At the root the scene is the whole-model mesh and both transforms are identity, so a tool that reads "the scene" sees **no behavioral difference** from today. (Exact accessor shape — a provider callable vs. a property — is a plan-level detail; the contract is "always the active context, always current.")
- **World ↔ local.** Geometry is stored definition-local. The viewport/snap pipeline:
  1. Camera ray is in **world** space. Before picking/snapping inside a moved group, convert the ray to **local** with `local_from_world`.
  2. Snap/inference results (world points) are converted to **local** before the tool writes vertices.
  3. The renderer converts local→world via the accumulated transform.
- At the root context the transform is identity ⇒ a literal no-op ⇒ zero behavior change vs today. The conversion "kicks in" only once the active context has a non-identity world transform (i.e. you entered a moved/rotated group). This boundary is the single fiddliest correctness point and gets explicit round-trip tests (§13).

## 6. Selection model

`Selection` (currently `{edges:set[int], faces:set[int]}`) gains a third bucket:

```python
class Selection:
    edges:     set[int]   # entity ids in the ACTIVE context's mesh
    faces:     set[int]   # entity ids in the ACTIVE context's mesh
    instances: set[int]   # selected Instance ids
    version:   int        # bumps on mutation (renderer change-detect), unchanged
```

- Entity ids are always interpreted against the **active context's** mesh.
- **Object vs entity:** clicking a nested *instance* selects the whole object (adds to `instances`); clicking *loose geometry* selects edges/faces as today. Loose geometry and instances coexist in the same context and are both selectable.
- Selection is **not** on the undo stack (unchanged from M4b).
- Switching the active context **clears** the selection (entity ids from one mesh are meaningless in another).

## 7. Tools & operations

All structural operations are undoable commands (§10), live in a new **Edit** menu, and use currently-free `Ctrl` shortcuts (the single-letter keys `L R P C G A Space E M Q S T` are all taken).

### 7.1 Select tool — enter/exit + object picking
- **Single click** on an instance → select it (object). On loose geometry → entity select (as today). On empty space *inside* a group → exit one level.
- **Double-click** an instance → `enter()` it (deeper if already inside). Outside dims (Option A).
- **`Esc`** → `exit_one()`; at the root keeps its current meaning (clear selection / cancel).
- **Hover** an instance → object silhouette highlight.
- Breadcrumb in the status bar shows the active path: `Model ▸ Group #3`.

### 7.2 Make Group (`Ctrl+G`) / Make Component (`Ctrl+Shift+G`)
- Operates on the current **entity** selection in the active context.
- *do:* create a new `Definition` (`is_group` True/False), move the selected vertices/edges/faces out of the active mesh into the definition's mesh, create **one** `Instance` of it in the active context, remove the lifted geometry from the parent. Selection becomes that instance.
- Make Component prompts for a name (a minimal Qt dialog, default `Component #N`); Make Group auto-names `Group #N`.
- Geometry is lifted **in place** — the new instance's transform is identity and the definition holds the geometry at its current world coords. (Insertion-axes/origin re-basing is deferred.)

### 7.3 Move / Rotate / Scale on an instance
- When the selection is an **instance**, the M4c tools compose the gesture into the instance's `transform` (a `TransformInstanceCommand`) — non-destructive, exact, and shared-definition-safe.
- When the selection is **entities** (inside a context), they edit vertices exactly as today.
- The tools detect which mode they're in from the selection contents. **Precedence:** if the selection contains *any* instances, the gesture is instance-mode (a mixed entity+instance selection is treated as instance-mode for M4e).

### 7.4 Move-copy (`Ctrl` held during Move)
- During a Move gesture on a selected **instance**, holding `Ctrl` at commit leaves the original and emits a `CreateInstanceCommand` for a **new** instance of the same definition at the moved transform.
- This is how additional component instances are placed. (Copying loose geometry is deferred.)

### 7.5 Explode (`Ctrl+Shift+E`)
- On a selected instance: bake its definition's geometry into the **parent** mesh (apply the instance transform to vertex positions), reparent its child instances up one level (composing transforms), and remove the instance. Undoable.

### 7.6 Make Unique (Edit menu)
- On a selected **component** instance sharing a definition with others: clone the definition (deep-copy its mesh + children) and repoint this instance at the clone, so further edits stop propagating. No-op (or disabled) for an instance that's already the sole user of its definition.

### 7.7 Delete / Eraser on an instance
- `Delete`/`Backspace` on a selected instance removes it (`DeleteInstanceCommand`). A definition with zero remaining instances becomes unreferenced; it is retained in memory for M4e (no GC/purge — a carry-over alongside the component browser).

### 7.8 Editing inside a component → propagation
- Push/Pull, drawing, vertex moves inside an entered component write to the shared definition's mesh ⇒ **all instances update**. This is automatic (they share one mesh) and is the headline feature.

## 8. Rendering

- The renderer iterates `model.traverse()` and, per `(definition, world_transform)`, draws that definition's `edge_line_buffer` / `face_triangle_buffer` (existing `Scene` methods) using `world_transform` as the model matrix.
- **Per-definition GL buffers** are cached and re-uploaded only when *that* definition's `Scene.dirty` trips. A definition reached by N instances uploads once, draws N times (CPU-side instancing).
- **Dim pass (Option A):** definitions **not** on the active path render through a desaturate+fade path; the active context renders at full color. A per-visit style flag set during traversal.
- **Overlays:**
  - *Object selection* → selection-blue **bounding box** from `definition.local_aabb()` transformed to world (8 corners → 12 edges) + corner ticks.
  - *Object hover* → object **silhouette** highlight.
  - *Entity selection* → existing M4b edge/face highlight (only inside the active context).
- Groups and components are visually identical when selected; they differ only by behavior and the breadcrumb label (`Group #3` vs `Component: Chair`).

## 9. Picking & snapping

- `Model.pick(ray_origin, ray_dir)` walks instances reachable from the **active context** (the default and only scope in M4e); for each, transforms the world ray into the instance's **local** frame (`inverse(world_transform)`), reuses the existing `ray_intersect_mesh` against that definition's mesh, and recurses into nested instances.
- **Scoped to the active context:** geometry outside the active path is **not** pickable — this is what enforces the §5/Option-A isolation.
  - *At the active level:* returns the top-most **instance** hit (object pick) or a loose **entity** hit, whichever is nearer along the ray.
  - *Inside a context:* returns entity hits on the active definition + nested instances as objects.
- The **snap engine** receives the active world↔local transforms so endpoint/midpoint/on-edge/on-face/axis inferences keep working while inside a moved group (candidates are gathered from the active context's mesh in local space; results surfaced in world space).

## 10. Commands & undo/redo

Single document-global `CommandStack` (unchanged). New `Command` subclasses (each `do`/`undo`/`redo`, `name` attr):

| Command | do | undo |
|---|---|---|
| `MakeGroupCommand` / `MakeComponentCommand` | lift selected entities → new Definition + 1 Instance | restore original entities (original IDs) to parent; drop new def + instance |
| `TransformInstanceCommand` | set instance.transform = new | restore prior matrix |
| `CreateInstanceCommand` | add new instance (Move-copy) | remove it |
| `ExplodeInstanceCommand` | bake geometry into parent + reparent children | reverse |
| `MakeUniqueCommand` | clone definition + repoint instance | repoint back, drop clone |
| `DeleteInstanceCommand` | remove instance (captured) | re-add |

Two rules that keep one global stack correct across contexts:
1. **Commands target an explicit `Definition`**, not "the active scene" — so undoing a geometry edit re-applies to the right mesh even after the user has entered/exited elsewhere.
2. After every undo/redo, `Model.revalidate_active_path()` runs: if the active definition was destroyed, pop the active path to the nearest surviving ancestor (and clear selection).

Geometry edits *inside* a context reuse the existing commands (`TransformVerticesCommand`, `DissolveEdgeCommand`, `SplitEdgeCommand`, delete/restore) — they already operate on a `Scene`; M4e just points them at the active definition's `Scene` and records that definition as the target.

Capture-and-restore for `MakeGroup`/`Explode`/`Delete` reuses the M4b pattern (`Scene.restore_vertex/edge/face` with original IDs).

## 11. Coordinate math

- Transforms are `(4,4)` float64 numpy matrices (`geometry/transforms.py` from M4c extended with compose/invert/apply-to-points helpers as needed).
- `apply_transform(points_Nx3, M) -> Nx3` (homogeneous), `invert(M)`, `compose(*Ms)`.
- A world bounding box = `apply_transform(local_aabb_corners, world_transform)` then min/max.
- Round-trip invariant under test: `local_from_world @ world_from_local ≈ I`; a point converted world→local→world returns to itself within float tolerance.

## 12. UI

- New **Edit** menu: Make Group (`Ctrl+G`), Make Component… (`Ctrl+Shift+G`), Make Unique, Explode (`Ctrl+Shift+E`). Items enable/disable based on selection contents.
- Status-bar **breadcrumb** of the active path; a single click on a crumb is *not* required for M4e (navigation is double-click/Esc), but the breadcrumb text reflects depth.
- The existing Units menu and VCB are untouched. The VCB continues to drive Move/Rotate/Scale — including when those act on an instance (typed distance/angle/factor applies to the instance transform).

## 13. Testing strategy

Data-level tests (pytest) + a final manual visual pass (GL pixels aren't unit-tested — consistent with prior milestones).

- **Data model:** `traverse()` accumulated transforms; nesting; one-definition/two-instances shares geometry; `local_aabb`.
- **Coordinate math:** world↔local round-trips; pick-ray transform; AABB→world bbox; compose/invert.
- **Commands:** each `do → undo → redo` restores exact state — geometry IDs, instance transforms, definition sharing, child reparenting. The rigorous core.
- **Propagation:** edit a shared definition → both instances' buffers reflect it; after **Make Unique**, they don't.
- **Explode:** baked positions equal transformed originals; children reparented with composed transforms.
- **Routing/isolation:** tool writes land in the active definition's mesh; `pick` is scoped to the active context (outside geometry not returned).
- **Active-path revalidation:** undoing the command that created the active context pops the path safely.
- **Regression (the safety net):** all existing **417 pytest + 76 ctest** stay green; the root/identity path is behaviorally identical to today.
- **Manual visual pass:** create group → enter/edit → move as unit → make component → Move-copy a 2nd instance → edit one, watch both update → Make Unique → Explode → undo/redo throughout.

## 14. Risks & implementation sequencing

**Primary risk:** this refactor touches `MainWindow`, the renderer, picking, selection, and every tool's notion of "the scene." Mitigation = the identity-root invariant + landing the pure model/commands first, fully unit-tested, before integration.

Intended sequence (writing-plans will break this into ordered tasks):
1. **Model core** — `Instance`, `Definition`, `Model` (traverse, active context, AABB) + unit tests. No UI wiring.
2. **Coordinate helpers** — transforms compose/invert/apply + round-trip tests.
3. **Commands** — all six new commands against the model + do/undo/redo tests. Still headless.
4. **Integration** — `MainWindow._scene → _model.active_scene`; route `ToolContext`; renderer over `traverse()`; picking scoped + ray-into-local; `Selection.instances`. Regression must stay green here (root/identity path).
5. **Editing context** — enter/exit, dim pass, breadcrumb, object selection/hover overlays.
6. **Operations** — Make Group/Component, instance Move/Rotate/Scale, Move-copy, Explode, Make Unique, Delete; Edit menu + shortcuts.
7. **Visual verification + release** (v0.1.4).

## 15. Deferred / carry-over (file as issues at release)

- Component browser / library panel + re-insert-from-list.
- Outliner (hierarchy tree) panel.
- On-disk component persistence (lands with M6 file format).
- Cross-document clipboard copy/paste; Move-copy of loose geometry.
- Unused-definition GC/purge.
- Glue-to-face, cut-opening, insertion-axes/origin UI, dynamic components.
- VBO hardware instancing (perf).
- General rename / Entity-Info panel.

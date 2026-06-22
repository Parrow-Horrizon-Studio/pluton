# M5c — Layers/Tags (object organization + per-tag visibility) — Design Spec

- **Milestone:** M5c (third and final sub-milestone of M5 "Materials & viewport styles", Phase 2 "Modeling App")
- **Depends on:** the scene graph (M4e — `Model`/`Definition`/`Instance`, `traverse`, `pick_instance`, `Selection.instances`, MakeGroup/MakeComponent commands); the dock + View-menu patterns established in M5b; the command stack (id-preserving undo).
- **Target release:** v0.1.7 (Layers/Tags).
- **Date:** 2026-06-22

---

## 1. Overview & Goals

Give the architect SketchUp's **Tags** (formerly "Layers") for organizing a model: assign objects to named tags, then **show/hide a whole tag** to declutter the view (e.g. hide "Furniture" while modeling "Walls"). This completes the M5 milestone.

What ships in M5c:

- **Tags are assigned to objects (group/component instances).** Hiding a tag hides those objects — and everything inside them — in the viewport and from picking.
- **An "active tag"** in a dockable Tags panel; **Assign to Selection** tags the selected objects, and newly-created groups/components **inherit** the active tag.
- **Visibility only** — each tag has a show/hide toggle. No per-tag color / "Color by Tag" in M5c.

**Guiding constraint — reuse, don't rebuild.** The data model mirrors M5b almost exactly: a per-`Model` `TagLibrary` of tags with an always-visible **"Untagged"** sentinel (id 0, like M5b's `DEFAULT_ID`), a tag reference on each `Instance`, an undoable assignment command, and a dock panel. Visibility filtering is a **visibility-aware traversal** (`Model.traverse_visible`) that prunes hidden instances and their subtrees; the renderer swaps one call. With no hidden tags the traversal is identical to today, so the render is **byte-identical**. **No tool, no `ToolContext` change, no shader change, no C++ kernel change.**

**Regression safety net.** With no tags hidden, `traverse_visible` yields the same `(definition, world)` sequence as `traverse()`, so the viewport is byte-identical to v0.1.6.

## 2. Non-goals / Deferrals

Explicitly **out of scope** for M5c (candidate follow-ups noted):

- **Loose-geometry (per-edge/face) tagging** — M5c tags whole objects (instances). Tagging individual edges/faces would need a per-entity `Scene` sidecar (like M5b materials) plus per-entity render filtering. Deferred.
- **Tag rename / delete / reorder** — M5c supports add + visibility + assign. Renaming, deleting (with a policy for objects still on a deleted tag), and reordering are deferred.
- **Per-tag color + "Color by Tag" view mode** — deferred; would add a color field, a view mode, and renderer tinting that interacts with the M5b material batches.
- **Tag folders / nesting** — deferred.
- **Context-menu / Entity-Info assignment** — M5c assigns via the dock button against the current selection. A right-click "Assign Tag ▸" menu or an Entity Info panel is deferred.
- **Tag persistence** in the document / file format — **M6** (file I/O). Tags and assignments are session-only; the data model is serialization-ready.
- **C++ kernel changes** — none.

## 3. Data model

### 3.1 `Tag` (new `python/pluton/model/tag.py`)

```python
@dataclass(slots=True)
class Tag:
    id: int
    name: str
    visible: bool = True
```

Unlike M5b's frozen `Material`, `Tag` is **mutable**: `visible` is live view state that toggles constantly. Tag visibility is not part of undo (see §3.4), so a mutable field is the honest model.

### 3.2 `TagLibrary` (same module)

- `UNTAGGED_ID = 0` — the **"Untagged"** tag: id 0, **always visible** (cannot be hidden or deleted). Mirrors M5b's `DEFAULT_ID` sentinel.
- Seeded at construction with only Untagged.
- `add(name: str) -> Tag` — appends a new tag with a fresh monotonic id, returns it.
- `get(tid: int) -> Tag` — returns the tag, or Untagged for an unknown id.
- `tags() -> list[Tag]` — ordered list, Untagged first.
- `set_visible(tid: int, visible: bool) -> None` — sets `tag.visible`; **no-op when `tid == UNTAGGED_ID`** (Untagged stays visible).
- `is_visible(tid: int) -> bool` — `self.get(tid).visible` (Untagged always True).

One `TagLibrary` lives on the **`Model`** (`model.tags`), seeded at construction: instances reference its ids, the renderer/picking consult it, and it travels with the model for M6.

### 3.3 `Instance.tag_id`

`Instance` gains a new slot `tag_id: int` (added to `__slots__`), default `UNTAGGED_ID`. Tags attach to the **placement** (instance), so two instances of the same component can sit on different tags. `Model.clone_definition` copies each child instance's `tag_id` so MakeUnique preserves tags.

### 3.4 Undo split (mirrors M5b's model-edit vs view-state split)

- **Tag assignment** to objects → a *model edit* → **undoable** (`TagInstancesCommand`, §5).
- **Visibility toggle** and **adding a tag** → *view / library state* → **not undoable** (like M5a's face-style/X-Ray and M5b's add-custom-material). Toggling mutates `Tag.visible` directly.

## 4. Visibility traversal & picking

### 4.1 `Model.traverse_visible` (new)

```python
def traverse_visible(self):
    """Like traverse(), but prunes any instance on a hidden tag — and its whole
    subtree (hiding an object hides its contents). Instances on the active editing
    path are always kept (you're editing inside them)."""
    active_ids = {inst.id for inst in self.active_path}
    yield from self._traverse_visible(self.root, np.eye(4, dtype=np.float64), active_ids)

def _traverse_visible(self, definition, world, active_ids):
    yield definition, world
    for inst in definition.children:
        if inst.id not in active_ids and not self.tags.is_visible(inst.tag_id):
            continue                              # prune hidden instance + subtree
        yield from self._traverse_visible(inst.definition, world @ inst.transform, active_ids)
```

- Subtree pruning is automatic — we simply don't recurse into a hidden instance.
- The Model owns `self.tags`, so no predicate is threaded.
- **Active-path bypass:** an instance on `self.active_path` is never pruned, so the group you're currently editing stays visible even if its tag is hidden (otherwise you'd be editing an invisible object). The original `traverse()` is unchanged, for non-render uses.

### 4.2 Renderer

One-line swap in `scene_renderer.py` `render()`: `for definition, world in model.traverse():` → `model.traverse_visible():`. The dim pass, world transforms, and per-material batching are unchanged. With no hidden tags, the yielded sequence is identical → **byte-identical render**.

### 4.3 Picking

`Model.pick_instance` adds one guard inside its `active_context.children` loop: `if not self.tags.is_visible(inst.tag_id): continue` — you can't select what you can't see. Loose-geometry picking (`pick_selectable`) operates inside the active context (always visible), so it needs no tag filter.

### 4.4 Selection bbox

The renderer's selected-instance bounding-box pass (which iterates `active_context.children`) gets the same hidden-tag skip, so a selected-but-hidden object doesn't show a stray bbox.

## 5. Assignment, active tag & inherit

### 5.1 `TagInstancesCommand` (new `python/pluton/commands/tag_commands.py`)

```python
class TagInstancesCommand(Command):
    """Assign a tag to a set of instances; undo restores each instance's prior tag."""
    name = "Assign Tag"
    def __init__(self, instances, new_tag_id: int) -> None:
        self._instances = list(instances)
        self._new = new_tag_id
        self._old: dict[int, int] = {}            # instance.id -> old tag_id
    def do(self, model) -> None:                  # group-command convention: target is the model
        for inst in self._instances:
            self._old[inst.id] = inst.tag_id
            inst.tag_id = self._new
    def undo(self, model) -> None:
        for inst in self._instances:
            inst.tag_id = self._old.get(inst.id, 0)   # 0 == UNTAGGED_ID
```

Captures each instance's prior tag at `do()` time (id-preserving undo, like `PaintFaceCommand`). Group commands' `do/undo` already take the **model** as their target (verified: `MakeGroupCommand.do(self, model)`); `TagInstancesCommand` follows the same convention.

### 5.2 Active tag

MainWindow owns `self._active_tag_id = TagLibrary.UNTAGGED_ID`. The Tags dock's active-row selection updates it via a signal (mirrors the Materials dock's active material).

### 5.3 Assign to Selection

The dock's **"Assign to Selection"** button → a MainWindow handler that gathers the selected instances:

```python
selected = [inst for inst in self._model.active_context.children
            if inst.id in self._selection.instances]
```

If `selected` is non-empty, it builds `TagInstancesCommand(selected, self._active_tag_id)`, executes it, calls `command_stack.push_executed(cmd, self._model)`, and refreshes the viewport. No-op when the selection has no instances.

### 5.4 Inherit

`MakeGroupCommand`/`MakeComponentCommand` gain an optional `tag_id: int = UNTAGGED_ID` kwarg. The created instance is assigned `tag_id` on **both** the initial `do()` and the `_redo()` path (so redo preserves the tag). MainWindow's `_on_make_group`/`_on_make_component` pass `tag_id=self._active_tag_id`. Since only instances carry tags in M5c, "new geometry inherits the active tag" means new **groups/components** — loose lines/faces are never tagged.

## 6. Tags dock & MainWindow wiring

### 6.1 `TagsDock(QDockWidget)` (new `python/pluton/ui/tags_dock.py`)

- A **`QListWidget`** where each row is a tag: the item's **checkbox = visibility**, the item **text = name**, and the **selected row = active tag**. No custom row widgets.
- The **Untagged** row is pinned: its checkbox is checked and not user-uncheckable (always visible); it remains selectable as the active tag.
- Buttons below: **"Add Tag"** (auto-names `Tag 1`, `Tag 2`, … via `library.add`) and **"Assign to Selection"**.
- Signals: `active_tag_changed(int)`, `visibility_changed()`, `assign_to_selection_requested()`. Plus `set_active(tag_id)` and an `active_tag_id` property.
- Rebuilds block signals to avoid re-entrancy (the same guard the Materials dock uses).

### 6.2 No tool, no `ToolContext` change

Unlike M5b (which needed a Paint tool + two context hooks), tag assignment reuses the existing **Select tool** + `Selection` — the dock button drives a MainWindow handler. So M5c touches **no** tool code and **no** `ToolContext`.

### 6.3 MainWindow

- `self._active_tag_id = TagLibrary.UNTAGGED_ID`.
- `self._tags_dock = TagsDock(self._model.tags, self)`; `addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tags_dock)`; then `self.tabifyDockWidget(self._materials_dock, self._tags_dock)` so Materials and Tags share the right-side area as tabs.
- Connect: `active_tag_changed → self._active_tag_id = tid`; `visibility_changed → self._viewport.update()`; `assign_to_selection_requested → self._on_assign_tag()` (§5.3).
- **View menu:** add `self._tags_dock.toggleViewAction()` (**View ▸ Tags**), beside View ▸ Materials.
- `_on_make_group`/`_on_make_component` pass `tag_id=self._active_tag_id`.

## 7. Testing strategy

GL pixels aren't headlessly testable, so decision logic lives in pure functions that **are** unit-tested; pixel output is verified by a manual visual pass.

**Unit-tested (pure / no GL):**

- `tag.py` — `TagLibrary` seeds Untagged first (id 0); `add` mints fresh monotonic ids; `get` falls back to Untagged; `set_visible` is a no-op on Untagged; `is_visible(Untagged)` always True.
- `Instance.tag_id` defaults to `UNTAGGED_ID`; `clone_definition` copies child `tag_id`.
- `Model.traverse_visible` — hidden tag prunes the instance **and its subtree**; an active-path instance bypasses the filter; **no hidden tags ⇒ identical sequence to `traverse()`**; a visible instance nested under a hidden one is still pruned.
- `Model.pick_instance` — skips hidden-tag instances.
- `TagInstancesCommand` — `do` assigns, `undo` restores each instance's prior tag (including a mix of different prior tags); redo re-applies.
- `MakeGroup`/`MakeComponent` — created instance gets the passed `tag_id` on both `do` and redo; defaults to Untagged when omitted.

**Qt (pytest-qt):** `TagsDock` (built from library, Untagged first; checkbox toggles visibility + emits; row selection changes active + emits; Add Tag grows the list; Assign emits) and MainWindow wiring (dock exists + tabified, **View ▸ Tags** toggle present, assign handler tags the selected instances, active tag tracks).

**Regression invariants (must stay green / byte-identical):** no hidden tags ⇒ `traverse_visible` == `traverse` ⇒ byte-identical render; full suite (633 pytest + 76/76 ctest) stays green; new tests add on top. No shader change, no C++ change.

**Manual visual pass (final task, needs the user):** group objects; add tags; Assign to Selection; toggle a tag's visibility (its objects hide/show and become unpickable); edit inside a group whose tag is hidden (it stays visible while editing); new group/component inherits the active tag; undo/redo a tag assignment; reopen the dock via View ▸ Tags; confirm Untagged can't be hidden; an untagged/no-hidden-tags model looks identical to v0.1.6.

## 8. Deliverables & sequencing

**New files:** `model/tag.py`, `commands/tag_commands.py`, `ui/tags_dock.py`, and test files.

**Edited files:** `model/instance.py` (`tag_id` slot), `model/model.py` (`tags` library + `traverse_visible` + `pick_instance` filter + `clone_definition` tag copy), `commands/group_commands.py` (`tag_id` inherit on do + redo), `viewport/scene_renderer.py` (`traverse_visible` swap + selection-bbox skip), `ui/main_window.py` (dock + wiring + View ▸ Tags toggle + make-group threading).

**No C++ kernel changes.**

**Indicative task order** (final plan produced by writing-plans): (1) `Tag`/`TagLibrary` + tests → (2) `Instance.tag_id` + `Model.tags` + `clone_definition` copy + tests → (3) `Model.traverse_visible` + `pick_instance` filter + tests → (4) renderer `traverse_visible` swap + selection-bbox skip → (5) `TagInstancesCommand` + tests → (6) MakeGroup/MakeComponent `tag_id` inherit + tests → (7) `TagsDock` + tests → (8) MainWindow wiring (dock + tabify + View toggle + assign handler + make-group threading) + tests → (9) full regression + manual visual pass → (10) release v0.1.7-m5c.

**Target release:** v0.1.7-m5c. Deferred items (loose-geometry tagging, rename/delete/reorder, color-by-tag, folders, context-menu assignment) filed as follow-up issues at release.

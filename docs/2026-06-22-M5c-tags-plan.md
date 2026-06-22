# M5c — Layers/Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SketchUp-style Tags — assign group/component objects to named tags and show/hide a whole tag — with no tool change, no shader change, and no C++ kernel change.

**Architecture:** A per-`Model` `TagLibrary` (with an always-visible "Untagged" sentinel id 0) plus a `tag_id` on each `Instance`. A visibility-aware `Model.traverse_visible` prunes hidden instances and their subtrees; the renderer swaps one call. Assignment is an undoable `TagInstancesCommand` driven by a list-based `TagsDock` against the current selection; new groups/components inherit the active tag.

**Tech Stack:** Python 3.13, numpy, PySide6 (Qt), PyOpenGL, pytest + pytest-qt. C++/nanobind kernel is **untouched**.

**Spec:** `docs/2026-06-22-M5c-tags-design.md`

## Global Constraints

- **Python interpreter / tests:** use `.venv/Scripts/python` explicitly (bash) — a bare `python`/`pytest` resolves to a drifting editable install. Run tests as `.venv/Scripts/python -m pytest …`.
- **Ruff:** the repo selects `["E","F","W","I","N","UP","B","C4","RUF"]`. **Never run `ruff --fix` broadly** — it strips intentional `# noqa: ANN001` comments (issue #48) the project deliberately keeps. Fix lint by hand; only run `ruff --fix` on a brand-new file with no intentional `noqa`.
- **Git:** work on `main` (no feature branches). Stage **specific files only** — never `git add -A` / `git add .`. **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay on). End every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **No C++ kernel changes.** No edits under `cpp/`. No version-file edits (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) except in Task 10 (release).
- **Regression invariant:** with no tags hidden, `traverse_visible` yields the same sequence as `traverse`, so the viewport is **byte-identical to v0.1.6**. Full suite (633 pytest + 76/76 ctest) stays green; new tests add on top.
- **UNTAGGED sentinel:** tag id `0` means "Untagged / always visible" everywhere. It is never hidden.
- **No tool / no ToolContext change** in M5c. **No shader change.**

---

### Task 1: `Tag` + `TagLibrary`

**Files:**
- Create: `python/pluton/model/tag.py`
- Test: `tests/test_tag_library.py`

**Interfaces:**
- Produces:
  - `Tag(id: int, name: str, visible: bool = True)` — mutable dataclass (`slots=True`).
  - `TagLibrary` with `UNTAGGED_ID = 0`, `add(name) -> Tag`, `get(tid) -> Tag` (falls back to Untagged), `tags() -> list[Tag]` (Untagged first), `set_visible(tid, visible) -> None` (no-op for Untagged), `is_visible(tid) -> bool` (Untagged always True).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tag_library.py
from __future__ import annotations

from pluton.model.tag import Tag, TagLibrary


def test_untagged_is_first_and_id_zero():
    lib = TagLibrary()
    tags = lib.tags()
    assert TagLibrary.UNTAGGED_ID == 0
    assert tags[0].id == 0
    assert tags[0].name == "Untagged"
    assert tags[0].visible is True


def test_add_mints_fresh_monotonic_ids():
    lib = TagLibrary()
    a = lib.add("Walls")
    b = lib.add("Furniture")
    assert a.id == 1
    assert b.id == 2
    assert [t.id for t in lib.tags()] == [0, 1, 2]


def test_get_unknown_falls_back_to_untagged():
    lib = TagLibrary()
    assert lib.get(999).id == TagLibrary.UNTAGGED_ID


def test_set_visible_toggles_user_tag():
    lib = TagLibrary()
    w = lib.add("Walls")
    lib.set_visible(w.id, False)
    assert lib.is_visible(w.id) is False
    lib.set_visible(w.id, True)
    assert lib.is_visible(w.id) is True


def test_untagged_cannot_be_hidden():
    lib = TagLibrary()
    lib.set_visible(TagLibrary.UNTAGGED_ID, False)
    assert lib.is_visible(TagLibrary.UNTAGGED_ID) is True


def test_is_visible_unknown_id_is_true():
    lib = TagLibrary()
    assert lib.is_visible(999) is True


def test_tag_is_mutable():
    t = Tag(1, "X", True)
    t.visible = False
    assert t.visible is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_tag_library.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluton.model.tag'`

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/model/tag.py
"""Tags ('Layers') for organizing objects + per-tag visibility (M5c).

Pure Python — no GL, no Qt — so it is fully unit-testable headlessly. Tags
attach to group/component Instances via Instance.tag_id; the renderer and
picking consult TagLibrary.is_visible to hide objects on a hidden tag. The
library is serialization-ready for M6 file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Tag:
    """A named tag. `visible` is mutable view state (not part of undo)."""

    id: int
    name: str
    visible: bool = True


class TagLibrary:
    """Owns the model's Tag objects: Untagged first, then user tags."""

    UNTAGGED_ID = 0

    def __init__(self) -> None:
        self._untagged = Tag(self.UNTAGGED_ID, "Untagged", True)
        self._tags: dict[int, Tag] = {self.UNTAGGED_ID: self._untagged}
        self._order: list[int] = [self.UNTAGGED_ID]
        self._next_id = 1

    def add(self, name: str) -> Tag:
        """Append a new tag with a fresh monotonic id and return it."""
        tag = Tag(self._next_id, str(name), True)
        self._tags[tag.id] = tag
        self._order.append(tag.id)
        self._next_id += 1
        return tag

    def get(self, tid: int) -> Tag:
        """Return the tag for `tid`, or the Untagged tag if unknown."""
        return self._tags.get(tid, self._untagged)

    def tags(self) -> list[Tag]:
        """All tags in display order (Untagged first)."""
        return [self._tags[i] for i in self._order]

    def set_visible(self, tid: int, visible: bool) -> None:
        """Set a tag's visibility. No-op for Untagged (always visible)."""
        if tid == self.UNTAGGED_ID:
            return
        tag = self._tags.get(tid)
        if tag is not None:
            tag.visible = bool(visible)

    def is_visible(self, tid: int) -> bool:
        """Whether entities on this tag should be drawn (Untagged always True)."""
        return self.get(tid).visible
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_tag_library.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Lint**

Run: `.venv/Scripts/python -m ruff check python/pluton/model/tag.py tests/test_tag_library.py`
Expected: no errors. (Safe to `ruff --fix` these two NEW files if I001 flags.)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/model/tag.py tests/test_tag_library.py
git commit -m "$(printf 'feat(m5c): Tag + TagLibrary with always-visible Untagged sentinel\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: `Instance.tag_id` + `Model.tags` + clone copy

**Files:**
- Modify: `python/pluton/model/instance.py` (`__slots__` + `__init__`)
- Modify: `python/pluton/model/model.py` (`__init__` adds `self.tags`; `clone_definition` copies child `tag_id`)
- Test: `tests/test_instance_tag.py`

**Interfaces:**
- Consumes: `TagLibrary` (Task 1).
- Produces: `Instance.tag_id: int` (default 0); `Model.tags: TagLibrary`; `clone_definition` preserves child `tag_id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_instance_tag.py
from __future__ import annotations

from pluton.model.model import Model
from pluton.model.tag import TagLibrary


def test_new_instance_defaults_to_untagged():
    m = Model()
    d = m.new_definition("D", is_group=True)
    inst = m.new_instance(d)
    assert inst.tag_id == TagLibrary.UNTAGGED_ID


def test_model_has_tag_library():
    m = Model()
    assert isinstance(m.tags, TagLibrary)
    assert m.tags.tags()[0].id == TagLibrary.UNTAGGED_ID


def test_clone_definition_copies_child_tag_ids():
    m = Model()
    outer = m.new_definition("Outer", is_group=True)
    inner = m.new_definition("Inner", is_group=True)
    child = m.new_instance(inner)
    child.tag_id = 5
    outer.children.append(child)
    clone = m.clone_definition(outer)
    assert clone.children[0].tag_id == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_instance_tag.py -v`
Expected: FAIL (`AttributeError: 'Instance' object has no attribute 'tag_id'` or `Model` has no attribute `tags`).

- [ ] **Step 3: Add `tag_id` to `Instance`**

In `python/pluton/model/instance.py`, change `__slots__` to include `tag_id` and set a default in `__init__`:

```python
    __slots__ = ("id", "definition", "transform", "tag_id")

    def __init__(
        self, instance_id: int, definition: Definition, transform: np.ndarray | None = None
    ) -> None:
        self.id = int(instance_id)
        self.definition = definition
        if transform is None:
            self.transform = np.eye(4, dtype=np.float64)
        else:
            self.transform = np.asarray(transform, dtype=np.float64).reshape(4, 4).copy()
        self.tag_id = 0  # 0 == TagLibrary.UNTAGGED_ID; set by MakeGroup inherit / clone / TagInstancesCommand
```

- [ ] **Step 4: Add `Model.tags` and copy tags in `clone_definition`**

In `python/pluton/model/model.py`, add the import near the other model imports:

```python
from pluton.model.tag import TagLibrary
```

In `Model.__init__` (after `self.active_path = []`):

```python
        self.tags = TagLibrary()
```

In `clone_definition`, the child loop currently reads:

```python
        for child in definition.children:
            clone.children.append(self.new_instance(child.definition, child.transform))
```

Replace it with one that copies the tag:

```python
        for child in definition.children:
            new_child = self.new_instance(child.definition, child.transform)
            new_child.tag_id = child.tag_id
            clone.children.append(new_child)
```

- [ ] **Step 5: Run tests + model regression**

Run: `.venv/Scripts/python -m pytest tests/test_instance_tag.py -v`
Expected: PASS (3 passed)

Run: `.venv/Scripts/python -m pytest tests/ -k "model or instance or group or clone" -q`
Expected: PASS (existing model/scene-graph tests still green)

- [ ] **Step 6: Lint (hand-fix only — model.py carries intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/model/instance.py python/pluton/model/model.py tests/test_instance_tag.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/model/instance.py python/pluton/model/model.py tests/test_instance_tag.py
git commit -m "$(printf 'feat(m5c): Instance.tag_id + Model.tags library + clone preserves tags\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: `Model.traverse_visible` + `pick_instance` filter

**Files:**
- Modify: `python/pluton/model/model.py` (add `traverse_visible`/`_traverse_visible`; add a guard to `pick_instance`)
- Test: `tests/test_traverse_visible.py`

**Interfaces:**
- Consumes: `Model.tags` (Task 2), `Instance.tag_id` (Task 2).
- Produces: `Model.traverse_visible()` (yields `(definition, world)` like `traverse`, pruning hidden-tag instances + subtrees, keeping active-path instances); `pick_instance` skips hidden-tag instances.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_traverse_visible.py
from __future__ import annotations

import numpy as np
from pluton.model.model import Model


def _child(m, parent, tag_id=0):
    d = m.new_definition("D", is_group=True)
    inst = m.new_instance(d)
    inst.tag_id = tag_id
    parent.children.append(inst)
    return inst, d


def test_no_hidden_tags_matches_traverse():
    m = Model()
    _child(m, m.root)
    _child(m, m.root)
    plain = [id(d) for d, _ in m.traverse()]
    visible = [id(d) for d, _ in m.traverse_visible()]
    assert plain == visible


def test_hidden_tag_prunes_instance():
    m = Model()
    walls = m.tags.add("Walls")
    _a, da = _child(m, m.root, tag_id=walls.id)
    m.tags.set_visible(walls.id, False)
    defs = [d for d, _ in m.traverse_visible()]
    assert da not in defs
    assert m.root in defs


def test_hidden_tag_prunes_subtree():
    m = Model()
    walls = m.tags.add("Walls")
    _a, da = _child(m, m.root, tag_id=walls.id)
    _c, dc = _child(m, da, tag_id=0)            # visible child inside hidden parent
    m.tags.set_visible(walls.id, False)
    defs = [d for d, _ in m.traverse_visible()]
    assert da not in defs
    assert dc not in defs                       # subtree pruned even though child is Untagged


def test_active_path_instance_bypasses_hidden():
    m = Model()
    walls = m.tags.add("Walls")
    a, da = _child(m, m.root, tag_id=walls.id)
    m.tags.set_visible(walls.id, False)
    m.enter(a)                                  # editing inside a
    defs = [d for d, _ in m.traverse_visible()]
    assert da in defs


def test_pick_instance_skips_hidden():
    m = Model()
    walls = m.tags.add("Walls")
    a, da = _child(m, m.root, tag_id=walls.id)
    v = [da.mesh.add_vertex(np.array([0.0, 0.0, 0.0])),
         da.mesh.add_vertex(np.array([1.0, 0.0, 0.0])),
         da.mesh.add_vertex(np.array([0.0, 1.0, 0.0]))]
    da.mesh.add_face_from_loop(v)
    origin = np.array([0.25, 0.25, 1.0])
    direction = np.array([0.0, 0.0, -1.0])
    assert m.pick_instance(origin, direction) is a      # visible → hit
    m.tags.set_visible(walls.id, False)
    assert m.pick_instance(origin, direction) is None    # hidden → skipped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_traverse_visible.py -v`
Expected: FAIL (`AttributeError: 'Model' object has no attribute 'traverse_visible'`).

- [ ] **Step 3: Add `traverse_visible` / `_traverse_visible`**

In `python/pluton/model/model.py`, just after the existing `_traverse` method, add:

```python
    def traverse_visible(self):
        """Like traverse(), but prunes any instance on a hidden tag — and its whole
        subtree (hiding an object hides its contents). Instances on the active
        editing path are always kept (you're editing inside them)."""
        active_ids = {inst.id for inst in self.active_path}
        yield from self._traverse_visible(self.root, np.eye(4, dtype=np.float64), active_ids)

    def _traverse_visible(self, definition, world, active_ids):  # noqa: ANN001
        yield definition, world
        for inst in definition.children:
            if inst.id not in active_ids and not self.tags.is_visible(inst.tag_id):
                continue
            yield from self._traverse_visible(inst.definition, world @ inst.transform, active_ids)
```

- [ ] **Step 4: Add the hidden-tag guard to `pick_instance`**

In `pick_instance`, the loop currently begins:

```python
        for inst in self.active_context.children:
            world = world0 @ inst.transform
```

Insert a skip at the top of the loop body so it reads:

```python
        for inst in self.active_context.children:
            if not self.tags.is_visible(inst.tag_id):
                continue
            world = world0 @ inst.transform
```

- [ ] **Step 5: Run tests + model regression**

Run: `.venv/Scripts/python -m pytest tests/test_traverse_visible.py -v`
Expected: PASS (5 passed)

Run: `.venv/Scripts/python -m pytest tests/ -k "model or traverse or pick" -q`
Expected: PASS

- [ ] **Step 6: Lint (hand-fix only — model.py carries intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/model/model.py tests/test_traverse_visible.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/model/model.py tests/test_traverse_visible.py
git commit -m "$(printf 'feat(m5c): Model.traverse_visible (prune hidden-tag subtrees) + pick filter\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: Renderer uses `traverse_visible` + selection-bbox skip

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py` (`render()` traverse swap + selection-bbox hidden-tag skip)

**Interfaces:**
- Consumes: `Model.traverse_visible` (Task 3), `Model.tags.is_visible` (Task 2).

This is a GL-bound change. The decision logic (`traverse_visible`, pick filter) is already unit-tested in Task 3; the renderer's pixel output is verified by net-diff inspection + the Task 9 manual visual pass (the renderer early-returns without a GL context, so it isn't headlessly testable). The acceptance bar is the byte-identical-with-no-hidden-tags invariant.

- [ ] **Step 1: Swap the traversal in `render()`**

In `scene_renderer.py`, the per-definition loop currently reads:

```python
            for definition, world in model.traverse():
```

Change it to:

```python
            for definition, world in model.traverse_visible():
```

- [ ] **Step 2: Skip hidden instances in the selection-bbox pass**

In `render()`, the selected-instance bounding-box pass currently reads:

```python
            if selection is not None and selection.instances:
                active_world = model.active_world_transform
                for inst in model.active_context.children:
                    if inst.id in selection.instances:
                        aabb = inst.definition.local_aabb()
```

Add a hidden-tag skip so a selected-but-hidden object shows no stray bbox:

```python
            if selection is not None and selection.instances:
                active_world = model.active_world_transform
                for inst in model.active_context.children:
                    if inst.id in selection.instances and model.tags.is_visible(inst.tag_id):
                        aabb = inst.definition.local_aabb()
```

- [ ] **Step 3: Run the full suite (regression)**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (full suite green — no behavior change when no tags are hidden).

- [ ] **Step 4: Inspect the net diff**

Run: `git diff -- python/pluton/viewport/scene_renderer.py`
Confirm exactly two changes: the `traverse()` → `traverse_visible()` swap, and the `and model.tags.is_visible(inst.tag_id)` guard in the bbox pass. No `# noqa` comments removed; no other lines touched.

- [ ] **Step 5: Lint (hand-fix only — scene_renderer.py carries intentional noqa; do NOT `ruff --fix`)**

Run: `.venv/Scripts/python -m ruff check python/pluton/viewport/scene_renderer.py`
Expected: only pre-existing `# noqa` debt — no NEW errors.

- [ ] **Step 6: Commit**

```bash
git add python/pluton/viewport/scene_renderer.py
git commit -m "$(printf 'feat(m5c): renderer honors tag visibility (traverse_visible + bbox skip)\n\nByte-identical when no tags are hidden. No shader change.\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: `TagInstancesCommand`

**Files:**
- Create: `python/pluton/commands/tag_commands.py`
- Test: `tests/test_tag_instances_command.py`

**Interfaces:**
- Consumes: `Command` base (`pluton.commands.command.Command`); `Instance.tag_id` (Task 2).
- Produces: `TagInstancesCommand(instances, new_tag_id)` with `do(model)` / `undo(model)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tag_instances_command.py
from __future__ import annotations

from pluton.commands.tag_commands import TagInstancesCommand
from pluton.model.model import Model


def _inst(m, tag_id=0):
    d = m.new_definition("D", is_group=True)
    i = m.new_instance(d)
    i.tag_id = tag_id
    return i


def test_do_assigns_and_undo_restores_mixed():
    m = Model()
    a = _inst(m, 0)
    b = _inst(m, 3)
    cmd = TagInstancesCommand([a, b], 5)
    cmd.do(m)
    assert a.tag_id == 5 and b.tag_id == 5
    cmd.undo(m)
    assert a.tag_id == 0 and b.tag_id == 3


def test_redo_reapplies():
    m = Model()
    a = _inst(m, 1)
    cmd = TagInstancesCommand([a], 7)
    cmd.do(m)
    cmd.undo(m)
    cmd.do(m)
    assert a.tag_id == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_tag_instances_command.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'pluton.commands.tag_commands'`).

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/commands/tag_commands.py
"""Tag commands (M5c): TagInstancesCommand."""

from __future__ import annotations

from pluton.commands.command import Command

_UNTAGGED_ID = 0  # == TagLibrary.UNTAGGED_ID


class TagInstancesCommand(Command):
    """Assign a tag to a set of instances; undo restores each instance's prior tag.

    Captures each instance's previous tag at do() time (id-preserving undo).
    Group commands take the model as their target, so do/undo take `model`.
    """

    name = "Assign Tag"

    def __init__(self, instances, new_tag_id: int) -> None:
        self._instances = list(instances)
        self._new = int(new_tag_id)
        self._old: dict[int, int] = {}

    def do(self, model) -> None:  # noqa: ANN001
        for inst in self._instances:
            self._old[inst.id] = inst.tag_id
            inst.tag_id = self._new

    def undo(self, model) -> None:  # noqa: ANN001
        for inst in self._instances:
            inst.tag_id = self._old.get(inst.id, _UNTAGGED_ID)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_tag_instances_command.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint (KEEP the `# noqa: ANN001`; do NOT `ruff --fix` material/command files)**

Run: `.venv/Scripts/python -m ruff check python/pluton/commands/tag_commands.py tests/test_tag_instances_command.py`
Expected: no errors (the `# noqa: ANN001` on do/undo is intentional, mirroring other commands).

- [ ] **Step 6: Commit**

```bash
git add python/pluton/commands/tag_commands.py tests/test_tag_instances_command.py
git commit -m "$(printf 'feat(m5c): TagInstancesCommand (id-preserving undo for tag assignment)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 6: MakeGroup/MakeComponent inherit the active tag

**Files:**
- Modify: `python/pluton/commands/group_commands.py` (`tag_id` kwarg on both commands; assign on `do()`)
- Test: `tests/test_make_group_tag_inherit.py`

**Interfaces:**
- Consumes: `Instance.tag_id` (Task 2).
- Produces: `MakeGroupCommand(..., *, is_group=True, name=None, tag_id=0)`; `MakeComponentCommand(..., *, name, tag_id=0)`; the created instance carries `tag_id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_make_group_tag_inherit.py
from __future__ import annotations

import numpy as np
from pluton.commands.group_commands import MakeComponentCommand, MakeGroupCommand
from pluton.model.model import Model


def _model_with_face():
    m = Model()
    s = m.active_scene
    v = [s.add_vertex(np.array([0.0, 0.0, 0.0])),
         s.add_vertex(np.array([1.0, 0.0, 0.0])),
         s.add_vertex(np.array([0.0, 1.0, 0.0]))]
    f = s.add_face_from_loop(v)
    return m, v, f


def test_make_group_inherits_tag_id():
    m, v, f = _model_with_face()
    cmd = MakeGroupCommand(m.active_context, v, [], [f], tag_id=4)
    cmd.do(m)
    assert cmd.created_instance.tag_id == 4


def test_make_group_defaults_untagged():
    m, v, f = _model_with_face()
    cmd = MakeGroupCommand(m.active_context, v, [], [f])
    cmd.do(m)
    assert cmd.created_instance.tag_id == 0


def test_tag_survives_undo_redo():
    m, v, f = _model_with_face()
    cmd = MakeGroupCommand(m.active_context, v, [], [f], tag_id=4)
    cmd.do(m)
    cmd.undo(m)
    cmd.do(m)                                  # routes to _redo, reusing the instance object
    assert cmd.created_instance.tag_id == 4


def test_make_component_inherits_tag_id():
    m, v, f = _model_with_face()
    cmd = MakeComponentCommand(m.active_context, v, [], [f], name="C", tag_id=9)
    cmd.do(m)
    assert cmd.created_instance.tag_id == 9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_make_group_tag_inherit.py -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'tag_id'`).

- [ ] **Step 3: Add `tag_id` to `MakeGroupCommand`**

In `python/pluton/commands/group_commands.py`, change `MakeGroupCommand.__init__` to accept and store `tag_id`:

```python
    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids,
                 *, is_group: bool = True, name: str | None = None, tag_id: int = 0) -> None:
        self._parent = parent_definition
        self._vids = list(vertex_ids)
        self._eids = list(edge_ids)
        self._fids = list(face_ids)
        self._is_group = is_group
        self._name = name
        self._tag_id = int(tag_id)
        self.created_instance = None
        self._captured = None  # (verts, edges, faces) descriptors for undo
```

In `do()`, the creation branch currently ends:

```python
        # 4. Create one instance in the parent.
        inst = model.new_instance(defn)
        self._parent.children.append(inst)
        self.created_instance = inst
```

Assign the tag on the created instance:

```python
        # 4. Create one instance in the parent.
        inst = model.new_instance(defn)
        inst.tag_id = self._tag_id
        self._parent.children.append(inst)
        self.created_instance = inst
```

(`_redo` reuses `self.created_instance`, which already carries `tag_id` from the first `do()` — no change needed there.)

- [ ] **Step 4: Thread `tag_id` through `MakeComponentCommand`**

In the same file, change `MakeComponentCommand.__init__`:

```python
class MakeComponentCommand(MakeGroupCommand):
    name = "Make Component"

    def __init__(self, parent_definition, vertex_ids, edge_ids, face_ids,
                 *, name: str, tag_id: int = 0) -> None:
        super().__init__(parent_definition, vertex_ids, edge_ids, face_ids,
                         is_group=False, name=name, tag_id=tag_id)
```

- [ ] **Step 5: Run tests + group regression**

Run: `.venv/Scripts/python -m pytest tests/test_make_group_tag_inherit.py -v`
Expected: PASS (4 passed)

Run: `.venv/Scripts/python -m pytest tests/ -k "group or component or make" -q`
Expected: PASS (existing group/component tests still green)

- [ ] **Step 6: Lint (hand-fix only — group_commands.py carries intentional noqa)**

Run: `.venv/Scripts/python -m ruff check python/pluton/commands/group_commands.py tests/test_make_group_tag_inherit.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add python/pluton/commands/group_commands.py tests/test_make_group_tag_inherit.py
git commit -m "$(printf 'feat(m5c): MakeGroup/MakeComponent inherit the active tag\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 7: `TagsDock`

**Files:**
- Create: `python/pluton/ui/tags_dock.py`
- Test: `tests/test_tags_dock.py`

**Interfaces:**
- Consumes: `TagLibrary` (Task 1).
- Produces: `TagsDock(library, parent=None)` with signals `active_tag_changed(int)`, `visibility_changed()`, `assign_to_selection_requested()`; methods `set_active(tag_id)`, `_rebuild()`, `_on_add()`, `_on_assign()`; property `active_tag_id`; internal `_list` (QListWidget).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tags_dock.py
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pluton.model.tag import TagLibrary
from pluton.ui.tags_dock import TagsDock


@pytest.fixture
def lib():
    return TagLibrary()


def test_dock_lists_untagged_first(qtbot, lib):
    lib.add("Walls")
    dock = TagsDock(lib)
    qtbot.addWidget(dock)
    assert dock._list.count() == 2
    assert dock._list.item(0).text() == "Untagged"


def test_checkbox_toggles_visibility_and_emits(qtbot, lib):
    walls = lib.add("Walls")
    dock = TagsDock(lib)
    qtbot.addWidget(dock)
    item = dock._list.item(1)                       # the Walls row
    with qtbot.waitSignal(dock.visibility_changed, timeout=500):
        item.setCheckState(Qt.CheckState.Unchecked)
    assert lib.is_visible(walls.id) is False


def test_selecting_row_changes_active_and_emits(qtbot, lib):
    walls = lib.add("Walls")
    dock = TagsDock(lib)
    qtbot.addWidget(dock)
    with qtbot.waitSignal(dock.active_tag_changed, timeout=500) as blocker:
        dock._list.setCurrentRow(1)
    assert dock.active_tag_id == walls.id
    assert blocker.args[0] == walls.id


def test_add_tag_grows_list(qtbot, lib):
    dock = TagsDock(lib)
    qtbot.addWidget(dock)
    n = dock._list.count()
    dock._on_add()
    assert dock._list.count() == n + 1


def test_assign_emits(qtbot, lib):
    dock = TagsDock(lib)
    qtbot.addWidget(dock)
    with qtbot.waitSignal(dock.assign_to_selection_requested, timeout=500):
        dock._on_assign()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_tags_dock.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'pluton.ui.tags_dock'`).

- [ ] **Step 3: Write the implementation**

```python
# python/pluton/ui/tags_dock.py
"""The Tags dock (M5c): a list panel for object tags + per-tag visibility."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pluton.model.tag import TagLibrary


class TagsDock(QDockWidget):
    """Tag list (checkbox = visibility, selected row = active tag) + Add/Assign buttons."""

    active_tag_changed = Signal(int)
    visibility_changed = Signal()
    assign_to_selection_requested = Signal()

    def __init__(self, library: TagLibrary, parent=None) -> None:  # noqa: ANN001
        super().__init__("Tags", parent)
        self._library = library
        self._active_id = TagLibrary.UNTAGGED_ID
        self._rebuilding = False

        container = QWidget(self)
        layout = QVBoxLayout(container)
        self._list = QListWidget(container)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self._list)
        add_btn = QPushButton("Add Tag", container)
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)
        assign_btn = QPushButton("Assign to Selection", container)
        assign_btn.clicked.connect(self._on_assign)
        layout.addWidget(assign_btn)
        self.setWidget(container)

        self._rebuild()

    def _rebuild(self) -> None:
        self._rebuilding = True
        self._list.clear()
        for tag in self._library.tags():
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            if tag.id == TagLibrary.UNTAGGED_ID:
                # Untagged: always visible — checkbox shown checked, not user-toggleable.
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if tag.visible else Qt.CheckState.Unchecked
                )
            self._list.addItem(item)
            if tag.id == self._active_id:
                self._list.setCurrentItem(item)
        self._rebuilding = False

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._rebuilding:
            return
        tid = int(item.data(Qt.ItemDataRole.UserRole))
        visible = item.checkState() == Qt.CheckState.Checked
        self._library.set_visible(tid, visible)
        self.visibility_changed.emit()

    def _on_current_changed(self, current, _previous) -> None:  # noqa: ANN001
        if self._rebuilding or current is None:
            return
        self._active_id = int(current.data(Qt.ItemDataRole.UserRole))
        self.active_tag_changed.emit(self._active_id)

    def _on_add(self) -> None:
        tag = self._library.add(f"Tag {len(self._library.tags())}")
        self._rebuild()
        self.set_active(tag.id)

    def _on_assign(self) -> None:
        self.assign_to_selection_requested.emit()

    def set_active(self, tag_id: int) -> None:
        """Select the row for `tag_id` (used to set the active tag programmatically)."""
        self._active_id = tag_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            if int(item.data(Qt.ItemDataRole.UserRole)) == tag_id:
                self._list.setCurrentItem(item)
                break

    @property
    def active_tag_id(self) -> int:
        return self._active_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_tags_dock.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Lint**

Run: `.venv/Scripts/python -m ruff check python/pluton/ui/tags_dock.py tests/test_tags_dock.py`
Expected: no errors. (Safe to `ruff --fix` these NEW files for I001; keep the `# noqa: ANN001` on `__init__`/`_on_current_changed`.)

- [ ] **Step 6: Commit**

```bash
git add python/pluton/ui/tags_dock.py tests/test_tags_dock.py
git commit -m "$(printf 'feat(m5c): TagsDock list panel (visibility checkboxes + active tag)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 8: MainWindow wiring

**Files:**
- Modify: `python/pluton/ui/main_window.py` (create + tabify the Tags dock; View ▸ Tags toggle; assign handler; active-tag handler; thread `tag_id` into make-group/component)
- Test: `tests/test_main_window_tags.py`

**Interfaces:**
- Consumes: `TagsDock` (Task 7), `TagInstancesCommand` (Task 5), `TagLibrary` (Task 1), `MakeGroupCommand`/`MakeComponentCommand` `tag_id` kwarg (Task 6).
- Produces: `MainWindow._tags_dock`, `_active_tag_id`, `_tags_dock_action`, handlers `_on_active_tag_changed`, `_on_assign_tag`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main_window_tags.py
from __future__ import annotations

import numpy as np
import pytest
from pluton.model.tag import TagLibrary
from pluton.ui.main_window import MainWindow
from pluton.ui.tags_dock import TagsDock


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_has_tags_dock(win):
    assert isinstance(win._tags_dock, TagsDock)


def test_view_menu_has_tags_toggle(win):
    assert win._tags_dock_action in win._view_menu.actions()


def test_active_tag_tracks_dock(win):
    walls = win._model.tags.add("Walls")
    win._tags_dock._rebuild()
    win._tags_dock.set_active(walls.id)
    assert win._active_tag_id == walls.id


def test_assign_tags_selected_instances(win):
    s = win._model.active_scene
    v = [s.add_vertex(np.array([0.0, 0.0, 0.0])),
         s.add_vertex(np.array([1.0, 0.0, 0.0])),
         s.add_vertex(np.array([0.0, 1.0, 0.0]))]
    f = s.add_face_from_loop(v)
    win._selection.replace(faces=[f])
    win._on_make_group()                          # groups the face; selects the new instance
    walls = win._model.tags.add("Walls")
    win._active_tag_id = walls.id
    win._on_assign_tag()
    inst_id = next(iter(win._selection.instances))
    inst = next(i for i in win._model.active_context.children if i.id == inst_id)
    assert inst.tag_id == walls.id


def test_new_group_inherits_active_tag(win):
    walls = win._model.tags.add("Walls")
    win._active_tag_id = walls.id
    s = win._model.active_scene
    v = [s.add_vertex(np.array([0.0, 0.0, 0.0])),
         s.add_vertex(np.array([1.0, 0.0, 0.0])),
         s.add_vertex(np.array([0.0, 1.0, 0.0]))]
    f = s.add_face_from_loop(v)
    win._selection.replace(faces=[f])
    win._on_make_group()
    inst_id = next(iter(win._selection.instances))
    inst = next(i for i in win._model.active_context.children if i.id == inst_id)
    assert inst.tag_id == walls.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_main_window_tags.py -v`
Expected: FAIL (`AttributeError: 'MainWindow' object has no attribute '_tags_dock'`).

- [ ] **Step 3: Add imports**

In `python/pluton/ui/main_window.py`, add near the other UI/model imports:

```python
from pluton.model.tag import TagLibrary
from pluton.ui.tags_dock import TagsDock
```

- [ ] **Step 4: Create + tabify the Tags dock**

Immediately after the Materials-dock block (the line `self._materials_dock.active_material_changed.connect(self._on_active_material_changed)`), add:

```python
        # Tags dock — tabbed with Materials on the right. Not referenced by the
        # ToolContext (tag assignment uses the existing Select tool + Selection).
        self._active_tag_id = TagLibrary.UNTAGGED_ID
        self._tags_dock = TagsDock(self._model.tags, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._tags_dock)
        self.tabifyDockWidget(self._materials_dock, self._tags_dock)
        self._tags_dock.active_tag_changed.connect(self._on_active_tag_changed)
        self._tags_dock.visibility_changed.connect(self._viewport.update)
        self._tags_dock.assign_to_selection_requested.connect(self._on_assign_tag)
```

- [ ] **Step 5: Add the View ▸ Tags toggle**

In the View-menu builder, after the Materials toggle lines:

```python
        self._materials_dock_action = self._materials_dock.toggleViewAction()
        self._view_menu.addAction(self._materials_dock_action)
```

add:

```python
        self._tags_dock_action = self._tags_dock.toggleViewAction()
        self._view_menu.addAction(self._tags_dock_action)
```

- [ ] **Step 6: Add the active-tag + assign handlers**

Next to `_on_active_material_changed`, add:

```python
    def _on_active_tag_changed(self, tag_id: int) -> None:
        self._active_tag_id = tag_id

    def _on_assign_tag(self) -> None:
        from pluton.commands.tag_commands import TagInstancesCommand

        sel = self._selection
        selected = [inst for inst in self._model.active_context.children
                    if inst.id in sel.instances]
        if not selected:
            self._status_bar.set_status("Select objects to assign a tag.")
            return
        cmd = TagInstancesCommand(selected, self._active_tag_id)
        self._command_stack.execute(cmd, self._model)
        self._viewport.update()
```

- [ ] **Step 7: Thread the active tag into make-group / make-component**

In `_on_make_group`, change the command construction:

```python
        cmd = MakeGroupCommand(self._model.active_context, vertex_ids, edge_ids, face_ids,
                               tag_id=self._active_tag_id)
```

In `_on_make_component`, change it to:

```python
        cmd = MakeComponentCommand(self._model.active_context, vertex_ids, edge_ids, face_ids,
                                   name=name, tag_id=self._active_tag_id)
```

- [ ] **Step 8: Run tests + full suite**

Run: `.venv/Scripts/python -m pytest tests/test_main_window_tags.py -v`
Expected: PASS (5 passed)

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS (full suite green)

- [ ] **Step 9: Lint (hand-fix only — main_window.py carries intentional noqa; do NOT `ruff --fix` it)**

Run: `.venv/Scripts/python -m ruff check python/pluton/ui/main_window.py tests/test_main_window_tags.py`
Expected: no errors. (Safe to `ruff --fix` ONLY the new test file for I001.)

- [ ] **Step 10: Commit**

```bash
git add python/pluton/ui/main_window.py tests/test_main_window_tags.py
git commit -m "$(printf 'feat(m5c): wire Tags dock into MainWindow (tabify, View toggle, assign, inherit)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 9: Full regression + manual visual pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS — 633 (v0.1.6) + the M5c additions, all green.

- [ ] **Step 2: Run the C++ tests (unchanged kernel)**

Run: `ctest --test-dir build/cp313-cp313-win_amd64 --output-on-failure`
Expected: 76/76 passed.

- [ ] **Step 3: Ruff over the whole tree (report only — do NOT `--fix`)**

Run: `.venv/Scripts/python -m ruff check python/ tests/`
Expected: only pre-existing `# noqa: ANN001` debt (issue #48) on edited files + the intentional `# noqa` on the new command/dock files — no NEW errors. Hand-fix anything new.

- [ ] **Step 4: Manual visual pass — launch the app**

Run: `.venv/Scripts/python -m pluton`

Verify (the GL/UX gate the unit tests can't cover):
- The **Tags** dock appears, tabbed with Materials; it lists **Untagged**.
- Draw a face, **Make Group** (G) → the object exists. Select it.
- **Add Tag** in the dock (e.g. "Walls"), select it as active, **Assign to Selection** → the object is now on "Walls".
- **Uncheck** "Walls" → the object disappears; it's no longer pickable. **Re-check** → it reappears.
- Enter a group (double-click) whose tag is hidden → it stays visible while you're editing inside it.
- With "Walls" active, make a **new** group → it inherits the "Walls" tag (hiding Walls hides it too).
- **Ctrl+Z / Ctrl+Y** undo/redo a tag assignment.
- Close the Tags dock, reopen via **View ▸ Tags**.
- **Untagged** can't be unchecked.
- A model with no hidden tags looks identical to v0.1.6 (no regression).

- [ ] **Step 5: Report results to the user and STOP for confirmation**

Do not proceed to release until the user confirms the visual pass looks right.

---

### Task 10: Release v0.1.7-m5c

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` (0.1.6 → 0.1.7)
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M5c shipped; mark M5 complete)

This task requires explicit user authorization for each outward-facing step (push, tag). Do NOT push/tag without it.

- [ ] **Step 1: Bump the version in all three files**

- `pyproject.toml`: `version = "0.1.6"` → `version = "0.1.7"`
- `CMakeLists.txt`: `VERSION 0.1.6` → `VERSION 0.1.7`
- `cpp/src/version.cpp`: `return "0.1.6";` → `return "0.1.7";`

- [ ] **Step 2: Rebuild so `_core.version()` reports 0.1.7**

Run: `.venv/Scripts/python -m pip install -e . --no-build-isolation`
Then: `.venv/Scripts/python -c "import pluton; print(pluton.__version__)"`
Expected: `0.1.7`

- [ ] **Step 3: Annotate the master roadmap**

In `docs/2026-05-16-pluton-design.md`, update the M5 line: mark **M5c ✅ *(shipped v0.1.7)*** — Layers/Tags (instances-only object tags + per-tag visibility). Since M5a/M5b/M5c are all shipped, note that **M5 is complete**.

- [ ] **Step 4: Final full suite + commit the release**

Run: `.venv/Scripts/python -m pytest tests/ -q` → green.

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "$(printf 'release: v0.1.7 (M5c — Layers/Tags)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

- [ ] **Step 5: (AUTH REQUIRED) Push, tag, watch CI**

After the user authorizes:

```bash
git push origin main
git tag -a v0.1.7-m5c -m "M5c — Layers/Tags"
git push origin v0.1.7-m5c
gh run watch
```
Expected: CI SUCCESS on ubuntu-24.04 + windows-2022.

- [ ] **Step 6: File deferred-feature follow-up issues**

After release, file issues for: loose-geometry (per-edge/face) tagging; tag rename/delete/reorder; per-tag color + "Color by Tag" view mode; tag folders/nesting; context-menu / Entity-Info assignment. (Persistence is already covered by M6.)

---

## Notes for the executor

- **Suggested models (subagent-driven):** Tasks 1, 5 = haiku (pure, complete code = transcription). Tasks 2, 3, 4, 6, 7, 8 = sonnet (model-graph edits / regression-critical renderer / Qt UI / multi-file wiring). Reviewers = sonnet floor; final whole-branch review = opus. Task 9/10 = controller-coordinated.
- **Task 4 is the regression-sensitive one.** Acceptance bar: with no tags hidden, `traverse_visible` yields the same sequence as `traverse`, so the render is byte-identical. The renderer GL isn't headlessly testable — verify by net-diff inspection (Step 4) + the Task 9 visual pass. The logic itself is unit-tested in Task 3.
- **Never run broad `ruff --fix`** on edited files that carry intentional `# noqa: ANN001` (issue #48): `model.py`, `instance.py`, `scene_renderer.py`, `group_commands.py`, `tag_commands.py`, `tags_dock.py`, `main_window.py`. Hand-fix lint. New-file-only `--fix` (for I001) is acceptable.
- **Layering:** `tag.py` stays import-free of GL/Qt; the `_UNTAGGED_ID = 0` literals in `instance.py`/`tag_commands.py` are deliberate (avoid importing the library for one constant), mirroring M5b's sentinel pattern.
- **No C++ changes** anywhere in Tasks 1–9. Version files only in Task 10. **No tool / ToolContext / shader changes.**
```

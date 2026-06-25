# M6a — Native `.pluton` File I/O — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship native `.pluton` save / open / new — a full round-trip of the in-memory document (scene graph, materials, tags, units, camera) — with standard File-menu UX and unsaved-changes guarding.

**Architecture:** A new pure `pluton/io/` package owns the format: a codec (`document_codec.py`, dict↔objects, no Qt/GL/zip) wrapped by a thin zip+manifest layer (`pluton_file.py`). The model classes stay format-agnostic; serialization reaches in via their existing public APIs. `MainWindow` gains a File menu, a `DocumentController` (path/dirty/title), one `CommandStack` change-listener for the dirty flag, and an in-place model-swap for atomic load.

**Tech Stack:** Python 3.13, `zipfile` + `json` (stdlib), numpy, PySide6 (Qt) for the menu/dialogs, pytest + pytest-qt.

**Spec:** `docs/2026-06-25-M6a-fileio-design.md`

## Global Constraints

- **Python interpreter:** use `.venv/Scripts/python` explicitly for all tests/pip (bash) — bare `python`/`pytest` resolve to a drifting editable install.
- **Purely additive:** no C++ kernel, shader, tool/ToolContext, renderer, or existing-command **logic** changes. The only edits to shared classes are additive methods/signals.
- **Git:** stage specific files only (never `git add -A`/`.`); SSH-signed commits; never `--no-verify` / `--amend` / `--no-gpg-sign`. Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Work on `main`.
- **Lint:** preserve the issue-#48 `# noqa: ANN001` convention; never run broad `ruff --fix` on files carrying intentional noqa. New-file-only `ruff --fix` for import sorting (I001) is fine.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) are touched **only** in Task 12.
- **Regression bar:** the full suite (674 pytest + 76/76 ctest, pre-M6a) stays green; M6a only adds tests.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.
- **Schema:** `CURRENT_SCHEMA = 1`. JSON written compact (`separators=(",", ":")`).

---

## File Structure

**New files**
- `python/pluton/io/__init__.py` — re-exports `save_document`, `load_document`, error types, `SCHEMA_VERSION`.
- `python/pluton/io/errors.py` — `PlutonIOError` / `PlutonFormatError` / `PlutonVersionError`.
- `python/pluton/io/document_codec.py` — pure dict↔objects: geometry, model graph, `CameraState`, `LoadedDocument`, `document_to_dict`/`document_from_dict`.
- `python/pluton/io/pluton_file.py` — zip + manifest + version gate + atomic write.
- `python/pluton/ui/document_controller.py` — `DocumentController` (path/dirty/title).
- Tests (flat, matching repo convention): `tests/test_io_errors.py`, `tests/test_document_codec.py`, `tests/test_pluton_file.py`, `tests/test_document_controller.py`, `tests/test_main_window_fileio.py`.

**Modified files**
- `python/pluton/model/material.py` — `MaterialLibrary.to_records`/`from_records`/`next_id`.
- `python/pluton/model/tag.py` — `TagLibrary.to_records`/`from_records`/`next_id`.
- `python/pluton/units.py` — `units_to_dict`/`units_from_dict`.
- `python/pluton/document.py` — `DocumentSettings.set_units`.
- `python/pluton/model/model.py` — `Model.load_from`.
- `python/pluton/commands/command_stack.py` — `add_change_listener` + `_fire_change` + `clear`.
- `python/pluton/ui/materials_dock.py` — `library_changed` signal + `set_library`.
- `python/pluton/ui/tags_dock.py` — `library_changed` signal + `set_library`.
- `python/pluton/ui/main_window.py` — File menu, controller wiring, dirty, guard, Save/Open/New, adopt, `closeEvent`, Ctrl+N repurpose, ClearScene→Edit menu.

**Dependency order:** 1 → 12 is a valid topological order (each task only consumes earlier tasks).

---

## Task 1: IO error hierarchy

**Files:**
- Create: `python/pluton/io/__init__.py` (empty for now — re-exports added in Task 6)
- Create: `python/pluton/io/errors.py`
- Test: `tests/test_io_errors.py`

**Interfaces:**
- Produces: `PlutonIOError(Exception)`, `PlutonFormatError(PlutonIOError)`, `PlutonVersionError(PlutonIOError)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_io_errors.py
from pluton.io.errors import PlutonFormatError, PlutonIOError, PlutonVersionError


def test_subclass_hierarchy():
    assert issubclass(PlutonFormatError, PlutonIOError)
    assert issubclass(PlutonVersionError, PlutonIOError)


def test_raisable_with_message():
    for exc in (PlutonIOError, PlutonFormatError, PlutonVersionError):
        try:
            raise exc("boom")
        except PlutonIOError as e:
            assert "boom" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_io_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.io'`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/io/__init__.py
"""Native .pluton file I/O (M6a). Re-exports added in pluton_file (Task 6)."""
```

```python
# python/pluton/io/errors.py
"""Exception hierarchy for .pluton load/save.

A PlutonIOError means 'this file is bad' (we own the message). OS-level errors
(permission, disk full) are left to propagate as OSError so the UI can tell the
two apart.
"""

from __future__ import annotations


class PlutonIOError(Exception):
    """Base for all .pluton load/save errors that mean 'this file is bad'."""


class PlutonFormatError(PlutonIOError):
    """Not a valid .pluton document: bad zip, missing entries, malformed structure."""


class PlutonVersionError(PlutonIOError):
    """The file's schema_version is newer than this build supports."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_io_errors.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/__init__.py python/pluton/io/errors.py tests/test_io_errors.py && git commit -m "feat(io): PlutonIOError hierarchy for M6a file I/O"
```

---

## Task 2: Library + value serialization helpers

**Files:**
- Modify: `python/pluton/model/material.py`
- Modify: `python/pluton/model/tag.py`
- Modify: `python/pluton/units.py`
- Modify: `python/pluton/document.py`
- Test: `tests/test_io_value_helpers.py`

**Interfaces:**
- Produces:
  - `MaterialLibrary.next_id -> int` (property); `MaterialLibrary.to_records() -> list[dict]`; `MaterialLibrary.from_records(records: list[dict], next_id: int) -> MaterialLibrary` (classmethod).
  - `TagLibrary.next_id -> int`; `TagLibrary.to_records() -> list[dict]`; `TagLibrary.from_records(records, next_id) -> TagLibrary`.
  - `units_to_dict(units: Units) -> dict`; `units_from_dict(data: dict) -> Units` (module functions in `pluton.units`).
  - `DocumentSettings.set_units(units: Units) -> None`.
- Record shapes: material `{"id":int,"name":str,"color":[r,g,b]}`; tag `{"id":int,"name":str,"visible":bool}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_io_value_helpers.py
from pluton.document import DocumentSettings
from pluton.model.material import MaterialLibrary
from pluton.model.tag import TagLibrary
from pluton.units import UnitSystem, Units, units_from_dict, units_to_dict


def test_material_library_roundtrip_preserves_customs_and_next_id():
    lib = MaterialLibrary()
    custom = lib.add_custom("My Teal", (0.1, 0.6, 0.6))
    records, nid = lib.to_records(), lib.next_id
    rebuilt = MaterialLibrary.from_records(records, nid)
    assert [(m.id, m.name, m.color) for m in rebuilt.materials()] == \
           [(m.id, m.name, m.color) for m in lib.materials()]
    assert rebuilt.next_id == nid
    assert rebuilt.get(custom.id).name == "My Teal"
    # Default sentinel still resolves after rebuild.
    assert rebuilt.get(MaterialLibrary.DEFAULT_ID).name == "Default"


def test_tag_library_roundtrip_preserves_visibility_and_next_id():
    lib = TagLibrary()
    walls = lib.add("Walls")
    furn = lib.add("Furniture")
    lib.set_visible(furn.id, False)
    rebuilt = TagLibrary.from_records(lib.to_records(), lib.next_id)
    assert [(t.id, t.name, t.visible) for t in rebuilt.tags()] == \
           [(t.id, t.name, t.visible) for t in lib.tags()]
    assert rebuilt.next_id == lib.next_id
    assert rebuilt.is_visible(walls.id) is True
    assert rebuilt.is_visible(furn.id) is False
    # Untagged sentinel survives.
    assert rebuilt.get(TagLibrary.UNTAGGED_ID).name == "Untagged"


def test_units_roundtrip_imperial():
    u = Units(system=UnitSystem.IMPERIAL, metric_unit="cm",
              metric_precision=2, imperial_denominator=32)
    back = units_from_dict(units_to_dict(u))
    assert back == u


def test_document_settings_set_units():
    doc = DocumentSettings()
    u = Units(system=UnitSystem.IMPERIAL, imperial_denominator=8)
    doc.set_units(u)
    assert doc.units == u
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_io_value_helpers.py -v`
Expected: FAIL — `AttributeError: type object 'MaterialLibrary' has no attribute 'from_records'` (and `ImportError` for `units_to_dict`).

- [ ] **Step 3: Write minimal implementation**

In `python/pluton/model/material.py`, add to class `MaterialLibrary`:

```python
    @property
    def next_id(self) -> int:
        return self._next_id

    def to_records(self) -> list[dict]:
        """Serialize all materials in display order (Default first)."""
        return [{"id": m.id, "name": m.name, "color": list(m.color)} for m in self.materials()]

    @classmethod
    def from_records(cls, records: list[dict], next_id: int) -> "MaterialLibrary":
        """Rebuild a library authoritatively from saved records (no auto-seed)."""
        lib = cls()  # seeds default + builtins, then we overwrite
        lib._materials = {}
        lib._order = []
        for r in records:
            color = r["color"]
            mat = Material(int(r["id"]), str(r["name"]),
                           (float(color[0]), float(color[1]), float(color[2])))
            lib._materials[mat.id] = mat
            lib._order.append(mat.id)
        lib._default = lib._materials.get(cls.DEFAULT_ID, lib._default)
        lib._next_id = int(next_id)
        return lib
```

In `python/pluton/model/tag.py`, add to class `TagLibrary`:

```python
    @property
    def next_id(self) -> int:
        return self._next_id

    def to_records(self) -> list[dict]:
        """Serialize all tags in display order (Untagged first)."""
        return [{"id": t.id, "name": t.name, "visible": t.visible} for t in self.tags()]

    @classmethod
    def from_records(cls, records: list[dict], next_id: int) -> "TagLibrary":
        """Rebuild a library authoritatively from saved records (no auto-seed)."""
        lib = cls()  # seeds Untagged, then we overwrite
        lib._tags = {}
        lib._order = []
        for r in records:
            tag = Tag(int(r["id"]), str(r["name"]), bool(r["visible"]))
            lib._tags[tag.id] = tag
            lib._order.append(tag.id)
        lib._untagged = lib._tags.get(cls.UNTAGGED_ID, lib._untagged)
        lib._next_id = int(next_id)
        return lib
```

In `python/pluton/units.py`, add at module level (after the `Units` dataclass):

```python
def units_to_dict(units: Units) -> dict:
    return {
        "system": units.system.value,
        "metric_unit": units.metric_unit,
        "metric_precision": units.metric_precision,
        "imperial_denominator": units.imperial_denominator,
    }


def units_from_dict(data: dict) -> Units:
    return Units(
        system=UnitSystem(data["system"]),
        metric_unit=str(data["metric_unit"]),
        metric_precision=int(data["metric_precision"]),
        imperial_denominator=int(data["imperial_denominator"]),
    )
```

In `python/pluton/document.py`, add to class `DocumentSettings`:

```python
    def set_units(self, units: Units) -> None:
        """Replace the active units wholesale (used by file load / New)."""
        self._units = units
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_io_value_helpers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/material.py python/pluton/model/tag.py python/pluton/units.py python/pluton/document.py tests/test_io_value_helpers.py && git commit -m "feat(io): serialization helpers for libraries, units, document settings"
```

---

## Task 3: Geometry codec (per-definition)

**Files:**
- Create: `python/pluton/io/document_codec.py`
- Test: `tests/test_document_codec.py`

**Interfaces:**
- Produces:
  - `geometry_to_dict(scene: Scene) -> dict` → `{"vertices":[[x,y,z]...], "edges":[[i,j]...], "faces":[[i,j,k...]...], "face_materials":{"<face_index>":material_id}}` (indices into `vertices`; painted-only, Default omitted).
  - `geometry_from_dict(scene: Scene, data: dict) -> None` — replays into an **empty** `scene`; raises `PlutonFormatError` on out-of-range indices.
- Consumes: `pluton.io.errors.PlutonFormatError` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_document_codec.py
import numpy as np
import pytest

from pluton.io.document_codec import geometry_from_dict, geometry_to_dict
from pluton.io.errors import PlutonFormatError
from pluton.scene.scene import Scene


def _square(scene: Scene) -> list[int]:
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)
    return vids


def test_geometry_roundtrip_painted_face():
    src = Scene()
    _square(src)
    fid = next(iter(src.faces_iter())).id
    src.set_face_material(fid, 5)

    data = geometry_to_dict(src)
    assert len(data["vertices"]) == 4
    assert len(data["faces"]) == 1
    assert data["face_materials"] == {"0": 5}

    dst = Scene()
    geometry_from_dict(dst, data)
    assert len(list(dst.vertices_iter())) == 4
    assert len(list(dst.faces_iter())) == 1
    new_fid = next(iter(dst.faces_iter())).id
    assert dst.face_material(new_fid) == 5


def test_geometry_roundtrip_compacts_id_gaps():
    src = Scene()
    vids = _square(src)
    # Add a loose vertex, then delete it -> leaves an id gap in the kernel.
    loose = src.add_vertex(np.array((9, 9, 9), dtype=np.float32))
    src.remove_vertex(loose)

    data = geometry_to_dict(src)
    assert len(data["vertices"]) == 4  # gap compacted away

    dst = Scene()
    geometry_from_dict(dst, data)
    got = sorted(tuple(round(float(c), 3) for c in v.position) for v in dst.vertices_iter())
    want = sorted(tuple(round(float(c), 3) for c in src.vertex(v).position) for v in vids)
    assert got == want


def test_geometry_from_dict_rejects_bad_index():
    dst = Scene()
    bad = {"vertices": [[0, 0, 0]], "edges": [[0, 7]], "faces": [], "face_materials": {}}
    with pytest.raises(PlutonFormatError):
        geometry_from_dict(dst, bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -v`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` for `geometry_to_dict`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/io/document_codec.py
"""Pure dict <-> document codec for the native .pluton format (M6a).

No Qt, GL, zip, or filesystem here — just dict <-> in-memory objects, so the
whole round-trip is headlessly unit-testable. Geometry is index-based (edges and
faces reference a vertex's POSITION in `vertices[]`, not its kernel id), which
compacts id gaps and lets load replay add_vertex/add_edge/add_face_from_loop.
"""

from __future__ import annotations

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.scene.scene import Scene

_DEFAULT_MATERIAL_ID = 0  # mirrors MaterialLibrary.DEFAULT_ID


def geometry_to_dict(scene: Scene) -> dict:
    """Serialize a Scene's geometry with index-based edges/faces."""
    idmap: dict[int, int] = {}
    vertices: list[list[float]] = []
    for v in scene.vertices_iter():
        idmap[v.id] = len(vertices)
        vertices.append([float(v.position[0]), float(v.position[1]), float(v.position[2])])

    edges = [[idmap[e.v1_id], idmap[e.v2_id]] for e in scene.edges_iter()]

    faces: list[list[int]] = []
    face_materials: dict[str, int] = {}
    for face_index, f in enumerate(scene.faces_iter()):
        faces.append([idmap[vid] for vid in f.loop_vertex_ids])
        mat = scene.face_material(f.id)
        if mat != _DEFAULT_MATERIAL_ID:
            face_materials[str(face_index)] = int(mat)

    return {"vertices": vertices, "edges": edges, "faces": faces,
            "face_materials": face_materials}


def geometry_from_dict(scene: Scene, data: dict) -> None:
    """Replay geometry into an empty `scene`. Raises PlutonFormatError on bad indices."""
    new_vids: list[int] = []
    for pos in data["vertices"]:
        new_vids.append(scene.add_vertex(np.asarray(pos, dtype=np.float32)))
    n = len(new_vids)

    def _vid(i: int) -> int:
        if not (0 <= i < n):
            raise PlutonFormatError(f"vertex index {i} out of range (0..{n - 1})")
        return new_vids[i]

    for a, b in data["edges"]:
        scene.add_edge(_vid(int(a)), _vid(int(b)))

    new_fids: list[int] = []
    for loop in data["faces"]:
        new_fids.append(scene.add_face_from_loop([_vid(int(i)) for i in loop]))

    for face_index_str, mat in data.get("face_materials", {}).items():
        fi = int(face_index_str)
        if not (0 <= fi < len(new_fids)):
            raise PlutonFormatError(f"face index {fi} out of range (0..{len(new_fids) - 1})")
        scene.set_face_material(new_fids[fi], int(mat))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/document_codec.py tests/test_document_codec.py && git commit -m "feat(io): index-based geometry codec (compacts id gaps)"
```

---

## Task 4: Model graph codec

**Files:**
- Modify: `python/pluton/io/document_codec.py`
- Test: `tests/test_document_codec.py` (append)

**Interfaces:**
- Produces:
  - `model_to_dict(model: Model) -> dict` → `{"next_def_id":int, "next_inst_id":int, "root_id":int, "definitions":[{"id","name","is_group","geometry","children":[{"id","definition_id","transform":[16 floats],"tag_id"}]}]}`. Definitions reachable from root are emitted once each (sharing preserved).
  - `model_from_dict(data: dict) -> Model` — two-pass; restores counters/root; raises `PlutonFormatError` on dangling refs / bad transform.
- Consumes: `geometry_to_dict`/`geometry_from_dict` (Task 3); `pluton.model.model.Model`, `pluton.model.definition.Definition`, `pluton.model.instance.Instance`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_document_codec.py  (append)
from pluton.io.document_codec import model_from_dict, model_to_dict
from pluton.model.model import Model


def _add_box(scene):
    import numpy as np
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)


def test_model_roundtrip_shared_component_is_one_definition_and_shared():
    model = Model()
    comp = model.new_definition("Chair", is_group=False)
    _add_box(comp.mesh)
    i1 = model.new_instance(comp)
    i2 = model.new_instance(comp)
    model.root.children.extend([i1, i2])

    data = model_to_dict(model)
    chair_records = [d for d in data["definitions"] if d["name"] == "Chair"]
    assert len(chair_records) == 1  # emitted once despite two instances

    loaded = model_from_dict(data)
    kids = loaded.root.children
    assert len(kids) == 2
    assert kids[0].definition is kids[1].definition  # sharing preserved (identity)


def test_model_roundtrip_restores_counters_and_tag_ids():
    model = Model()
    g = model.new_definition("Grp", is_group=True)
    inst = model.new_instance(g)
    inst.tag_id = 7
    model.root.children.append(inst)

    loaded = model_from_dict(model_to_dict(model))
    assert loaded._next_def_id == model._next_def_id
    assert loaded._next_inst_id == model._next_inst_id
    assert loaded.root.children[0].tag_id == 7


def test_model_from_dict_rejects_dangling_definition_ref():
    import pytest
    from pluton.io.errors import PlutonFormatError
    data = {
        "next_def_id": 2, "next_inst_id": 1, "root_id": 0,
        "definitions": [{
            "id": 0, "name": "Model", "is_group": False,
            "geometry": {"vertices": [], "edges": [], "faces": [], "face_materials": {}},
            "children": [{"id": 0, "definition_id": 99,
                          "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                          "tag_id": 0}],
        }],
    }
    with pytest.raises(PlutonFormatError):
        model_from_dict(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -k model -v`
Expected: FAIL — `ImportError: cannot import name 'model_to_dict'`.

- [ ] **Step 3: Write minimal implementation**

Append to `python/pluton/io/document_codec.py` (and add the imports at the top):

```python
# add to the imports block at the top of the file:
from pluton.model.definition import Definition
from pluton.model.instance import Instance
from pluton.model.model import Model
```

```python
def model_to_dict(model: Model) -> dict:
    """Serialize the scene graph. Definitions reachable from root are emitted once."""
    defs_by_id: dict[int, Definition] = {}
    stack = [model.root]
    while stack:
        d = stack.pop()
        if d.id in defs_by_id:
            continue
        defs_by_id[d.id] = d
        for inst in d.children:
            stack.append(inst.definition)

    definitions = []
    for d in defs_by_id.values():
        definitions.append({
            "id": d.id,
            "name": d.name,
            "is_group": d.is_group,
            "geometry": geometry_to_dict(d.mesh),
            "children": [
                {"id": inst.id,
                 "definition_id": inst.definition.id,
                 "transform": [float(x) for x in inst.transform.flatten()],
                 "tag_id": int(inst.tag_id)}
                for inst in d.children
            ],
        })

    return {
        "next_def_id": model._next_def_id,
        "next_inst_id": model._next_inst_id,
        "root_id": model.root.id,
        "definitions": definitions,
    }


def model_from_dict(data: dict) -> Model:
    """Rebuild a Model (two-pass: skeleton, then geometry + children)."""
    model = Model()  # throwaway root/libraries get replaced below

    # Pass 1: empty definitions, keyed by id.
    defs_by_id: dict[int, Definition] = {}
    for rec in data["definitions"]:
        d = Definition(int(rec["id"]), str(rec["name"]), bool(rec["is_group"]))
        defs_by_id[d.id] = d

    # Pass 2: geometry + child instances.
    for rec in data["definitions"]:
        d = defs_by_id[rec["id"]]
        geometry_from_dict(d.mesh, rec["geometry"])
        for crec in rec["children"]:
            def_id = int(crec["definition_id"])
            if def_id not in defs_by_id:
                raise PlutonFormatError(f"child references unknown definition {def_id}")
            transform = crec["transform"]
            if len(transform) != 16:
                raise PlutonFormatError(f"transform must have 16 numbers, got {len(transform)}")
            inst = Instance(int(crec["id"]), defs_by_id[def_id],
                            np.asarray(transform, dtype=np.float64).reshape(4, 4))
            inst.tag_id = int(crec["tag_id"])
            d.children.append(inst)
            inst.definition.instances.append(inst)

    root_id = int(data["root_id"])
    if root_id not in defs_by_id:
        raise PlutonFormatError(f"root_id {root_id} not found among definitions")
    model.root = defs_by_id[root_id]
    model.active_path = []
    model._next_def_id = int(data["next_def_id"])
    model._next_inst_id = int(data["next_inst_id"])
    return model
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -v`
Expected: PASS (6 passed — Task 3 + Task 4).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/document_codec.py tests/test_document_codec.py && git commit -m "feat(io): model-graph codec (two-pass, preserves component sharing)"
```

---

## Task 5: Document codec (camera + units + top level)

**Files:**
- Modify: `python/pluton/io/document_codec.py`
- Test: `tests/test_document_codec.py` (append)

**Interfaces:**
- Produces:
  - `CameraState` (frozen dataclass: `position`, `target`, `up` as 3-tuples, `fov_y_deg`) with `from_camera(cam)`, `to_dict()`, `from_dict(d)`, `apply_to(cam)`.
  - `LoadedDocument(NamedTuple)`: `model: Model`, `camera_state: CameraState`, `units: Units`.
  - `document_to_dict(model, camera, doc) -> dict` → `{"units","camera","materials":{"next_id","items"},"tags":{"next_id","items"},"model"}`.
  - `document_from_dict(data) -> LoadedDocument` — wraps structural `KeyError`/`TypeError`/`ValueError` as `PlutonFormatError`.
- Consumes: `model_to_dict`/`model_from_dict` (Task 4); `MaterialLibrary`/`TagLibrary` `to_records`/`from_records` and `units_to_dict`/`units_from_dict` (Task 2); `pluton.viewport.camera.Camera`, `pluton.document.DocumentSettings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_document_codec.py  (append)
from pluton.document import DocumentSettings
from pluton.io.document_codec import (
    CameraState,
    document_from_dict,
    document_to_dict,
)
from pluton.units import UnitSystem, Units
from pluton.viewport.camera import Camera


def test_document_roundtrip_camera_units_materials_tags():
    model = Model()
    _add_box(model.root.mesh)
    fid = next(iter(model.root.mesh.faces_iter())).id
    teal = model.materials.add_custom("Teal", (0.1, 0.6, 0.6))
    model.root.mesh.set_face_material(fid, teal.id)
    walls = model.tags.add("Walls")
    model.tags.set_visible(walls.id, False)

    cam = Camera()
    cam.position = np.array([3, -4, 5], dtype=np.float32)
    doc = DocumentSettings()
    doc.set_units(Units(system=UnitSystem.IMPERIAL, imperial_denominator=8))

    data = document_to_dict(model, cam, doc)
    loaded = document_from_dict(data)

    assert loaded.units.system is UnitSystem.IMPERIAL
    assert loaded.units.imperial_denominator == 8
    assert tuple(round(x, 3) for x in loaded.camera_state.position) == (3.0, -4.0, 5.0)
    assert loaded.model.materials.get(teal.id).name == "Teal"
    assert loaded.model.tags.is_visible(walls.id) is False
    new_fid = next(iter(loaded.model.root.mesh.faces_iter())).id
    assert loaded.model.root.mesh.face_material(new_fid) == teal.id


def test_camera_state_apply_to_roundtrip():
    cam = Camera()
    cam.position = np.array([1, 2, 3], dtype=np.float32)
    cam.fov_y_deg = 33.0
    state = CameraState.from_dict(CameraState.from_camera(cam).to_dict())
    target = Camera()
    state.apply_to(target)
    assert tuple(round(float(x), 3) for x in target.position) == (1.0, 2.0, 3.0)
    assert round(target.fov_y_deg, 3) == 33.0


def test_document_from_dict_wraps_structural_errors():
    import pytest
    from pluton.io.errors import PlutonFormatError
    with pytest.raises(PlutonFormatError):
        document_from_dict({"model": {}})  # missing keys everywhere
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -k "document or camera_state" -v`
Expected: FAIL — `ImportError: cannot import name 'document_to_dict'`.

- [ ] **Step 3: Write minimal implementation**

Append to `python/pluton/io/document_codec.py` (add imports at top):

```python
# add to the imports block:
from dataclasses import dataclass
from typing import NamedTuple

from pluton.model.material import MaterialLibrary
from pluton.model.tag import TagLibrary
from pluton.units import Units, units_from_dict, units_to_dict
```

```python
@dataclass(frozen=True)
class CameraState:
    position: tuple
    target: tuple
    up: tuple
    fov_y_deg: float

    @classmethod
    def from_camera(cls, cam) -> "CameraState":  # noqa: ANN001
        return cls(
            position=tuple(float(x) for x in cam.position),
            target=tuple(float(x) for x in cam.target),
            up=tuple(float(x) for x in cam.up),
            fov_y_deg=float(cam.fov_y_deg),
        )

    def to_dict(self) -> dict:
        return {"position": list(self.position), "target": list(self.target),
                "up": list(self.up), "fov_y_deg": self.fov_y_deg}

    @classmethod
    def from_dict(cls, d: dict) -> "CameraState":
        return cls(
            position=tuple(float(x) for x in d["position"]),
            target=tuple(float(x) for x in d["target"]),
            up=tuple(float(x) for x in d["up"]),
            fov_y_deg=float(d["fov_y_deg"]),
        )

    def apply_to(self, cam) -> None:  # noqa: ANN001
        cam.position = np.array(self.position, dtype=np.float32)
        cam.target = np.array(self.target, dtype=np.float32)
        cam.up = np.array(self.up, dtype=np.float32)
        cam.fov_y_deg = float(self.fov_y_deg)


class LoadedDocument(NamedTuple):
    model: Model
    camera_state: CameraState
    units: Units


def document_to_dict(model: Model, camera, doc) -> dict:  # noqa: ANN001
    return {
        "units": units_to_dict(doc.units),
        "camera": CameraState.from_camera(camera).to_dict(),
        "materials": {"next_id": model.materials.next_id,
                      "items": model.materials.to_records()},
        "tags": {"next_id": model.tags.next_id, "items": model.tags.to_records()},
        "model": model_to_dict(model),
    }


def document_from_dict(data: dict) -> LoadedDocument:
    try:
        model = model_from_dict(data["model"])
        model.materials = MaterialLibrary.from_records(
            data["materials"]["items"], data["materials"]["next_id"])
        model.tags = TagLibrary.from_records(
            data["tags"]["items"], data["tags"]["next_id"])
        camera_state = CameraState.from_dict(data["camera"])
        units = units_from_dict(data["units"])
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise PlutonFormatError(f"malformed document: {e}") from e
    return LoadedDocument(model=model, camera_state=camera_state, units=units)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/document_codec.py tests/test_document_codec.py && git commit -m "feat(io): top-level document codec (camera, units, libraries)"
```

---

## Task 6: Zip file layer + version gate + atomic save

**Files:**
- Create: `python/pluton/io/pluton_file.py`
- Modify: `python/pluton/io/__init__.py`
- Test: `tests/test_pluton_file.py`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION = 1`.
  - `save_document(path, model, camera, doc) -> None` — atomic (temp + `os.replace`).
  - `load_document(path) -> LoadedDocument` — manifest gate + corruption → typed errors.
  - `pluton.io` re-exports: `save_document`, `load_document`, `SCHEMA_VERSION`, `PlutonIOError`, `PlutonFormatError`, `PlutonVersionError`.
- Consumes: `document_to_dict`/`document_from_dict` (Task 5); `pluton._core.version`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pluton_file.py
import json
import zipfile

import numpy as np
import pytest

from pluton.document import DocumentSettings
from pluton.io import (
    PlutonFormatError,
    PlutonVersionError,
    load_document,
    save_document,
)
from pluton.model.model import Model
from pluton.viewport.camera import Camera


def _model_with_box():
    model = Model()
    vids = [model.root.mesh.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    model.root.mesh.add_face_from_loop(vids)
    return model


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "house.pluton"
    save_document(path, _model_with_box(), Camera(), DocumentSettings())
    loaded = load_document(path)
    assert len(list(loaded.model.root.mesh.faces_iter())) == 1


def test_load_rejects_newer_schema(tmp_path):
    path = tmp_path / "future.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "pluton", "schema_version": 999}))
        zf.writestr("document.json", "{}")
    with pytest.raises(PlutonVersionError):
        load_document(path)


def test_load_rejects_foreign_format(tmp_path):
    path = tmp_path / "alien.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "sketchup", "schema_version": 1}))
        zf.writestr("document.json", "{}")
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_load_rejects_non_zip(tmp_path):
    path = tmp_path / "garbage.pluton"
    path.write_text("not a zip at all")
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_load_rejects_missing_document_entry(tmp_path):
    path = tmp_path / "incomplete.pluton"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json",
                    json.dumps({"format": "pluton", "schema_version": 1}))
    with pytest.raises(PlutonFormatError):
        load_document(path)


def test_save_is_atomic_old_file_survives_failure(tmp_path, monkeypatch):
    path = tmp_path / "keep.pluton"
    save_document(path, _model_with_box(), Camera(), DocumentSettings())
    original = path.read_bytes()

    import pluton.io.pluton_file as pf
    monkeypatch.setattr(pf, "document_to_dict",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        save_document(path, _model_with_box(), Camera(), DocumentSettings())
    assert path.read_bytes() == original  # untouched
    assert not (tmp_path / "keep.pluton.tmp").exists()  # temp cleaned up
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_pluton_file.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_document' from 'pluton.io'`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/io/pluton_file.py
"""Zip container + manifest version gate for the native .pluton format (M6a).

The only part of pluton.io that touches the filesystem. A .pluton file is a zip
holding manifest.json (the version gate) + document.json (the codec payload).
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from pluton._core import version as _core_version
from pluton.io.document_codec import (
    LoadedDocument,
    document_from_dict,
    document_to_dict,
)
from pluton.io.errors import PlutonFormatError, PlutonVersionError

SCHEMA_VERSION = 1
_MANIFEST = "manifest.json"
_DOCUMENT = "document.json"


def save_document(path, model, camera, doc) -> None:  # noqa: ANN001
    """Write the document to `path` atomically (temp file + os.replace)."""
    path = Path(path)
    data = document_to_dict(model, camera, doc)
    manifest = {"format": "pluton", "schema_version": SCHEMA_VERSION,
                "app_version": _core_version()}
    tmp = path.with_name(path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST, json.dumps(manifest, separators=(",", ":")))
            zf.writestr(_DOCUMENT, json.dumps(data, separators=(",", ":")))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def load_document(path) -> LoadedDocument:  # noqa: ANN001
    """Read a .pluton file. Raises PlutonFormatError / PlutonVersionError / OSError."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            manifest = json.loads(zf.read(_MANIFEST))
            if manifest.get("format") != "pluton":
                raise PlutonFormatError("not a Pluton file (bad 'format' in manifest)")
            ver = manifest.get("schema_version")
            if not isinstance(ver, int) or ver > SCHEMA_VERSION:
                raise PlutonVersionError(
                    f"file schema_version {ver} is newer than supported ({SCHEMA_VERSION})")
            data = json.loads(zf.read(_DOCUMENT))
    except zipfile.BadZipFile as e:
        raise PlutonFormatError("not a valid .pluton file (not a zip archive)") from e
    except KeyError as e:
        raise PlutonFormatError(f"missing entry in .pluton archive: {e}") from e
    except json.JSONDecodeError as e:
        raise PlutonFormatError(f"corrupt JSON in .pluton archive: {e}") from e
    return document_from_dict(data)
```

Note: the `try/finally` unlinks the temp file on the failure path; on success `os.replace` has already consumed it, so `tmp.exists()` is False. The version-gate raises are inside the `try` but are not caught by the `except` clauses (they are `PlutonError` subclasses, not `BadZipFile`/`KeyError`/`JSONDecodeError`), so they propagate cleanly.

Update `python/pluton/io/__init__.py`:

```python
# python/pluton/io/__init__.py
"""Native .pluton file I/O (M6a)."""

from pluton.io.errors import PlutonFormatError, PlutonIOError, PlutonVersionError
from pluton.io.pluton_file import SCHEMA_VERSION, load_document, save_document

__all__ = [
    "SCHEMA_VERSION",
    "PlutonFormatError",
    "PlutonIOError",
    "PlutonVersionError",
    "load_document",
    "save_document",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_pluton_file.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/pluton_file.py python/pluton/io/__init__.py tests/test_pluton_file.py && git commit -m "feat(io): zip file layer, manifest version gate, atomic save"
```

---

## Task 7: CommandStack change-listener + clear

**Files:**
- Modify: `python/pluton/commands/command_stack.py`
- Test: `tests/test_command_stack.py` (append)

**Interfaces:**
- Produces: `CommandStack.add_change_listener(fn) -> None` (fn() fires after `execute`, `push_executed`, `undo`, `redo`); `CommandStack.clear() -> None` (empties both stacks; does NOT fire change listeners).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_command_stack.py  (append)
from pluton.commands.command_stack import CommandStack


class _NoOpCmd:
    def do(self, target):  # noqa: ANN001
        pass

    def undo(self, target):  # noqa: ANN001
        pass


def test_change_listener_fires_on_every_mutation():
    stack = CommandStack()
    calls = []
    stack.add_change_listener(lambda: calls.append(1))

    stack.execute(_NoOpCmd(), object())
    assert len(calls) == 1
    stack.push_executed(_NoOpCmd(), object())
    assert len(calls) == 2
    stack.undo()
    assert len(calls) == 3
    stack.redo()
    assert len(calls) == 4


def test_clear_empties_both_stacks():
    stack = CommandStack()
    stack.execute(_NoOpCmd(), object())
    stack.undo()
    assert stack.can_redo
    stack.clear()
    assert not stack.can_undo
    assert not stack.can_redo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_command_stack.py -k "change_listener or clear" -v`
Expected: FAIL — `AttributeError: 'CommandStack' object has no attribute 'add_change_listener'`.

- [ ] **Step 3: Write minimal implementation**

In `python/pluton/commands/command_stack.py`:

In `__init__`, after the existing listener lists, add:
```python
        self._on_change: list = []  # list[Callable[[], None]]
```

Add these methods to the class:
```python
    def add_change_listener(self, fn) -> None:  # noqa: ANN001
        """Register a zero-arg callable fired after every stack mutation."""
        self._on_change.append(fn)

    def _fire_change(self) -> None:
        for fn in self._on_change:
            fn()

    def clear(self) -> None:
        """Empty both stacks (used when switching documents). Fires no listeners."""
        self._undo.clear()
        self._redo.clear()
```

Add `self._fire_change()` as the **last** line of `execute`, `push_executed`, `undo` (after the existing `_on_after_undo` loop, before `return True`), and `redo` (after the `_on_after_redo` loop, before `return True`). For `undo`/`redo`, only fire on the success path (after popping). The resulting `execute`:
```python
    def execute(self, cmd: Command, target) -> None:  # noqa: ANN001
        cmd.do(target)
        self._undo.append((cmd, target))
        self._redo.clear()
        self._fire_change()
```
and `push_executed`:
```python
    def push_executed(self, cmd: Command, target) -> None:  # noqa: ANN001
        self._undo.append((cmd, target))
        self._redo.clear()
        self._fire_change()
```
and the tail of `undo` (after `for fn in self._on_after_undo: fn()`):
```python
        self._fire_change()
        return True
```
and the tail of `redo` (after `for fn in self._on_after_redo: fn()`):
```python
        self._fire_change()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_command_stack.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/command_stack.py tests/test_command_stack.py && git commit -m "feat(commands): CommandStack change-listener + clear for dirty/doc-switch"
```

---

## Task 8: DocumentController + adopt-support primitives

**Files:**
- Create: `python/pluton/ui/document_controller.py`
- Modify: `python/pluton/model/model.py` (add `load_from`)
- Modify: `python/pluton/ui/materials_dock.py` (add `library_changed` signal + `set_library`)
- Modify: `python/pluton/ui/tags_dock.py` (add `library_changed` signal + `set_library` + emits)
- Test: `tests/test_document_controller.py`

**Interfaces:**
- Produces:
  - `DocumentController` with attrs `current_path: Path | None`, `dirty: bool`; methods `mark_dirty()`, `mark_clean()`, `set_path(path)`, `display_title() -> str`.
  - `Model.load_from(other: Model) -> None` — swaps contents in place (keeps identity).
  - `MaterialsDock.library_changed` (Signal), `MaterialsDock.set_library(library) -> None`.
  - `TagsDock.library_changed` (Signal), `TagsDock.set_library(library) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_document_controller.py
import numpy as np

from pluton.model.model import Model
from pluton.ui.document_controller import DocumentController


def test_controller_dirty_transitions_and_title():
    c = DocumentController()
    assert c.current_path is None
    assert c.dirty is False
    assert c.display_title() == "Untitled — Pluton"

    c.mark_dirty()
    assert c.display_title() == "Untitled* — Pluton"

    c.set_path("/tmp/house.pluton")
    c.mark_clean()
    assert c.display_title() == "house.pluton — Pluton"
    c.mark_dirty()
    assert c.display_title() == "house.pluton* — Pluton"


def test_model_load_from_keeps_identity_swaps_contents():
    target = Model()
    target_id = id(target)
    other = Model()
    g = other.new_definition("Grp", is_group=True)
    inst = other.new_instance(g)
    other.root.children.append(inst)

    target.load_from(other)
    assert id(target) == target_id           # same object
    assert target.root is other.root         # contents swapped
    assert target.materials is other.materials
    assert target.tags is other.tags
    assert target.active_path == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.ui.document_controller'`.

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/ui/document_controller.py
"""DocumentController (M6a): the document session state — path, dirty flag, and
the window-title string. No Qt widgets, so it is unit-testable headlessly.
"""

from __future__ import annotations

from pathlib import Path

_APP = "Pluton"


class DocumentController:
    def __init__(self) -> None:
        self.current_path: Path | None = None
        self.dirty: bool = False

    def mark_dirty(self) -> None:
        self.dirty = True

    def mark_clean(self) -> None:
        self.dirty = False

    def set_path(self, path) -> None:  # noqa: ANN001
        self.current_path = Path(path) if path else None

    def display_title(self) -> str:
        name = self.current_path.name if self.current_path else "Untitled"
        star = "*" if self.dirty else ""
        return f"{name}{star} — {_APP}"
```

In `python/pluton/model/model.py`, add to class `Model`:
```python
    def load_from(self, other: "Model") -> None:
        """Replace this model's contents with another's, in place (keeps identity).

        Lets the viewport / tool context keep their existing Model reference while
        the whole document is swapped underneath (file Open / New).
        """
        self.root = other.root
        self.active_path = []
        self._next_def_id = other._next_def_id
        self._next_inst_id = other._next_inst_id
        self.materials = other.materials
        self.tags = other.tags
```

In `python/pluton/ui/materials_dock.py`:
- Add to the signals (next to `active_material_changed`): `library_changed = Signal()`.
- In `_on_custom`, after `self._rebuild_swatches()` (before `self._on_pick(mat.id)`), add: `self.library_changed.emit()`.
- Add method:
```python
    def set_library(self, library: MaterialLibrary) -> None:
        """Rebind to a new library (after file Open / New) and rebuild swatches."""
        self._library = library
        self._active_id = MaterialLibrary.DEFAULT_ID
        self._rebuild_swatches()
```

In `python/pluton/ui/tags_dock.py`:
- Add to the signals: `library_changed = Signal()`.
- In `_on_add`, after `tag = self._library.add(...)`, add: `self.library_changed.emit()`.
- In `_on_item_changed`, inside the rename branch (after `self._library.rename(tid, new_name)`), add: `self.library_changed.emit()`.
- Add method:
```python
    def set_library(self, library: TagLibrary) -> None:
        """Rebind to a new library (after file Open / New) and rebuild the list."""
        self._library = library
        self._active_id = TagLibrary.UNTAGGED_ID
        self._rebuild()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_controller.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/document_controller.py python/pluton/model/model.py python/pluton/ui/materials_dock.py python/pluton/ui/tags_dock.py tests/test_document_controller.py && git commit -m "feat(io): DocumentController + in-place model swap + dock rebind/dirty signals"
```

---

## Task 9: MainWindow — File menu, dirty tracking, Save, guard

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_fileio.py`

**Interfaces:**
- Consumes: `DocumentController` (T8); `CommandStack.add_change_listener`/`clear` (T7); `save_document`, `PlutonIOError` (T6); dock `library_changed`/`visibility_changed` signals (T8/existing).
- Produces (methods on `MainWindow`): `_on_document_changed`, `_update_window_title`, `_on_file_save`, `_on_file_save_as`, `_save_to`, `_prompt_save_path`, `_prompt_discard`, `_confirm_discard_if_dirty`, `closeEvent`. The File menu and `Ctrl+O`/`Ctrl+S`/`Ctrl+Shift+S` shortcuts; `Ctrl+N` rebound to `_on_file_new` (defined in T10 — see note).

**Note on ordering:** `_on_file_new`/`_on_file_open` are added in Task 10. In this task, bind `Ctrl+N` and the File-menu "New"/"Open…" actions to those handlers by name; Task 9's tests do not exercise New/Open (they cover Save + dirty + guard), and Task 10 adds the handlers and their tests. If running tasks strictly independently, add temporary stubs `def _on_file_new(self): pass` / `def _on_file_open(self): pass` and replace them in Task 10. (Under subagent-driven execution the tasks land in order, so the Task 10 handlers will exist before New/Open are invoked.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_window_fileio.py
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from pluton.commands.scene_commands import ClearSceneCommand
from pluton.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def _draw_something(win):
    scene = win._model.active_scene
    vids = [scene.add_vertex(np.array(p, dtype=np.float32))
            for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    scene.add_face_from_loop(vids)


def test_command_execution_marks_dirty_and_titles(app):
    win = MainWindow()
    assert win._doc_controller.dirty is False
    assert win.windowTitle() == "Untitled — Pluton"
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    assert win._doc_controller.dirty is True
    assert win.windowTitle() == "Untitled* — Pluton"


def test_save_as_writes_file_and_marks_clean(app, tmp_path, monkeypatch):
    win = MainWindow()
    _draw_something(win)
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    assert win._doc_controller.dirty is True

    target = tmp_path / "out.pluton"
    monkeypatch.setattr(win, "_prompt_save_path", lambda: str(target))
    assert win._on_file_save_as() is True
    assert target.exists()
    assert win._doc_controller.dirty is False
    assert win.windowTitle() == "out.pluton — Pluton"


def test_guard_cancel_aborts(app):
    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "cancel"
    assert win._confirm_discard_if_dirty() is False


def test_guard_discard_proceeds(app):
    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "discard"
    assert win._confirm_discard_if_dirty() is True


def test_file_menu_has_actions(app):
    win = MainWindow()
    labels = [a.text() for a in win._file_menu.actions() if a.text()]
    assert any("New" in t for t in labels)
    assert any("Open" in t for t in labels)
    assert any("Save" in t for t in labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_fileio.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_doc_controller'`.

- [ ] **Step 3: Write minimal implementation**

In `python/pluton/ui/main_window.py`:

(a) Add imports near the other `pluton` imports at the top:
```python
from pathlib import Path

from pluton.io import PlutonIOError, load_document, save_document
from pluton.ui.document_controller import DocumentController
```

(b) In `__init__`, after the Tags-dock wiring block (after `self._tags_dock.assign_to_selection_requested.connect(self._on_assign_tag)`), add the controller + dirty wiring:
```python
        # Document session state (path / dirty / title) + dirty signal sources.
        self._doc_controller = DocumentController()
        self._command_stack.add_change_listener(self._on_document_changed)
        self._materials_dock.library_changed.connect(self._on_document_changed)
        self._tags_dock.library_changed.connect(self._on_document_changed)
        self._tags_dock.visibility_changed.connect(self._on_document_changed)
```

(c) Change the `Ctrl+N` shortcut (currently `activated=self._on_clear_scene`) to New, and add the file shortcuts. Replace the `Ctrl+N` line and add three lines after it:
```python
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_file_new)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._on_file_open)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_file_save)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self._on_file_save_as)
```

(d) Build the File menu **before** the `# Edit menu` block (so File is leftmost). Insert immediately before `self._edit_menu = menubar.addMenu("Edit")`:
```python
        # File menu (M6a) — leftmost.
        self._file_menu = menubar.addMenu("File")
        self._file_menu.addAction("New\tCtrl+N", self._on_file_new)
        self._file_menu.addAction("Open…\tCtrl+O", self._on_file_open)
        self._file_menu.addSeparator()
        self._file_menu.addAction("Save\tCtrl+S", self._on_file_save)
        self._file_menu.addAction("Save As…\tCtrl+Shift+S", self._on_file_save_as)
```

(e) Add "Clear Active Context" to the Edit menu (Ctrl+N no longer triggers it). After the existing Edit-menu actions (`self._edit_menu.addAction("Make Unique", self._on_make_unique)`):
```python
        self._edit_menu.addSeparator()
        self._edit_menu.addAction("Clear Active Context", self._on_clear_scene)
```

(f) At the very end of `__init__`, set the initial title:
```python
        self._update_window_title()
```

(g) Append the units-menu dirty hook: in `_set_units_metric` and `_set_units_imperial` (locate both methods), add `self._on_document_changed()` as the last line of each.

(h) Add the new methods (place them in a clearly-marked `# --- File I/O ---` section):
```python
    # --- File I/O --------------------------------------------------------

    def _on_document_changed(self) -> None:
        self._doc_controller.mark_dirty()
        self._update_window_title()

    def _update_window_title(self) -> None:
        self.setWindowTitle(self._doc_controller.display_title())

    def _prompt_save_path(self) -> str | None:
        """Return a chosen save path (or None). Overridable for testing."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Save As", "", "Pluton files (*.pluton)")
        return path or None

    def _save_to(self, path) -> bool:  # noqa: ANN001
        path = str(path)
        if not path.endswith(".pluton"):
            path += ".pluton"
        try:
            save_document(path, self._model, self._viewport.camera, self._doc)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Save failed", str(e))
            return False
        self._doc_controller.set_path(path)
        self._doc_controller.mark_clean()
        self._update_window_title()
        self._status_bar.set_status(f"Saved {Path(path).name}")
        return True

    def _on_file_save(self) -> bool:
        if self._doc_controller.current_path is None:
            return self._on_file_save_as()
        return self._save_to(self._doc_controller.current_path)

    def _on_file_save_as(self) -> bool:
        path = self._prompt_save_path()
        if not path:
            return False
        return self._save_to(path)

    def _prompt_discard(self) -> str:
        """Return 'save' | 'discard' | 'cancel'. Overridable for testing."""
        from PySide6.QtWidgets import QMessageBox
        name = (self._doc_controller.current_path.name
                if self._doc_controller.current_path else "Untitled")
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Save changes to {name}?")
        box.setStandardButtons(QMessageBox.StandardButton.Save
                               | QMessageBox.StandardButton.Discard
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return "save"
        if choice == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _confirm_discard_if_dirty(self) -> bool:
        """True if it's safe to proceed (discard a New/Open/close)."""
        if not self._doc_controller.dirty:
            return True
        choice = self._prompt_discard()
        if choice == "save":
            return self._on_file_save()
        if choice == "discard":
            return True
        return False

    def closeEvent(self, event):  # noqa: N802, ANN001
        if self._confirm_discard_if_dirty():
            event.accept()
        else:
            event.ignore()
```

Note: `test_guard_cancel_aborts` uses a local name in the lambda; ensure your copy assigns `win._prompt_discard = lambda: "cancel"` (the test body above shows the intent — a fresh subagent should write `win._prompt_discard = lambda: "cancel"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_fileio.py -v`
Expected: PASS (all File-menu/dirty/guard/save tests). (New/Open tests arrive in Task 10.)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_fileio.py && git commit -m "feat(ui): File menu, dirty tracking, Save/Save As, unsaved-changes guard"
```

---

## Task 10: MainWindow — New, Open & atomic adopt

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Test: `tests/test_main_window_fileio.py` (append)

**Interfaces:**
- Consumes: `_reset_document` building blocks — `Model.load_from`, dock `set_library` (T8); `CommandStack.clear` (T7); `CameraState`/`load_document` (T5/T6); `Selection.clear`, `_rebuild_tool_context`, `_refresh_breadcrumb`, `_refresh_status_text` (existing).
- Produces (methods on `MainWindow`): `_reset_document`, `_on_file_new`, `_on_file_open`, `_prompt_open_path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_window_fileio.py  (append)
def test_new_resets_to_clean_untitled(app, tmp_path):
    win = MainWindow()
    _draw_something(win)
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "discard"
    win._on_file_new()
    assert win._doc_controller.current_path is None
    assert win._doc_controller.dirty is False
    assert win.windowTitle() == "Untitled — Pluton"
    assert not win._command_stack.can_undo  # history cleared


def test_open_success_swaps_model_and_clears_history(app, tmp_path, monkeypatch):
    # First, save a file with a known box.
    saver = MainWindow()
    _draw_something(saver)
    target = tmp_path / "doc.pluton"
    saver._prompt_save_path = lambda: str(target)
    assert saver._on_file_save_as() is True

    # Now open it in a fresh window with a dirty scratch doc.
    win = MainWindow()
    win._command_stack.execute(ClearSceneCommand(), win._model.active_scene)
    win._prompt_discard = lambda: "discard"
    win._prompt_open_path = lambda: str(target)
    win._on_file_open()
    assert win._doc_controller.current_path == target
    assert win._doc_controller.dirty is False
    assert len(list(win._model.root.mesh.faces_iter())) == 1
    assert not win._command_stack.can_undo


def test_open_failure_keeps_current_model(app, monkeypatch):
    from pluton.io import PlutonFormatError
    win = MainWindow()
    _draw_something(win)
    before_root = win._model.root
    win._prompt_open_path = lambda: "/whatever.pluton"

    import pluton.ui.main_window as mw
    monkeypatch.setattr(mw, "load_document",
                        lambda p: (_ for _ in ()).throw(PlutonFormatError("bad")))
    # Suppress + record the error dialog.
    shown = {}
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **k: shown.setdefault("called", True))
    win._on_file_open()
    assert win._model.root is before_root      # unchanged
    assert shown.get("called") is True         # error surfaced
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_fileio.py -k "new_resets or open_" -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_file_new'` (or the T9 temporary stubs are no-ops).

- [ ] **Step 3: Write minimal implementation**

In `python/pluton/ui/main_window.py`, add to the `# --- File I/O ---` section (and ensure the imports `from pluton.io.document_codec import CameraState` and `from pluton.model.model import Model`, `from pluton.units import Units`, `from pluton.viewport.camera import Camera` are present — `Model` is already imported; add the others):

```python
    def _reset_document(self, model, camera_state, units, path) -> None:  # noqa: ANN001
        """Adopt a (model, camera, units) into the live window, in place."""
        self._model.load_from(model)
        self._materials_dock.set_library(self._model.materials)
        self._tags_dock.set_library(self._model.tags)
        camera_state.apply_to(self._viewport.camera)
        self._doc.set_units(units)
        self._active_material_id = self._model.materials.DEFAULT_ID
        self._active_tag_id = self._model.tags.UNTAGGED_ID
        self._selection.clear()
        self._command_stack.clear()
        self._doc_controller.set_path(path)
        self._doc_controller.mark_clean()
        self._rebuild_tool_context()
        self._refresh_breadcrumb()
        self._refresh_status_text()
        self._update_window_title()
        self._viewport.update()

    def _on_file_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        from pluton.units import Units
        from pluton.viewport.camera import Camera
        self._reset_document(Model(), CameraState.from_camera(Camera()), Units(), None)

    def _prompt_open_path(self) -> str | None:
        """Return a chosen open path (or None). Overridable for testing."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "Pluton files (*.pluton)")
        return path or None

    def _on_file_open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        path = self._prompt_open_path()
        if not path:
            return
        try:
            loaded = load_document(path)
        except (PlutonIOError, OSError) as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Open failed", str(e))
            return
        self._reset_document(loaded.model, loaded.camera_state, loaded.units, path)
```

Add the import at the top with the others: `from pluton.io.document_codec import CameraState`. Remove any temporary `_on_file_new`/`_on_file_open` stubs added in Task 9.

Note: `_on_file_open` references the module-level `load_document` name (imported in Task 9), which `test_open_failure_keeps_current_model` monkeypatches via `pluton.ui.main_window.load_document` — keep `load_document` imported at module scope (not inside the method).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_fileio.py -v`
Expected: PASS (all File-I/O window tests).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_fileio.py && git commit -m "feat(ui): File New/Open with atomic in-place document adoption"
```

---

## Task 11: Full regression + manual visual pass

**Files:** none (verification only).

- [ ] **Step 1: Full Python suite**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest -q`
Expected: all green — the prior 674 plus the new M6a tests (~30+), 0 failures.

- [ ] **Step 2: Lint the new/modified Python**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m ruff check python/pluton/io python/pluton/ui/document_controller.py`
Expected: clean (or only import-sort fixes on the brand-new files — apply with `ruff check --fix` on the new files only; never broad-fix files carrying intentional `# noqa`).

- [ ] **Step 3: C++ suite unchanged (sanity)**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && ctest --test-dir build/<wheel_tag> --output-on-failure` (use the existing build dir).
Expected: 76/76 pass (M6a is Python-only; this confirms no accidental kernel impact).

- [ ] **Step 4: Manual visual verification (launch the app)**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pluton.app`
Checklist:
- Draw a box, paint a face, make a group, assign a tag, hide that tag, switch to imperial units, orbit the camera.
- File ▸ Save As → choose `test.pluton`. Title shows `test.pluton — Pluton` (no `*`).
- Make another edit → title shows `test.pluton*`.
- File ▸ New → prompts Save/Don't Save/Cancel; choose Don't Save → empty untitled doc, camera reset.
- File ▸ Open → `test.pluton` → geometry, paint, group, tag (still hidden), units (imperial), and camera view all restored; title clean.
- Close the window with unsaved edits → prompts; Cancel keeps the window open.

- [ ] **Step 5: Commit (if any lint-only fixups were applied)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add -p && git commit -m "chore(io): lint fixups for M6a"
```
(Skip if nothing changed. Stage specific hunks only.)

---

## Task 12: Release v0.1.8-m6a

**Files:**
- Modify: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M6a shipped)

**Interfaces:** none.

- [ ] **Step 1: Bump version 0.1.7 → 0.1.8** in all three files (`pyproject.toml` `version`, `CMakeLists.txt` `project(... VERSION 0.1.8 ...)`, `cpp/src/version.cpp` return string).

- [ ] **Step 2: Rebuild the editable install and confirm version**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pip install -e . --no-build-isolation` then `.venv/Scripts/python -c "import pluton._core; print(pluton._core.version())"`
Expected: `0.1.8`.

- [ ] **Step 3: Annotate the master design doc** — under M6 in `docs/2026-05-16-pluton-design.md`, add a sub-milestone line: **M6a** ✅ *(shipped v0.1.8)* — native `.pluton` save/open/new (zip+JSON, schema v1, model+camera, dirty-guard); OBJ (M6b) and glTF/Assimp (M6c) deferred.

- [ ] **Step 4: Full suite green at the new version**

Run: `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md && git commit -m "release: v0.1.8-m6a — native .pluton file I/O"
```

- [ ] **Step 6: Push + tag + CI + carry-over issues (REQUIRES explicit user authorization per turn)**

After the user authorizes the outward-facing actions:
```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main
git tag v0.1.8-m6a && git push origin v0.1.8-m6a
```
Watch CI to green on ubuntu-24.04 + windows-2022. File carry-over issues: OBJ import/export (M6b), glTF/Assimp (M6c), recent-files list, autosave/crash-recovery, launch-with-file / OS association, "Revert to Saved", multiple saved cameras/Scenes (M7).

---

## Self-Review

**1. Spec coverage** — every design section maps to a task:
- §3 schema (zip + document.json) → Tasks 3–6 (encoding) + Task 6 (manifest/zip).
- §4 codec (geometry / model / document, atomic build) → Tasks 3, 4, 5.
- §5 file layer (save/load, version gate, error taxonomy, atomic write) → Tasks 1, 6.
- §6 controller / dirty / File menu / guard / adopt → Tasks 7, 8, 9, 10.
- §7 testing (4 tiers) → codec Tasks 3–5 (Tier 1), Task 6 (Tier 2), Task 8 (Tier 3), Tasks 9–10 (Tier 4), Task 11 (regression + visual).
- §2 decisions D1–D10 → all honored (D8 camera non-dirtying: camera moves never call `_on_document_changed`; D9 ClearScene kept on Edit menu in Task 9; D10 compact JSON in Task 6).

**2. Placeholder scan** — no "TBD"/"add error handling"/"similar to Task N"; every code step shows complete code; every test step shows real assertions. (Task 9's cross-task note about `_on_file_new`/`_on_file_open` is an explicit ordering instruction, not a placeholder — Task 10 supplies the bodies.)

**3. Type consistency** — names verified across tasks: `geometry_to_dict`/`geometry_from_dict`, `model_to_dict`/`model_from_dict`, `document_to_dict`/`document_from_dict`, `LoadedDocument(model, camera_state, units)`, `CameraState.apply_to`, `MaterialLibrary.from_records`/`to_records`/`next_id`, `TagLibrary.from_records`/`to_records`/`next_id`, `units_to_dict`/`units_from_dict`, `DocumentSettings.set_units`, `Model.load_from`, `CommandStack.add_change_listener`/`clear`, dock `library_changed`/`set_library`, `DocumentController.set_path`/`display_title`/`mark_dirty`/`mark_clean`, MainWindow `_reset_document`/`_save_to`/`_confirm_discard_if_dirty`/`_prompt_save_path`/`_prompt_open_path`/`_prompt_discard`/`_update_window_title`/`_on_document_changed`. All consumers match producers.

# M7e — Scenes (Saved Views) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Named saved **Scenes** (camera + tag visibility + render style) listed in a dockable panel, recalled with an animated camera tween, persisted through `.pluton`, and managed with undo.

**Architecture:** A pure `SavedView` snapshot + `ViewLibrary` (owned by `Model` as `model.views`, mirroring `TagLibrary`) hold the data; a pure numpy `interpolate_pose` (orbit-decomposition) plus a thin `ViewAnimator` (Qt `QVariantAnimation`) drive animated recall; five undoable commands and a `TagsDock`-shaped `ScenesDock` provide management; `document_codec` gains top-level `scenes` + `style` keys behind a schema bump.

**Tech Stack:** Python 3.13, numpy, PySide6/Qt, pytest + pytest-qt. No C++/kernel change.

## Global Constraints

- **Ship as v0.2.5.** Version bumped ONLY in the release task (Task 11): `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` — all `0.2.4` → `0.2.5`.
- **Python-only.** No kernel change; `ctest` stays **79/79**. Full `pytest` must stay well above the **977** baseline.
- **Internal class is `SavedView`; package is `pluton.views`.** NEVER name the new class `Scene` (collides with `pluton.scene.scene.Scene`, the mesh). User-facing text is always "Scene"/"Scenes".
- **Capture = camera + tag visibility + render style. Always restore all three.** No per-Scene property checkboxes.
- **Recall animates the camera only** (orbit-decomposition tween, `QEasingCurve.InOutSine`, 700 ms); tag visibility and render style apply instantly at recall time. Recall is NOT undoable and does NOT dirty the document.
- **Scene management is undoable** via `CommandStack`: create, update, rename, delete, reorder — identity/index-preserving; delete restores at its original index.
- **`SCHEMA_VERSION` 2 → 3.** Two new top-level codec keys (`"scenes"`, `"style"`), each tolerated as absent on read (`data.get(...)`) so v2 `.pluton` files still open (empty `ViewLibrary`, default `RenderStyle`).
- **New files carry NO `# noqa`.** Ruff select is `["E","F","W","I","N","UP","B","C4","RUF"]`; `ANN` is not selected, so an `ANN0xx` suppression is itself an RUF100. Keep lines ≤ 100 chars.
- **`main_window.py` stays additive** — ruff finding count held at exactly **9** (issue #48). Run `ruff check python/pluton/ui/main_window.py` after editing and confirm 9.
- **Git discipline:** never `git add -A`/`git add .` — stage listed files only. Never `--no-verify`/`--amend`/`--no-gpg-sign`. Commit on `main`. Trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Build/test with `.venv/Scripts/python` explicitly** (bare `python` hits a drifting editable install). Bash cwd resets between calls — prefix every command with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.
- **Deliberate deviation from the spec (documented):** `LoadedDocument` gains only a `style` field, NOT a `scenes` field — the loaded scenes ride on `model.views` (via `load_from`), exactly as tags/materials do, so a separate `scenes` field would be redundant.

## File Structure

**New files:**
- `python/pluton/views/__init__.py` — package marker (empty).
- `python/pluton/views/saved_view.py` — `SavedView` frozen dataclass.
- `python/pluton/views/view_library.py` — `ViewLibrary` (list owner + records).
- `python/pluton/views/capture.py` — `capture_view` / `apply_view` / `apply_tags_and_style`.
- `python/pluton/views/interpolate.py` — pure `interpolate_pose` tween math.
- `python/pluton/viewport/view_animator.py` — `ViewAnimator` (Qt shell).
- `python/pluton/commands/view_commands.py` — five undoable commands.
- `python/pluton/ui/scenes_dock.py` — `ScenesDock` panel.
- Tests: `tests/test_saved_view.py`, `test_view_library.py`, `test_capture.py`, `test_interpolate.py`, `test_view_animator.py`, `test_view_commands.py`, `test_scenes_dock.py`, `test_main_window_scenes.py`.

**Modified files:**
- `python/pluton/model/model.py` — `self.views` in `__init__` + `load_from`.
- `python/pluton/io/document_codec.py` — render-style codec, `scenes`/`style` keys, `LoadedDocument.style`.
- `python/pluton/io/pluton_file.py` — `SCHEMA_VERSION = 3`; `render_style` arg through `save_document`.
- `python/pluton/viewport/viewport_widget.py` — `set_camera_input_callback` + calls in MMB-drag / wheel.
- `python/pluton/ui/tags_dock.py` — public `refresh()`.
- `python/pluton/ui/main_window.py` — dock, animator, signal routing, recall, adopt style on New/Open.
- `docs/2026-05-16-pluton-design.md` — annotate M7 line (Task 10).
- `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp` — version (Task 11).

---

### Task 1: SavedView + ViewLibrary

**Files:**
- Create: `python/pluton/views/__init__.py` (empty)
- Create: `python/pluton/views/saved_view.py`
- Create: `python/pluton/views/view_library.py`
- Test: `tests/test_saved_view.py`, `tests/test_view_library.py`

**Interfaces:**
- Consumes: `CameraState` from `pluton.io.document_codec` — frozen dataclass, fields `position,target,up,fov_y_deg`, methods `.to_dict()` and classmethod `CameraState.from_dict(d)`.
- Produces:
  - `SavedView(id: int, name: str, camera: CameraState, tag_visibility: dict, face_style: str, xray: bool)` — frozen dataclass.
  - `ViewLibrary`: `add(view)->view`, `get(vid)->SavedView|None`, `index_of(vid)->int`, `remove(vid)`, `insert(index, view)`, `rename(vid, name)`, `replace_view(vid, view)`, `move(vid, direction)->bool`, `views()->list`, `next_id` (property), `to_records()->list[dict]`, classmethod `from_records(records, next_id)->ViewLibrary`.

- [ ] **Step 1: Write the failing tests** — `tests/test_saved_view.py`:

```python
import dataclasses

from pluton.io.document_codec import CameraState
from pluton.views.saved_view import SavedView


def _cam():
    return CameraState(position=(1.0, 2.0, 3.0), target=(0.0, 0.0, 0.0),
                       up=(0.0, 0.0, 1.0), fov_y_deg=45.0)


def test_saved_view_holds_its_fields():
    v = SavedView(id=7, name="Front", camera=_cam(),
                  tag_visibility={2: False}, face_style="SHADED", xray=True)
    assert v.id == 7
    assert v.name == "Front"
    assert v.camera.position == (1.0, 2.0, 3.0)
    assert v.tag_visibility == {2: False}
    assert v.face_style == "SHADED"
    assert v.xray is True


def test_saved_view_is_frozen():
    v = SavedView(1, "A", _cam(), {}, "SHADED", False)
    try:
        v.name = "B"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("SavedView must be frozen")
```

`tests/test_view_library.py`:

```python
from pluton.io.document_codec import CameraState
from pluton.views.saved_view import SavedView
from pluton.views.view_library import ViewLibrary


def _view(vid, name="V"):
    cam = CameraState(position=(float(vid), 0.0, 0.0), target=(0.0, 0.0, 0.0),
                      up=(0.0, 0.0, 1.0), fov_y_deg=45.0)
    return SavedView(vid, name, cam, {vid: False}, "SHADED", False)


def test_add_advances_next_id_past_the_view():
    lib = ViewLibrary()
    assert lib.next_id == 0
    lib.add(_view(0))
    assert lib.next_id == 1
    lib.add(_view(5))
    assert lib.next_id == 6  # jumps past the highest id seen


def test_get_and_index_of():
    lib = ViewLibrary()
    lib.add(_view(0, "A"))
    lib.add(_view(1, "B"))
    assert lib.get(1).name == "B"
    assert lib.get(99) is None
    assert lib.index_of(1) == 1
    assert lib.index_of(99) == -1


def test_remove_then_insert_restores_position():
    lib = ViewLibrary()
    a, b, c = _view(0, "A"), _view(1, "B"), _view(2, "C")
    lib.add(a); lib.add(b); lib.add(c)
    lib.remove(1)
    assert [v.name for v in lib.views()] == ["A", "C"]
    lib.insert(1, b)
    assert [v.name for v in lib.views()] == ["A", "B", "C"]


def test_rename_replaces_frozen_view():
    lib = ViewLibrary()
    lib.add(_view(0, "Old"))
    lib.rename(0, "New")
    assert lib.get(0).name == "New"
    lib.rename(0, "")  # empty rejected
    assert lib.get(0).name == "New"


def test_move_up_swaps_returns_true():
    lib = ViewLibrary()
    lib.add(_view(0, "A")); lib.add(_view(1, "B")); lib.add(_view(2, "C"))
    assert lib.move(1, -1) is True          # move "B" up one
    assert [v.name for v in lib.views()] == ["B", "A", "C"]


def test_move_clamps_at_ends_returns_false():
    lib = ViewLibrary()
    lib.add(_view(0, "A")); lib.add(_view(1, "B"))
    assert lib.move(0, -1) is False         # "A" already first
    assert lib.move(1, +1) is False         # "B" already last
    assert [v.name for v in lib.views()] == ["A", "B"]  # unchanged


def test_records_round_trip_preserves_order_and_next_id():
    lib = ViewLibrary()
    lib.add(_view(0, "A")); lib.add(_view(3, "B"))
    records = lib.to_records()
    assert records[0]["name"] == "A"
    assert records[0]["tag_visibility"] == {"0": False}  # keys stringified for JSON
    rebuilt = ViewLibrary.from_records(records, lib.next_id)
    assert [v.name for v in rebuilt.views()] == ["A", "B"]
    assert rebuilt.get(0).tag_visibility == {0: False}   # keys back to int
    assert rebuilt.next_id == 4
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_saved_view.py tests/test_view_library.py -q
```
Expected: FAIL (`ModuleNotFoundError: No module named 'pluton.views'`).

- [ ] **Step 3: Create `python/pluton/views/__init__.py`** — an empty file.

- [ ] **Step 4: Create `python/pluton/views/saved_view.py`**

```python
"""SavedView (M7e): an immutable snapshot of a named Scene.

Holds the camera pose plus the tag-visibility and render-style state to
restore when the Scene is recalled. Pure data — no Qt. Named SavedView (not
Scene) to avoid colliding with pluton.scene.scene.Scene (the editable mesh).
"""

from __future__ import annotations

from dataclasses import dataclass

from pluton.io.document_codec import CameraState


@dataclass(frozen=True)
class SavedView:
    """One saved Scene: camera + tag visibility + render style, restored together."""

    id: int
    name: str
    camera: CameraState
    tag_visibility: dict  # dict[int, bool] — {tag_id: visible} at capture time
    face_style: str       # FaceStyle member name, e.g. "SHADED"
    xray: bool
```

- [ ] **Step 5: Create `python/pluton/views/view_library.py`**

```python
"""ViewLibrary (M7e): owns the ordered list of SavedViews for a document.

Mirrors TagLibrary/MaterialLibrary: a plain list owner with to_records() /
from_records() for .pluton persistence. Lives on Model as `model.views`.
SavedView is frozen, so rename/replace swap in a new dataclass copy.
"""

from __future__ import annotations

from dataclasses import replace

from pluton.io.document_codec import CameraState
from pluton.views.saved_view import SavedView


class ViewLibrary:
    """The document's saved Scenes, in display order."""

    def __init__(self) -> None:
        self._views: list[SavedView] = []
        self._next_id = 0

    def add(self, view: SavedView) -> SavedView:
        """Append `view` (identity preserved) and advance next_id past its id."""
        self._views.append(view)
        self._next_id = max(self._next_id, int(view.id) + 1)
        return view

    def get(self, vid: int) -> SavedView | None:
        for v in self._views:
            if v.id == vid:
                return v
        return None

    def index_of(self, vid: int) -> int:
        for i, v in enumerate(self._views):
            if v.id == vid:
                return i
        return -1

    def remove(self, vid: int) -> None:
        i = self.index_of(vid)
        if i >= 0:
            del self._views[i]

    def insert(self, index: int, view: SavedView) -> None:
        """Restore `view` at `index` (used by DeleteViewCommand undo)."""
        self._views.insert(index, view)
        self._next_id = max(self._next_id, int(view.id) + 1)

    def rename(self, vid: int, name: str) -> None:
        """Rename (no-op on empty name); replaces the frozen view with a copy."""
        i = self.index_of(vid)
        if i >= 0 and name:
            self._views[i] = replace(self._views[i], name=str(name))

    def replace_view(self, vid: int, view: SavedView) -> None:
        """Overwrite the view at vid's position (used by UpdateViewCommand)."""
        i = self.index_of(vid)
        if i >= 0:
            self._views[i] = view

    def move(self, vid: int, direction: int) -> bool:
        """Swap one place up (<0) or down (>0). Returns False if clamped at an end."""
        i = self.index_of(vid)
        if i < 0:
            return False
        j = i + (1 if direction > 0 else -1)
        if j < 0 or j >= len(self._views):
            return False
        self._views[i], self._views[j] = self._views[j], self._views[i]
        return True

    def views(self) -> list[SavedView]:
        return list(self._views)

    @property
    def next_id(self) -> int:
        return self._next_id

    def to_records(self) -> list[dict]:
        records = []
        for v in self._views:
            records.append({
                "id": int(v.id),
                "name": str(v.name),
                "camera": v.camera.to_dict(),
                "tag_visibility": {str(k): bool(vis) for k, vis in v.tag_visibility.items()},
                "face_style": str(v.face_style),
                "xray": bool(v.xray),
            })
        return records

    @classmethod
    def from_records(cls, records: list[dict], next_id: int) -> "ViewLibrary":
        lib = cls()
        for r in records:
            lib._views.append(SavedView(
                id=int(r["id"]),
                name=str(r["name"]),
                camera=CameraState.from_dict(r["camera"]),
                tag_visibility={int(k): bool(v) for k, v in r.get("tag_visibility", {}).items()},
                face_style=str(r["face_style"]),
                xray=bool(r["xray"]),
            ))
        lib._next_id = int(next_id)
        return lib
```

- [ ] **Step 6: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_saved_view.py tests/test_view_library.py -q && .venv/Scripts/python -m ruff check python/pluton/views/
```
Expected: PASS; ruff clean.

- [ ] **Step 7: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/views/__init__.py python/pluton/views/saved_view.py python/pluton/views/view_library.py tests/test_saved_view.py tests/test_view_library.py && git commit -F- <<'MSG'
feat(m7e): SavedView + ViewLibrary (saved-view data core)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 2: Capture & apply helpers

**Files:**
- Create: `python/pluton/views/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: `SavedView`, `CameraState.from_camera(cam)`, `RenderStyle`/`FaceStyle` from `pluton.viewport.render_style`, a `TagLibrary` (duck-typed: `.tags()`, `.UNTAGGED_ID`, `.set_visible(id, bool)`), a `Camera` (duck-typed: `.position/.target/.up/.fov_y_deg`).
- Produces:
  - `capture_view(view_id, name, camera, tag_library, render_style) -> SavedView`
  - `apply_tags_and_style(view, tag_library, render_style) -> None` (no camera — used by animated recall)
  - `apply_view(view, camera, tag_library, render_style) -> None` (all three — used by tests / non-animated paths)

- [ ] **Step 1: Write the failing tests** — `tests/test_capture.py`:

```python
from pluton.model.tag import TagLibrary
from pluton.viewport.camera import Camera
from pluton.viewport.render_style import FaceStyle, RenderStyle
from pluton.views.capture import apply_tags_and_style, apply_view, capture_view


def _tags():
    lib = TagLibrary()
    lib.add("Walls")   # id 1
    lib.add("Roof")    # id 2
    return lib


def test_capture_snapshots_camera_tags_and_style():
    cam = Camera()
    cam.position[:] = (5.0, 6.0, 7.0)
    tags = _tags()
    tags.set_visible(2, False)   # hide Roof
    style = RenderStyle(face_style=FaceStyle.WIREFRAME, xray=True)

    v = capture_view(0, "Test", cam, tags, style)

    assert v.id == 0 and v.name == "Test"
    assert v.camera.position == (5.0, 6.0, 7.0)
    assert v.face_style == "WIREFRAME"
    assert v.xray is True
    # Untagged (id 0) is excluded; Walls visible, Roof hidden.
    assert v.tag_visibility == {1: True, 2: False}


def test_apply_view_restores_all_three():
    tags = _tags()
    style = RenderStyle()
    v = capture_view(0, "V", _capture_source_camera(), _hidden_roof_tags(), 
                     RenderStyle(face_style=FaceStyle.MONOCHROME, xray=True))
    cam = Camera()
    apply_view(v, cam, tags, style)
    assert tuple(float(x) for x in cam.position) == (9.0, 0.0, 0.0)
    assert tags.is_visible(2) is False
    assert style.face_style is FaceStyle.MONOCHROME
    assert style.xray is True


def test_apply_tolerates_unknown_tag_id():
    tags = TagLibrary()          # only Untagged exists
    style = RenderStyle()
    cam = Camera()
    v = capture_view(0, "V", cam, tags, style)
    # Inject a stale id that no longer exists in this library:
    from pluton.views.saved_view import SavedView
    stale = SavedView(v.id, v.name, v.camera, {999: False}, v.face_style, v.xray)
    apply_view(stale, cam, tags, style)   # must not raise
    assert tags.is_visible(999) is True   # unknown id → treated visible (no-op)


def _capture_source_camera():
    cam = Camera()
    cam.position[:] = (9.0, 0.0, 0.0)
    return cam


def _hidden_roof_tags():
    lib = _tags()
    lib.set_visible(2, False)
    return lib
```

(`_tags` here is defined at module top; the two helper factories reuse it.)

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_capture.py -q
```
Expected: FAIL (`ModuleNotFoundError: pluton.views.capture`).

- [ ] **Step 3: Create `python/pluton/views/capture.py`**

```python
"""Capture / apply helpers (M7e): snapshot live view state into a SavedView
and restore it. Pure — no Qt. Tag-visibility restore is tolerant of ids that
no longer exist (TagLibrary.set_visible is a no-op for unknown ids)."""

from __future__ import annotations

from pluton.io.document_codec import CameraState
from pluton.viewport.render_style import FaceStyle
from pluton.views.saved_view import SavedView


def capture_view(view_id, name, camera, tag_library, render_style) -> SavedView:
    """Snapshot the current camera, tag visibility and render style as a SavedView."""
    tag_visibility = {
        t.id: bool(t.visible)
        for t in tag_library.tags()
        if t.id != tag_library.UNTAGGED_ID
    }
    return SavedView(
        id=int(view_id),
        name=str(name),
        camera=CameraState.from_camera(camera),
        tag_visibility=tag_visibility,
        face_style=render_style.face_style.name,
        xray=bool(render_style.xray),
    )


def apply_tags_and_style(view, tag_library, render_style) -> None:
    """Restore tag visibility + render style from `view` (leaves the camera alone)."""
    for tid, visible in view.tag_visibility.items():
        tag_library.set_visible(int(tid), bool(visible))
    render_style.face_style = FaceStyle[view.face_style]
    render_style.xray = bool(view.xray)


def apply_view(view, camera, tag_library, render_style) -> None:
    """Restore all three: tags + style (instant) and the camera pose (direct)."""
    apply_tags_and_style(view, tag_library, render_style)
    view.camera.apply_to(camera)
```

The parameters are intentionally untyped (the codebase's convention for duck-typed
Qt/model objects). Because `ANN` is not in ruff's select list, untyped params need
**no** `# noqa` — do not add any; a `# noqa: ANN0xx` here would itself be an RUF100.

- [ ] **Step 4: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_capture.py -q && .venv/Scripts/python -m ruff check python/pluton/views/capture.py
```
Expected: PASS; ruff clean (zero findings — confirm no RUF100).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/views/capture.py tests/test_capture.py && git commit -F- <<'MSG'
feat(m7e): capture_view / apply_view helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 3: Orbit-decomposition tween math

**Files:**
- Create: `python/pluton/views/interpolate.py`
- Test: `tests/test_interpolate.py`

**Interfaces:**
- Consumes: `CameraState` from `pluton.io.document_codec`.
- Produces: `interpolate_pose(from_cam: CameraState, to_cam: CameraState, t: float) -> CameraState` — the eased-`t` pose. Decomposes each endpoint into `(target, azimuth, elevation, distance, fov)`, interpolates (azimuth via short-way wrap; target/elevation/distance/fov linear; up via normalized lerp), recomposes. World is **Z-up** (horizontal plane = XY), matching `Camera`.

- [ ] **Step 1: Write the failing tests** — `tests/test_interpolate.py`:

```python
import math

import numpy as np

from pluton.io.document_codec import CameraState
from pluton.views.interpolate import interpolate_pose


def _cam(pos, target=(0.0, 0.0, 0.0), up=(0.0, 0.0, 1.0), fov=45.0):
    return CameraState(position=tuple(pos), target=tuple(target), up=tuple(up), fov_y_deg=fov)


def test_t0_reproduces_from_pose():
    a = _cam((5.0, -3.0, 4.0), target=(1.0, 1.0, 0.5), fov=40.0)
    b = _cam((-2.0, 6.0, 9.0), target=(0.0, 0.0, 0.0), fov=60.0)
    out = interpolate_pose(a, b, 0.0)
    assert np.allclose(out.position, a.position, atol=1e-6)
    assert np.allclose(out.target, a.target, atol=1e-6)
    assert out.fov_y_deg == 40.0


def test_t1_reproduces_to_pose():
    a = _cam((5.0, -3.0, 4.0), fov=40.0)
    b = _cam((-2.0, 6.0, 9.0), target=(1.0, 0.0, 2.0), fov=60.0)
    out = interpolate_pose(a, b, 1.0)
    assert np.allclose(out.position, b.position, atol=1e-6)
    assert np.allclose(out.target, b.target, atol=1e-6)
    assert out.fov_y_deg == 60.0


def test_midpoint_orbits_distance_is_pinned():
    # Same target, distances 2 and 8; the midpoint eye must sit at distance 5
    # from the (interpolated) target — proving orbit decomposition, not a
    # straight-line lerp of the eye (which would give a different distance).
    a = _cam((2.0, 0.0, 0.0))     # distance 2 along +X
    b = _cam((0.0, 8.0, 0.0))     # distance 8 along +Y
    out = interpolate_pose(a, b, 0.5)
    tgt = np.array(out.target)
    dist = np.linalg.norm(np.array(out.position) - tgt)
    assert abs(dist - 5.0) < 1e-6


def test_azimuth_takes_short_way_across_pi_seam():
    # 170° -> -170° must pass through 180°, not sweep back through 0°.
    a170 = math.radians(170.0)
    an170 = math.radians(-170.0)
    a = _cam((math.cos(a170), math.sin(a170), 0.0))
    b = _cam((math.cos(an170), math.sin(an170), 0.0))
    out = interpolate_pose(a, b, 0.5)
    p = np.array(out.position)
    assert p[0] < -0.99          # near (-1, 0, 0): azimuth 180°
    assert abs(p[1]) < 1e-6
    # NOT near (+1, 0, 0), which is what sweeping through 0° would give:
    assert p[0] < 0.0


def test_identical_poses_are_constant_with_no_nan():
    a = _cam((3.0, 3.0, 3.0), target=(1.0, 1.0, 1.0))
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = interpolate_pose(a, a, t)
        assert np.all(np.isfinite(out.position))
        assert np.allclose(out.position, a.position, atol=1e-6)


def test_degenerate_zero_distance_does_not_nan():
    # Eye == target (distance 0) must not produce NaN.
    a = _cam((1.0, 1.0, 1.0), target=(1.0, 1.0, 1.0))
    b = _cam((4.0, 0.0, 0.0), target=(0.0, 0.0, 0.0))
    out = interpolate_pose(a, b, 0.5)
    assert np.all(np.isfinite(out.position))
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_interpolate.py -q
```
Expected: FAIL (`ModuleNotFoundError: pluton.views.interpolate`).

- [ ] **Step 3: Create `python/pluton/views/interpolate.py`**

```python
"""Camera tween math (M7e): orbit-decomposition interpolation between two
CameraStates. PURE numpy — no Qt — so it is deterministically unit-testable.

Each endpoint is decomposed into (target, azimuth, elevation, distance, fov)
and interpolated component-wise, then recomposed. This makes the eye ORBIT the
model (constant-ish framing, monotonic distance) instead of straight-lining
through geometry. Azimuth interpolates the short way across the +/-pi seam.
World is Z-up: the horizontal plane is XY, elevation is the angle above it.
"""

from __future__ import annotations

import math

import numpy as np

from pluton.io.document_codec import CameraState

_EPS = 1e-9


def _decompose(cam: CameraState):
    """(target, azimuth, elevation, distance, fov) for a CameraState (Z-up)."""
    target = np.array(cam.target, dtype=np.float64)
    eye = np.array(cam.position, dtype=np.float64)
    d = eye - target
    distance = float(np.linalg.norm(d))
    if distance < _EPS:
        return target, 0.0, 0.0, 0.0, float(cam.fov_y_deg)
    dn = d / distance
    azimuth = math.atan2(float(dn[1]), float(dn[0]))
    elevation = math.asin(max(-1.0, min(1.0, float(dn[2]))))
    return target, azimuth, elevation, distance, float(cam.fov_y_deg)


def _wrap(a: float) -> float:
    """Map an angle delta into (-pi, pi] so interpolation takes the short way."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _nlerp(a, b, t: float):
    """Normalized lerp of two unit-ish vectors (for the up vector)."""
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    v = va + (vb - va) * t
    n = float(np.linalg.norm(v))
    if n < _EPS:
        return tuple(float(x) for x in va)
    return tuple(float(x) for x in (v / n))


def interpolate_pose(from_cam: CameraState, to_cam: CameraState, t: float) -> CameraState:
    """The eased-`t` pose between two CameraStates (t clamped to [0, 1])."""
    t = max(0.0, min(1.0, float(t)))
    tgt0, az0, el0, dist0, fov0 = _decompose(from_cam)
    tgt1, az1, el1, dist1, fov1 = _decompose(to_cam)

    target = tgt0 + (tgt1 - tgt0) * t
    azimuth = az0 + _wrap(az1 - az0) * t
    elevation = _lerp(el0, el1, t)
    distance = _lerp(dist0, dist1, t)
    fov = _lerp(fov0, fov1, t)

    ce = math.cos(elevation)
    direction = np.array(
        [math.cos(azimuth) * ce, math.sin(azimuth) * ce, math.sin(elevation)],
        dtype=np.float64,
    )
    position = target + direction * distance
    up = _nlerp(from_cam.up, to_cam.up, t)

    return CameraState(
        position=tuple(float(x) for x in position),
        target=tuple(float(x) for x in target),
        up=up,
        fov_y_deg=float(fov),
    )
```

- [ ] **Step 4: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_interpolate.py -q && .venv/Scripts/python -m ruff check python/pluton/views/interpolate.py
```
Expected: PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/views/interpolate.py tests/test_interpolate.py && git commit -F- <<'MSG'
feat(m7e): orbit-decomposition camera tween (interpolate_pose)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 4: Model owns the ViewLibrary

**Files:**
- Modify: `python/pluton/model/model.py` (`__init__` ~line 14-22; `load_from` ~line 163-176)
- Test: `tests/test_model_views.py` (new)

**Interfaces:**
- Consumes: `ViewLibrary` from `pluton.views.view_library`.
- Produces: `Model.views: ViewLibrary` — initialized empty in `__init__`, copied by reference in `load_from` (mirroring `materials`/`tags`).

**Note on import (IMPORTANT — avoids a real import cycle):** Do NOT add a top-level `from pluton.views.view_library import ViewLibrary` in `model.py`. That would close a cycle: `model.py` → `views.view_library` → `io.document_codec` → `from pluton.model.model import Model` (line 21 of `document_codec.py`), and at that moment `model.py` is only partway loaded (its `class Model` not yet defined) → `ImportError`. Instead, use a **function-level** import inside `Model.__init__` — the same idiom `model.py` already uses for `mat_invert` inside `pick_instance`/`pick_face_local`. `load_from` needs no import (it just does `self.views = other.views`).

- [ ] **Step 1: Write the failing test** — `tests/test_model_views.py`:

```python
from pluton.model.model import Model
from pluton.views.view_library import ViewLibrary


def test_new_model_has_empty_view_library():
    m = Model()
    assert isinstance(m.views, ViewLibrary)
    assert m.views.views() == []


def test_load_from_copies_views():
    src = Model()
    from pluton.io.document_codec import CameraState
    from pluton.views.saved_view import SavedView
    cam = CameraState(position=(1.0, 0.0, 0.0), target=(0.0, 0.0, 0.0),
                      up=(0.0, 0.0, 1.0), fov_y_deg=45.0)
    src.views.add(SavedView(0, "Front", cam, {}, "SHADED", False))

    dst = Model()
    dst.load_from(src)
    assert [v.name for v in dst.views.views()] == ["Front"]
    assert dst.views is src.views   # adopted by reference, like tags/materials
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_model_views.py -q
```
Expected: FAIL (`AttributeError: 'Model' object has no attribute 'views'`).

- [ ] **Step 3: Edit `python/pluton/model/model.py`**

In `__init__`, after the `self._next_annotation_id = 0` line, add (function-level import to avoid the cycle described above):

```python
        # M7e: saved Scenes (camera + tags + style). Imported here, not at module
        # top, to avoid a model <-> io.document_codec import cycle.
        from pluton.views.view_library import ViewLibrary
        self.views = ViewLibrary()
```

In `load_from`, after the `self._next_annotation_id = other._next_annotation_id` line, add:

```python
        self.views = other.views
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_model_views.py tests/test_model.py -q
```
Expected: PASS (also confirms existing model tests still pass).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/model.py tests/test_model_views.py && git commit -F- <<'MSG'
feat(m7e): Model owns the ViewLibrary (rides load_from like tags/materials)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 5: Persistence — scenes + render style in .pluton

**Files:**
- Modify: `python/pluton/io/document_codec.py`
- Modify: `python/pluton/io/pluton_file.py`
- Modify: `python/pluton/ui/main_window.py` (one line in `_save_to`, ~line 873)
- Modify (call-site updates): `tests/test_annotation_persistence.py` (lines 25, 59, 122), `tests/test_document_codec.py` (line 136)
- Test: extend `tests/test_document_codec.py`, `tests/test_pluton_file.py`

**Interfaces:**
- Consumes: `ViewLibrary.to_records()` / `ViewLibrary.from_records(records, next_id)`; `RenderStyle`, `FaceStyle` from `pluton.viewport.render_style`.
- Produces:
  - `render_style_to_dict(style) -> dict`, `render_style_from_dict(d) -> RenderStyle`
  - `document_to_dict(model, camera, doc, render_style) -> dict` — **new required `render_style` param**; adds top-level `"scenes"` and `"style"`.
  - `document_from_dict(data) -> LoadedDocument` — sets `model.views`; returns a `LoadedDocument` now carrying `style: RenderStyle`.
  - `LoadedDocument(model, camera_state, units, style)` — new 4th field `style`.
  - `save_document(path, model, camera, doc, render_style)` — **new required `render_style` param**.
  - `SCHEMA_VERSION = 3`.

**Design note:** `render_style` is a **required** positional arg (not defaulted) so a caller can never silently persist a default style. The loaded scenes ride on `model.views`; `LoadedDocument` gains only `style` (no redundant `scenes` field), per the Global Constraints deviation.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_document_codec.py`:

```python
def test_document_dict_round_trips_scenes_and_style():
    from pluton.io.document_codec import (
        CameraState,
        document_from_dict,
        document_to_dict,
    )
    from pluton.model.model import Model
    from pluton.document import DocumentSettings
    from pluton.viewport.camera import Camera
    from pluton.viewport.render_style import FaceStyle, RenderStyle
    from pluton.views.saved_view import SavedView

    model = Model()
    cam_state = CameraState(position=(2.0, 2.0, 2.0), target=(0.0, 0.0, 0.0),
                            up=(0.0, 0.0, 1.0), fov_y_deg=50.0)
    model.views.add(SavedView(0, "Front", cam_state, {1: False}, "WIREFRAME", True))
    style = RenderStyle(face_style=FaceStyle.MONOCHROME, xray=True)

    data = document_to_dict(model, Camera(), DocumentSettings(), style)
    assert data["scenes"]["items"][0]["name"] == "Front"
    assert data["scenes"]["items"][0]["tag_visibility"] == {"1": False}
    assert data["style"] == {"face_style": "MONOCHROME", "xray": True}

    loaded = document_from_dict(data)
    assert [v.name for v in loaded.model.views.views()] == ["Front"]
    assert loaded.model.views.get(0).tag_visibility == {1: False}
    assert loaded.style.face_style is FaceStyle.MONOCHROME
    assert loaded.style.xray is True


def test_document_from_dict_without_scenes_or_style_uses_defaults():
    # A v2-shaped document (no "scenes"/"style" keys) still loads.
    from pluton.io.document_codec import document_from_dict, document_to_dict
    from pluton.model.model import Model
    from pluton.document import DocumentSettings
    from pluton.viewport.camera import Camera
    from pluton.viewport.render_style import RenderStyle

    data = document_to_dict(Model(), Camera(), DocumentSettings(), RenderStyle())
    del data["scenes"]
    del data["style"]
    loaded = document_from_dict(data)
    assert loaded.model.views.views() == []
    assert loaded.style == RenderStyle()   # RenderStyle default (SHADED, xray False)
```

Append to `tests/test_pluton_file.py`:

```python
def test_save_load_round_trips_scenes_and_style(tmp_path):
    from pluton.io.document_codec import CameraState
    from pluton.io.pluton_file import load_document, save_document
    from pluton.viewport.camera import Camera
    from pluton.viewport.render_style import FaceStyle, RenderStyle
    from pluton.views.saved_view import SavedView

    model = _model_with_box()
    cam_state = CameraState(position=(3.0, 3.0, 3.0), target=(0.0, 0.0, 0.0),
                            up=(0.0, 0.0, 1.0), fov_y_deg=55.0)
    model.views.add(SavedView(0, "Iso", cam_state, {}, "HIDDEN_LINE", False))
    style = RenderStyle(face_style=FaceStyle.WIREFRAME, xray=True)

    path = tmp_path / "scenes.pluton"
    save_document(path, model, Camera(), DocumentSettings(), style)
    loaded = load_document(path)

    assert [v.name for v in loaded.model.views.views()] == ["Iso"]
    assert loaded.style.face_style is FaceStyle.WIREFRAME
    assert loaded.style.xray is True


def test_v2_file_without_scenes_still_opens(tmp_path):
    # Hand-craft a v2 .pluton (schema_version 2, document.json without
    # scenes/style) and confirm the version gate accepts it and load yields
    # an empty ViewLibrary + default RenderStyle.
    import json
    import zipfile

    from pluton.io.document_codec import document_to_dict
    from pluton.io.pluton_file import load_document
    from pluton.viewport.camera import Camera
    from pluton.viewport.render_style import RenderStyle

    data = document_to_dict(_model_with_box(), Camera(), DocumentSettings(), RenderStyle())
    del data["scenes"]
    del data["style"]
    manifest = {"format": "pluton", "schema_version": 2, "app_version": "0.2.4"}

    path = tmp_path / "legacy.pluton"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("document.json", json.dumps(data))

    loaded = load_document(path)
    assert loaded.model.views.views() == []
    assert loaded.style == RenderStyle()
```

- [ ] **Step 2: Update the existing call sites so they compile** (do this before running — the new required param otherwise breaks import/collection):

In `tests/test_annotation_persistence.py`, add `from pluton.viewport.render_style import RenderStyle` to the imports, and change the three calls:
- line ~25: `document_to_dict(model, camera, doc)` → `document_to_dict(model, camera, doc, RenderStyle())`
- line ~59: `document_to_dict(model, Camera(), DocumentSettings())` → `document_to_dict(model, Camera(), DocumentSettings(), RenderStyle())`
- line ~122: same change as line 59.

In `tests/test_document_codec.py`, ensure `from pluton.viewport.render_style import RenderStyle` is imported, and change line ~136: `document_to_dict(model, cam, doc)` → `document_to_dict(model, cam, doc, RenderStyle())`.

In `tests/test_pluton_file.py`, add `from pluton.viewport.render_style import RenderStyle`, and change the four `save_document(...)` calls (lines ~34, 77, 84, 146) to pass `RenderStyle()` as the final arg, e.g. `save_document(path, _model_with_box(), Camera(), DocumentSettings(), RenderStyle())`.

- [ ] **Step 3: Run to verify the new tests fail** (and the collection succeeds after Step 2 edits)

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py tests/test_pluton_file.py -q
```
Expected: FAIL — the two new codec tests and two new file tests fail because `document_to_dict` doesn't yet accept `render_style` / emit `scenes`/`style` (a `TypeError: document_to_dict() takes 3 positional arguments but 4 were given`).

- [ ] **Step 4: Edit `python/pluton/io/document_codec.py`.**

Add to the imports at the top (after the existing model/tag imports):

```python
from pluton.viewport.render_style import FaceStyle, RenderStyle
```

Add the two render-style codec functions (place them just above `class CameraState`):

```python
def render_style_to_dict(style: RenderStyle) -> dict:
    """Serialize the document's render style (face style name + X-Ray)."""
    return {"face_style": style.face_style.name, "xray": bool(style.xray)}


def render_style_from_dict(d: dict | None) -> RenderStyle:
    """Rebuild a RenderStyle; missing/empty data yields the default (SHADED)."""
    if not d:
        return RenderStyle()
    return RenderStyle(face_style=FaceStyle[d["face_style"]], xray=bool(d.get("xray", False)))
```

Extend `LoadedDocument`:

```python
class LoadedDocument(NamedTuple):
    """Result of loading a .pluton document: model + camera + units + render style."""

    model: Model
    camera_state: CameraState
    units: Units
    style: RenderStyle
```

Change `document_to_dict` to take `render_style` and emit the two new keys:

```python
def document_to_dict(model: Model, camera, doc, render_style) -> dict:
    """Serialize the top-level document: units, camera, libraries, scenes, style, model."""
    return {
        "units": units_to_dict(doc.units),
        "camera": CameraState.from_camera(camera).to_dict(),
        "materials": {"next_id": model.materials.next_id,
                      "items": model.materials.to_records()},
        "tags": {"next_id": model.tags.next_id, "items": model.tags.to_records()},
        "scenes": {"next_id": model.views.next_id, "items": model.views.to_records()},
        "style": render_style_to_dict(render_style),
        "model": model_to_dict(model),
    }
```

Change `document_from_dict` to populate `model.views` and return `style` (note the **function-level** `ViewLibrary` import that breaks the import cycle):

```python
def document_from_dict(data: dict) -> LoadedDocument:
    """Rebuild a LoadedDocument. Any structural malformation anywhere in the
    document (including in nested geometry/model data) is normalized into
    PlutonFormatError — the only exception callers need to catch."""
    from pluton.views.view_library import ViewLibrary  # function-level: breaks import cycle
    try:
        model = model_from_dict(data["model"])
        model.materials = MaterialLibrary.from_records(
            data["materials"]["items"], data["materials"]["next_id"])
        model.tags = TagLibrary.from_records(
            data["tags"]["items"], data["tags"]["next_id"])
        scenes = data.get("scenes", {})
        model.views = ViewLibrary.from_records(
            scenes.get("items", []), scenes.get("next_id", 0))
        camera_state = CameraState.from_dict(data["camera"])
        units = units_from_dict(data["units"])
        style = render_style_from_dict(data.get("style"))
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise PlutonFormatError(f"malformed document: {e}") from e
    return LoadedDocument(model=model, camera_state=camera_state, units=units, style=style)
```

- [ ] **Step 5: Edit `python/pluton/io/pluton_file.py`.**

Bump the schema version:

```python
SCHEMA_VERSION = 3  # M7e: bumped for top-level "scenes" + "style"
```

Thread `render_style` through `save_document`:

```python
def save_document(path, model, camera, doc, render_style) -> None:
    """Write the document to `path` atomically (temp file + os.replace)."""
    path = Path(path)
    data = document_to_dict(model, camera, doc, render_style)
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
```

- [ ] **Step 6: Edit `python/pluton/ui/main_window.py`** — the one production call site (`_save_to`, ~line 873):

```python
            save_document(path, self._model, self._viewport.camera, self._doc, self._render_style)
```

(`self._render_style` already exists — created at `main_window.py:77`. The `_reset_document`/New/Open adoption of the loaded `style` is deferred to Task 9; loading is unaffected because `LoadedDocument.style` is simply not read yet.)

- [ ] **Step 7: Run the full I/O test group + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_document_codec.py tests/test_pluton_file.py tests/test_annotation_persistence.py -q && .venv/Scripts/python -m ruff check python/pluton/io/document_codec.py python/pluton/io/pluton_file.py && .venv/Scripts/python -m ruff check python/pluton/ui/main_window.py
```
Expected: PASS; `document_codec.py`/`pluton_file.py` ruff clean; `main_window.py` still exactly **9** findings (the `_save_to` edit is a same-line change, additive).

- [ ] **Step 8: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/document_codec.py python/pluton/io/pluton_file.py python/pluton/ui/main_window.py tests/test_document_codec.py tests/test_pluton_file.py tests/test_annotation_persistence.py && git commit -F- <<'MSG'
feat(m7e): persist scenes + render style in .pluton (schema 2 -> 3)

Adds top-level "scenes" and "style" keys; old v2 files still open (missing
keys default to an empty ViewLibrary + SHADED RenderStyle). Also fixes the
latent bug where X-Ray/Wireframe was lost on save (render style was never
persisted). save_document / document_to_dict gain a required render_style arg.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 6: ViewAnimator + viewport camera-input cancel hook

**Files:**
- Create: `python/pluton/viewport/view_animator.py`
- Modify: `python/pluton/viewport/viewport_widget.py` (add setter + two call sites)
- Test: `tests/test_view_animator.py`, extend `tests/test_viewport.py` (or create `tests/test_viewport_camera_input.py` if no such file exists)

**Interfaces:**
- Consumes: `interpolate_pose` (Task 3); `CameraState`; a live `Camera` (mutated in place via `CameraState.apply_to`); an `on_tick` zero-arg callable (`viewport.update`).
- Produces:
  - `ViewAnimator(camera, on_tick, parent=None)` (a `QObject`): `start(from_state, to_state)`, `cancel()`, `is_running` (property), `finished` (Signal). Drives a `QVariantAnimation` 0→1 over 700 ms, `QEasingCurve.InOutSine`, writing each interpolated pose into `camera` and calling `on_tick`. `_on_value(t)` and `_on_finished()` are the internal slots (callable directly in tests).
  - `ViewportWidget.set_camera_input_callback(fn)` + internal `_notify_camera_input()`, called at the start of the MMB-drag branch of `mouseMoveEvent` and at the top of `wheelEvent`.

- [ ] **Step 1: Write the failing tests** — `tests/test_view_animator.py`:

```python
import numpy as np

from pluton.io.document_codec import CameraState
from pluton.viewport.camera import Camera
from pluton.viewport.view_animator import ViewAnimator


def _state(pos, target=(0.0, 0.0, 0.0)):
    return CameraState(position=tuple(pos), target=tuple(target),
                       up=(0.0, 0.0, 1.0), fov_y_deg=45.0)


def test_on_value_writes_interpolated_pose(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 2.0, 0.0))
    a._from, a._to = s0, s1
    a._on_value(1.0)
    assert np.allclose(cam.position, (0.0, 2.0, 0.0), atol=1e-6)


def test_start_finishes_on_target(qtbot):
    cam = Camera()
    ticks = []
    a = ViewAnimator(cam, on_tick=lambda: ticks.append(1))
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 1.0))
    with qtbot.waitSignal(a.finished, timeout=3000):
        a.start(s0, s1)
    assert np.allclose(cam.position, (0.0, 3.0, 1.0), atol=1e-5)
    assert not a.is_running
    assert ticks   # on_tick fired during the animation


def test_cancel_stops_before_target(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    s0, s1 = _state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 0.0))
    a.start(s0, s1)
    a._on_value(0.5)          # advance partway deterministically
    a.cancel()
    assert not a.is_running
    # Camera is somewhere on the arc, not at the target:
    assert not np.allclose(cam.position, (0.0, 3.0, 0.0), atol=1e-3)


def test_retarget_midflight(qtbot):
    cam = Camera()
    a = ViewAnimator(cam, on_tick=None)
    a.start(_state((2.0, 0.0, 0.0)), _state((0.0, 3.0, 0.0)))
    a._on_value(0.5)
    # Retarget from wherever the camera is now to a new destination:
    from_now = CameraState.from_camera(cam)
    a.start(from_now, _state((5.0, 0.0, 0.0)))
    assert a.is_running
    a.cancel()
```

Extend the viewport test (append to `tests/test_viewport.py`; if that file does not exist, create `tests/test_viewport_camera_input.py` with the same imports the other viewport tests use):

```python
def test_camera_input_callback_fires(qtbot):
    from pluton.viewport.viewport_widget import ViewportWidget
    vp = ViewportWidget()
    qtbot.addWidget(vp)
    fired = []
    vp.set_camera_input_callback(lambda: fired.append(1))
    vp._notify_camera_input()
    assert fired == [1]
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_view_animator.py -q
```
Expected: FAIL (`ModuleNotFoundError: pluton.viewport.view_animator`).

- [ ] **Step 3: Create `python/pluton/viewport/view_animator.py`**

```python
"""ViewAnimator (M7e): tweens the live Camera between two CameraStates using a
Qt QVariantAnimation (built-in easing + timing). The pose math is delegated to
the pure interpolate_pose; this shell only drives ticks and writes the camera.

Only the camera is animated. Tag visibility and render style are applied
instantly by MainWindow before start() (matching SketchUp, where geometry
visibility snaps and the camera flies). Any camera input or a new recall
cancels/retargets the running animation.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation, Signal

from pluton.views.interpolate import interpolate_pose


class ViewAnimator(QObject):
    """Animate a Camera from one CameraState to another over a fixed duration."""

    finished = Signal()
    _DURATION_MS = 700

    def __init__(self, camera, on_tick, parent=None) -> None:
        super().__init__(parent)
        self._camera = camera
        self._on_tick = on_tick
        self._from = None
        self._to = None
        self._anim = None

    def start(self, from_state, to_state) -> None:
        """Begin (or retarget) the tween from `from_state` to `to_state`."""
        self.cancel()
        self._from = from_state
        self._to = to_state
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._DURATION_MS)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.valueChanged.connect(self._on_value)
        anim.finished.connect(self._on_finished)
        self._anim = anim
        anim.start()

    def _on_value(self, t) -> None:
        if self._from is None or self._to is None:
            return
        interpolate_pose(self._from, self._to, float(t)).apply_to(self._camera)
        if self._on_tick is not None:
            self._on_tick()

    def _on_finished(self) -> None:
        # Land exactly on target (guards against easing not hitting 1.0 cleanly).
        if self._to is not None:
            self._to.apply_to(self._camera)
            if self._on_tick is not None:
                self._on_tick()
        self._anim = None
        self.finished.emit()

    def cancel(self) -> None:
        """Stop any running animation, leaving the camera wherever it is."""
        if self._anim is not None:
            self._anim.stop()
            self._anim.valueChanged.disconnect(self._on_value)
            self._anim.finished.disconnect(self._on_finished)
            self._anim = None

    @property
    def is_running(self) -> bool:
        return self._anim is not None
```

- [ ] **Step 4: Edit `python/pluton/viewport/viewport_widget.py`.**

In `__init__`, after `self._units_provider = None` (~line 37), add:

```python
        self._camera_input_callback = None  # M7e — invoked when the user moves the camera
```

Add the setter + notifier near the other setters (after `set_units_provider`, ~line 66):

```python
    def set_camera_input_callback(self, fn) -> None:
        """M7e: install a zero-arg callable invoked when the user manipulates the
        camera (MMB orbit/pan, wheel zoom). MainWindow wires this to the view
        animator's cancel(), so a manual camera move interrupts a running tween."""
        self._camera_input_callback = fn

    def _notify_camera_input(self) -> None:
        if self._camera_input_callback is not None:
            self._camera_input_callback()
```

In `mouseMoveEvent`, inside the MMB-drag branch — immediately after the `if (self._dragging_button == Qt.MouseButton.MiddleButton and self._last_mouse_pos is not None):` guard opens (before computing `current`) — add:

```python
            self._notify_camera_input()
```

In `wheelEvent`, right after the `notches == 0` early-return block (before `cursor = event.position()`), add:

```python
        self._notify_camera_input()
```

- [ ] **Step 5: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_view_animator.py tests/test_viewport.py -q && .venv/Scripts/python -m ruff check python/pluton/viewport/view_animator.py python/pluton/viewport/viewport_widget.py
```
Expected: PASS; ruff clean. (If you created `tests/test_viewport_camera_input.py` instead, run that file.) Note `viewport_widget.py` has a pre-existing per-file `N802` ignore; the two additions introduce no new findings.

- [ ] **Step 6: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/view_animator.py python/pluton/viewport/viewport_widget.py tests/test_view_animator.py tests/test_viewport.py && git commit -F- <<'MSG'
feat(m7e): ViewAnimator (camera tween) + viewport camera-input cancel hook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

(If a separate `tests/test_viewport_camera_input.py` was created, stage it instead of `tests/test_viewport.py`.)

---

### Task 7: Undoable Scene-management commands

**Files:**
- Create: `python/pluton/commands/view_commands.py`
- Test: `tests/test_view_commands.py`

**Interfaces:**
- Consumes: `Command` ABC (`do(self, target)` / `undo(self, target)`); the command target is a `Model` whose `model.views` is a `ViewLibrary` (Task 1 API: `add/get/index_of/remove/insert/rename/replace_view/move`).
- Produces (all subclass `Command`, `target=model`):
  - `CreateViewCommand(view)` — `do` adds `view`; `undo` removes it by id; redo re-adds the same object.
  - `DeleteViewCommand(view_id)` — captures the view + its index on first `do`; `undo` re-inserts at that index.
  - `RenameViewCommand(view_id, new_name)` — captures old name on first `do` only; `undo` restores it.
  - `ReorderViewCommand(view_id, direction)` — records whether the move happened; `undo` reverses it only if it did.
  - `UpdateViewCommand(view_id, new_view)` — captures the prior view on first `do` only; `undo` restores it.

**Precedent:** `TagInstancesCommand` (`pluton/commands/tag_commands.py`) — the existing non-geometry, model-targeted command with first-do capture (`self._old`).

- [ ] **Step 1: Write the failing tests** — `tests/test_view_commands.py`:

```python
from pluton.commands.command_stack import CommandStack
from pluton.commands.view_commands import (
    CreateViewCommand,
    DeleteViewCommand,
    RenameViewCommand,
    ReorderViewCommand,
    UpdateViewCommand,
)
from pluton.io.document_codec import CameraState
from pluton.model.model import Model
from pluton.views.saved_view import SavedView


def _view(vid, name="V", fov=45.0):
    cam = CameraState(position=(float(vid), 0.0, 0.0), target=(0.0, 0.0, 0.0),
                      up=(0.0, 0.0, 1.0), fov_y_deg=fov)
    return SavedView(vid, name, cam, {}, "SHADED", False)


def _names(model):
    return [v.name for v in model.views.views()]


def test_create_do_undo_redo():
    model = Model()
    stack = CommandStack()
    view = _view(model.views.next_id, "A")
    stack.execute(CreateViewCommand(view), model)
    assert _names(model) == ["A"]
    stack.undo()
    assert _names(model) == []
    stack.redo()
    assert _names(model) == ["A"]
    assert model.views.get(0) is view   # same object re-attached on redo


def test_delete_restores_at_original_index():
    model = Model()
    stack = CommandStack()
    for i, n in enumerate("ABC"):
        model.views.add(_view(i, n))
    stack.execute(DeleteViewCommand(1), model)   # delete "B" (middle)
    assert _names(model) == ["A", "C"]
    stack.undo()
    assert _names(model) == ["A", "B", "C"]       # back in the middle
    stack.redo()
    assert _names(model) == ["A", "C"]


def test_rename_undo_restores_true_original():
    model = Model()
    stack = CommandStack()
    model.views.add(_view(0, "Old"))
    cmd = RenameViewCommand(0, "New")
    stack.execute(cmd, model)
    assert model.views.get(0).name == "New"
    # Mutate live state between do and undo — undo must still restore "Old":
    model.views.rename(0, "Externally Changed")
    stack.undo()
    assert model.views.get(0).name == "Old"


def test_reorder_do_undo():
    model = Model()
    stack = CommandStack()
    for i, n in enumerate("ABC"):
        model.views.add(_view(i, n))
    stack.execute(ReorderViewCommand(0, +1), model)  # move "A" down
    assert _names(model) == ["B", "A", "C"]
    stack.undo()
    assert _names(model) == ["A", "B", "C"]


def test_reorder_clamped_move_is_a_noop_on_undo():
    model = Model()
    stack = CommandStack()
    model.views.add(_view(0, "A"))
    model.views.add(_view(1, "B"))
    stack.execute(ReorderViewCommand(0, -1), model)  # "A" already first → no move
    assert _names(model) == ["A", "B"]
    stack.undo()                                      # must NOT move anything
    assert _names(model) == ["A", "B"]


def test_update_undo_restores_prior_snapshot():
    model = Model()
    stack = CommandStack()
    model.views.add(_view(0, "V", fov=30.0))
    new_view = _view(0, "V", fov=90.0)               # same id/name, new camera
    cmd = UpdateViewCommand(0, new_view)
    stack.execute(cmd, model)
    assert model.views.get(0).camera.fov_y_deg == 90.0
    # Mutate live between do and undo — undo restores the fov=30 snapshot:
    model.views.replace_view(0, _view(0, "V", fov=12.0))
    stack.undo()
    assert model.views.get(0).camera.fov_y_deg == 30.0
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_view_commands.py -q
```
Expected: FAIL (`ModuleNotFoundError: pluton.commands.view_commands`).

- [ ] **Step 3: Create `python/pluton/commands/view_commands.py`**

```python
"""Scene-management commands (M7e): undoable create/delete/rename/reorder/update
of SavedViews. All take the Model as their target and mutate model.views.

Recall (going TO a Scene) is deliberately NOT a command — it is a view change,
like an orbit, and bypasses the undo stack (matching SketchUp). Only management
operations are undoable. Captures happen on the FIRST do() only, so repeated
undo/redo restores the true original (the M7d Move/EditLabel lesson)."""

from __future__ import annotations

from pluton.commands.command import Command


class CreateViewCommand(Command):
    """Add a SavedView; undo removes it; redo re-attaches the same object."""

    name = "Create Scene"

    def __init__(self, view) -> None:
        self._view = view

    def do(self, model) -> None:
        model.views.add(self._view)

    def undo(self, model) -> None:
        model.views.remove(self._view.id)


class DeleteViewCommand(Command):
    """Remove a SavedView; undo restores it at its original index."""

    name = "Delete Scene"

    def __init__(self, view_id: int) -> None:
        self._id = int(view_id)
        self._view = None
        self._index = -1

    def do(self, model) -> None:
        if self._view is None:
            self._view = model.views.get(self._id)
            self._index = model.views.index_of(self._id)
        model.views.remove(self._id)

    def undo(self, model) -> None:
        if self._view is not None and self._index >= 0:
            model.views.insert(self._index, self._view)


class RenameViewCommand(Command):
    """Rename a SavedView; undo restores the original name (captured once)."""

    name = "Rename Scene"

    def __init__(self, view_id: int, new_name: str) -> None:
        self._id = int(view_id)
        self._new = str(new_name)
        self._old = None

    def do(self, model) -> None:
        if self._old is None:
            current = model.views.get(self._id)
            self._old = current.name if current is not None else ""
        model.views.rename(self._id, self._new)

    def undo(self, model) -> None:
        model.views.rename(self._id, self._old)


class ReorderViewCommand(Command):
    """Move a SavedView one place up/down; undo reverses it (only if it moved)."""

    name = "Reorder Scene"

    def __init__(self, view_id: int, direction: int) -> None:
        self._id = int(view_id)
        self._dir = int(direction)
        self._moved = False

    def do(self, model) -> None:
        self._moved = model.views.move(self._id, self._dir)

    def undo(self, model) -> None:
        if self._moved:
            model.views.move(self._id, -self._dir)


class UpdateViewCommand(Command):
    """Overwrite a SavedView's snapshot; undo restores the prior one (captured once)."""

    name = "Update Scene"

    def __init__(self, view_id: int, new_view) -> None:
        self._id = int(view_id)
        self._new = new_view
        self._old = None

    def do(self, model) -> None:
        if self._old is None:
            self._old = model.views.get(self._id)
        model.views.replace_view(self._id, self._new)

    def undo(self, model) -> None:
        if self._old is not None:
            model.views.replace_view(self._id, self._old)
```

- [ ] **Step 4: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_view_commands.py -q && .venv/Scripts/python -m ruff check python/pluton/commands/view_commands.py
```
Expected: PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/view_commands.py tests/test_view_commands.py && git commit -F- <<'MSG'
feat(m7e): undoable Scene-management commands (create/delete/rename/reorder/update)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 8: ScenesDock panel

**Files:**
- Create: `python/pluton/ui/scenes_dock.py`
- Test: `tests/test_scenes_dock.py`

**Interfaces:**
- Consumes: a `ViewLibrary` (`views()` → list of `SavedView`; each has `.id`, `.name`).
- Produces: `ScenesDock(QDockWidget)` with:
  - Signals: `create_requested()`, `update_requested(int)`, `delete_requested(int)`, `rename_requested(int, str)`, `reorder_requested(int, int)`, `recall_requested(int)`.
  - `set_library(library)` — rebind after Open/New. `refresh(select_id=None)` — rebuild rows, optionally reselect a row by id (never fires recall).

**Design:** a `QListWidget` of scene names (id on `Qt.ItemDataRole.UserRole`, double-click to rename) + Add / Update / Delete / ↑ / ↓ buttons. **Recall fires on `itemClicked`** (a mouse click on a row), NOT on `currentItemChanged` — so arrow-key navigation and programmatic reselection don't trigger recall storms. Update/Delete/↑/↓ act on the current row and are disabled when the list is empty. Clone of `TagsDock` structure (guarded `_rebuilding`, `UserRole` id round-trip, `set_library`).

- [ ] **Step 1: Write the failing tests** — `tests/test_scenes_dock.py`:

```python
from pluton.io.document_codec import CameraState
from pluton.ui.scenes_dock import ScenesDock
from pluton.views.saved_view import SavedView
from pluton.views.view_library import ViewLibrary


def _cam():
    return CameraState(position=(1.0, 0.0, 0.0), target=(0.0, 0.0, 0.0),
                       up=(0.0, 0.0, 1.0), fov_y_deg=45.0)


def _lib(names=("Front", "Top")):
    lib = ViewLibrary()
    for i, n in enumerate(names):
        lib.add(SavedView(i, n, _cam(), {}, "SHADED", False))
    return lib


def test_lists_scene_names_with_ids(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    assert dock._list.count() == 2
    from PySide6.QtCore import Qt
    assert dock._list.item(0).text() == "Front"
    assert int(dock._list.item(0).data(Qt.ItemDataRole.UserRole)) == 0


def test_add_button_emits_create(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    with qtbot.waitSignal(dock.create_requested, timeout=500):
        dock._add_btn.click()


def test_delete_emits_selected_id(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    dock._list.setCurrentRow(1)                 # select "Top" (id 1)
    with qtbot.waitSignal(dock.delete_requested, timeout=500) as blocker:
        dock._delete_btn.click()
    assert blocker.args == [1]


def test_reorder_buttons_emit_direction(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    dock._list.setCurrentRow(0)
    with qtbot.waitSignal(dock.reorder_requested, timeout=500) as down:
        dock._down_btn.click()
    assert down.args == [0, 1]
    with qtbot.waitSignal(dock.reorder_requested, timeout=500) as up:
        dock._up_btn.click()
    assert up.args == [0, -1]


def test_click_recalls(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    item = dock._list.item(1)
    with qtbot.waitSignal(dock.recall_requested, timeout=500) as blocker:
        dock._list.itemClicked.emit(item)
    assert blocker.args == [1]


def test_double_click_rename_emits(qtbot):
    dock = ScenesDock(_lib(), None)
    qtbot.addWidget(dock)
    item = dock._list.item(0)
    with qtbot.waitSignal(dock.rename_requested, timeout=500) as blocker:
        item.setText("Renamed")                 # triggers itemChanged
    assert blocker.args == [0, "Renamed"]


def test_buttons_disabled_when_empty(qtbot):
    dock = ScenesDock(ViewLibrary(), None)
    qtbot.addWidget(dock)
    assert dock._add_btn.isEnabled()
    assert not dock._delete_btn.isEnabled()
    assert not dock._update_btn.isEnabled()
    assert not dock._up_btn.isEnabled()
    assert not dock._down_btn.isEnabled()


def test_set_library_rebinds(qtbot):
    dock = ScenesDock(_lib(("A",)), None)
    qtbot.addWidget(dock)
    assert dock._list.count() == 1
    dock.set_library(_lib(("X", "Y", "Z")))
    assert dock._list.count() == 3
    assert dock._list.item(0).text() == "X"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_scenes_dock.py -q
```
Expected: FAIL (`ModuleNotFoundError: pluton.ui.scenes_dock`).

- [ ] **Step 3: Create `python/pluton/ui/scenes_dock.py`**

```python
"""The Scenes dock (M7e): a list panel of saved Scenes with recall + management.

Clicking a row recalls that Scene; Add captures the current view; Update
overwrites the selected Scene; Delete removes it; the arrows reorder. Rename is
inline (double-click). A near-clone of TagsDock. The dock only emits intent
signals — MainWindow routes them through CommandStack / the view animator.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ScenesDock(QDockWidget):
    """Saved-Scene list + Add/Update/Delete/reorder controls."""

    create_requested = Signal()
    update_requested = Signal(int)
    delete_requested = Signal(int)
    rename_requested = Signal(int, str)
    reorder_requested = Signal(int, int)
    recall_requested = Signal(int)

    def __init__(self, library, parent=None) -> None:
        super().__init__("Scenes", parent)
        self._library = library
        self._rebuilding = False

        container = QWidget(self)
        layout = QVBoxLayout(container)

        self._list = QListWidget(container)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.currentItemChanged.connect(lambda *_: self._update_button_states())
        layout.addWidget(self._list)

        self._add_btn = QPushButton("Add", container)
        self._add_btn.clicked.connect(lambda: self.create_requested.emit())
        self._update_btn = QPushButton("Update", container)
        self._update_btn.clicked.connect(self._on_update)
        self._delete_btn = QPushButton("Delete", container)
        self._delete_btn.clicked.connect(self._on_delete)
        row = QHBoxLayout()
        row.addWidget(self._add_btn)
        row.addWidget(self._update_btn)
        row.addWidget(self._delete_btn)
        layout.addLayout(row)

        self._up_btn = QPushButton("Move Up", container)
        self._up_btn.clicked.connect(lambda: self._on_reorder(-1))
        self._down_btn = QPushButton("Move Down", container)
        self._down_btn.clicked.connect(lambda: self._on_reorder(1))
        arrows = QHBoxLayout()
        arrows.addWidget(self._up_btn)
        arrows.addWidget(self._down_btn)
        layout.addLayout(arrows)

        self.setWidget(container)
        self._rebuild()

    # --- current-row helpers ---------------------------------------------

    def _current_id(self):
        item = self._list.currentItem()
        return None if item is None else int(item.data(Qt.ItemDataRole.UserRole))

    def _update_button_states(self) -> None:
        has = self._list.currentItem() is not None
        self._update_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        self._up_btn.setEnabled(has)
        self._down_btn.setEnabled(has)

    # --- rebuild ----------------------------------------------------------

    def _rebuild(self, select_id=None) -> None:
        self._rebuilding = True
        self._list.clear()
        for view in self._library.views():
            item = QListWidgetItem(view.name)
            item.setData(Qt.ItemDataRole.UserRole, view.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)
            if view.id == select_id:
                self._list.setCurrentItem(item)
        self._rebuilding = False
        self._update_button_states()

    # --- slots ------------------------------------------------------------

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if self._rebuilding or item is None:
            return
        self.recall_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._rebuilding or item is None:
            return
        vid = int(item.data(Qt.ItemDataRole.UserRole))
        self.rename_requested.emit(vid, item.text().strip())

    def _on_update(self) -> None:
        vid = self._current_id()
        if vid is not None:
            self.update_requested.emit(vid)

    def _on_delete(self) -> None:
        vid = self._current_id()
        if vid is not None:
            self.delete_requested.emit(vid)

    def _on_reorder(self, direction: int) -> None:
        vid = self._current_id()
        if vid is not None:
            self.reorder_requested.emit(vid, direction)

    # --- public API -------------------------------------------------------

    def refresh(self, select_id=None) -> None:
        """Rebuild rows from the current library (never fires recall)."""
        self._rebuild(select_id=select_id)

    def set_library(self, library) -> None:
        """Rebind to a new library (after file Open / New) and rebuild."""
        self._library = library
        self._rebuild()
```

- [ ] **Step 4: Run tests + ruff**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_scenes_dock.py -q && .venv/Scripts/python -m ruff check python/pluton/ui/scenes_dock.py
```
Expected: PASS; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/scenes_dock.py tests/test_scenes_dock.py && git commit -F- <<'MSG'
feat(m7e): ScenesDock panel (list + Add/Update/Delete/reorder, click-to-recall)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 9: MainWindow integration

**Files:**
- Modify: `python/pluton/ui/main_window.py`
- Modify: `python/pluton/ui/tags_dock.py` (add public `refresh()`)
- Test: `tests/test_main_window_scenes.py`

**Interfaces:**
- Consumes: `ScenesDock` (signals from Task 8); `ViewAnimator` (Task 6); `capture_view`/`apply_tags_and_style` (Task 2); the five commands (Task 7); `CameraState`, `RenderStyle`, `FaceStyle`.
- Produces: dock wired + tabified; animator owned + camera-input cancel wired; recall path; CRUD slots; render style adopted on New/Open (`_reset_document` gains a `style` param); `TagsDock.refresh()`.

**Constraint:** `main_window.py` stays additive — ruff finding count held at exactly **9**. Keep every new line ≤ 100 chars and add no `# noqa`.

- [ ] **Step 1: Write the failing tests** — `tests/test_main_window_scenes.py`:

```python
import numpy as np

from pluton.viewport.render_style import FaceStyle


def _make_window(qtbot):
    from pluton.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_create_scene_adds_to_library_and_dock(qtbot):
    win = _make_window(qtbot)
    win._on_create_view()
    assert len(win._model.views.views()) == 1
    assert win._scenes_dock._list.count() == 1


def test_recall_applies_style_and_starts_animation(qtbot):
    win = _make_window(qtbot)
    # Save a scene while in WIREFRAME:
    win._render_style.face_style = FaceStyle.WIREFRAME
    win._on_create_view()
    vid = win._model.views.views()[0].id
    # Switch to SHADED, then recall — style must snap back to WIREFRAME:
    win._render_style.face_style = FaceStyle.SHADED
    win._on_recall_view(vid)
    assert win._render_style.face_style is FaceStyle.WIREFRAME
    assert win._view_animator.is_running        # camera tween started
    win._view_animator.cancel()


def test_delete_scene_is_undoable(qtbot):
    win = _make_window(qtbot)
    win._on_create_view()
    vid = win._model.views.views()[0].id
    win._on_delete_view(vid)
    assert win._model.views.views() == []
    win._command_stack.undo()
    assert len(win._model.views.views()) == 1


def test_render_style_persists_through_save_new_open(qtbot, tmp_path):
    win = _make_window(qtbot)
    win._render_style.face_style = FaceStyle.MONOCHROME
    win._render_style.xray = True
    path = str(tmp_path / "styled.pluton")
    assert win._save_to(path) is True
    win._on_file_new()
    assert win._render_style.face_style is FaceStyle.SHADED   # reset by New
    # Re-open and confirm the saved style is adopted:
    from pluton.io.pluton_file import load_document
    loaded = load_document(path)
    win._reset_document(loaded.model, loaded.camera_state, loaded.units,
                        loaded.style, path)
    assert win._render_style.face_style is FaceStyle.MONOCHROME
    assert win._render_style.xray is True
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_scenes.py -q
```
Expected: FAIL (`AttributeError: 'MainWindow' object has no attribute '_on_create_view'`).

- [ ] **Step 3: Add `refresh()` to `python/pluton/ui/tags_dock.py`** — after `set_library` (or anywhere in the public section):

```python
    def refresh(self) -> None:
        """Rebuild the list from the current library (reflects programmatic changes)."""
        self._rebuild()
```

- [ ] **Step 4: Edit `python/pluton/ui/main_window.py` — imports.** Add near the other command/ui imports:

```python
from pluton.commands.view_commands import (
    CreateViewCommand,
    DeleteViewCommand,
    RenameViewCommand,
    ReorderViewCommand,
    UpdateViewCommand,
)
from pluton.ui.scenes_dock import ScenesDock
from pluton.viewport.view_animator import ViewAnimator
from pluton.views.capture import apply_tags_and_style, capture_view
```

`CameraState` and `RenderStyle` are already imported; `FaceStyle` is already imported (View menu). `Camera` is imported locally inside `_on_file_new`.

- [ ] **Step 5: Build the dock + animator.** In `__init__`, right after the Tags-dock block (after `self._tags_dock.assign_to_selection_requested.connect(self._on_assign_tag)`, ~line 131), add:

```python
        # Scenes dock (M7e) — tabbed with Materials/Tags on the right.
        self._scenes_dock = ScenesDock(self._model.views, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._scenes_dock)
        self.tabifyDockWidget(self._tags_dock, self._scenes_dock)
        self._scenes_dock.create_requested.connect(self._on_create_view)
        self._scenes_dock.update_requested.connect(self._on_update_view)
        self._scenes_dock.delete_requested.connect(self._on_delete_view)
        self._scenes_dock.rename_requested.connect(self._on_rename_view)
        self._scenes_dock.reorder_requested.connect(self._on_reorder_view)
        self._scenes_dock.recall_requested.connect(self._on_recall_view)

        # Camera tween animator (M7e). Owns the same live camera object the
        # viewport mutates in place; a manual camera move cancels a running tween.
        self._view_animator = ViewAnimator(self._viewport.camera, self._viewport.update, self)
        self._viewport.set_camera_input_callback(self._view_animator.cancel)
```

- [ ] **Step 6: Refresh the dock on undo/redo.** In `_on_after_undo_redo` (~line 739), add at the end of the method body:

```python
        self._scenes_dock.refresh()
```

- [ ] **Step 7: Add the View-menu toggle.** After the Tags-dock toggle (`self._view_menu.addAction(self._tags_dock_action)`, ~line 303), add:

```python
        self._scenes_dock_action = self._scenes_dock.toggleViewAction()
        self._view_menu.addAction(self._scenes_dock_action)
```

- [ ] **Step 8: Add the Scene slots.** Add a new section (e.g. after the File I/O section, near `_on_set_face_style`):

```python
    # --- Scenes (M7e) ----------------------------------------------------

    def _sync_render_style_ui(self) -> None:
        """Reflect self._render_style in the View menu + viewport (no signal echo)."""
        for st, action in self._face_style_actions.items():
            action.setChecked(st == self._render_style.face_style)
        self._xray_action.blockSignals(True)
        self._xray_action.setChecked(self._render_style.xray)
        self._xray_action.blockSignals(False)
        self._viewport.set_render_style(self._render_style)

    def _on_create_view(self) -> None:
        name = f"Scene {len(self._model.views.views()) + 1}"
        view = capture_view(self._model.views.next_id, name, self._viewport.camera,
                            self._model.tags, self._render_style)
        self._command_stack.execute(CreateViewCommand(view), self._model)
        self._scenes_dock.refresh(select_id=view.id)

    def _on_update_view(self, view_id: int) -> None:
        old = self._model.views.get(int(view_id))
        if old is None:
            return
        new_view = capture_view(old.id, old.name, self._viewport.camera,
                                self._model.tags, self._render_style)
        self._command_stack.execute(UpdateViewCommand(old.id, new_view), self._model)
        self._scenes_dock.refresh(select_id=old.id)

    def _on_delete_view(self, view_id: int) -> None:
        if self._model.views.get(int(view_id)) is None:
            return
        self._command_stack.execute(DeleteViewCommand(int(view_id)), self._model)
        self._scenes_dock.refresh()

    def _on_rename_view(self, view_id: int, name: str) -> None:
        name = str(name).strip()
        old = self._model.views.get(int(view_id))
        if old is None or not name or name == old.name:
            self._scenes_dock.refresh(select_id=int(view_id))
            return
        self._command_stack.execute(RenameViewCommand(int(view_id), name), self._model)
        self._scenes_dock.refresh(select_id=int(view_id))

    def _on_reorder_view(self, view_id: int, direction: int) -> None:
        self._command_stack.execute(
            ReorderViewCommand(int(view_id), int(direction)), self._model)
        self._scenes_dock.refresh(select_id=int(view_id))

    def _on_recall_view(self, view_id: int) -> None:
        view = self._model.views.get(int(view_id))
        if view is None:
            return
        apply_tags_and_style(view, self._model.tags, self._render_style)
        self._sync_render_style_ui()
        self._tags_dock.refresh()
        from_state = CameraState.from_camera(self._viewport.camera)
        self._view_animator.start(from_state, view.camera)
```

Note: `_on_create_view`/`_on_update_view`/etc. mark the document dirty automatically — `CommandStack.execute` fires the change listener that `main_window` already registered (`self._command_stack.add_change_listener(self._on_document_changed)`). Recall does NOT go through the stack, so it does not dirty the document (correct — a view change is not a document edit).

- [ ] **Step 9: Adopt style + rebind the dock on New/Open.** Change `_reset_document` signature and body (~line 931):

```python
    def _reset_document(self, model, camera_state, units, style, path) -> None:
        """Adopt a (model, camera, units, render style) into the live window, in place."""
        from dataclasses import replace
        self._model.load_from(model)
        self._materials_dock.set_library(self._model.materials)
        self._tags_dock.set_library(self._model.tags)
        self._scenes_dock.set_library(self._model.views)
        camera_state.apply_to(self._viewport.camera)
        self._view_animator.cancel()
        self._render_style = replace(style)
        self._sync_render_style_ui()
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
```

Update the two callers:

`_on_file_new` (~line 950) — pass a default `RenderStyle()`:

```python
    def _on_file_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        from pluton.units import Units
        from pluton.viewport.camera import Camera
        self._reset_document(Model(), CameraState.from_camera(Camera()), Units(),
                            RenderStyle(), None)
```

`_on_file_open` (~line 976) — pass `loaded.style`:

```python
        self._reset_document(loaded.model, loaded.camera_state, loaded.units,
                            loaded.style, path)
```

- [ ] **Step 10: Run the window tests + the broader UI suites + ruff finding count**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest tests/test_main_window_scenes.py tests/test_view_menu.py tests/test_main_window_tags.py tests/test_pluton_file.py -q && .venv/Scripts/python -m ruff check python/pluton/ui/main_window.py python/pluton/ui/tags_dock.py
```
Expected: tests PASS. `tags_dock.py` ruff clean. `main_window.py` ruff must report **exactly 9** findings (unchanged from baseline). If it reports more, the new code introduced a finding (most likely E501 line-too-long) — wrap the offending line to ≤ 100 chars; do not add `# noqa`.

- [ ] **Step 11: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py python/pluton/ui/tags_dock.py tests/test_main_window_scenes.py && git commit -F- <<'MSG'
feat(m7e): wire Scenes dock, animated recall, and style adoption into MainWindow

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 10: Full regression + master design-doc annotation

**Files:** Modify `docs/2026-05-16-pluton-design.md`

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass, well above the 977 baseline (M7e adds ~40+ tests across the 8 new test files).

- [ ] **Step 2: C++ regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure | tail -3)
```
Expected: 79/79 (Python-only milestone — kernel untouched).

- [ ] **Step 3: Full ruff sweep** (confirms no new lint across the whole tree, and main_window's count held)

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m ruff check python/pluton && echo "---main_window---" && .venv/Scripts/python -m ruff check python/pluton/ui/main_window.py
```
Expected: the only findings are `main_window.py`'s 9 pre-existing ones (issue #48); every new `pluton/views/*`, `view_animator.py`, `view_commands.py`, `scenes_dock.py` file is clean.

- [ ] **Step 4: Annotate the master design doc.** On the **M7** line (currently ends `... Remaining sub-milestones: **M7e** Scenes (saved cameras/views).`), after the M7d note append this **M7e** note, then replace the trailing "Remaining sub-milestones" sentence.

Append after the M7d sentence:

> **M7e** ✅ *(shipped v0.2.5)* — **Scenes** (saved views): the **Scenes dock** saves the current view — **camera + tag visibility + render style (Face Style / X-Ray)** — as a named Scene, recalled by clicking it with a **SketchUp-style animated camera tween** (orbit-decomposition interpolation, `QVariantAnimation` + `InOutSine`, ~700 ms; interrupted by any manual camera move). Scenes are managed with full undo (create / update / rename / delete / reorder via `CreateViewCommand` … `ReorderViewCommand`) and round-trip through `.pluton` (`schema_version` 2→3, new top-level `scenes` + `style` keys, older files still open). The spine is a pure `SavedView` snapshot + `ViewLibrary` on `Model` (mirroring `TagLibrary`) with a pure numpy `interpolate_pose` shared by nothing but tested in isolation; recall applies tags/style instantly and only the camera flies. Also persists the document render style for the first time (previously X-Ray/Wireframe was silently lost on save). Python-only (ctest stays 79/79).

Then change the trailing sentence:

- From: `Remaining sub-milestones: **M7e** Scenes (saved cameras/views).`
- To: `**All M7 sub-milestones (M7a–M7e) shipped.**`

- [ ] **Step 5: Confirm the M8 line is untouched**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && grep -c "M8:" docs/2026-05-16-pluton-design.md
```
Expected: unchanged from before the edit (record the number before editing; it must match after).

- [ ] **Step 6: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -F- <<'MSG'
docs(m7e): annotate master design M7 line — Scenes shipped, M7 complete

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

---

### Task 11: Release v0.2.5

**Files:** Modify `pyproject.toml` (line ~10), `CMakeLists.txt` (line ~15), `cpp/src/version.cpp` (line ~6)

**Note on outward-facing steps:** the local build/version/commit steps below are safe to run. **Push, tag, and issue-filing require explicit per-turn user authorization** — do the local steps, then stop and report; do not push/tag until the user says so.

- [ ] **Step 1: Bump the version in all three files** — `0.2.4` → `0.2.5`:
  - `pyproject.toml`: `version = "0.2.4"` → `version = "0.2.5"`
  - `CMakeLists.txt`: `VERSION 0.2.4` → `VERSION 0.2.5`
  - `cpp/src/version.cpp`: `return "0.2.4";` → `return "0.2.5";`

- [ ] **Step 2: Rebuild the editable install (picks up the C++ version string)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pip install -e . --no-build-isolation 2>&1 | tail -5
```
Expected: builds and reinstalls cleanly.

- [ ] **Step 3: Verify the reported version**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -c "from pluton._core import version; print(version())"
```
Expected: `0.2.5`.

- [ ] **Step 4: Final full regression at 0.2.5**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass.

- [ ] **Step 5: Create the signed release commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -F- <<'MSG'
release: v0.2.5 — Scenes / saved views (M7e)

Named Scenes capturing camera + tag visibility + render style, recalled with
an animated orbit-decomposition camera tween, managed via an undoable Scenes
dock, and persisted through .pluton (schema 2 -> 3). Completes M7. Also
persists the document render style for the first time. Python-only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
MSG
```

- [ ] **Step 6: Verify the release commit is signed**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git cat-file -p HEAD | grep -c "BEGIN SSH SIGNATURE"
```
Expected: `1`. (A `git log --show-signature` printing "No signature" is the known local `allowedSignersFile` gap, not a failure — the `grep -c` above is the source of truth.)

- [ ] **Step 7: STOP — report to the user.** Local release is complete (version bumped, rebuilt, verified `0.2.5`, full suite green, signed release commit created). **Do not push or tag** until the user authorizes it. When authorized: push `main`, then create + push a signed `v0.2.5` tag (verify `git cat-file -p v0.2.5 | grep -c "BEGIN SSH SIGNATURE"` == 1), confirm CI green on both platforms, and file any carry-over issues.

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- SavedView / ViewLibrary spine → Task 1. capture/apply → Task 2. interpolate → Task 3.
- Model.views + load_from → Task 4. Persistence (scenes+style, schema bump, back-compat) → Task 5.
- Animated recall + interrupt (ViewAnimator + camera-input cancel) → Task 6.
- Undoable management commands → Task 7. ScenesDock (Add/Update/Delete/reorder, click-recall, rename) → Task 8.
- MainWindow wiring, recall path, style adoption on New/Open, View-menu toggle, undo/redo refresh → Task 9.
- Regression + design-doc annotation → Task 10. Release v0.2.5 → Task 11.
- Testing strategy (all 8 suites) → distributed across Tasks 1–9 as written.

**2. Placeholder scan:** no TBD/TODO; every code step shows complete code; every test step shows the actual assertions.

**3. Type/name consistency:** `SavedView(id,name,camera,tag_visibility,face_style,xray)`, `ViewLibrary.add/get/index_of/remove/insert/rename/replace_view/move/views/next_id/to_records/from_records`, `capture_view`/`apply_tags_and_style`/`apply_view`, `interpolate_pose`, `ViewAnimator(camera,on_tick,parent)` with `start/cancel/is_running/finished/_on_value/_on_finished`, the five `*ViewCommand` classes, `ScenesDock` signals (`create_requested`/`update_requested(int)`/`delete_requested(int)`/`rename_requested(int,str)`/`reorder_requested(int,int)`/`recall_requested(int)`) and `refresh(select_id)`/`set_library` — all used identically across tasks. `document_to_dict(model,camera,doc,render_style)` and `save_document(...,render_style)` and `_reset_document(model,camera_state,units,style,path)` are consistent between the persistence task (5), the animator/style-adoption task (9), and every call site each names.

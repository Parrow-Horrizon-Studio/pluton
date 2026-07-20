# M7d — Dimensions & Annotations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent, selectable linear **dimensions** and **text labels with leaders**, drawn screen-space over the viewport, stored per editing context, round-tripped through `.pluton`, and fully editable (select / erase / retype / move). Ship as **v0.2.4**.

**Architecture:** A pure `plan_annotation` draw plan is the single source of truth — **both** the `QPainter` renderer and the picker consume it. Entities live in `Definition.annotations` (per-context, so they ride moved groups). Measurement text is derived at draw time from the document's units.

**Tech Stack:** Python 3.13 + numpy; PySide6 (`QPainter` text, `QInputDialog` text entry); pytest (+ pytest-qt).

**Spec:** `docs/2026-07-14-M7d-annotations-design.md` (decisions D1–D12).

## Global Constraints

- **Purity boundary:** `annotations/draw_plan.py` is PURE (numpy only — no Qt/GL/Model). It is where ALL annotation geometry/layout lives. `viewport/annotation_painter.py` executes a plan against a painter-like object and holds no layout logic. Rendering and picking MUST consume the same plan (D7).
- **Per-context storage (D2):** annotations live in `Definition.annotations`; coordinates are context-local. Ids come from `Model` and are globally unique, but selection/picking are scoped to the **active context** (like edges/faces).
- **Derived text (D8):** dimension measurement text is computed from the WORLD distance and the document `Units` at draw time — never stored.
- **No kernel change** → `ctest` stays **79/79**.
- **`# noqa` RULE (repo ruff `select=["E","F","W","I","N","UP","B","C4","RUF"]` — ANN NOT enabled):** do **NOT** write any `# noqa` in new code (an unused noqa is itself RUF100). New files must be genuinely `ruff check`-clean. Follow `wall_tool.py`/`opening_tool.py`/`roof_tool.py` (no noqa on untyped `snap` params), NOT the older `rectangle_tool.py`.
- **Tests:** `.venv/Scripts/python` explicitly; `timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Baseline (v0.2.3): **852 pytest + 79/79 ctest**. **NEVER** broad `ruff --fix` on `main_window.py` (issue #48 — exactly 9 deliberate pre-existing findings: 5 RUF100 + 3 E501 + 1 I001; additive-only, keep it at 9).
- **Git:** stage specific files only (no `git add -A`). SSH-signed; never `--no-verify`/`--amend`/`--no-gpg-sign`. Trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. On `main`. Verify sig via `git cat-file -p <sha> | grep -c "BEGIN SSH SIGNATURE"` (==1).
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) edited ONLY in the release task. `0.2.3` → `0.2.4`.
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.

---

## File Structure

- Create `python/pluton/model/annotation.py` — `Dimension`, `Label` (T1).
- Modify `python/pluton/model/definition.py` — `annotations` list (T1).
- Modify `python/pluton/model/model.py` — `_next_annotation_id` + `new_annotation_id()` (T1).
- Create `python/pluton/annotations/__init__.py`, `python/pluton/annotations/draw_plan.py` — pure plan (T2 dimensions, T3 labels).
- Create `python/pluton/viewport/annotation_painter.py` — plan executor (T4).
- Modify `python/pluton/viewport/viewport_widget.py` — paint hook (T4).
- Create `python/pluton/commands/annotation_commands.py` — 4 commands (T5).
- Modify `python/pluton/io/document_codec.py` — annotations block + schema bump (T6).
- Create `python/pluton/annotations/picking.py` — `pick_annotation` (T7).
- Modify `python/pluton/selection.py` — `annotations` set (T7).
- Create `python/pluton/tools/dimension_tool.py` (T8), `python/pluton/tools/text_tool.py` (T9).
- Modify `python/pluton/tools/select_tool.py` (T10), `erase_tool.py` (T11), `move_tool.py` (T12).
- Modify `python/pluton/ui/main_window.py` — register, shortcuts, menus, Delete, edit-text prompt (T11/T12/T13; additive, issue #48).
- Tests: `tests/test_annotation_entities.py`, `test_draw_plan_dimension.py`, `test_draw_plan_label.py`, `test_annotation_painter.py`, `test_annotation_commands.py`, `test_annotation_persistence.py`, `test_annotation_picking.py`, `test_dimension_tool.py`, `test_text_tool.py`, `test_annotation_select_erase.py`, `test_annotation_edit_move.py`, `test_main_window_annotations.py`.

---

### Task 1: Annotation entities + per-context storage

**Files:** Create `python/pluton/model/annotation.py`; Modify `python/pluton/model/definition.py`, `python/pluton/model/model.py`; Test `tests/test_annotation_entities.py`

**Interfaces:**
- Produces: `Dimension(id, p1, p2, offset)` and `Label(id, anchor, text_pos, text)` — frozen-ish dataclasses holding context-local 3-tuples; `Definition.annotations: list`; `Model.new_annotation_id() -> int`. Consumed by every later task.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_entities.py`:

```python
from __future__ import annotations

from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def test_dimension_holds_local_points():
    d = Dimension(id=1, p1=(0.0, 0.0, 0.0), p2=(3.0, 0.0, 0.0), offset=(0.0, -0.5, 0.0))
    assert d.p1 == (0.0, 0.0, 0.0)
    assert d.p2 == (3.0, 0.0, 0.0)
    assert d.offset == (0.0, -0.5, 0.0)
    assert d.kind == "dimension"


def test_label_holds_anchor_text_pos_and_text():
    lab = Label(id=2, anchor=(1.0, 0.0, 0.0), text_pos=(2.0, 1.0, 0.0), text="Load-bearing")
    assert lab.anchor == (1.0, 0.0, 0.0)
    assert lab.text_pos == (2.0, 1.0, 0.0)
    assert lab.text == "Load-bearing"
    assert lab.kind == "label"


def test_definition_starts_with_no_annotations():
    model = Model()
    assert model.active_context.annotations == []


def test_annotation_ids_are_unique_and_increasing():
    model = Model()
    a = model.new_annotation_id()
    b = model.new_annotation_id()
    assert isinstance(a, int) and b == a + 1


def test_annotations_are_stored_per_context():
    model = Model()
    root = model.active_context
    grp = model.new_definition("G", is_group=True)
    inst = model.new_instance(grp)
    root.children.append(inst)
    root.annotations.append(Dimension(model.new_annotation_id(), (0, 0, 0), (1, 0, 0), (0, -1, 0)))
    grp.annotations.append(Label(model.new_annotation_id(), (0, 0, 0), (1, 1, 0), "inside"))
    assert len(root.annotations) == 1
    assert len(grp.annotations) == 1
    assert root.annotations[0].id != grp.annotations[0].id
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_entities.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.model.annotation`).

- [ ] **Step 3: Implement**

`python/pluton/model/annotation.py`:

```python
"""Annotation entities (M7d): linear dimensions and leader text labels.

Both store CONTEXT-LOCAL coordinates as plain 3-tuples and live in
Definition.annotations, so they ride along when their group/component moves.
Pure data — no Model/Scene/Qt/GL imports. A dimension's measurement text is
NOT stored; it is derived at draw time from the world distance and the
document's units.
"""
from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float, float]


def _pt(value) -> Point:
    x, y, z = value
    return (float(x), float(y), float(z))


@dataclass
class Dimension:
    """A linear dimension between two local points.

    `offset` is a local vector from the p1->p2 midpoint to the dimension-line
    midpoint (it positions the dimension line away from the geometry).
    """

    id: int
    p1: Point
    p2: Point
    offset: Point
    kind: str = "dimension"

    def __post_init__(self) -> None:
        self.id = int(self.id)
        self.p1 = _pt(self.p1)
        self.p2 = _pt(self.p2)
        self.offset = _pt(self.offset)


@dataclass
class Label:
    """A text note: an anchor point, where the text sits, and the text."""

    id: int
    anchor: Point
    text_pos: Point
    text: str
    kind: str = "label"

    def __post_init__(self) -> None:
        self.id = int(self.id)
        self.anchor = _pt(self.anchor)
        self.text_pos = _pt(self.text_pos)
        self.text = str(self.text)
```

In `python/pluton/model/definition.py`, add to `Definition.__init__` after `self.instances: list[Instance] = []`:

```python
        self.annotations: list = []   # M7d: per-context Dimension/Label entities
```

In `python/pluton/model/model.py`, add to `Model.__init__` after `self.opening_definitions = {}`:

```python
        self._next_annotation_id = 0   # M7d: model-wide unique annotation ids
```

and add a method next to `new_instance`:

```python
    def new_annotation_id(self) -> int:
        """Allocate a model-wide unique annotation id."""
        annotation_id = self._next_annotation_id
        self._next_annotation_id += 1
        return annotation_id
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_entities.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/model/annotation.py tests/test_annotation_entities.py
```
Expected: 5 passed; ruff clean (and `model.py`/`definition.py` gain no new ruff findings — check each with `ruff check` and confirm the count is unchanged; do NOT autofix).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/model/annotation.py python/pluton/model/definition.py python/pluton/model/model.py tests/test_annotation_entities.py && git commit -m "$(cat <<'EOF'
feat(m7d): annotation entities + per-context storage

Dimension (p1/p2/offset) and Label (anchor/text_pos/text) as pure local-coordinate
dataclasses, stored in Definition.annotations so they ride moved groups. Model
allocates globally-unique annotation ids.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Pure draw plan — dimensions

**Files:** Create `python/pluton/annotations/__init__.py`, `python/pluton/annotations/draw_plan.py`; Test `tests/test_draw_plan_dimension.py`

**Interfaces:**
- Consumes: `Camera.world_to_screen(world_xyz, w, h) -> (sx, sy, depth) | None`; `pluton.units.format_length`.
- Produces: `AnnotationDraw(segments_px, texts, hit_boxes)`, `TextDraw(text, x, y, align)`, and `plan_annotation(ann, world_transform, camera, width, height, units) -> AnnotationDraw | None`. Labels are added in Task 3. Consumed by the painter (T4) and the picker (T7).

- [ ] **Step 1: Write the failing test**

`tests/test_draw_plan_dimension.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.annotations.draw_plan import plan_annotation
from pluton.model.annotation import Dimension
from pluton.units import Units


class _FlatCamera:
    """Orthographic-ish stand-in: x,y map straight to pixels, z is depth."""

    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)


def _plan(dim, camera=None):
    return plan_annotation(dim, np.eye(4), camera or _FlatCamera(), 640, 480, Units())


def test_dimension_plan_has_line_ticks_extensions_and_text():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    assert plan is not None
    # 1 dimension line + 2 extension lines + 2 ticks = 5 segments
    assert len(plan.segments_px) == 5
    assert len(plan.texts) == 1
    assert len(plan.hit_boxes) >= 1


def test_dimension_text_is_derived_from_world_distance():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    # 4 m at default (metric) units
    assert "4" in plan.texts[0].text


def test_dimension_text_follows_the_world_transform_scale():
    # a 2x uniform scale makes the same local 4 m measure 8 m in the world
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    m = np.eye(4)
    m[0, 0] = m[1, 1] = m[2, 2] = 2.0
    plan = plan_annotation(d, m, _FlatCamera(), 640, 480, Units())
    assert "8" in plan.texts[0].text


def test_dimension_line_sits_at_the_offset_not_on_the_geometry():
    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    plan = _plan(d)
    # geometry is at world y=0 -> screen y=200; offset -2 -> screen y=220
    ys = [seg[1] for seg in plan.segments_px] + [seg[3] for seg in plan.segments_px]
    assert max(ys) > 215.0


def test_point_behind_camera_yields_no_plan():
    class _Behind:
        def world_to_screen(self, world_xyz, width, height):
            return None

    d = Dimension(1, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    assert _plan(d, _Behind()) is None


def test_degenerate_zero_length_dimension_yields_no_plan():
    d = Dimension(1, (1.0, 1.0, 0.0), (1.0, 1.0, 0.0), (0.0, -2.0, 0.0))
    assert _plan(d) is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_draw_plan_dimension.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.annotations.draw_plan`).

- [ ] **Step 3: Implement**

`python/pluton/annotations/__init__.py`:

```python
"""Annotation layout, rendering plans and picking (M7d)."""
```

`python/pluton/annotations/draw_plan.py`:

```python
"""Pure screen-space layout for annotations (M7d).

plan_annotation turns an annotation plus a camera into screen-space primitives:
line segments, text placements and hit boxes. It is the SINGLE source of truth —
the QPainter renderer draws the plan and the picker hit-tests the same plan, so
what the user can click is exactly what they can see.

Numpy only: no Qt, no GL, no Model imports. All sizes are in pixels, so the
annotation keeps a constant on-screen size at any zoom.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pluton.units import format_length

# Pixel constants (annotation styling is fixed in M7d — see design D11).
FONT_PX = 12.0
_CHAR_W = 0.55 * FONT_PX      # rough advance width, enough for hit boxes
_TEXT_GAP_PX = 5.0            # text sits this far above the dimension line
_EXT_GAP_PX = 4.0             # extension line starts this far off the geometry
_EXT_OVERSHOOT_PX = 6.0       # ...and runs this far past the dimension line
_TICK_PX = 6.0                # half-length of a 45-degree tick
_EPS = 1e-9


@dataclass
class TextDraw:
    text: str
    x: float
    y: float
    align: str = "center"      # "center" | "left" | "right"


@dataclass
class AnnotationDraw:
    annotation_id: int
    segments_px: list = field(default_factory=list)   # (x1, y1, x2, y2)
    texts: list = field(default_factory=list)         # TextDraw
    hit_boxes: list = field(default_factory=list)     # (x0, y0, x1, y1)


def _to_world(point, world_transform):
    p = np.asarray(point, dtype=np.float64)
    return (np.asarray(world_transform, dtype=np.float64) @ np.append(p, 1.0))[:3]


def _vec_to_world(vec, world_transform):
    v = np.asarray(vec, dtype=np.float64)
    return np.asarray(world_transform, dtype=np.float64)[:3, :3] @ v


def _project(world_point, camera, width, height):
    hit = camera.world_to_screen(np.asarray(world_point, dtype=np.float64), width, height)
    if hit is None:
        return None
    return np.array([float(hit[0]), float(hit[1])], dtype=np.float64)


def _unit(v):
    n = float(np.linalg.norm(v))
    if n < _EPS:
        return None
    return v / n


def _text_box(text, x, y, align):
    w = max(len(text), 1) * _CHAR_W
    h = FONT_PX
    if align == "center":
        x0 = x - w / 2.0
    elif align == "right":
        x0 = x - w
    else:
        x0 = x
    return (x0, y - h, x0 + w, y)


def _segment_box(seg, pad=3.0):
    x0, y0, x1, y1 = seg
    return (min(x0, x1) - pad, min(y0, y1) - pad, max(x0, x1) + pad, max(y0, y1) + pad)


def plan_annotation(annotation, world_transform, camera, width, height, units):
    """Return an AnnotationDraw for `annotation`, or None if it cannot be drawn."""
    if getattr(annotation, "kind", None) == "dimension":
        return _plan_dimension(annotation, world_transform, camera, width, height, units)
    return None


def _plan_dimension(dim, world_transform, camera, width, height, units):
    p1_w = _to_world(dim.p1, world_transform)
    p2_w = _to_world(dim.p2, world_transform)
    off_w = _vec_to_world(dim.offset, world_transform)
    measured = float(np.linalg.norm(p2_w - p1_w))
    if measured < _EPS:
        return None

    p1_px = _project(p1_w, camera, width, height)
    p2_px = _project(p2_w, camera, width, height)
    d1_px = _project(p1_w + off_w, camera, width, height)
    d2_px = _project(p2_w + off_w, camera, width, height)
    if p1_px is None or p2_px is None or d1_px is None or d2_px is None:
        return None

    along = _unit(d2_px - d1_px)
    if along is None:
        return None
    perp = np.array([-along[1], along[0]], dtype=np.float64)

    plan = AnnotationDraw(annotation_id=dim.id)

    # dimension line
    dim_seg = (float(d1_px[0]), float(d1_px[1]), float(d2_px[0]), float(d2_px[1]))
    plan.segments_px.append(dim_seg)

    # extension lines: small gap off the geometry, slight overshoot past the line
    for geom_px, dim_px in ((p1_px, d1_px), (p2_px, d2_px)):
        direction = _unit(dim_px - geom_px)
        if direction is None:
            continue
        start = geom_px + direction * _EXT_GAP_PX
        end = dim_px + direction * _EXT_OVERSHOOT_PX
        plan.segments_px.append(
            (float(start[0]), float(start[1]), float(end[0]), float(end[1]))
        )

    # 45-degree tick terminators, bisecting along/perp at each end
    tick_dir = _unit(along + perp)
    if tick_dir is not None:
        for end_px in (d1_px, d2_px):
            a = end_px - tick_dir * _TICK_PX
            b = end_px + tick_dir * _TICK_PX
            plan.segments_px.append((float(a[0]), float(a[1]), float(b[0]), float(b[1])))

    # measurement text, above the line on the side away from the geometry
    mid_dim = (d1_px + d2_px) / 2.0
    mid_geom = (p1_px + p2_px) / 2.0
    away = perp if float(np.dot(perp, mid_dim - mid_geom)) >= 0.0 else -perp
    text_at = mid_dim + away * _TEXT_GAP_PX
    label = format_length(measured, units)
    text = TextDraw(text=label, x=float(text_at[0]), y=float(text_at[1]), align="center")
    plan.texts.append(text)

    plan.hit_boxes.append(_text_box(label, text.x, text.y, text.align))
    plan.hit_boxes.append(_segment_box(dim_seg))
    return plan
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_draw_plan_dimension.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/annotations/ tests/test_draw_plan_dimension.py
```
Expected: 6 passed; ruff clean. (If `format_length(meters, units)` has a different signature, ground it against `python/pluton/units.py` and adjust the call only.)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/annotations/__init__.py python/pluton/annotations/draw_plan.py tests/test_draw_plan_dimension.py && git commit -m "$(cat <<'EOF'
feat(m7d): pure screen-space draw plan for dimensions

plan_annotation projects a Dimension through the camera and lays out the
architectural anatomy in pixels: extension lines with gap + overshoot, 45-degree
tick terminators, and derived measurement text above an unbroken dimension line,
plus hit boxes. Pure numpy — the single source of truth for both rendering and
picking.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Pure draw plan — labels (classic callout)

**Files:** Modify `python/pluton/annotations/draw_plan.py`; Test `tests/test_draw_plan_label.py`

**Interfaces:**
- Produces: `plan_annotation` also handles `Label` — arrowhead at the anchor, slanted leader into a horizontal landing, text on the landing, side auto-flipping.

- [ ] **Step 1: Write the failing test**

`tests/test_draw_plan_label.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.annotations.draw_plan import plan_annotation
from pluton.model.annotation import Label
from pluton.units import Units


class _FlatCamera:
    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)


def _plan(lab, camera=None):
    return plan_annotation(lab, np.eye(4), camera or _FlatCamera(), 640, 480, Units())


def test_label_plan_has_leader_landing_arrow_and_text():
    lab = Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "Load-bearing")
    plan = _plan(lab)
    assert plan is not None
    # leader + landing + 2 arrowhead strokes = 4 segments
    assert len(plan.segments_px) == 4
    assert len(plan.texts) == 1
    assert plan.texts[0].text == "Load-bearing"


def test_landing_is_horizontal():
    lab = Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    plan = _plan(lab)
    # exactly one segment is perfectly horizontal (the landing)
    horiz = [s for s in plan.segments_px if abs(s[1] - s[3]) < 1e-9]
    assert len(horiz) == 1


def test_text_side_flips_when_text_is_left_of_the_anchor():
    right = _plan(Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note"))
    left = _plan(Label(2, (5.0, 0.0, 0.0), (0.0, 3.0, 0.0), "note"))
    assert right.texts[0].align == "left"
    assert left.texts[0].align == "right"


def test_label_hit_boxes_cover_text_and_leader():
    lab = Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    plan = _plan(lab)
    assert len(plan.hit_boxes) >= 2


def test_label_behind_camera_yields_no_plan():
    class _Behind:
        def world_to_screen(self, world_xyz, width, height):
            return None

    assert _plan(Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "n"), _Behind()) is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_draw_plan_label.py -q -p no:cacheprovider
```
Expected: FAIL (`plan_annotation` returns None for labels → `assert plan is not None`).

- [ ] **Step 3: Implement** — add the label constants next to the others, extend the dispatch, and append `_plan_label`.

Add constants after `_TICK_PX`:

```python
_LANDING_PX = 26.0            # horizontal landing under the text
_ARROW_PX = 9.0               # arrowhead stroke length
_ARROW_SPREAD = 0.42          # radians each side of the leader direction
```

Extend the dispatch in `plan_annotation` (before the final `return None`):

```python
    if getattr(annotation, "kind", None) == "label":
        return _plan_label(annotation, world_transform, camera, width, height)
```

Append:

```python
def _plan_label(label, world_transform, camera, width, height):
    anchor_w = _to_world(label.anchor, world_transform)
    text_w = _to_world(label.text_pos, world_transform)
    anchor_px = _project(anchor_w, camera, width, height)
    text_px = _project(text_w, camera, width, height)
    if anchor_px is None or text_px is None:
        return None

    plan = AnnotationDraw(annotation_id=label.id)
    to_right = float(text_px[0]) >= float(anchor_px[0])
    sign = 1.0 if to_right else -1.0
    # the landing runs from the elbow toward the text side
    elbow = np.array([float(text_px[0]) - sign * _LANDING_PX, float(text_px[1])])

    leader = (float(anchor_px[0]), float(anchor_px[1]), float(elbow[0]), float(elbow[1]))
    landing = (float(elbow[0]), float(elbow[1]), float(text_px[0]), float(text_px[1]))
    plan.segments_px.append(leader)
    plan.segments_px.append(landing)

    # arrowhead: two strokes fanned about the leader direction, tip at the anchor
    direction = _unit(elbow - anchor_px)
    if direction is not None:
        for spread in (_ARROW_SPREAD, -_ARROW_SPREAD):
            c, s = float(np.cos(spread)), float(np.sin(spread))
            rotated = np.array([direction[0] * c - direction[1] * s,
                                direction[0] * s + direction[1] * c])
            tail = anchor_px + rotated * _ARROW_PX
            plan.segments_px.append(
                (float(anchor_px[0]), float(anchor_px[1]), float(tail[0]), float(tail[1]))
            )

    align = "left" if to_right else "right"
    text = TextDraw(
        text=label.text,
        x=float(text_px[0]),
        y=float(text_px[1]) - _TEXT_GAP_PX * 0.4,
        align=align,
    )
    plan.texts.append(text)
    plan.hit_boxes.append(_text_box(label.text, text.x, text.y, align))
    plan.hit_boxes.append(_segment_box(leader))
    return plan
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_draw_plan_label.py tests/test_draw_plan_dimension.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/annotations/ tests/test_draw_plan_label.py
```
Expected: 11 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/annotations/draw_plan.py tests/test_draw_plan_label.py && git commit -m "$(cat <<'EOF'
feat(m7d): draw plan for classic-callout labels

Arrowhead at the anchor, slanted leader into a horizontal landing, text on the
landing with the side auto-flipping so it always reads away from the anchor.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Annotation painter + viewport hook

**Files:** Create `python/pluton/viewport/annotation_painter.py`; Modify `python/pluton/viewport/viewport_widget.py`; Test `tests/test_annotation_painter.py`

**Interfaces:**
- Produces: `paint_annotation_plans(painter, plans, color, selected_ids, selected_color)` — executes plans against ANY painter-like object exposing `setPen`, `drawLine(x1,y1,x2,y2)`, `drawText(x, y, s)`. Testable with a recording stub; the real caller passes a `QPainter`.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_painter.py`:

```python
from __future__ import annotations

from pluton.annotations.draw_plan import AnnotationDraw, TextDraw
from pluton.viewport.annotation_painter import paint_annotation_plans


class _RecordingPainter:
    def __init__(self):
        self.lines = []
        self.texts = []
        self.pens = []

    def setPen(self, pen):
        self.pens.append(pen)

    def drawLine(self, x1, y1, x2, y2):
        self.lines.append((x1, y1, x2, y2))

    def drawText(self, x, y, s):
        self.texts.append((x, y, s))


def _plan(ann_id=1):
    return AnnotationDraw(
        annotation_id=ann_id,
        segments_px=[(0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0)],
        texts=[TextDraw("3600", 5.0, -2.0, "center")],
        hit_boxes=[],
    )


def test_paints_every_segment_and_text():
    p = _RecordingPainter()
    paint_annotation_plans(p, [_plan()], (0.1, 0.1, 0.1), set(), (0.2, 0.5, 0.9))
    assert len(p.lines) == 2
    assert len(p.texts) == 1
    assert p.texts[0][2] == "3600"


def test_selected_annotation_uses_the_selection_pen():
    p = _RecordingPainter()
    paint_annotation_plans(p, [_plan(7)], (0.1, 0.1, 0.1), {7}, (0.2, 0.5, 0.9))
    # a pen is set per annotation; the selected colour must have been used
    assert len(p.pens) >= 1


def test_empty_plan_list_draws_nothing():
    p = _RecordingPainter()
    paint_annotation_plans(p, [], (0.1, 0.1, 0.1), set(), (0.2, 0.5, 0.9))
    assert p.lines == [] and p.texts == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_painter.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.viewport.annotation_painter`).

- [ ] **Step 3: Implement**

`python/pluton/viewport/annotation_painter.py`:

```python
"""Execute annotation draw plans (M7d).

Deliberately thin: ALL layout lives in the pure annotations.draw_plan module.
This module only turns a plan into painter calls, so it works against any object
exposing setPen / drawLine / drawText (a QPainter in the app, a recording stub in
tests).
"""
from __future__ import annotations

from pluton.annotations.draw_plan import FONT_PX


def _align_offset(text, align):
    if align == "center":
        return -0.5 * 0.55 * FONT_PX * max(len(text), 1)
    if align == "right":
        return -0.55 * FONT_PX * max(len(text), 1)
    return 0.0


def paint_annotation_plans(painter, plans, color, selected_ids, selected_color):
    """Draw every plan; annotations whose id is in `selected_ids` use the
    selection colour."""
    for plan in plans:
        is_selected = plan.annotation_id in selected_ids
        painter.setPen(selected_color if is_selected else color)
        for x1, y1, x2, y2 in plan.segments_px:
            painter.drawLine(x1, y1, x2, y2)
        for text in plan.texts:
            painter.drawText(text.x + _align_offset(text.text, text.align), text.y, text.text)
```

Then wire the viewport. In `python/pluton/viewport/viewport_widget.py`, at the END of `paintGL` (after all GL drawing), add an annotation pass. **Ground the surrounding code first** — read `paintGL` and the widget's access to the model/camera/selection/units, then add:

```python
        self._paint_annotations()
```

and a new method:

```python
    def _paint_annotations(self) -> None:
        """M7d: draw the active context's annotations in screen space, on top."""
        from PySide6.QtGui import QColor, QFont, QPainter

        from pluton.annotations.draw_plan import FONT_PX, plan_annotation
        from pluton.viewport.annotation_painter import paint_annotation_plans

        model = getattr(self, "_model", None)
        if model is None:
            return
        annotations = model.active_context.annotations
        if not annotations:
            return
        width, height = self.width(), self.height()
        world = model.active_world_transform
        units = self._units_provider() if self._units_provider is not None else None
        plans = []
        for ann in annotations:
            plan = plan_annotation(ann, world, self.camera, width, height, units)
            if plan is not None:
                plans.append(plan)
        if not plans:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont()
        font.setPixelSize(int(FONT_PX))
        painter.setFont(font)
        paint_annotation_plans(
            painter,
            plans,
            QColor(30, 30, 30),
            set(self._selection.annotations) if self._selection is not None else set(),
            QColor(51, 140, 242),
        )
        painter.end()
```

**Grounding required:** confirm the widget's real attribute names for the model, camera, selection and units provider (they may be `self._model` / `self.camera` / `self._selection` / `self._units_provider` or differ) and adjust ONLY those accessors. If the widget has no units provider, thread one through the same way the renderer receives its dependencies. `Selection.annotations` lands in Task 7 — until then guard with `getattr(self._selection, "annotations", set())`.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_painter.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/viewport/annotation_painter.py tests/test_annotation_painter.py
```
Expected: 3 passed; ruff clean. Also run the existing viewport tests to confirm no regression: `timeout 200 .venv/Scripts/python -m pytest tests/ -q -p no:cacheprovider -k viewport`.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/annotation_painter.py python/pluton/viewport/viewport_widget.py tests/test_annotation_painter.py && git commit -m "$(cat <<'EOF'
feat(m7d): annotation painter + viewport screen-space pass

Thin plan executor (setPen/drawLine/drawText) usable with QPainter or a test
stub, plus a paintGL pass that plans the active context's annotations and draws
them on top of the GL render. All layout stays in the pure draw_plan module.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Annotation commands (create / delete / edit / move)

**Files:** Create `python/pluton/commands/annotation_commands.py`; Test `tests/test_annotation_commands.py`

**Interfaces:**
- Produces: `CreateAnnotationCommand(annotation, target_context)`, `DeleteAnnotationsCommand(annotation_ids, target_context)`, `EditLabelTextCommand(annotation_id, new_text, target_context)`, `MoveAnnotationsCommand(annotation_ids, delta, target_context)` — all undoable, all model-target.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_commands.py`:

```python
from __future__ import annotations

from pluton.commands.annotation_commands import (
    CreateAnnotationCommand,
    DeleteAnnotationsCommand,
    EditLabelTextCommand,
    MoveAnnotationsCommand,
)
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def _dim(model):
    return Dimension(model.new_annotation_id(), (0, 0, 0), (4, 0, 0), (0, -1, 0))


def _label(model, text="note"):
    return Label(model.new_annotation_id(), (0, 0, 0), (2, 2, 0), text)


def test_create_adds_and_undo_removes():
    model = Model()
    ctx = model.active_context
    cmd = CreateAnnotationCommand(_dim(model), ctx)
    cmd.do(model)
    assert len(ctx.annotations) == 1
    cmd.undo(model)
    assert len(ctx.annotations) == 0
    cmd.do(model)   # redo re-adds the same object
    assert len(ctx.annotations) == 1


def test_delete_removes_and_undo_restores():
    model = Model()
    ctx = model.active_context
    ann = _dim(model)
    ctx.annotations.append(ann)
    cmd = DeleteAnnotationsCommand([ann.id], ctx)
    cmd.do(model)
    assert ctx.annotations == []
    cmd.undo(model)
    assert len(ctx.annotations) == 1
    assert ctx.annotations[0].id == ann.id


def test_edit_label_text_and_undo_restores_old_text():
    model = Model()
    ctx = model.active_context
    lab = _label(model, "before")
    ctx.annotations.append(lab)
    cmd = EditLabelTextCommand(lab.id, "after", ctx)
    cmd.do(model)
    assert ctx.annotations[0].text == "after"
    cmd.undo(model)
    assert ctx.annotations[0].text == "before"


def test_move_shifts_dimension_offset_and_label_text_pos():
    model = Model()
    ctx = model.active_context
    dim = _dim(model)
    lab = _label(model)
    ctx.annotations.extend([dim, lab])
    cmd = MoveAnnotationsCommand([dim.id, lab.id], (0.0, 0.0, 1.0), ctx)
    cmd.do(model)
    assert ctx.annotations[0].offset == (0.0, -1.0, 1.0)
    assert ctx.annotations[1].text_pos == (2.0, 2.0, 1.0)
    assert ctx.annotations[1].anchor == (0.0, 0.0, 0.0)   # anchor stays put
    cmd.undo(model)
    assert ctx.annotations[0].offset == (0.0, -1.0, 0.0)
    assert ctx.annotations[1].text_pos == (2.0, 2.0, 0.0)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_commands.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.commands.annotation_commands`).

- [ ] **Step 3: Implement**

`python/pluton/commands/annotation_commands.py`:

```python
"""Undoable annotation commands (M7d)."""
from __future__ import annotations

from pluton.commands.command import Command


def _find(context, annotation_id):
    for ann in context.annotations:
        if ann.id == annotation_id:
            return ann
    return None


def _shift(point, delta):
    return (point[0] + delta[0], point[1] + delta[1], point[2] + delta[2])


class CreateAnnotationCommand(Command):
    """Append one annotation to a context; undo detaches the same object."""

    name = "Create Annotation"

    def __init__(self, annotation, target_context) -> None:
        self._annotation = annotation
        self._target = target_context

    def do(self, model) -> None:
        if self._annotation not in self._target.annotations:
            self._target.annotations.append(self._annotation)

    def undo(self, model) -> None:
        if self._annotation in self._target.annotations:
            self._target.annotations.remove(self._annotation)


class DeleteAnnotationsCommand(Command):
    """Remove annotations by id; undo restores them at their original indices."""

    name = "Delete Annotations"

    def __init__(self, annotation_ids, target_context) -> None:
        self._ids = list(annotation_ids)
        self._target = target_context
        self._removed = []   # (index, annotation), ascending by index

    def do(self, model) -> None:
        self._removed = []
        wanted = set(self._ids)
        for index, ann in enumerate(list(self._target.annotations)):
            if ann.id in wanted:
                self._removed.append((index, ann))
        for _index, ann in self._removed:
            self._target.annotations.remove(ann)

    def undo(self, model) -> None:
        for index, ann in self._removed:
            self._target.annotations.insert(index, ann)
        self._removed = []


class EditLabelTextCommand(Command):
    """Replace a Label's text; undo restores the previous string."""

    name = "Edit Label Text"

    def __init__(self, annotation_id, new_text, target_context) -> None:
        self._id = int(annotation_id)
        self._new_text = str(new_text)
        self._target = target_context
        self._old_text = None

    def do(self, model) -> None:
        ann = _find(self._target, self._id)
        if ann is None or getattr(ann, "kind", None) != "label":
            return
        self._old_text = ann.text
        ann.text = self._new_text

    def undo(self, model) -> None:
        if self._old_text is None:
            return
        ann = _find(self._target, self._id)
        if ann is not None:
            ann.text = self._old_text


class MoveAnnotationsCommand(Command):
    """Translate annotations by a local delta.

    A Dimension's `offset` shifts (moving the dimension line); a Label's
    `text_pos` shifts while its `anchor` stays put so the leader re-aims."""

    name = "Move Annotations"

    def __init__(self, annotation_ids, delta, target_context) -> None:
        self._ids = list(annotation_ids)
        self._delta = (float(delta[0]), float(delta[1]), float(delta[2]))
        self._target = target_context

    def _apply(self, delta) -> None:
        wanted = set(self._ids)
        for ann in self._target.annotations:
            if ann.id not in wanted:
                continue
            if getattr(ann, "kind", None) == "dimension":
                ann.offset = _shift(ann.offset, delta)
            elif getattr(ann, "kind", None) == "label":
                ann.text_pos = _shift(ann.text_pos, delta)

    def do(self, model) -> None:
        self._apply(self._delta)

    def undo(self, model) -> None:
        self._apply((-self._delta[0], -self._delta[1], -self._delta[2]))
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_commands.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/commands/annotation_commands.py tests/test_annotation_commands.py
```
Expected: 4 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/commands/annotation_commands.py tests/test_annotation_commands.py && git commit -m "$(cat <<'EOF'
feat(m7d): undoable annotation commands

Create (reuses the same object on redo), Delete (restores at original indices),
EditLabelText (restores the previous string) and Move (shifts a dimension's
offset / a label's text_pos, anchor unchanged).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Persistence — annotations in the `.pluton` codec

**Files:** Modify `python/pluton/io/document_codec.py`; Test `tests/test_annotation_persistence.py`

**Interfaces:**
- Produces: each serialized `Definition` gains an `"annotations"` array; reading a document without the key yields `[]`. `schema_version` bumped.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_persistence.py`:

```python
from __future__ import annotations

from pluton.io.document_codec import document_from_dict, document_to_dict
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def _roundtrip(model, camera, doc):
    data = document_to_dict(model, camera, doc)
    return document_from_dict(data)


def test_annotations_round_trip_in_the_root_context(default_camera, default_doc):
    model = Model()
    model.active_context.annotations.append(
        Dimension(model.new_annotation_id(), (0, 0, 0), (4, 0, 0), (0, -1, 0))
    )
    model.active_context.annotations.append(
        Label(model.new_annotation_id(), (0, 0, 0), (2, 2, 0), "Load-bearing")
    )
    restored, _cam, _doc = _roundtrip(model, default_camera, default_doc)
    anns = restored.active_context.annotations
    assert len(anns) == 2
    assert anns[0].kind == "dimension" and anns[0].p2 == (4.0, 0.0, 0.0)
    assert anns[1].kind == "label" and anns[1].text == "Load-bearing"


def test_annotations_round_trip_inside_a_group(default_camera, default_doc):
    model = Model()
    grp = model.new_definition("G", is_group=True)
    model.active_context.children.append(model.new_instance(grp))
    grp.annotations.append(Label(model.new_annotation_id(), (0, 0, 0), (1, 1, 0), "inside"))
    restored, _cam, _doc = _roundtrip(model, default_camera, default_doc)
    inner = restored.active_context.children[0].definition
    assert len(inner.annotations) == 1
    assert inner.annotations[0].text == "inside"


def test_document_without_annotations_key_still_loads(default_camera, default_doc):
    model = Model()
    data = document_to_dict(model, default_camera, default_doc)
    for defn in data["definitions"]:
        defn.pop("annotations", None)
    restored, _cam, _doc = document_from_dict(data)
    assert restored.active_context.annotations == []
```

**Grounding required:** confirm the real codec entry points and the definitions container key (`document_to_dict` / `document_from_dict` / `data["definitions"]` may be named differently — read `python/pluton/io/document_codec.py`) and adjust the test's calls and the `default_camera` / `default_doc` fixtures to whatever the existing persistence tests use (see `tests/test_document_codec.py`). Do not invent fixtures — reuse the established ones.

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_persistence.py -q -p no:cacheprovider
```
Expected: FAIL (annotations are dropped → length assertions fail).

- [ ] **Step 3: Implement**

In `python/pluton/io/document_codec.py`:

1. Add encode/decode helpers near the other per-entity helpers:

```python
def annotation_to_dict(ann):
    if ann.kind == "dimension":
        return {"kind": "dimension", "id": ann.id,
                "p1": list(ann.p1), "p2": list(ann.p2), "offset": list(ann.offset)}
    return {"kind": "label", "id": ann.id,
            "anchor": list(ann.anchor), "text_pos": list(ann.text_pos), "text": ann.text}


def annotation_from_dict(record):
    from pluton.model.annotation import Dimension, Label

    if record.get("kind") == "dimension":
        return Dimension(record["id"], tuple(record["p1"]), tuple(record["p2"]),
                         tuple(record["offset"]))
    return Label(record["id"], tuple(record["anchor"]), tuple(record["text_pos"]),
                 record["text"])
```

2. Where a `Definition` is serialized, add `"annotations": [annotation_to_dict(a) for a in defn.annotations]`.
3. Where a `Definition` is rebuilt, add `defn.annotations = [annotation_from_dict(r) for r in record.get("annotations", [])]` — using `.get(..., [])` so older documents load unchanged.
4. After rebuilding, restore the id counter so new annotations never collide with loaded ones:

```python
        max_ann_id = -1
        for defn in <all rebuilt definitions>:
            for ann in defn.annotations:
                max_ann_id = max(max_ann_id, ann.id)
        model._next_annotation_id = max_ann_id + 1
```

5. Bump the `schema_version` constant by one and keep the existing version gate behaviour.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_persistence.py tests/test_document_codec.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/io/document_codec.py tests/test_annotation_persistence.py
```
Expected: all pass (existing codec tests included); no new ruff findings in `document_codec.py`.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/io/document_codec.py tests/test_annotation_persistence.py && git commit -m "$(cat <<'EOF'
feat(m7d): persist annotations in the .pluton codec

Each Definition gains an "annotations" array (dimensions and labels), the
annotation id counter is restored on load, and a missing key reads as empty so
older documents open unchanged. schema_version bumped.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Annotation picking + `Selection.annotations`

**Files:** Create `python/pluton/annotations/picking.py`; Modify `python/pluton/selection.py`; Test `tests/test_annotation_picking.py`

**Interfaces:**
- Produces: `pick_annotation(cursor_px, annotations, world_transform, camera, width, height, units) -> int | None` (nearest hit by box centre distance); `Selection.annotations` set plus `replace`/`add`/`remove`/`clear`/`counts` support.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_picking.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.annotations.picking import pick_annotation
from pluton.model.annotation import Dimension, Label
from pluton.selection import Selection
from pluton.units import Units


class _FlatCamera:
    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)


def _pick(cursor, anns):
    return pick_annotation(cursor, anns, np.eye(4), _FlatCamera(), 640, 480, Units())


def test_click_on_the_dimension_line_hits_it():
    d = Dimension(5, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    # dimension line runs at world y=-2 -> screen y=220, x from 100 to 140
    assert _pick((120.0, 220.0), [d]) == 5


def test_click_far_away_hits_nothing():
    d = Dimension(5, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    assert _pick((600.0, 50.0), [d]) is None


def test_click_on_label_text_hits_the_label():
    lab = Label(9, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    # text sits at the projected text_pos -> (150, 170)
    assert _pick((152.0, 168.0), [lab]) == 9


def test_selection_tracks_annotations():
    sel = Selection()
    assert sel.annotations == set()
    sel.replace(annotations=[1, 2])
    assert sel.annotations == {1, 2}
    sel.add(annotations=[3])
    assert sel.annotations == {1, 2, 3}
    sel.clear()
    assert sel.annotations == set()
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_picking.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.annotations.picking`).

- [ ] **Step 3: Implement**

`python/pluton/annotations/picking.py`:

```python
"""Screen-space annotation picking (M7d).

Hit-tests the SAME draw plan the painter renders, so anything visible is
clickable and nothing invisible is.
"""
from __future__ import annotations

from pluton.annotations.draw_plan import plan_annotation


def _inside(box, x, y):
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def _box_distance_sq(box, x, y):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return (cx - x) ** 2 + (cy - y) ** 2


def pick_annotation(cursor_px, annotations, world_transform, camera, width, height, units):
    """Return the id of the nearest annotation under the cursor, or None."""
    x, y = float(cursor_px[0]), float(cursor_px[1])
    best_id = None
    best_d2 = float("inf")
    for ann in annotations:
        plan = plan_annotation(ann, world_transform, camera, width, height, units)
        if plan is None:
            continue
        for box in plan.hit_boxes:
            if not _inside(box, x, y):
                continue
            d2 = _box_distance_sq(box, x, y)
            if d2 < best_d2:
                best_d2 = d2
                best_id = plan.annotation_id
    return best_id
```

In `python/pluton/selection.py` — **purely additive**, mirroring `_instances` exactly:

1. Add `"_annotations"` to `__slots__`.
2. `self._annotations: set[int] = set()` in `__init__`.
3. An `annotations` property returning `self._annotations`.
4. Add an `annotations: Iterable[int] = ()` keyword to `replace`, `add`, and any `remove`/`toggle` methods, handling it exactly as `instances` is handled.
5. Include annotations in `clear()`, `is_empty()` and `counts()` if those exist — read the file and extend every method that already enumerates edges/faces/instances. Do not leave one out.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_picking.py tests/test_selection.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/annotations/picking.py python/pluton/selection.py tests/test_annotation_picking.py
```
Expected: all pass (existing selection tests included); ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/annotations/picking.py python/pluton/selection.py tests/test_annotation_picking.py && git commit -m "$(cat <<'EOF'
feat(m7d): annotation picking + Selection.annotations

pick_annotation hit-tests the same draw plan the painter renders (visible ==
clickable), and Selection gains an annotations set alongside edges/faces/instances.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `DimensionTool` (`I`)

**Files:** Create `python/pluton/tools/dimension_tool.py`; Test `tests/test_dimension_tool.py`

**Interfaces:**
- Consumes: `Tool`/`ToolContext`/`ToolOverlay`; `snap.kind` / `snap.world_position` / `SnapKind`; `world_to_local_point`; `CreateAnnotationCommand`; `Dimension`; `model.new_annotation_id()`.
- Produces: `DimensionTool` with `shortcut = "I"`; three-click gesture.

- [ ] **Step 1: Write the failing test**

`tests/test_dimension_tool.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.model.model import Model
from pluton.tools.dimension_tool import DimensionTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


class _Snap:
    def __init__(self, x, y, z=0.0):
        self.kind = SnapKind.ON_FACE
        self.world_position = np.array([x, y, z], dtype=np.float64)


def _ctx(model, stack):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model, camera=None,
        widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def _make(tool, ax, ay, bx, by, ox, oy):
    tool.on_mouse_press(None, _Snap(ax, ay))
    tool.on_mouse_press(None, _Snap(bx, by))
    tool.on_mouse_move(None, _Snap(ox, oy))
    tool.on_mouse_press(None, _Snap(ox, oy))


def test_three_clicks_create_one_dimension():
    model = Model()
    tool = DimensionTool()
    tool.activate(_ctx(model, CommandStack()))
    _make(tool, 0.0, 0.0, 4.0, 0.0, 2.0, -1.0)
    anns = model.active_context.annotations
    assert len(anns) == 1
    assert anns[0].kind == "dimension"
    assert anns[0].p1 == (0.0, 0.0, 0.0)
    assert anns[0].p2 == (4.0, 0.0, 0.0)


def test_offset_is_perpendicular_to_the_measured_axis():
    model = Model()
    tool = DimensionTool()
    tool.activate(_ctx(model, CommandStack()))
    # third click is off to the side AND along the axis; only the perpendicular
    # component may survive
    _make(tool, 0.0, 0.0, 4.0, 0.0, 3.5, -1.0)
    off = model.active_context.annotations[0].offset
    assert abs(off[0]) < 1e-9      # along-axis component removed
    assert abs(off[1] + 1.0) < 1e-9


def test_degenerate_second_click_creates_nothing():
    model = Model()
    tool = DimensionTool()
    tool.activate(_ctx(model, CommandStack()))
    _make(tool, 1.0, 1.0, 1.0, 1.0, 2.0, 2.0)
    assert model.active_context.annotations == []


def test_escape_cancels_the_gesture():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    model = Model()
    tool = DimensionTool()
    tool.activate(_ctx(model, CommandStack()))
    tool.on_mouse_press(None, _Snap(0.0, 0.0))
    tool.on_key_press(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                Qt.KeyboardModifier.NoModifier))
    assert tool.has_active_gesture is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_dimension_tool.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.tools.dimension_tool`).

- [ ] **Step 3: Implement**

`python/pluton/tools/dimension_tool.py`:

```python
"""The linear Dimension tool (M7d).

Three clicks: two measured points, then the offset that positions the dimension
line. Points are stored in the active context's local frame.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.annotation_commands import CreateAnnotationCommand
from pluton.model.annotation import Dimension
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import world_to_local_point
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND, SnapKind

_NEUTRAL = (0.85, 0.85, 0.85)
_EPS = 1e-9


class DimensionTool(Tool):
    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._p1 = None            # local
        self._p2 = None            # local
        self._preview_offset = None
        self._snap_pos = None
        self._snap_color = _NEUTRAL
        self._snap_kind = 0

    @property
    def name(self) -> str:
        return "Dimension"

    @property
    def shortcut(self) -> str:
        return "I"

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def _to_local(self, world_pt):
        wt = self._model.active_world_transform if self._model is not None else None
        return np.asarray(world_to_local_point(world_pt, wt), dtype=np.float64)

    def _perpendicular_offset(self, local_pt):
        p1 = np.asarray(self._p1, dtype=np.float64)
        p2 = np.asarray(self._p2, dtype=np.float64)
        axis = p2 - p1
        n = float(np.linalg.norm(axis))
        if n < _EPS:
            return None
        axis = axis / n
        mid = (p1 + p2) / 2.0
        raw = np.asarray(local_pt, dtype=np.float64) - mid
        return raw - axis * float(np.dot(raw, axis))

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            self._snap_pos = None
            self._snap_kind = 0
            return
        self._snap_pos = np.asarray(snap.world_position, np.float64).copy()
        self._snap_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL)
        self._snap_kind = int(snap.kind)
        if self._p1 is not None and self._p2 is not None:
            self._preview_offset = self._perpendicular_offset(
                self._to_local(snap.world_position)
            )

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            return
        local = self._to_local(snap.world_position)
        if self._p1 is None:
            self._p1 = local
            return
        if self._p2 is None:
            if float(np.linalg.norm(local - self._p1)) < _EPS:
                self._reset()        # degenerate measurement
                return
            self._p2 = local
            return
        offset = self._perpendicular_offset(local)
        if offset is None:
            self._reset()
            return
        dim = Dimension(
            self._model.new_annotation_id(),
            tuple(float(v) for v in self._p1),
            tuple(float(v) for v in self._p2),
            tuple(float(v) for v in offset),
        )
        self._command_stack.execute(
            CreateAnnotationCommand(dim, self._model.active_context), self._model
        )
        self._reset()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        segments = np.zeros((0, 3), dtype=np.float32)
        return ToolOverlay(
            rubber_band_segments=segments,
            rubber_band_color=_NEUTRAL,
            snap_marker_position=self._snap_pos.copy() if self._snap_pos is not None else None,
            snap_marker_color=self._snap_color,
            snap_marker_kind=self._snap_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._p1 is not None

    @property
    def anchor_or_none(self):
        return None

    @property
    def status_text(self):
        return None

    def _reset(self) -> None:
        self._p1 = None
        self._p2 = None
        self._preview_offset = None
        self._snap_pos = None
        self._snap_kind = 0
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_dimension_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/dimension_tool.py tests/test_dimension_tool.py
```
Expected: 4 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/dimension_tool.py tests/test_dimension_tool.py && git commit -m "$(cat <<'EOF'
feat(m7d): DimensionTool (I) — three-click linear dimension

Snap two measured points, then a third click whose perpendicular component
becomes the dimension-line offset. Points stored in the active context's local
frame; degenerate measurement creates nothing; Esc cancels.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `TextTool` (`N`)

**Files:** Create `python/pluton/tools/text_tool.py`; Test `tests/test_text_tool.py`

**Interfaces:**
- Produces: `TextTool` with `shortcut = "N"`; two clicks then a prompt. Text entry goes through an **overridable** `prompt_text(default)` method (returns `str | None`) so tests stub it — mirroring MainWindow's `_prompt_component_name`.

- [ ] **Step 1: Write the failing test**

`tests/test_text_tool.py`:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.model.model import Model
from pluton.tools.text_tool import TextTool
from pluton.tools.tool import ToolContext
from pluton.viewport.snap_engine import SnapKind


class _Snap:
    def __init__(self, x, y, z=0.0):
        self.kind = SnapKind.ON_FACE
        self.world_position = np.array([x, y, z], dtype=np.float64)


def _ctx(model, stack):
    return ToolContext(
        scene=model.active_scene, command_stack=stack, model=model, camera=None,
        widget_size_provider=lambda: (100, 100), units_provider=lambda: None,
    )


def _tool(model, answer="Load-bearing"):
    tool = TextTool()
    tool.prompt_text = lambda default="": answer
    tool.activate(_ctx(model, CommandStack()))
    return tool


def test_two_clicks_plus_prompt_create_a_label():
    model = Model()
    tool = _tool(model)
    tool.on_mouse_press(None, _Snap(0.0, 0.0))
    tool.on_mouse_press(None, _Snap(2.0, 2.0))
    anns = model.active_context.annotations
    assert len(anns) == 1
    assert anns[0].kind == "label"
    assert anns[0].anchor == (0.0, 0.0, 0.0)
    assert anns[0].text_pos == (2.0, 2.0, 0.0)
    assert anns[0].text == "Load-bearing"


def test_cancelled_prompt_creates_nothing():
    model = Model()
    tool = _tool(model, answer=None)
    tool.on_mouse_press(None, _Snap(0.0, 0.0))
    tool.on_mouse_press(None, _Snap(2.0, 2.0))
    assert model.active_context.annotations == []


def test_blank_text_creates_nothing():
    model = Model()
    tool = _tool(model, answer="   ")
    tool.on_mouse_press(None, _Snap(0.0, 0.0))
    tool.on_mouse_press(None, _Snap(2.0, 2.0))
    assert model.active_context.annotations == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_text_tool.py -q -p no:cacheprovider
```
Expected: FAIL (`ModuleNotFoundError: pluton.tools.text_tool`).

- [ ] **Step 3: Implement**

`python/pluton/tools/text_tool.py`:

```python
"""The Text (leader label) tool (M7d).

Click the anchor, click where the text goes, then type it in a dialog. The
dialog lives behind an overridable prompt_text() so tests can stub it, mirroring
MainWindow._prompt_component_name.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.commands.annotation_commands import CreateAnnotationCommand
from pluton.model.annotation import Label
from pluton.tools.tool import Tool, ToolContext, ToolOverlay
from pluton.viewport.picking import world_to_local_point
from pluton.viewport.snap_engine import MARKER_COLOR_BY_KIND, SnapKind

_NEUTRAL = (0.85, 0.85, 0.85)


class TextTool(Tool):
    def __init__(self) -> None:
        self._scene = None
        self._model = None
        self._command_stack = None
        self._anchor = None        # local
        self._snap_pos = None
        self._snap_color = _NEUTRAL
        self._snap_kind = 0

    @property
    def name(self) -> str:
        return "Text"

    @property
    def shortcut(self) -> str:
        return "N"

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._command_stack = ctx.command_stack
        self._model = ctx.model
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def prompt_text(self, default: str = "") -> str | None:
        """Ask the user for the label text. Overridable for testing."""
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(None, "Text", "Label:", text=default)
        return text if ok else None

    def _to_local(self, world_pt):
        wt = self._model.active_world_transform if self._model is not None else None
        return np.asarray(world_to_local_point(world_pt, wt), dtype=np.float64)

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            self._snap_pos = None
            self._snap_kind = 0
            return
        self._snap_pos = np.asarray(snap.world_position, np.float64).copy()
        self._snap_color = MARKER_COLOR_BY_KIND.get(snap.kind, _NEUTRAL)
        self._snap_kind = int(snap.kind)

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:
        if snap.kind == SnapKind.NONE:
            return
        local = self._to_local(snap.world_position)
        if self._anchor is None:
            self._anchor = local
            return
        text = self.prompt_text("")
        if text is None or not text.strip():
            self._reset()
            return
        label = Label(
            self._model.new_annotation_id(),
            tuple(float(v) for v in self._anchor),
            tuple(float(v) for v in local),
            text.strip(),
        )
        self._command_stack.execute(
            CreateAnnotationCommand(label, self._model.active_context), self._model
        )
        self._reset()

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), dtype=np.float32),
            rubber_band_color=_NEUTRAL,
            snap_marker_position=self._snap_pos.copy() if self._snap_pos is not None else None,
            snap_marker_color=self._snap_color,
            snap_marker_kind=self._snap_kind,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._anchor is not None

    @property
    def anchor_or_none(self):
        return None

    @property
    def status_text(self):
        return None

    def _reset(self) -> None:
        self._anchor = None
        self._snap_pos = None
        self._snap_kind = 0
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_text_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/text_tool.py tests/test_text_tool.py
```
Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/text_tool.py tests/test_text_tool.py && git commit -m "$(cat <<'EOF'
feat(m7d): TextTool (N) — leader label with dialog text entry

Click the anchor, click the text position, then type in a QInputDialog behind an
overridable prompt_text() so tests can stub it. Cancelled or blank input creates
nothing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: SelectTool integration (click / Shift / hover)

**Files:** Modify `python/pluton/tools/select_tool.py`; Test `tests/test_annotation_select_erase.py` (selection half)

**Interfaces:** SelectTool hit-tests annotations via `pick_annotation` **before** falling back to geometry picking (annotations draw on top, so they should pick on top), sets `Selection.annotations`, and supports Shift-toggle.

- [ ] **Step 1: Write the failing test** — create `tests/test_annotation_select_erase.py` with the selection cases:

```python
from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.model.annotation import Dimension
from pluton.model.model import Model
from pluton.selection import Selection
from pluton.tools.select_tool import SelectTool
from pluton.tools.tool import ToolContext
from pluton.units import Units


class _FlatCamera:
    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)

    def ray_from_screen(self, cx, cy, w, h):
        return np.array([0.0, 0.0, 50.0]), np.array([0.0, 0.0, -1.0])


class _Event:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def position(self):
        class _P:
            def __init__(self, x, y):
                self.__x, self.__y = x, y

            def x(self):
                return self.__x

            def y(self):
                return self.__y

        return _P(self._x, self._y)


def _model_with_dimension():
    model = Model()
    model.active_context.annotations.append(
        Dimension(5, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    )
    return model


def _ctx(model, selection):
    return ToolContext(
        scene=model.active_scene, command_stack=CommandStack(), model=model,
        camera=_FlatCamera(), widget_size_provider=lambda: (640, 480),
        units_provider=lambda: Units(), selection=selection,
    )


def test_clicking_a_dimension_selects_it():
    model = _model_with_dimension()
    sel = Selection()
    tool = SelectTool()
    tool.activate(_ctx(model, sel))
    tool.on_mouse_press(_Event(120.0, 220.0), None)
    assert sel.annotations == {5}


def test_clicking_empty_space_clears_the_annotation_selection():
    model = _model_with_dimension()
    sel = Selection()
    tool = SelectTool()
    tool.activate(_ctx(model, sel))
    tool.on_mouse_press(_Event(120.0, 220.0), None)
    tool.on_mouse_press(_Event(600.0, 40.0), None)
    assert sel.annotations == set()
```

**Grounding required:** read `select_tool.py` and `ToolContext` first. The selection may reach the tool via `ctx.selection` or another accessor, and `on_mouse_press` may take `(event, snap)`. Adapt the test's `ToolContext(...)` construction and event/snap arguments to the REAL signatures — do not invent them. Keep the assertions.

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_select_erase.py -q -p no:cacheprovider
```
Expected: FAIL (annotations never selected).

- [ ] **Step 3: Implement** — in `select_tool.py`, at the start of the click-handling path (before geometry picking), add an annotation pass:

```python
        ann_id = pick_annotation(
            (cx, cy),
            self._model.active_context.annotations,
            self._model.active_world_transform,
            self._camera,
            width,
            height,
            self._units_provider() if self._units_provider is not None else None,
        )
        if ann_id is not None:
            if shift_held:
                if ann_id in self._selection.annotations:
                    self._selection.remove(annotations=[ann_id])
                else:
                    self._selection.add(annotations=[ann_id])
            else:
                self._selection.replace(annotations=[ann_id])
            return
```

and when a click hits nothing, ensure the existing "clear selection" path also clears `annotations` (it will, if `replace()` is called with no annotations — verify). Mirror the tool's existing Shift and hover conventions exactly; add a hover highlight only if the tool already tracks a hover id for geometry.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_select_erase.py tests/test_select_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/select_tool.py
```
Expected: all pass (existing select-tool tests included); no new ruff findings.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/select_tool.py tests/test_annotation_select_erase.py && git commit -m "$(cat <<'EOF'
feat(m7d): select annotations with the Select tool

Annotations are hit-tested before geometry (they draw on top), with Shift-toggle
and clear-on-empty-click matching the existing selection conventions.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Erase + Delete integration

**Files:** Modify `python/pluton/tools/erase_tool.py`, `python/pluton/ui/main_window.py`; Test `tests/test_annotation_select_erase.py` (erase half)

**Interfaces:** the Eraser tool removes a clicked annotation; the Delete key removes all selected annotations. Both go through `DeleteAnnotationsCommand`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_annotation_select_erase.py`:

```python
def test_delete_removes_selected_annotations_and_undo_restores():
    from pluton.commands.annotation_commands import DeleteAnnotationsCommand

    model = _model_with_dimension()
    ctx = model.active_context
    stack = CommandStack()
    stack.execute(DeleteAnnotationsCommand([5], ctx), model)
    assert ctx.annotations == []
    stack.undo()
    assert len(ctx.annotations) == 1


def test_eraser_click_removes_an_annotation():
    from pluton.tools.erase_tool import EraserTool

    model = _model_with_dimension()
    sel = Selection()
    tool = EraserTool()
    tool.activate(_ctx(model, sel))
    tool.on_mouse_press(_Event(120.0, 220.0), None)
    assert model.active_context.annotations == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_select_erase.py -q -p no:cacheprovider
```
Expected: the eraser test FAILS (annotation survives).

- [ ] **Step 3: Implement**

1. In `erase_tool.py`, at the start of the click path, run `pick_annotation` (same call shape as Task 10); on a hit, execute `DeleteAnnotationsCommand([ann_id], model.active_context)` through the command stack and return.
2. In `main_window.py` `_on_delete_selection`, **additively** handle annotations: if `self._selection.annotations` is non-empty, build a `DeleteAnnotationsCommand(list(self._selection.annotations), self._model.active_context)` and execute it (composing with the existing instance/geometry deletion the same way the method already composes commands), then clear the selection. Do not restructure the existing branches.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_select_erase.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/erase_tool.py && .venv/Scripts/python -m ruff check python/pluton/ui/main_window.py
```
Expected: all pass; `main_window.py` STILL exactly **9** findings.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/erase_tool.py python/pluton/ui/main_window.py tests/test_annotation_select_erase.py && git commit -m "$(cat <<'EOF'
feat(m7d): erase annotations via the Eraser and the Delete key

Eraser click removes the annotation under the cursor; Delete removes every
selected annotation. Both undoable via DeleteAnnotationsCommand.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Edit label text + Move annotations

**Files:** Modify `python/pluton/tools/select_tool.py`, `python/pluton/tools/move_tool.py`; Test `tests/test_annotation_edit_move.py`

**Interfaces:** double-clicking a label reopens the prompt and commits `EditLabelTextCommand`; the Move tool translates selected annotations via `MoveAnnotationsCommand`.

- [ ] **Step 1: Write the failing test**

`tests/test_annotation_edit_move.py`:

```python
from __future__ import annotations

from pluton.commands.annotation_commands import EditLabelTextCommand, MoveAnnotationsCommand
from pluton.commands.command_stack import CommandStack
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def test_edit_label_text_through_the_command_stack():
    model = Model()
    ctx = model.active_context
    ctx.annotations.append(Label(1, (0, 0, 0), (1, 1, 0), "before"))
    stack = CommandStack()
    stack.execute(EditLabelTextCommand(1, "after", ctx), model)
    assert ctx.annotations[0].text == "after"
    stack.undo()
    assert ctx.annotations[0].text == "before"


def test_move_selected_annotations_through_the_command_stack():
    model = Model()
    ctx = model.active_context
    ctx.annotations.append(Dimension(1, (0, 0, 0), (4, 0, 0), (0, -1, 0)))
    stack = CommandStack()
    stack.execute(MoveAnnotationsCommand([1], (0.0, -0.5, 0.0), ctx), model)
    assert ctx.annotations[0].offset == (0.0, -1.5, 0.0)
    stack.undo()
    assert ctx.annotations[0].offset == (0.0, -1.0, 0.0)
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_edit_move.py -q -p no:cacheprovider
```
Expected: PASS if Task 5 is complete (these exercise the commands). If so, the remaining work is UI wiring — proceed to Step 3 and add the wiring tests below.

- [ ] **Step 3: Wire the UI paths**

1. **Edit text** — in `select_tool.py` implement `on_mouse_double_click(event, snap)`: `pick_annotation` at the cursor; if the hit annotation's `kind == "label"`, call an overridable `prompt_text(default)` on the tool (same pattern as `TextTool.prompt_text`, so it can be stubbed) pre-filled with the current text; on a non-None, non-blank result execute `EditLabelTextCommand(ann_id, text, model.active_context)`.
2. **Move** — in `move_tool.py`, where the committed translation delta is known, additionally execute `MoveAnnotationsCommand(list(selection.annotations), local_delta, model.active_context)` when `selection.annotations` is non-empty, composing with the existing vertex/instance move exactly as the tool already composes commands. The delta must be the **context-local** delta the tool already computes for geometry — do not recompute it differently.
3. Add wiring tests to `tests/test_annotation_edit_move.py`: a stubbed-prompt double-click renames a label; a Move gesture with an annotation selected shifts its offset. Ground the tools' real gesture entry points before writing these.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_annotation_edit_move.py tests/test_move_tool.py tests/test_select_tool.py -q -p no:cacheprovider && .venv/Scripts/python -m ruff check python/pluton/tools/select_tool.py python/pluton/tools/move_tool.py tests/test_annotation_edit_move.py
```
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/tools/select_tool.py python/pluton/tools/move_tool.py tests/test_annotation_edit_move.py && git commit -m "$(cat <<'EOF'
feat(m7d): edit label text (double-click) and move annotations

Double-clicking a label reopens the prompt pre-filled and commits an undoable
EditLabelTextCommand; the Move tool translates selected annotations (dimension
offset / label text_pos) alongside geometry.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: MainWindow integration (register `I` + `N`)

**Files:** Modify `python/pluton/ui/main_window.py`; Test `tests/test_main_window_annotations.py`

- [ ] **Step 1: Write the failing test**

`tests/test_main_window_annotations.py`:

```python
from __future__ import annotations

from pluton.tools.dimension_tool import DimensionTool
from pluton.tools.text_tool import TextTool
from pluton.ui.main_window import MainWindow


def test_dimension_tool_registered_with_i(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("I")
    assert isinstance(w._tool_manager.active, DimensionTool)


def test_text_tool_registered_with_n(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._tool_manager.activate_by_shortcut("N")
    assert isinstance(w._tool_manager.active, TextTool)


def test_i_and_n_key_shortcuts_registered(qtbot):
    from PySide6.QtGui import QShortcut

    w = MainWindow()
    qtbot.addWidget(w)
    keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
    assert "I" in keys and "N" in keys
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_annotations.py -q -p no:cacheprovider
```
Expected: FAIL (no `I`/`N` tools).

- [ ] **Step 3: Wire MainWindow** — **additive only; keep the finding count at exactly 9.**

1. Import `DimensionTool` and `TextTool` in correct alphabetical position (`dimension_tool` before `erase_tool`; `text_tool` before `tool_manager`) — no new I001.
2. Register both alongside the other tools:
   ```python
   self._dimension_tool = DimensionTool()
   self._tool_manager.register(self._dimension_tool)
   self._text_tool = TextTool()
   self._tool_manager.register(self._text_tool)
   ```
3. Add bare-key shortcuts next to the other single-key tool `QShortcut`s (there is NO generic dispatcher — each tool binds its own):
   ```python
   QShortcut(QKeySequence("I"), self, activated=lambda: self._activate("I"))
   QShortcut(QKeySequence("N"), self, activated=lambda: self._activate("N"))
   ```
4. Add `Tools ▸ Dimension (I)` and `Tools ▸ Text (N)` entries matching the existing `"Wall\tW"` / `"Roof\tO"` idiom.
5. Confirm `I` and `N` are otherwise unused before finalizing.

- [ ] **Step 4: Run to verify it passes**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 200 .venv/Scripts/python -m pytest tests/test_main_window_annotations.py -q -p no:cacheprovider
```
Expected: 3 passed. Then confirm `.venv/Scripts/python -m ruff check python/pluton/ui/main_window.py` still reports **exactly 9** findings (same 5 RUF100 + 3 E501 + 1 I001).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/ui/main_window.py tests/test_main_window_annotations.py && git commit -m "$(cat <<'EOF'
feat(m7d): register DimensionTool (I) + TextTool (N) in MainWindow

Both tools registered with their own QShortcuts and Tools-menu entries.
Additive-only (issue #48).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Full regression + master design-doc annotation

**Files:** Modify `docs/2026-05-16-pluton-design.md`

- [ ] **Step 1: Full Python regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```
Expected: all pass, well above the 852 baseline.

- [ ] **Step 2: C++ regression**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && (cd build/tests && ctest --output-on-failure | tail -3)
```
Expected: 79/79 (Python-only milestone).

- [ ] **Step 3: Annotate the master design doc** — on the **M7** line, after the M7c note, add an **M7d** ✅ *(shipped v0.2.4)* note: the Dimension tool (`I`) and Text tool (`N`) create persistent architectural-style annotations stored per editing context, drawn screen-space via `QPainter` (constant size at any zoom), with a pure `plan_annotation` draw plan shared by rendering and picking, derived measurement text that follows the document's units, `.pluton` persistence, and full select / erase / retype / move. Update "Remaining sub-milestones" to just **M7e** Scenes. Confirm the M8 line is untouched (`grep -c "M8:"` stays 1).

- [ ] **Step 4: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
docs(m7d): annotate master design M7 line — annotations shipped

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: Release v0.2.4

*(Outward-facing steps — push, tag, issues — require explicit per-turn user authorization.)*

- [ ] **Step 1: Bump the version to 0.2.4** — `pyproject.toml` → `version = "0.2.4"`; `CMakeLists.txt` → `VERSION 0.2.4`; `cpp/src/version.cpp` → `return "0.2.4";`

- [ ] **Step 2: Rebuild and verify**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake" .venv/Scripts/python -m pip install -e . --no-build-isolation && .venv/Scripts/python -c "import pluton._core as c; assert c.version()=='0.2.4', c.version(); print('version OK', c.version())"
```

- [ ] **Step 3: Final full suite**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && timeout 300 .venv/Scripts/python -m pytest -q -p no:cacheprovider
```

- [ ] **Step 4: Commit the release**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp && git commit -m "$(cat <<'EOF'
release: v0.2.4 — Dimensions & annotations (M7d)

Bump 0.2.3 -> 0.2.4. Fourth M7 sub-milestone: persistent linear dimensions and
leader text labels, drawn screen-space via QPainter from a pure draw plan shared
by rendering and picking, stored per editing context, round-tripped through
.pluton, and fully selectable / erasable / editable / movable.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Verify signatures**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && for s in $(git log --format=%H 8efcae1..HEAD); do echo "$s $(git cat-file -p $s | grep -c 'BEGIN SSH SIGNATURE')"; done
```
Expected: every commit shows `1`.

- [ ] **Step 6: Push, tag, issues — AFTER explicit user authorization**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git push origin main && git tag -s v0.2.4 -m "Pluton v0.2.4 — Dimensions & annotations (M7d)" && git push origin v0.2.4
```
Then watch CI green on both platforms. File carry-over issues: angular/radial dimensions; leaderless + screen-pinned notes; annotation styling options (text height, font, colour, tick/arrow size); true associativity to geometry; depth-aware occlusion; dimension text override; multi-line/rich text; 2D drawing/PDF output.

- [ ] **Step 7: Manual visual pass (user)**

Launch the app; press `I`, snap two points, set the offset, confirm the dimension draws with ticks + text above and stays constant-size while zooming; press `N`, place a label and type text; select, move, retype and delete both; save/reopen and confirm they persist; draw one inside a group and confirm it rides the group when moved.

---

## Self-Review

**1. Spec coverage.** D1 two kinds → T8/T9. D2 per-context static points → T1. D3 QPainter screen-space → T4. D4 architectural dimension style → T2. D5 classic callout → T3. D6 leader-only → T9 (no leaderless path). D7 shared draw plan → T2/T3 consumed by T4 (render) and T7 (pick). D8 derived text → T2 (`format_length` at plan time). D9 select/erase/edit/move + dialog entry → T10/T11/T12. D10 persistence + no OBJ/glTF export → T6. D11 shortcuts `I`/`N`, no options bar → T13. D12 v0.2.4 → T15. **All covered.**

**2. Placeholder scan.** No TBD/"handle errors". The **"Grounding required"** notes (T4 viewport accessors, T6 codec entry points/fixtures, T10/T12 tool signatures) are explicit confirm-against-real-code instructions naming the exact files and what to adapt — they exist because those tasks modify pre-existing files whose signatures must be read rather than assumed, and each says precisely what may be adapted (accessors/fixtures only) and what may not (the assertions). No `# noqa` anywhere.

**3. Type/interface consistency.** `Dimension(id,p1,p2,offset)` / `Label(id,anchor,text_pos,text)` identical across T1/T2/T3/T5/T6/T8/T9. `plan_annotation(ann, world_transform, camera, width, height, units)` produced in T2, extended in T3, consumed identically in T4 and T7. `AnnotationDraw(annotation_id, segments_px, texts, hit_boxes)` consistent T2→T4/T7. `pick_annotation(cursor_px, annotations, world_transform, camera, width, height, units)` produced in T7, consumed in T10/T11/T12. Command signatures consistent T5→T10/T11/T12.

**4. Ordering.** Entities (1) → pure plan for dimensions (2) → labels (3) → painter (4) → commands (5) → persistence (6) → picking + selection state (7) → the two creation tools (8, 9) → select (10) → erase (11) → edit/move (12) → MainWindow (13) → regression/doc (14) → release (15). Each task independently testable; no forward dependency.

**5. Known risk to watch.** Task 4 is the only task whose core deliverable (QPainter over `QOpenGLWidget`) cannot be fully verified by an automated test — the painter logic IS tested via a recording stub, but that the text actually appears over the GL surface must be confirmed in the Task 15 manual visual pass. If `QPainter(self)` inside `paintGL` does not composite correctly on this platform, the fallback is to override `paintEvent` and wrap the GL call in `beginNativePainting()`/`endNativePainting()`; flag it rather than silently restructuring the renderer.

Plan complete.

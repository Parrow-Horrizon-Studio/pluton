# M4d — Units & Measurement (VCB + Tape Measure) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure units layer (metric + full architectural fractional imperial), a non-focused SketchUp-style Measurements box (VCB) wired into all nine tools via `apply_typed_value`, and a measure-only Tape Measure tool.

**Architecture:** `units.py` is pure parse/format (internal length = meters). A `DocumentSettings` on `MainWindow` holds the current `Units` (switchable from a Units menu). A `ValueControlBox` (pure state) + a Qt event filter capture typed input non-focused: a digit activates the box, every printable char then feeds it (suspending letter shortcuts), Enter calls `active_tool.apply_typed_value(text, units)`, Esc clears. Each tool re-resolves its in-progress gesture at the exact value using its existing command path. Tape Measure reuses the M4c overlay primitives.

**Tech Stack:** Python 3.13 · numpy · PySide6 (Qt) · pytest + pytest-qt. No C++/kernel changes. Spec: `docs/2026-06-16-M4d-units-measurement-design.md`.

---

## Conventions & guardrails (read before every task)

- **Interpreter:** always `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash). Never bare `python`/`pytest`.
- **Working dir:** run from `F:\dev\00_Parrow-Horrizon-Studio\pluton`. Bash cwd resets between calls — prefix with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton && …`.
- **No C++ rebuild needed** — M4d is pure Python (editable install). A brand-new module imports without reinstall.
- **Git:** work on `main`. Stage **specific files only** — never `git add -A`/`git add .`. End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  **Never** pass `--no-verify`, `--amend`, or `--no-gpg-sign`. Fix hook failures at the cause.
- **Ruff:** keep NEW code clean. The repo carries pre-existing RUF100 (`# noqa: ANN001`) debt — do NOT fix it; match the existing tools' style on Qt-event overrides (`# noqa: ANN001`). No NEW non-RUF100 findings (no F401/E501). Lines ≤ 100. CI does **not** run ruff (build.yml = pytest + ctest), but keep new files tidy.
- **Do not touch version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) until the release task (Task 15).
- **TDD:** failing test → watch fail → minimal code → watch pass → commit. One commit per task.
- **Qt mouse events in tests:** `QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x,y), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)`. Key events: `QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier, text)`. Tool tests need `qtbot`.
- **Fake snaps:** tools read only `snap.kind` + `snap.world_position`. Use `types.SimpleNamespace(kind=SnapKind.ENDPOINT, world_position=np.array([...],np.float32), axis=None, vertex_id=None, edge_id=None, edge_t=None)`.

---

## File structure

| File | Responsibility |
|------|----------------|
| `python/pluton/units.py` | **new** — `UnitSystem`, `Units`, `parse_length`/`format_length`/`parse_angle`/`format_angle`. Pure. |
| `python/pluton/document.py` | **new** — `DocumentSettings` (holds current `Units`). |
| `python/pluton/ui/value_control_box.py` | **new** — `ValueControlBox` (pure typed-buffer state). |
| `python/pluton/tools/tool.py` | + `Tool.apply_typed_value` (default False); + `ToolContext.units_provider`. |
| `python/pluton/ui/main_window.py` | DocumentSettings + Units menu; install VCB event filter; status-bar display; pass `units_provider` in ToolContext. |
| `python/pluton/tools/{move,rotate,scale,line,rectangle,circle,polygon,arc,push_pull}_tool.py` | + `apply_typed_value`; unit-aware `status_text`. |
| `python/pluton/tools/tape_measure_tool.py` | **new** — `TapeMeasureTool` (T). |
| `python/pluton/tools/__init__.py` | export `TapeMeasureTool`. |
| `tests/...` | per task. |

---

## Task 1: Units — metric parse/format

**Files:**
- Create: `python/pluton/units.py`
- Test: `tests/test_units_metric.py`

- [ ] **Step 1: Write the failing test** — `tests/test_units_metric.py`:

```python
"""Metric parse/format (internal length = meters)."""

from __future__ import annotations

import pytest

from pluton.units import Units, UnitSystem, format_length, parse_length

M = Units(system=UnitSystem.METRIC, metric_unit="m", metric_precision=3)
MM = Units(system=UnitSystem.METRIC, metric_unit="mm", metric_precision=1)


def test_parse_explicit_units():
    assert parse_length("1500mm", M) == pytest.approx(1.5)
    assert parse_length("150 cm", M) == pytest.approx(1.5)
    assert parse_length("1.5m", M) == pytest.approx(1.5)
    assert parse_length("2.5 m", MM) == pytest.approx(2.5)


def test_parse_bare_number_uses_display_unit():
    assert parse_length("1500", MM) == pytest.approx(1.5)   # mm display
    assert parse_length("1.5", M) == pytest.approx(1.5)     # m display


def test_parse_comma_decimal_and_space():
    assert parse_length("1,5 m", M) == pytest.approx(1.5)


def test_parse_rejects_garbage_and_negative():
    assert parse_length("", M) is None
    assert parse_length("abc", M) is None
    assert parse_length("-3m", M) is None


def test_format_metric():
    assert format_length(1.5, M) == "1.5 m"
    assert format_length(1.5, MM) == "1500 mm"
    assert format_length(2.0, M) == "2 m"        # trailing zeros stripped
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_units_metric.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** — `python/pluton/units.py`:

```python
"""Units: parse/format lengths and angles. Internal length unit is the METER.

Pure module — no Qt, no Scene. parse_* return None on unparseable input (the
caller ignores None). The model's base unit is 1 model unit = 1 meter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

INCH_M = 0.0254
_METRIC_FACTOR = {"mm": 0.001, "cm": 0.01, "m": 1.0}


class UnitSystem(Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


@dataclass(frozen=True)
class Units:
    system: UnitSystem = UnitSystem.METRIC
    metric_unit: str = "m"          # "mm" | "cm" | "m"
    metric_precision: int = 3       # decimal places when formatting metric
    imperial_denominator: int = 16  # smallest fraction denominator (…/16")


_METRIC_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mm|cm|m)?\s*$", re.IGNORECASE)


def _parse_metric(text: str, units: Units) -> float | None:
    m = _METRIC_RE.match(text)
    if not m:
        return None
    value = float(m.group(1))
    unit = (m.group(2) or units.metric_unit).lower()
    if unit not in _METRIC_FACTOR:
        return None
    return value * _METRIC_FACTOR[unit]


def format_length(meters: float, units: Units) -> str:
    if units.system is UnitSystem.IMPERIAL:
        return _format_imperial(meters, units)   # Task 3
    factor = _METRIC_FACTOR.get(units.metric_unit, 1.0)
    value = meters / factor
    s = f"{value:.{units.metric_precision}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s} {units.metric_unit}"


def parse_length(text: str, units: Units) -> float | None:
    if text is None:
        return None
    t = text.strip().replace(",", ".")
    if not t:
        return None
    if "'" in t or '"' in t:
        return _parse_imperial(t)   # Task 2
    return _parse_metric(t, units)
```

> Note: `_parse_imperial` and `_format_imperial` are added in Tasks 2 and 3. Add minimal stubs now so the module imports: `def _parse_imperial(text): return None` and `def _format_imperial(meters, units): return ""`. The metric tests don't exercise them. (Tasks 2/3 replace the stubs.)

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_units_metric.py -q` → PASS. Ruff: `.venv\Scripts\python.exe -m ruff check python/pluton/units.py tests/test_units_metric.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/units.py tests/test_units_metric.py
git commit -m "feat(units): metric length parse/format (base unit = meter)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Units — imperial parse (architectural)

**Files:**
- Modify: `python/pluton/units.py` (replace the `_parse_imperial` stub)
- Test: `tests/test_units_imperial_parse.py`

- [ ] **Step 1: Write the failing test** — `tests/test_units_imperial_parse.py`:

```python
"""Architectural imperial parse → meters."""

from __future__ import annotations

import pytest

from pluton.units import INCH_M, Units, UnitSystem, parse_length

IMP = Units(system=UnitSystem.IMPERIAL)


def _in(inches: float) -> float:
    return inches * INCH_M


def test_feet_inches_fraction():
    assert parse_length("3' 6 1/2\"", IMP) == pytest.approx(_in(42.5))
    assert parse_length("3'6\"", IMP) == pytest.approx(_in(42.0))
    assert parse_length("3'", IMP) == pytest.approx(_in(36.0))
    assert parse_length("42\"", IMP) == pytest.approx(_in(42.0))
    assert parse_length("6 3/4\"", IMP) == pytest.approx(_in(6.75))
    assert parse_length("6 1/2\"", IMP) == pytest.approx(_in(6.5))


def test_feet_no_close_quote():
    assert parse_length("3' 6", IMP) == pytest.approx(_in(42.0))


def test_bare_number_is_inches_in_imperial():
    assert parse_length("42", IMP) == pytest.approx(_in(42.0))


def test_imperial_garbage_returns_none():
    assert parse_length("3' x 5\"", IMP) is None
```

- [ ] **Step 2: Run; confirm FAIL** — `.venv\Scripts\python.exe -m pytest tests/test_units_imperial_parse.py -q` → FAIL (stub returns None).

- [ ] **Step 3: Implement** — in `python/pluton/units.py` replace the `_parse_imperial` stub and adjust `parse_length`'s bare-number branch for imperial. Add:

```python
_IMPERIAL_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*')?"           # optional feet
    r"\s*(?:(\d+)\s*)?"                        # optional whole inches
    r"(?:(\d+)\s*/\s*(\d+)\s*)?"               # optional fraction
    r'"?\s*$'                                  # optional close-quote
)


def _parse_imperial(text: str) -> float | None:
    # Require at least a foot or inch marker so plain numbers don't match here.
    if "'" not in text and '"' not in text:
        return None
    m = _IMPERIAL_RE.match(text)
    if not m:
        return None
    feet = float(m.group(1)) if m.group(1) else 0.0
    whole_in = float(m.group(2)) if m.group(2) else 0.0
    if m.group(3) and m.group(4):
        den = int(m.group(4))
        if den == 0:
            return None
        frac = int(m.group(3)) / den
    else:
        frac = 0.0
    if not (m.group(1) or m.group(2) or m.group(3)):
        return None  # empty / just a quote
    inches = feet * 12.0 + whole_in + frac
    return inches * INCH_M
```

And in `parse_length`, the bare-number (no quote) imperial case must mean inches:

```python
def parse_length(text: str, units: Units) -> float | None:
    if text is None:
        return None
    t = text.strip().replace(",", ".")
    if not t:
        return None
    if "'" in t or '"' in t:
        return _parse_imperial(t)
    if units.system is UnitSystem.IMPERIAL:
        # bare number → inches
        try:
            return float(t) * INCH_M if float(t) >= 0 else None
        except ValueError:
            return None
    return _parse_metric(t, units)
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_units_imperial_parse.py tests/test_units_metric.py -q` → all PASS (metric still green). Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/units.py tests/test_units_imperial_parse.py
git commit -m "feat(units): architectural imperial length parse (feet/inches/fraction)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Units — imperial format + angles

**Files:**
- Modify: `python/pluton/units.py` (replace `_format_imperial` stub; add angle fns)
- Test: `tests/test_units_imperial_format.py`, `tests/test_units_angle.py`

- [ ] **Step 1: Write the failing tests** — `tests/test_units_imperial_format.py`:

```python
"""Architectural imperial format with carry/reduce/omit."""

from __future__ import annotations

from pluton.units import INCH_M, Units, UnitSystem, format_length

IMP = Units(system=UnitSystem.IMPERIAL, imperial_denominator=16)


def _m(inches: float) -> float:
    return inches * INCH_M


def test_basic_forms():
    assert format_length(_m(42.5), IMP) == "3' 6 1/2\""
    assert format_length(_m(36.0), IMP) == "3'"
    assert format_length(_m(42.0), IMP) == "3' 6\""
    assert format_length(_m(6.5), IMP) == "6 1/2\""
    assert format_length(_m(6.0), IMP) == "6\""


def test_fraction_reduces():
    assert format_length(_m(6.0 + 8 / 16), IMP) == "6 1/2\""   # 8/16 → 1/2


def test_fraction_carries_to_inch_and_foot():
    # 11 + 15.9/16" rounds the fraction up to a whole inch → 12" → carries to 1'
    assert format_length(_m(11.0 + 15.97 / 16), IMP) == "1'"
    # 6 + 15.97/16 → 7"
    assert format_length(_m(6.0 + 15.97 / 16), IMP) == "7\""


def test_zero():
    assert format_length(0.0, IMP) == "0\""
```

`tests/test_units_angle.py`:

```python
from __future__ import annotations

import pytest

from pluton.units import format_angle, parse_angle


def test_parse_angle():
    assert parse_angle("47") == pytest.approx(47.0)
    assert parse_angle("47.5°") == pytest.approx(47.5)
    assert parse_angle("30 deg") == pytest.approx(30.0)
    assert parse_angle("nope") is None


def test_format_angle():
    assert format_angle(47.0) == "47°"
    assert format_angle(47.5) == "47.5°"
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — replace `_format_imperial` and add angle functions in `python/pluton/units.py`:

```python
def _format_imperial(meters: float, units: Units) -> str:
    den = max(1, units.imperial_denominator)
    total_in = meters / INCH_M
    # Round to the nearest 1/den inch up-front, then split.
    sixteenths = round(total_in * den)
    feet = sixteenths // (12 * den)
    rem = sixteenths - feet * 12 * den          # in 1/den inches
    whole_in = rem // den
    frac_units = rem - whole_in * den           # numerator over den
    parts: list[str] = []
    if feet:
        parts.append(f"{feet}'")
    inch_str = ""
    if whole_in or frac_units:
        if frac_units:
            f = Fraction(frac_units, den)        # reduces
            inch_str = (f"{whole_in} {f.numerator}/{f.denominator}\""
                        if whole_in else f"{f.numerator}/{f.denominator}\"")
        else:
            inch_str = f"{whole_in}\""
    if inch_str:
        parts.append(inch_str)
    if not parts:
        return "0\""
    return " ".join(parts)


_ANGLE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:°|deg|degrees)?\s*$", re.IGNORECASE)


def parse_angle(text: str) -> float | None:
    if text is None:
        return None
    m = _ANGLE_RE.match(text.strip())
    return float(m.group(1)) if m else None


def format_angle(degrees: float, precision: int = 1) -> str:
    s = f"{degrees:.{precision}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}°"
```

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_units_imperial_format.py tests/test_units_angle.py tests/test_units_metric.py tests/test_units_imperial_parse.py -q` → all PASS. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/units.py tests/test_units_imperial_format.py tests/test_units_angle.py
git commit -m "feat(units): imperial format (carry/reduce/omit) + angle parse/format

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `DocumentSettings` + Units menu

**Files:**
- Create: `python/pluton/document.py`
- Modify: `python/pluton/ui/main_window.py` (add a Units menu + `self._doc`)
- Test: `tests/test_document_settings.py`

- [ ] **Step 1: Write the failing test** — `tests/test_document_settings.py`:

```python
from __future__ import annotations

from pluton.document import DocumentSettings
from pluton.units import UnitSystem


def test_default_is_metric_meters():
    d = DocumentSettings()
    assert d.units.system is UnitSystem.METRIC
    assert d.units.metric_unit == "m"


def test_set_units_replaces():
    d = DocumentSettings()
    d.set_metric("mm")
    assert d.units.metric_unit == "mm"
    d.set_imperial()
    assert d.units.system is UnitSystem.IMPERIAL


def test_main_window_has_doc_and_units_menu(qtbot):
    from pluton.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win._doc.units.system is UnitSystem.METRIC
    titles = [m.title() for m in win.menuBar().findChildren(type(win.menuBar().addMenu("x")))]
    assert any("Units" in t for t in titles)
```

> If `MainWindow` has no menu bar yet, the test's menu assertion must still pass: add a `QMenuBar` with a "Units" menu in Task step 3. If introspection of menus is awkward, assert instead that `win._units_menu is not None` — keep whichever matches the implementation.

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — `python/pluton/document.py`:

```python
"""DocumentSettings — per-document preferences (in-memory for M4d).

Holds the active Units. File persistence arrives with the native format (M6).
"""

from __future__ import annotations

from pluton.units import Units, UnitSystem


class DocumentSettings:
    def __init__(self) -> None:
        self._units = Units()

    @property
    def units(self) -> Units:
        return self._units

    def set_metric(self, metric_unit: str = "m") -> None:
        self._units = Units(system=UnitSystem.METRIC, metric_unit=metric_unit,
                            metric_precision=self._units.metric_precision,
                            imperial_denominator=self._units.imperial_denominator)

    def set_imperial(self, denominator: int = 16) -> None:
        self._units = Units(system=UnitSystem.IMPERIAL,
                            imperial_denominator=denominator,
                            metric_unit=self._units.metric_unit,
                            metric_precision=self._units.metric_precision)
```

In `python/pluton/ui/main_window.py`: in `__init__`, add `self._doc = DocumentSettings()` (before building the ToolContext), and build a Units menu:

```python
        # Units menu
        menubar = self.menuBar()
        self._units_menu = menubar.addMenu("Units")
        for label, fn in (
            ("Metric — m", lambda: self._set_units_metric("m")),
            ("Metric — cm", lambda: self._set_units_metric("cm")),
            ("Metric — mm", lambda: self._set_units_metric("mm")),
            ("Imperial — architectural", self._set_units_imperial),
        ):
            self._units_menu.addAction(label, fn)
```

and the slots:

```python
    def _set_units_metric(self, unit: str) -> None:
        self._doc.set_metric(unit)
        self._refresh_status_text()
        self._viewport.update()

    def _set_units_imperial(self) -> None:
        self._doc.set_imperial()
        self._refresh_status_text()
        self._viewport.update()
```

(Import `DocumentSettings` at the top.)

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_document_settings.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/document.py python/pluton/ui/main_window.py tests/test_document_settings.py
git commit -m "feat(ui): DocumentSettings + Units menu (metric/imperial switch)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `ValueControlBox` (pure state)

**Files:**
- Create: `python/pluton/ui/value_control_box.py`
- Test: `tests/test_value_control_box.py`

- [ ] **Step 1: Write the failing test** — `tests/test_value_control_box.py`:

```python
from __future__ import annotations

from pluton.ui.value_control_box import ValueControlBox


def test_starts_empty_inactive():
    v = ValueControlBox()
    assert not v.active
    assert v.text == ""


def test_feed_activates_and_appends():
    v = ValueControlBox()
    v.feed("1"); v.feed("5"); v.feed("0"); v.feed("0"); v.feed("m"); v.feed("m")
    assert v.active
    assert v.text == "1500mm"


def test_backspace_edits_and_deactivates_when_empty():
    v = ValueControlBox()
    v.feed("4"); v.feed("2")
    v.backspace()
    assert v.text == "4" and v.active
    v.backspace()
    assert v.text == "" and not v.active


def test_clear():
    v = ValueControlBox()
    v.feed("9")
    v.clear()
    assert v.text == "" and not v.active
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — `python/pluton/ui/value_control_box.py`:

```python
"""ValueControlBox — pure state for the Measurements box (VCB).

Holds the typed buffer + an `active` flag. The MainWindow event filter feeds
it characters; the active tool consumes `text` on Enter. No Qt dependency.
"""

from __future__ import annotations


class ValueControlBox:
    def __init__(self) -> None:
        self._buffer = ""
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def text(self) -> str:
        return self._buffer

    def feed(self, ch: str) -> None:
        self._buffer += ch
        self._active = True

    def backspace(self) -> None:
        self._buffer = self._buffer[:-1]
        if not self._buffer:
            self._active = False

    def clear(self) -> None:
        self._buffer = ""
        self._active = False
```

- [ ] **Step 4: Run; confirm PASS.** Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/value_control_box.py tests/test_value_control_box.py
git commit -m "feat(ui): ValueControlBox typed-buffer state

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Tool ABC — `apply_typed_value` + `ToolContext.units_provider`

**Files:**
- Modify: `python/pluton/tools/tool.py`
- Test: `tests/test_tool_apply_typed_default.py`

- [ ] **Step 1: Write the failing test** — `tests/test_tool_apply_typed_default.py`:

```python
from __future__ import annotations

from pluton.tools.tool import ToolContext


def test_toolcontext_has_units_provider():
    ctx = ToolContext(scene=object())
    assert ctx.units_provider is None


def test_apply_typed_value_default_false():
    from pluton.tools.line_tool import LineTool
    assert LineTool().apply_typed_value("3", None) is False
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — in `python/pluton/tools/tool.py`:

Add to `ToolContext` (after `selection`):
```python
    units_provider: object = None  # M4d — callable () -> pluton.units.Units (or None)
```

Add to `Tool` (a concrete default method, next to `on_key_press`):
```python
    def apply_typed_value(self, text: str, units) -> bool:  # noqa: ANN001
        """Apply a typed VCB value to the in-progress gesture.

        Returns True if the value was consumed (the tool re-resolved + committed
        or advanced its gesture), else False. Default: not supported.
        """
        return False
```

- [ ] **Step 4: Run; confirm PASS.**

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tool.py tests/test_tool_apply_typed_default.py
git commit -m "feat(tools): Tool.apply_typed_value default + ToolContext.units_provider

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: VCB event filter + status-bar display (MainWindow)

**Files:**
- Modify: `python/pluton/ui/main_window.py` (install event filter; show VCB in status bar; pass `units_provider` in ToolContext)
- Test: `tests/test_vcb_event_filter.py`

- [ ] **Step 1: Write the failing test** — `tests/test_vcb_event_filter.py`:

```python
"""The VCB event filter: digit activates + consumes; Enter applies; Esc clears."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from pluton.ui.main_window import MainWindow


def _key(key, text=""):
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)


def test_digit_activates_and_is_consumed(qtbot):
    win = MainWindow(); qtbot.addWidget(win)
    win._tool_manager.activate_by_shortcut("M")  # a tool that supports typed entry
    consumed = win._vcb_handle_key(_key(Qt.Key.Key_1, "1"))
    assert consumed
    assert win._vcb.active and win._vcb.text == "1"


def test_letter_while_inactive_not_consumed(qtbot):
    win = MainWindow(); qtbot.addWidget(win)
    win._tool_manager.activate_by_shortcut("M")
    assert win._vcb_handle_key(_key(Qt.Key.Key_L, "l")) is False  # 'L' falls through to shortcut


def test_letter_while_active_is_consumed(qtbot):
    win = MainWindow(); qtbot.addWidget(win)
    win._tool_manager.activate_by_shortcut("M")
    win._vcb_handle_key(_key(Qt.Key.Key_1, "1"))
    assert win._vcb_handle_key(_key(Qt.Key.Key_M, "m")) is True
    assert win._vcb.text == "1m"


def test_enter_clears_and_esc_clears(qtbot):
    win = MainWindow(); qtbot.addWidget(win)
    win._tool_manager.activate_by_shortcut("M")
    win._vcb_handle_key(_key(Qt.Key.Key_1, "1"))
    win._vcb_handle_key(_key(Qt.Key.Key_Return, "\r"))  # apply (no gesture → tool returns False, but VCB clears)
    assert not win._vcb.active
    win._vcb_handle_key(_key(Qt.Key.Key_5, "5"))
    win._vcb_handle_key(_key(Qt.Key.Key_Escape, "\x1b"))
    assert not win._vcb.active
```

> The test calls a small pure-logic helper `MainWindow._vcb_handle_key(event) -> bool` (returns whether the key was consumed) so the filter logic is testable without simulating Qt's full event dispatch. The actual `eventFilter` delegates to it.

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — in `python/pluton/ui/main_window.py`:

`__init__`: `self._vcb = ValueControlBox()`, and install the filter: `from PySide6.QtWidgets import QApplication; QApplication.instance().installEventFilter(self)` (or `self.installEventFilter(self)` on the window — match the existing widget hierarchy). Pass `units_provider=lambda: self._doc.units` into the `ToolContext`.

Add the pure handler + the Qt `eventFilter`:

```python
    _VCB_PRINTABLE = set("0123456789.,'\"/ ")

    def _vcb_handle_key(self, event) -> bool:  # noqa: ANN001
        """Pure VCB key logic. Returns True if the key was consumed."""
        active_tool = self._tool_manager.active
        if active_tool is None:
            return False
        key = event.key()
        text = event.text()
        if self._vcb.active:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._vcb.text:
                    active_tool.apply_typed_value(self._vcb.text, self._doc.units)
                self._vcb.clear()
                self._refresh_status_text(); self._viewport.update()
                return True
            if key == Qt.Key.Key_Escape:
                self._vcb.clear()
                self._refresh_status_text(); self._viewport.update()
                return True
            if key == Qt.Key.Key_Backspace:
                self._vcb.backspace()
                self._refresh_status_text(); self._viewport.update()
                return True
            if text and text.isprintable() and text not in ("\r", "\n"):
                self._vcb.feed(text)
                self._refresh_status_text(); self._viewport.update()
                return True
            return False
        # inactive: only a digit activates the box.
        if text in set("0123456789"):
            self._vcb.feed(text)
            self._refresh_status_text(); self._viewport.update()
            return True
        return False

    def eventFilter(self, obj, event):  # noqa: ANN001, N802
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            if self._vcb.active or (event.type() == QEvent.Type.KeyPress
                                    and event.text() in set("0123456789")):
                if self._vcb_handle_key(event):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)
```

Update `_refresh_status_text` so the status bar shows the VCB buffer when active:

```python
    def _refresh_status_text(self) -> None:
        active = self._tool_manager.active
        if self._vcb.active:
            self._status_bar.set_status(self._vcb.text + "▏")
        elif active is None:
            self._status_bar.set_status("")
        else:
            self._status_bar.set_status(active.status_text or "")
        self._refresh_selection_status()
```

> **Implementer note:** the `ShortcutOverride` handling is what suspends the single-letter tool shortcuts while the VCB is active — accepting that event prevents the QShortcut from firing. Verify by the pytest-qt test plus a manual check (typing `1500mm` during a Move must not switch tools). If `QApplication.instance()` is None in a unit test, guard the install (`app = QApplication.instance(); if app: app.installEventFilter(self)`).

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_vcb_event_filter.py -q` → PASS. Then full suite → no regression.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/ui/main_window.py tests/test_vcb_event_filter.py
git commit -m "feat(ui): VCB event filter (digit-activates, shortcut-suspend, Enter/Esc)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: VCB for transforms (Move / Rotate / Scale)

**Files:**
- Modify: `python/pluton/tools/move_tool.py`, `rotate_tool.py`, `scale_tool.py`
- Test: `tests/test_vcb_transforms.py`

- [ ] **Step 1: Write the failing test** — `tests/test_vcb_transforms.py`:

```python
"""apply_typed_value on Move/Rotate/Scale resolves the gesture at the exact value."""

from __future__ import annotations

import math
import types

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.selection import Selection
from pluton.tools.move_tool import MoveTool
from pluton.tools.rotate_tool import RotateTool
from pluton.tools.scale_tool import ScaleTool
from pluton.tools.tool import ToolContext
from pluton.tools.transform_support import GripSpec
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind

U = Units()  # metric meters


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(p):
    return types.SimpleNamespace(kind=SnapKind.ENDPOINT, world_position=np.asarray(p, np.float32),
                                 axis=None, vertex_id=None, edge_id=None, edge_t=None)


def _square(s):
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([2, 0, 0], np.float32))
    c = s.add_vertex(np.array([2, 2, 0], np.float32))
    d = s.add_vertex(np.array([0, 2, 0], np.float32))
    f = s.add_face_from_loop([a, b, c, d])
    return a, b, c, d, f


def _ctx(s, stack, sel):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), selection=sel,
                       units_provider=lambda: U)


def test_move_typed_distance(qtbot):
    s = Scene(); a, b, c, d, f = _square(s)
    sel = Selection(); sel.replace(faces=[f]); stack = CommandStack()
    t = MoveTool(); t.activate(_ctx(s, stack, sel))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # grab
    t.on_mouse_move(_press(), _snap([0, 0, 1]))      # direction +Z (any magnitude)
    assert t.apply_typed_value("5", U) is True       # 5 m along +Z
    assert np.allclose(s.vertex(a).position, [0, 0, 5])
    assert stack.can_undo


def test_rotate_typed_angle(qtbot, monkeypatch):
    s = Scene()
    a = s.add_vertex(np.array([1, 0, 0], np.float32))
    b = s.add_vertex(np.array([2, 0, 0], np.float32))
    e = s.add_edge(a, b)
    sel = Selection(); sel.replace(edges=[e]); stack = CommandStack()
    t = RotateTool(); t.activate(_ctx(s, stack, sel))
    monkeypatch.setattr(t, "_pick_plane_normal", lambda ev: np.array([0, 0, 1], np.float32))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # center
    t.on_mouse_press(_press(), _snap([1, 0, 0]))     # start dir +X
    t.on_mouse_move(_press(), _snap([1, 1, 0]))      # sweeping CCW (+)
    assert t.apply_typed_value("90", U) is True
    assert np.allclose(s.vertex(a).position, [0, 1, 0], atol=1e-4)


def test_scale_typed_factor(qtbot, monkeypatch):
    s = Scene(); a, b, c, d, f = _square(s)
    sel = Selection(); sel.replace(faces=[f]); stack = CommandStack()
    t = ScaleTool(); t.activate(_ctx(s, stack, sel))
    grip = GripSpec(position=np.array([2, 2, 0], np.float32),
                    opposite=np.array([0, 0, 0], np.float32), axes=(0, 1))
    monkeypatch.setattr(t, "_pick_grip", lambda ev: grip)
    monkeypatch.setattr(t, "_cursor_world", lambda ev: np.array([3, 3, 0], np.float32))
    t.on_mouse_press(_press(), None)                 # arm grip (anchor origin)
    assert t.apply_typed_value("2", U) is True       # 2× about origin
    assert np.allclose(s.vertex(c).position, [4, 4, 0])
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — add `apply_typed_value` to each transform tool. The shared imports: `from pluton.units import parse_length, parse_angle`.

**MoveTool** (`move_tool.py`) — direction from the current `_delta`:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if not self._dragging or self._grab is None:
            return False
        dist = parse_length(text, units)
        if dist is None:
            return False
        norm = float(np.linalg.norm(self._delta))
        if norm < 1e-9:
            return False
        direction = (self._delta / norm).astype(np.float32)
        moves = {}
        for v in self._vertex_ids:
            old = self._orig[v]
            moves[v] = (old, (old + direction * dist).astype(np.float32))
        from pluton.commands.scene_commands import TransformVerticesCommand
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset()
        return True
```

**RotateTool** (`rotate_tool.py`) — sign from current sweep:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_angle
        if self._stage != _Stage.HAVE_START:
            return False
        deg = parse_angle(text)
        if deg is None:
            return False
        sign = 1.0 if self._swept_angle_from_cur() >= 0 else -1.0
        angle = sign * math.radians(deg)
        moves = self._compute_moves(angle)
        from pluton.commands.scene_commands import TransformVerticesCommand
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset()
        return True
```

**ScaleTool** (`scale_tool.py`) — uniform factor on the grip's driven axes:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        if self._active is None:
            return False
        try:
            factor = float(text.strip())
        except (ValueError, AttributeError):
            return False
        if factor <= 0:
            return False
        out = np.ones(3, np.float32)
        extent = (self._hi - self._lo).astype(np.float32)
        for ax in self._active.axes:
            if abs(float(extent[ax])) > 1e-9:
                out[ax] = factor
        ids = self._vertex_ids
        pts = np.array([self._orig[v] for v in ids], np.float32)
        from pluton.geometry.transforms import scale as scale_pts
        new = scale_pts(pts, self._anchor, out)
        moves = {v: (self._orig[v], new[i]) for i, v in enumerate(ids)}
        from pluton.commands.scene_commands import TransformVerticesCommand
        cmd = TransformVerticesCommand(moves)
        if not cmd.is_empty() and self._stack is not None:
            self._stack.execute(cmd, self._scene)
        self._reset_drag(); self._rebuild_box()
        return True
```

Also update each tool's numeric `status_text` to format via `units_provider` when present (store `self._units_provider = ctx.units_provider` in `activate`). Move:
```python
    @property
    def status_text(self):
        if self._selection is None or self._selection.is_empty():
            return "Select geometry first"
        if self._dragging:
            dist = float(np.linalg.norm(self._delta))
            if self._units_provider is not None:
                from pluton.units import format_length
                return f"Move {format_length(dist, self._units_provider())}"
            return f"Move {dist:.3f}"
        return "Move: pick a grab point"
```
Rotate `status_text` formats the angle via `format_angle`; Scale shows the factor (unitless). (Store `_units_provider = None` in `__init__`, set in `activate`.)

- [ ] **Step 4: Run; confirm PASS** — `.venv\Scripts\python.exe -m pytest tests/test_vcb_transforms.py -q` → 3 PASS. Full suite → no regression.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/move_tool.py python/pluton/tools/rotate_tool.py python/pluton/tools/scale_tool.py tests/test_vcb_transforms.py
git commit -m "feat(tools): VCB typed entry for Move/Rotate/Scale + unit-aware status

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: VCB for Line + Rectangle

**Files:**
- Modify: `python/pluton/tools/line_tool.py`, `rectangle_tool.py`
- Test: `tests/test_vcb_line_rect.py`

- [ ] **Step 1: Write the failing test** — `tests/test_vcb_line_rect.py`:

```python
from __future__ import annotations

import types

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.line_tool import LineTool
from pluton.tools.rectangle_tool import RectangleTool
from pluton.tools.tool import ToolContext
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind

U = Units()


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(p, kind=SnapKind.ENDPOINT):
    return types.SimpleNamespace(kind=kind, world_position=np.asarray(p, np.float32),
                                 axis=None, vertex_id=None, edge_id=None, edge_t=None)


def _ctx(s, stack):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), units_provider=lambda: U)


def test_line_typed_length(qtbot):
    s = Scene(); stack = CommandStack()
    t = LineTool(); t.activate(_ctx(s, stack))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # start
    t.on_mouse_move(_press(), _snap([1, 0, 0]))      # +X direction
    assert t.apply_typed_value("3", U) is True       # 3 m along +X
    # the second vertex must be at (3,0,0)
    assert any(np.allclose(v.position, [3, 0, 0]) for v in s.vertices_iter())


def test_rectangle_typed_dims(qtbot):
    s = Scene(); stack = CommandStack()
    t = RectangleTool(); t.activate(_ctx(s, stack))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # first corner
    t.on_mouse_move(_press(), _snap([1, 1, 0]))      # drag into +X/+Y quadrant
    assert t.apply_typed_value("4x2", U) is True     # 4 wide, 2 tall
    assert any(np.allclose(v.position, [4, 2, 0]) for v in s.vertices_iter())
    assert stack.can_undo
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement.**

**LineTool** (`line_tool.py`) — place the next vertex at the typed length along the current preview direction, reusing the gesture-extend path:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._state != _State.DRAWING or self._preview_tip is None or not self._gesture_vertex_ids:
            return False
        length = parse_length(text, units)
        if length is None or length <= 0:
            return False
        s = self._scene
        anchor = s.vertex(self._gesture_vertex_ids[-1]).position
        direction = np.asarray(self._preview_tip, np.float32) - anchor
        norm = float(np.linalg.norm(direction))
        if norm < 1e-9:
            return False
        target = (anchor + (direction / norm) * length).astype(np.float32)
        # reuse the extend path: add a vertex at `target` + an edge from the tip.
        from pluton.commands.scene_commands import AddEdgeCommand, AddVertexCommand
        assert self._composite is not None
        v_cmd = AddVertexCommand(target); v_cmd.do(s); self._composite.children.append(v_cmd)
        new_vid = v_cmd._vertex_id  # type: ignore[attr-defined]
        e_cmd = AddEdgeCommand(self._gesture_vertex_ids[-1], new_vid)
        e_cmd.do(s); self._composite.children.append(e_cmd)
        self._gesture_vertex_ids.append(new_vid)
        self._preview_tip = target.copy()
        return True
```

**RectangleTool** (`rectangle_tool.py`) — parse `W×H`, build from `_first_corner` with signs from `_preview_corner`, commit (factor the commit out of `on_mouse_press` into `_commit_rect(second_corner)` and call it from both):
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._state != _State.DRAGGING or self._first_corner is None or self._preview_corner is None:
            return False
        parts = text.replace("*", "x").replace("X", "x").split("x")
        if len(parts) != 2:
            return False
        w = parse_length(parts[0], units); h = parse_length(parts[1], units)
        if w is None or h is None or w <= 0 or h <= 0:
            return False
        fx, fy = float(self._first_corner[0]), float(self._first_corner[1])
        sx = 1.0 if self._preview_corner[0] >= fx else -1.0
        sy = 1.0 if self._preview_corner[1] >= fy else -1.0
        second = np.array([fx + sx * w, fy + sy * h, 0.0], np.float32)
        self._commit_rect(second)
        return True
```
where `_commit_rect(self, second)` contains the existing `on_mouse_press` DRAGGING body (the `xlo/xhi/ylo/yhi` normalize + composite build + push + `_reset_gesture`); `on_mouse_press` now calls `self._commit_rect(snap.world_position)`.

- [ ] **Step 4: Run; confirm PASS.** Full suite green.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/line_tool.py python/pluton/tools/rectangle_tool.py tests/test_vcb_line_rect.py
git commit -m "feat(tools): VCB typed entry for Line (length) + Rectangle (WxH)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: VCB for Circle + Polygon

**Files:**
- Modify: `python/pluton/tools/circle_tool.py`, `polygon_tool.py`
- Test: `tests/test_vcb_circle_polygon.py`

- [ ] **Step 1: Write the failing test** — `tests/test_vcb_circle_polygon.py`:

```python
from __future__ import annotations

import types

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.circle_tool import CircleTool
from pluton.tools.polygon_tool import PolygonTool
from pluton.tools.tool import ToolContext
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind

U = Units()


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(p):
    return types.SimpleNamespace(kind=SnapKind.ON_FACE, world_position=np.asarray(p, np.float32),
                                 axis=None, vertex_id=None, edge_id=None, edge_t=None)


def _ctx(s, stack):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), units_provider=lambda: U)


def _max_radius_from_origin(s):
    return max(float(np.linalg.norm(v.position[:2])) for v in s.vertices_iter())


def test_circle_typed_radius(qtbot):
    s = Scene(); stack = CommandStack()
    t = CircleTool(); t.activate(_ctx(s, stack))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # center on ground
    assert t.apply_typed_value("2", U) is True       # radius 2 m
    assert _max_radius_from_origin(s) == \
        __import__("pytest").approx(2.0, abs=1e-3)
    assert stack.can_undo


def test_polygon_sides_then_radius(qtbot):
    s = Scene(); stack = CommandStack()
    t = PolygonTool(); t.activate(_ctx(s, stack))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))     # center
    assert t.apply_typed_value("8s", U) is True      # set 8 sides, keep drawing
    assert t._sides == 8
    assert t.has_active_gesture                       # still drawing
    assert t.apply_typed_value("2", U) is True        # radius 2 → commit
    assert sum(1 for _ in s.vertices_iter()) == 8
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement.**

**CircleTool** (`circle_tool.py`) — typed radius commits using the existing build path:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._state != _State.DRAWING or self._plane is None:
            return False
        radius = parse_length(text, units)
        if radius is None or radius < _MIN_RADIUS:
            return False
        from pluton.geometry import circle
        from pluton.tools.shape_support import build_closed_face
        ring_uv = circle(radius, _SEGMENTS, self._start_angle)
        world = self._plane.to_world(ring_uv).astype(np.float32)
        composite = build_closed_face(self._scene, world, name="Draw Circle")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()
        return True
```

**PolygonTool** (`polygon_tool.py`) — `Ns` sets sides (continue), else radius commits:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        if self._state != _State.DRAWING or self._plane is None:
            return False
        t = text.strip().lower()
        if t.endswith("s"):
            try:
                n = int(t[:-1])
            except ValueError:
                return False
            self._sides = max(_MIN_SIDES, min(_MAX_SIDES, n))
            return True
        from pluton.units import parse_length
        radius = parse_length(t, units)
        if radius is None or radius < _MIN_RADIUS:
            return False
        from pluton.geometry import polygon
        from pluton.tools.shape_support import build_closed_face
        ring_uv = polygon(radius, self._sides, self._start_angle)
        world = self._plane.to_world(ring_uv).astype(np.float32)
        composite = build_closed_face(self._scene, world, name="Draw Polygon")
        if composite is not None and self._command_stack is not None:
            self._command_stack.push_executed(composite)
        self._reset_gesture()
        return True
```

Also route Circle/Polygon `status_text` radius through `format_length` when `units_provider` is set (store it in `activate`).

- [ ] **Step 4: Run; confirm PASS.** Full suite green.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/circle_tool.py python/pluton/tools/polygon_tool.py tests/test_vcb_circle_polygon.py
git commit -m "feat(tools): VCB typed entry for Circle (radius) + Polygon (radius/Ns)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: VCB for Arc + Push/Pull

**Files:**
- Modify: `python/pluton/tools/arc_tool.py`, `push_pull_tool.py`
- Test: `tests/test_vcb_arc_pushpull.py`

- [ ] **Step 1: Write the failing test** — `tests/test_vcb_arc_pushpull.py`:

```python
from __future__ import annotations

import types

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.arc_tool import ArcTool
from pluton.tools.push_pull_tool import PushPullTool
from pluton.tools.tool import ToolContext
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind

U = Units()


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(p):
    return types.SimpleNamespace(kind=SnapKind.ON_FACE, world_position=np.asarray(p, np.float32),
                                 axis=None, vertex_id=None, edge_id=None, edge_t=None)


def _ctx(s, stack):
    return ToolContext(scene=s, command_stack=stack, camera=None,
                       widget_size_provider=lambda: (800, 600), units_provider=lambda: U)


def test_arc_typed_chord_then_bulge(qtbot):
    s = Scene(); stack = CommandStack()
    t = ArcTool(); t.activate(_ctx(s, stack))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))      # start
    t.on_mouse_move(_press(), _snap([1, 0, 0]))       # +X dir for the chord
    assert t.apply_typed_value("4", U) is True        # chord length 4 → places end, advances
    t.on_mouse_move(_press(), _snap([2, 1, 0]))       # bulge side preview
    assert t.apply_typed_value("1", U) is True        # sagitta 1 → commit
    assert stack.can_undo


def test_pushpull_typed_distance(qtbot, monkeypatch):
    s = Scene()
    # build a unit square face on the ground
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([1, 0, 0], np.float32))
    c = s.add_vertex(np.array([1, 1, 0], np.float32))
    d = s.add_vertex(np.array([0, 1, 0], np.float32))
    f = s.add_face_from_loop([a, b, c, d])
    stack = CommandStack()
    t = PushPullTool(); t.activate(_ctx(s, stack))
    t._arm_face(f)                                     # enter DRAGGING directly
    assert t.apply_typed_value("3", U) is True         # extrude 3 m
    # a top vertex must exist at z = 3
    assert any(np.allclose(v.position, [0, 0, 3]) for v in s.vertices_iter())
    assert stack.can_undo
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement.**

**PushPullTool** (`push_pull_tool.py`) — set depth + commit:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._state != _State.DRAGGING or self._armed_face_id is None:
            return False
        depth = parse_length(text, units)
        if depth is None or depth < _MIN_COMMIT_DEPTH:
            return False
        self._current_depth = float(depth)
        self._commit_extrusion()
        self._reset_to_idle()
        return True
```

**ArcTool** (`arc_tool.py`) — chord length in PLACING_END (advance), sagitta in PLACING_BULGE (commit). The plane is 2D `(u,v)` with the start at the origin; the chord direction is the current `_cursor_uv` direction; the sagitta is the perpendicular height of the bulge point from the chord:
```python
    def apply_typed_value(self, text, units) -> bool:  # noqa: ANN001
        from pluton.units import parse_length
        if self._plane is None:
            return False
        val = parse_length(text, units)
        if val is None or val <= 0:
            return False
        if self._state == _State.PLACING_END and self._cursor_uv is not None:
            d = np.asarray(self._cursor_uv, np.float64)
            norm = float(np.linalg.norm(d))
            if norm < _MIN_CHORD:
                return False
            self._end_uv = (d / norm * val).astype(np.float64)
            self._cursor_uv = self._end_uv.copy()
            self._state = _State.PLACING_BULGE
            return True
        if self._state == _State.PLACING_BULGE and self._end_uv is not None:
            # Bulge point = chord midpoint + sagitta * unit-perpendicular, on the
            # side the cursor is currently on.
            mid = (_ORIGIN_UV + self._end_uv) / 2.0
            chord = self._end_uv - _ORIGIN_UV
            perp = np.array([-chord[1], chord[0]], np.float64)
            perp /= (np.linalg.norm(perp) + 1e-12)
            side = 1.0
            if self._cursor_uv is not None and float(np.dot(self._cursor_uv - mid, perp)) < 0:
                side = -1.0
            bulge_uv = mid + side * val * perp
            from pluton.geometry import arc_2pt
            from pluton.tools.shape_support import build_open_polyline
            pts_uv = arc_2pt(_ORIGIN_UV, self._end_uv, bulge_uv, _SEGMENTS)
            if len(pts_uv) < 2:
                return False
            world = self._plane.to_world(pts_uv).astype(np.float32)
            composite = build_open_polyline(self._scene, world, name="Draw Arc")
            if composite is not None and self._command_stack is not None:
                self._command_stack.push_executed(composite)
            self._reset_gesture()
            return True
        return False
```

- [ ] **Step 4: Run; confirm PASS.** Full suite green.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/arc_tool.py python/pluton/tools/push_pull_tool.py tests/test_vcb_arc_pushpull.py
git commit -m "feat(tools): VCB typed entry for Arc (chord/sagitta) + Push/Pull (depth)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Tape Measure tool (T)

**Files:**
- Create: `python/pluton/tools/tape_measure_tool.py`
- Modify: `python/pluton/tools/__init__.py` (export), `python/pluton/ui/main_window.py` (register + `T` shortcut)
- Test: `tests/test_tape_measure_tool.py`

- [ ] **Step 1: Write the failing test** — `tests/test_tape_measure_tool.py`:

```python
from __future__ import annotations

import types

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from pluton.scene.scene import Scene
from pluton.tools.tape_measure_tool import TapeMeasureTool
from pluton.tools.tool import ToolContext
from pluton.units import Units
from pluton.viewport.snap_engine import SnapKind

U = Units()


def _press():
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def _snap(p):
    return types.SimpleNamespace(kind=SnapKind.ENDPOINT, world_position=np.asarray(p, np.float32),
                                 axis=None, vertex_id=None, edge_id=None, edge_t=None)


def _ctx(s):
    return ToolContext(scene=s, command_stack=None, camera=None,
                       widget_size_provider=lambda: (800, 600), units_provider=lambda: U)


def test_distance_readout(qtbot):
    s = Scene()
    t = TapeMeasureTool(); t.activate(_ctx(s))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))
    t.on_mouse_press(_press(), _snap([3, 4, 0]))   # 3-4-5 → distance 5
    assert "5" in (t.status_text or "")
    assert t.shortcut == "T" and t.name == "Tape Measure"


def test_measure_only_no_mutation(qtbot):
    s = Scene()
    before = sum(1 for _ in s.vertices_iter())
    t = TapeMeasureTool(); t.activate(_ctx(s))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))
    t.on_mouse_press(_press(), _snap([1, 0, 0]))
    assert sum(1 for _ in s.vertices_iter()) == before


def test_esc_resets(qtbot):
    from PySide6.QtGui import QKeyEvent
    s = Scene()
    t = TapeMeasureTool(); t.activate(_ctx(s))
    t.on_mouse_press(_press(), _snap([0, 0, 0]))
    t.on_key_press(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not t.has_active_gesture
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — `python/pluton/tools/tape_measure_tool.py`:

```python
"""The Tape Measure tool (T) — point-to-point distance readout (measure-only)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent

from pluton.tools.tool import Tool, ToolContext, ToolOverlay

_LINE_COLOR = (0.95, 0.85, 0.20)


class TapeMeasureTool(Tool):
    @property
    def name(self) -> str:
        return "Tape Measure"

    @property
    def shortcut(self) -> str:
        return "T"

    def __init__(self) -> None:
        self._scene = None
        self._units_provider = None
        self._a: np.ndarray | None = None
        self._b: np.ndarray | None = None
        self._cursor: np.ndarray | None = None

    def activate(self, ctx: ToolContext) -> None:
        self._scene = ctx.scene
        self._units_provider = ctx.units_provider
        self._reset()

    def deactivate(self) -> None:
        self._reset()

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if snap.kind != SnapKind.NONE:
            self._cursor = np.asarray(snap.world_position, np.float32).copy()

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        from pluton.viewport.snap_engine import SnapKind
        if event.button() != Qt.MouseButton.LeftButton or snap.kind == SnapKind.NONE:
            return
        p = np.asarray(snap.world_position, np.float32).copy()
        if self._a is None:
            self._a = p
        elif self._b is None:
            self._b = p
        else:  # third click starts a fresh measurement
            self._a, self._b = p, None

    def on_key_press(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()

    def overlay(self) -> ToolOverlay:
        polylines = []
        end = self._b if self._b is not None else self._cursor
        if self._a is not None and end is not None:
            seg = np.array([self._a, end], np.float32)
            polylines.append((seg, _LINE_COLOR, 2.0))
        return ToolOverlay(
            rubber_band_segments=np.zeros((0, 3), np.float32),
            rubber_band_color=(1, 1, 1),
            snap_marker_position=None,
            snap_marker_color=(1, 1, 1),
            world_polylines=polylines,
        )

    @property
    def has_active_gesture(self) -> bool:
        return self._a is not None

    @property
    def anchor_or_none(self) -> np.ndarray | None:
        return self._a.copy() if self._a is not None else None

    @property
    def status_text(self):
        end = self._b if self._b is not None else self._cursor
        if self._a is None or end is None:
            return "Tape Measure: pick the first point"
        delta = np.asarray(end, np.float32) - self._a
        dist = float(np.linalg.norm(delta))
        if self._units_provider is not None:
            from pluton.units import format_length
            d = format_length(dist, self._units_provider())
            dx = format_length(abs(float(delta[0])), self._units_provider())
            dy = format_length(abs(float(delta[1])), self._units_provider())
            dz = format_length(abs(float(delta[2])), self._units_provider())
            return f"Distance {d}   Δ({dx}, {dy}, {dz})"
        return f"Distance {dist:.3f}"

    def _reset(self) -> None:
        self._a = None
        self._b = None
        self._cursor = None
```

Export in `python/pluton/tools/__init__.py` (`from pluton.tools.tape_measure_tool import TapeMeasureTool` + `__all__`). Register + shortcut in `main_window.py`: `self._tool_manager.register(TapeMeasureTool())` and `QShortcut(QKeySequence("T"), self, activated=lambda: self._activate("T"))`.

- [ ] **Step 4: Run; confirm PASS.** Full suite green.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/tape_measure_tool.py python/pluton/tools/__init__.py python/pluton/ui/main_window.py tests/test_tape_measure_tool.py
git commit -m "feat(tools): Tape Measure (T) — point-to-point distance readout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: ToolContext units wiring sweep (status formatting parity)

**Files:**
- Modify: any of the 9 tools whose `status_text` still shows raw numbers (Push/Pull depth at minimum) to format via `units_provider`.
- Test: `tests/test_status_formatting.py`

- [ ] **Step 1: Write the failing test** — `tests/test_status_formatting.py`:

```python
"""Numeric status_text honours the unit system when a units_provider is set."""

from __future__ import annotations

import numpy as np

from pluton.scene.scene import Scene
from pluton.tools.push_pull_tool import PushPullTool
from pluton.tools.tool import ToolContext
from pluton.units import Units, UnitSystem


def _ctx(s, units):
    return ToolContext(scene=s, command_stack=None, camera=None,
                       widget_size_provider=lambda: (800, 600), units_provider=lambda: units)


def test_pushpull_depth_formats_imperial(qtbot):
    s = Scene()
    a = s.add_vertex(np.array([0, 0, 0], np.float32))
    b = s.add_vertex(np.array([1, 0, 0], np.float32))
    c = s.add_vertex(np.array([1, 1, 0], np.float32))
    d = s.add_vertex(np.array([0, 1, 0], np.float32))
    f = s.add_face_from_loop([a, b, c, d])
    t = PushPullTool(); t.activate(_ctx(s, Units(system=UnitSystem.IMPERIAL)))
    t._arm_face(f)
    t._current_depth = 0.0254 * 12  # 1 foot
    assert "'" in (t.status_text or "")   # shows feet/inches, not "0.305"
```

- [ ] **Step 2: Run; confirm FAIL.**

- [ ] **Step 3: Implement** — store `self._units_provider = ctx.units_provider` in each tool's `activate` (where not already done in Tasks 8/10) and format numeric `status_text` via `pluton.units.format_length` / `format_angle` when the provider is present. For Push/Pull:
```python
    @property
    def status_text(self):
        if self._state == _State.DRAGGING:
            if self._units_provider is not None:
                from pluton.units import format_length
                return f"depth: {format_length(self._current_depth, self._units_provider())}"
            return f"depth: {self._current_depth:.3f}"
        return None
```
(Add `self._units_provider = None` in `__init__` and set it in `activate`.) Apply the same pattern to any remaining tool with a raw-number `status_text`.

- [ ] **Step 4: Run; confirm PASS.** Full suite green. Ruff clean on all touched tools.

- [ ] **Step 5: Commit**

```bash
git add python/pluton/tools/push_pull_tool.py tests/test_status_formatting.py
git commit -m "feat(tools): unit-aware numeric status_text (Push/Pull depth + sweep)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Full regression + manual visual verification

- [ ] **Step 1: C++ suite** — `ctest --test-dir build/tests --output-on-failure` → 76/76 (unchanged; M4d touches no C++).
- [ ] **Step 2: Python suite** — `.venv\Scripts\python.exe -m pytest -q` → all green; note the new total.
- [ ] **Step 3: Ruff on new/modified M4d files** — `.venv\Scripts\python.exe -m ruff check python/pluton/units.py python/pluton/document.py python/pluton/ui/value_control_box.py python/pluton/tools/tape_measure_tool.py` → clean (the `# noqa: ANN001` RUF100 on Qt-event overrides in the modified tools is the pre-existing repo pattern, acceptable).
- [ ] **Step 4: Manual visual verification** — `.venv\Scripts\python.exe -m pluton`, report observations:
  - Units menu switches Metric ⇄ Imperial; status readouts reformat live.
  - Move: drag a direction, type `2m` (or `2'`), Enter → exact move; undo restores.
  - Rotate: center + start, type `30`, Enter → 30°.
  - Scale: grab a grip, type `2`, Enter → 2×.
  - Line: click start, type `3m`, Enter → 3 m segment; Circle: center, type `2`, Enter; Polygon: `8s` then `2`; Rectangle: `4x2`; Push/Pull: arm a face, type `1m`.
  - Typing `1500mm` during a gesture does NOT switch tools (shortcut suspension works); Esc clears the box.
  - Tape Measure (T): pick two points → distance + Δ in current units; measure-only; Esc resets.
- [ ] **Step 5:** no code change expected; skip commit unless a notes file is added.

---

## Task 15: Release v0.1.3 (M4d)

> Only now touch version files. Follow the M4c release sequence.

**Files:** `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`, `docs/2026-05-16-pluton-design.md`.

- [ ] **Step 1: Bump version to 0.1.3** in all three files (`version = "0.1.3"`, `VERSION 0.1.3`, `return "0.1.3";`).
- [ ] **Step 2: Annotate the master design doc** — change the `**M4d** units & measurement (incl. the typed-entry VCB)` fragment to:
  `**M4d** ✅ *(shipped v0.1.3)* — units & measurement (metric + architectural imperial; the typed-entry VCB across all 9 tools; measure-only Tape Measure)`
- [ ] **Step 3: Rebuild + verify** — `.venv\Scripts\python.exe -m pip install -e . --no-build-isolation` then `.venv\Scripts\python.exe -c "import pluton._core as c; print(c.version())"` → `0.1.3`.
- [ ] **Step 4: Full suite once more** — `ctest …` (76/76) + `.venv\Scripts\python.exe -m pytest -q` (green).
- [ ] **Step 5: Commit the release**

```bash
git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md
git commit -m "release: v0.1.3 (M4d — units & measurement, VCB, Tape Measure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + watch the RIGHT CI run** — `git push`; find the **Build & Test** run on `main` (NOT Dependency Graph / CodeQL) and watch it:
```bash
gh run list --branch main --workflow "Build & Test" --limit 1
gh run watch <that-run-id> --exit-status
gh run view <id> --json status,conclusion,jobs   # confirm windows-2022 + ubuntu-24.04 = success
```
- [ ] **Step 7: Tag (annotated, SSH-signed) + push**
```bash
git tag -a v0.1.3-m4d -m "M4d — units & measurement (VCB + Tape Measure)"
git cat-file -t v0.1.3-m4d                                   # → tag
git cat-file tag v0.1.3-m4d | grep -c "BEGIN SSH SIGNATURE"  # → 1
git push origin v0.1.3-m4d
```
- [ ] **Step 8: File carry-over issues** (`gh issue create`): construction guides; tape-measure global rescale; persist unit preference in the file format (M6); locale-aware number formatting; VCB expression evaluation (`1m+200mm`).

---

## Self-review (plan author)

**Spec coverage:** units module metric+imperial+angles (T1–T3 ↔ spec §4.1); DocumentSettings + Units menu (T4 ↔ §4.2); ValueControlBox (T5 ↔ §4.3); Tool ABC `apply_typed_value` + `units_provider` (T6 ↔ §4.4/§4.6); event filter + status display (T7 ↔ §4.3/§4.6); per-tool VCB for all 9 tools (T8 transforms, T9 Line/Rect, T10 Circle/Polygon, T11 Arc/Push-Pull ↔ §4.4 table); Tape Measure (T12 ↔ §4.5); status formatting parity (T13 ↔ §4.6); regression+visual (T14 ↔ §6); release+carry-overs (T15 ↔ §7/§8). All spec sections map to a task.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; the Task 1 imperial stubs are explicitly replaced in Tasks 2–3.

**Type consistency:** `Units` fields (`system`/`metric_unit`/`metric_precision`/`imperial_denominator`), `parse_length(text, units)`/`format_length(meters, units)`/`parse_angle`/`format_angle` consistent T1↔T2↔T3↔tools. `apply_typed_value(self, text, units) -> bool` consistent T6↔T8–T13. `ValueControlBox.feed/backspace/clear/active/text` consistent T5↔T7. `ToolContext.units_provider` consistent T6↔T7↔all tools. `DocumentSettings.units/set_metric/set_imperial` consistent T4↔T7. The `_commit_rect` extraction (T9) is referenced only within RectangleTool.

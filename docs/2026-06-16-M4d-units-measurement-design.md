# M4d — Units & Measurement (VCB + Tape Measure) — Design Spec

- **Milestone:** M4d (fourth sub-milestone of M4, Phase 2 "Modeling App")
- **Depends on:** all prior tools (M2 Line/Rectangle, M3c Push/Pull, M4a Circle/Polygon/Arc, M4c Move/Rotate/Scale), the snap engine (M3d), the status bar.
- **Target release:** v0.1.3 (units + VCB + Tape Measure together).
- **Date:** 2026-06-16

---

## 1. Overview & Goals

Add precise numeric input and measurement, the three pieces shipping together:

- **Units** — a pure parse/format layer: user strings (`1500mm`, `3' 6 1/2"`) ↔ an internal length, plus a per-document unit preference (metric ↔ imperial) switchable from a Units menu.
- **VCB (Measurements box)** — SketchUp-style typed entry: start typing during any tool gesture and the keystrokes accumulate in the status bar's Measurements box; **Enter** applies the exact value and the active tool re-resolves its gesture; **Esc** clears.
- **Tape Measure (T)** — a point-to-point measurement tool that reports the distance (and Δx/Δy/Δz) in the current units.

**Base unit:** 1 model unit = **1 meter**. The C++ kernel stays raw `float`; units are a *display + parse* layer in Python. The snap grid stays 1 unit = 1 m.

**Why together:** the units module underpins both the VCB (parse/format) and the Tape Measure (readout). The VCB is the spine; once it exists, wiring each tool is small and mechanical. This directly unblocks carry-over [#47](https://github.com/Parrow-Horrizon-Studio/pluton/issues/47) (exact Move distance / Rotate angle / Scale factor) and the M4a exact-radius/sides cases.

## 2. Non-goals / Deferrals

- **Construction guides** (dashed guide lines/points from the Tape Measure) — a separate construction-geometry subsystem (new entity type, dashed rendering, guide snapping). Its own future milestone. **Carry-over.**
- **Tape-measure global rescale** (measure a known length, type the true length, scale the model). **Carry-over.**
- **File persistence of the unit setting** — belongs to native file I/O (**M6**). M4d keeps the unit preference in memory with a sensible default.
- **VCB before a gesture starts** (e.g. typing polygon sides before the first click is supported via the `Ns` syntax, but pre-gesture free typing for tools that don't need it is not). Typed entry applies to the *in-progress* gesture.
- **Localised decimal separators / thousands separators** — parse accepts `.` as the decimal point; `,` is treated as `.` for convenience but locale handling is out of scope.

## 3. Key decisions

| Decision | Choice |
|---|---|
| Scope | Units + VCB + Tape Measure in one release (v0.1.3). |
| Imperial depth | **Full architectural fractional feet-inches** (`3' 6 1/2"`), nearest 1/denominator (default 1/16"). |
| Tape Measure | Measure-only (distance + Δ readout). |
| VCB coverage | **All 9 natural tools**: Line, Rectangle, Circle, Polygon, Arc, Push/Pull, Move, Rotate, Scale. |
| VCB capture | Non-focused, SketchUp-style via an event filter; first digit activates and suspends letter shortcuts. |
| Base unit | 1 model unit = 1 m. |
| Default system | Metric (display unit `m`), switchable any time. |

## 4. Architecture

### 4.1 Units module — `python/pluton/units.py` (pure, no Qt)

```python
class UnitSystem(Enum): METRIC; IMPERIAL

@dataclass(frozen=True)
class Units:
    system: UnitSystem = UnitSystem.METRIC
    metric_unit: str = "m"          # "mm" | "cm" | "m"
    metric_precision: int = 3       # decimals shown in metric
    imperial_denominator: int = 16  # smallest fraction (…/16")
```

- `INCH_M = 0.0254`; metric factors mm=0.001, cm=0.01, m=1.0.
- `parse_length(text, units) -> float | None` — returns **meters**, or None if unparseable (the caller ignores None):
  - Explicit metric suffix: `1500mm`, `150cm`, `1.5m` (also `1.5 m`).
  - Architectural imperial (presence of `'` or `"`): `3' 6 1/2"`, `3' 6"`, `3'`, `6 3/4"`, `42"`, `6 1/2"`. Grammar: optional `<feet>'`, optional `<whole>` inches, optional `<num>/<den>` fraction, optional `"`.
  - Bare number (no unit): interpreted in the **current display unit** when metric; interpreted as **inches** when imperial (SketchUp architectural convention). Documented explicitly.
  - `,` accepted as `.`. Leading/trailing space tolerated. Negative rejected (returns None) for lengths.
- `format_length(meters, units) -> str`:
  - Metric → convert to `metric_unit`, round to `metric_precision`, strip trailing zeros sensibly, append unit: `1.5 m`, `1500 mm`.
  - Imperial → feet/inches with a reduced fraction to `imperial_denominator`, with carry (fraction→1 carries to inches; inches→12 carries to feet) and reduction (`8/16`→`1/2`). Omission rules: drop the fraction when zero; show `3'` for whole feet with zero inches; show only inches when feet == 0 (`6 1/2"`); show `0"` only for exactly zero.
- `parse_angle(text) -> float | None` (degrees; strips `°`/`deg`); `format_angle(deg, precision=1) -> str` (`47°`, `47.5°`). Scale factor parses as a plain positive float (no units).

Fully unit-tested; the fractional round-trip (`format` then `parse` ≈ identity within the denominator) is a key test.

### 4.2 Document settings — `DocumentSettings`

A small object (e.g. `python/pluton/document.py`) holding the current `Units`, owned by `MainWindow`. A **Units menu** (`QMenu`) offers system + metric-display-unit choices; selecting one replaces `Units` and refreshes the status bar (and any live overlay readout). In-memory only (persistence = M6).

### 4.3 VCB plumbing — `python/pluton/ui/value_control_box.py` + event filter

`ValueControlBox` (pure state, Qt-free):
```python
buffer: str; active: bool
feed(ch)          # append; active = True
backspace()       # drop last; active = False when buffer empties
clear()           # buffer = "", active = False
text -> str
```

Event filter installed by `MainWindow` (on the app or the window). On a key event **while a tool is active**:
- Printable VCB char (`0-9`, `.`, `,`, `'`, `"`, `/`, space, and unit letters `m c f` etc.): `feed`, refresh the status bar, **consume** the event (so the single-letter tool shortcut does NOT fire). The first such char activates the box.
- `Backspace`: `backspace()`, consume.
- `Enter`/`Return`: if `active` and `buffer` non-empty → `applied = active_tool.apply_typed_value(buffer, units)`; `clear()`; consume. Else fall through to the existing finish-gesture path.
- `Esc`: if `active` → `clear()`, consume; else fall through to the existing escape path.
- Letters when **not** active → fall through (the tool shortcut fires as today).

Qt detail: the filter must handle **`ShortcutOverride`** (accept it to pre-empt the QShortcut while the VCB is active) in addition to `KeyPress`, because single-letter QShortcuts otherwise swallow letter keys. The status bar shows `buffer` (with a trailing caret) while active, else the tool's live `status_text`.

### 4.4 `apply_typed_value(text, units) -> bool` — the 9 tools

New optional `Tool` method (default `return False`). **Common rule:** the typed value resolves the *in-progress gesture* along the already-established direction/anchor, then commits (or advances) exactly as a final mouse click/release would — using the same commands. Returns `True` if it consumed the value.

| Tool | Parsed as | Re-resolves to |
|---|---|---|
| Line | length (`parse_length`) | place next vertex at that length along the current preview direction; continue the polyline |
| Rectangle | `W×H` (two lengths, `x`/`*` separator) | set rectangle dimensions from the start corner |
| Circle | radius (`parse_length`); `Ns` → segment count | radius about the placed center (or set segments) |
| Polygon | radius; `Ns` → side count | radius about center (or set sides; `Ns` works before the center too) |
| Arc | bulge/radius (`parse_length`) | set the arc's sagitta/radius for the current chord |
| Push/Pull | distance (`parse_length`, signed by current drag side) | extrude the armed face by that distance |
| Move | distance (`parse_length`) | move the selection by that distance along the current drag direction |
| Rotate | angle (`parse_angle`) | rotate the selection by that angle about the placed center/axis |
| Scale | factor (plain float) | scale the selection by that factor about the active anchor |

Each tool already retains the needed state (anchor/direction/center) from its mouse gesture; `apply_typed_value` reuses the existing command path (e.g. `TransformVerticesCommand`, `AddEdge/Face`, push/pull commands). If the gesture isn't in a state that accepts a value (e.g. no direction yet), return `False`.

### 4.5 Tape Measure tool — `python/pluton/tools/tape_measure_tool.py` (shortcut **T**)

- Pick A (snapped) → pick B (snapped). The Measurements box shows the live distance during the second pick and the final distance + `Δx/Δy/Δz` after, all via `format_length`. Overlay: the A→B segment + endpoint markers + a midpoint distance label (reuses the M4c `world_polylines`/marker overlay path; the label via `status_text`).
- Measure-only — never mutates the scene. Esc resets; switching tools resets.
- `apply_typed_value` is **not** used by Tape Measure in M4d (rescale is deferred).

### 4.6 Status bar / rendering integration

- `MainWindow._refresh_status_text` shows the VCB buffer (with caret) when `vcb.active`, else `active.status_text`. Tools' numeric `status_text` (Move/Push-Pull/Circle/Tape Measure …) is routed through `format_length`/`format_angle` so readouts honour the unit setting.
- No new shaders. Tape Measure reuses the existing overlay primitives.

## 5. Edge cases & invariants

- **Unparseable input:** `parse_*` returns None; `apply_typed_value` returns False; the buffer is left for the user to fix (not auto-cleared on a bad Enter). A bad value never mutates the scene.
- **Shortcut/letter collision:** resolved by VCB-active suspension (§4.3). When the buffer empties via Backspace, `active` flips false and letter shortcuts resume.
- **Imperial formatting carries:** `5 15/16"` rounding up → `6"`; `11 3/4" `+ carry across 12 → `1' 0"` family; fractions reduced.
- **Bare-number ambiguity:** metric → display unit; imperial → inches. Documented; tested both ways.
- **Typed-then-mouse:** after `apply_typed_value` commits and resets a gesture, a trailing mouse release is a no-op (tools already guard "no active gesture").
- **Unit switch mid-session:** changes display/parse immediately; existing geometry is unchanged (it was always meters).
- **Angle/scale:** Rotate uses degrees (not the length parser); Scale factor is unitless and must be > 0.

## 6. Testing strategy

- **Units (pure, exhaustive):** metric parse/format round-trips at mm/cm/m; imperial parse of every grammar form; imperial format with carry + reduction + omission rules; bare-number metric-vs-inches; unparseable → None; angle parse/format; the `format→parse` near-identity property.
- **ValueControlBox (pure):** feed/backspace/clear/active transitions; backspace-to-empty deactivates.
- **Event filter (pytest-qt):** a digit activates + is consumed (shortcut suppressed); Enter calls `apply_typed_value` and clears; Esc clears; letters pass through when inactive.
- **Per-tool `apply_typed_value` (pytest-qt + Scene):** each of the 9 tools — establish the gesture, feed a value, assert the resolved geometry matches the exact value and one undoable command is pushed; bad value → False, no mutation. Reuse the M4c fake-snap harness.
- **Tape Measure:** A→B distance equals the Euclidean distance, formatted per units; Esc resets; no scene mutation.
- **Regression:** full C++ (76) + pytest suites stay green; existing tool gestures unaffected when nothing is typed.

## 7. Acceptance criteria

1. `units.py` parses + formats metric and full architectural imperial, with a `Units` preference object; all round-trip tests green.
2. A `DocumentSettings` + Units menu switches the system live and the status bar reflects it.
3. The Measurements box captures typed input non-focused, suspends letter shortcuts while active, applies on Enter, clears on Esc.
4. All 9 tools implement `apply_typed_value` and produce the exact-value geometry as one undoable command; a bad value is a no-op.
5. Tape Measure (T) reports distance + Δ in current units, measure-only, Esc-resettable.
6. Full suite green on Windows + Linux CI; manual visual verification passes.

## 8. Carry-over issues (file at release)

- Construction guides (Tape Measure guide lines/points) — own subsystem/milestone.
- Tape-measure global rescale (measure → type true length → scale model).
- Persist the unit preference in the file format (M6).
- Locale-aware number formatting (decimal/thousands separators).
- VCB history/expression evaluation (e.g. `1m+200mm`) if ever wanted.

## 9. Risks

- **VCB event-filter + ShortcutOverride** is the main integration risk — getting the single-letter-shortcut suspension right across Qt's shortcut/keypress ordering. Isolated in one filter + `ValueControlBox`, and covered by pytest-qt tests.
- **Architectural imperial formatting** edge cases (carry/reduce/omit) — contained in `units.py`, pinned by exhaustive tests.
- **Per-tool re-resolve** consistency — mitigated by a shared "resolve along established direction/anchor" rule and reuse of existing commands.

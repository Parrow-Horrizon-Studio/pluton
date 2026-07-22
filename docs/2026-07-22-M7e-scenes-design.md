# M7e — Scenes (Saved Views) — Design Spec

**Milestone:** M7e (fifth and final M7 "Architecture-specific tools" sub-milestone), following M7a (Wall, v0.2.1), M7b (Door/Window, v0.2.2), M7c (Roof, v0.2.3) and M7d (Dimensions & annotations, v0.2.4).

**Goal:** Named, saved **Scenes** — each capturing the camera, tag visibility, and render style — listed in a dockable panel, recalled with an **animated camera tween**, persisted through `.pluton`, and fully managed (create / update / rename / delete / reorder) with undo. Ship as **v0.2.5**.

**One-line summary:** A Scenes dock lets the user save the current view (camera + visible tags + Face Style / X-Ray) as a named Scene and fly back to it later with a SketchUp-style animated transition.

## Context & constraints (what shapes this design)

- **`Scene` is already taken.** `pluton.scene.scene.Scene` is the editable half-edge mesh, referenced across ~10 geometry-test files and every geometry command. To avoid a second, unrelated meaning colliding in the same namespace, the internal class for a saved view is named **`SavedView`** in a new **`pluton.views`** package. The *user-facing* label is **"Scenes"** everywhere (dock title, menu, buttons) — matching SketchUp's terminology, which is the point of the feature.
- **Camera state already round-trips.** `CameraState` (`io/document_codec.py`) is a frozen dataclass — `position`, `target`, `up`, `fov_y_deg` — with `from_camera` / `to_dict` / `from_dict` / `apply_to`, already converting numpy `float32` through plain Python floats for JSON. A `SavedView` reuses `CameraState` verbatim as its camera field; the float32↔JSON precision concern is already absorbed by this existing code.
- **Tag visibility is persisted; render style is not.** `Tag.visible` lives on `TagLibrary` and already round-trips. `RenderStyle(face_style: FaceStyle, xray: bool)` (`viewport/render_style.py`) is owned **only** by `MainWindow._render_style` and is **absent from `document_to_dict`** — set X-Ray, save, reopen, and it is silently lost today. Because a Scene captures render style, M7e persists `RenderStyle` document-wide, closing that latent bug as a bonus.
- **The camera has no animation system.** `Camera` is a plain mutable dataclass with no tween/interpolation. M7e introduces animated recall — but Qt supplies the timing loop (`QVariantAnimation` with built-in easing curves), so the new work is the *pure interpolation math*, not a hand-rolled timer.
- **No undo precedent for view/document-level state.** Units, tag visibility, and render-style toggles all mutate directly and bypass `CommandStack`; only entity-identity mutations (`TagInstancesCommand`) go through the stack. M7e deliberately makes Scene **management** (create/update/rename/delete/reorder) undoable — accidental deletion of a saved view must be recoverable — while Scene **recall** (a view change) is *not* undoable, matching SketchUp and the existing "view changes bypass the stack" convention.
- **Document state is scattered, not centralized.** There is no single `Document` object: `Model` (graph, tags, materials), `DocumentSettings` (units), `Camera` (on `ViewportWidget`), and `RenderStyle` (on `MainWindow`) are owned separately. Scenes attach to `Model` as `model.views` (riding `load_from` like `tags`/`materials`); recall reaches through `MainWindow` into camera / tag library / render style individually, exactly as `_reset_document` already does.
- **Scope of capture = what Pluton actually has.** SketchUp Scenes also store section planes, shadows, hidden geometry, and axes location. Pluton has **none** of those systems, so camera + tag visibility + render style is the *complete* set of current view state, not a partial subset.
- **Python-only. No C++/kernel change** → `ctest` stays **79/79**.

## Global Constraints

- **Ship as v0.2.5.** Version bumped only in the release task, in all three files: `pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`.
- **Python-only milestone.** No kernel change; `ctest` stays 79/79. Full `pytest` must remain well above the current **977** baseline.
- **Internal class `SavedView`; package `pluton.views`.** Never name the new class `Scene`. User-facing text is always "Scene"/"Scenes".
- **User-facing label is "Scenes"** — dock title, menu, and buttons — matching SketchUp.
- **Capture = camera + tag visibility + render style. Always restore all three** (no per-Scene property checkboxes in M7e).
- **Recall animates the camera only** (orbit-decomposition tween); tag visibility and render style apply **instantly** at animation start. Recall is **not** undoable.
- **Scene management is undoable** via `CommandStack`: create, update, rename, delete, reorder — each identity-preserving, delete restoring at its original index.
- **`SCHEMA_VERSION` bumped by exactly 1.** Two new top-level codec keys (`"scenes"`, `"style"`), each tolerated as absent on read so older `.pluton` files still open (empty `ViewLibrary`, default `RenderStyle`).
- **New files carry no `# noqa`.** Ruff select is `["E","F","W","I","N","UP","B","C4","RUF"]`; `ANN` is not selected, so an `ANN0xx` suppression is itself an RUF100. `main_window.py` stays additive — issue #48 finding count held at exactly **9**.
- **The tween interpolator is pure numpy, no Qt**, so it is unit-testable headlessly and deterministically.

---

## Section 1 — Architecture & layering

The spine: a **pure snapshot type + a library that owns the list**, mirroring `Tag`/`TagLibrary` and `CameraState`. The hard logic (interpolation, capture/apply, library ops, codec) is pure and headless-testable; only thin Qt shells (dock, animator) touch Qt.

- **`python/pluton/views/saved_view.py`** — `SavedView` (frozen dataclass): `id: int`, `name: str`, `camera: CameraState`, `tag_visibility: dict[int, bool]`, `face_style: str`, `xray: bool`. Pure data, no Qt. Reuses the existing `CameraState` as the camera field. `face_style` stores the `FaceStyle` enum member's `.name` (e.g. `"SHADED"`); reconstructed via `FaceStyle[name]`.
- **`python/pluton/views/view_library.py`** — `ViewLibrary`: owns `list[SavedView]` + `next_id`. Methods `add(view) -> SavedView`, `get(vid) -> SavedView | None`, `remove(vid)`, `rename(vid, name)`, `move(vid, direction)` (±1, clamped at ends), `update(vid, view)`, `views() -> list[SavedView]`, `to_records() -> list[dict]`, `from_records(records, next_id) -> ViewLibrary`. The exact method shape `TagLibrary`/`MaterialLibrary` use. Lives on `Model` as `model.views`.
- **`python/pluton/views/capture.py`** — pure helpers. `capture_view(next_id, name, camera, tag_library, render_style) -> SavedView` snapshots live state; `apply_view(view, camera, tag_library, render_style) -> None` restores it. Tag-visibility restore is a tolerant per-id `set_visible` — unknown ids (deleted tags) are silently skipped, matching `TagLibrary`'s dict-get safety.
- **`python/pluton/views/interpolate.py`** — the tween core, **pure numpy, no Qt**. Decompose each camera endpoint into `(target, azimuth, elevation, distance, fov)`; interpolate each under eased `t ∈ [0, 1]` (azimuth taking the short way across the ±180° seam); recompose to a camera pose `(position, target, up, fov_y_deg)`. Decomposition makes the camera *orbit* the model instead of straight-lining the eye through geometry. Signature: `interpolate_pose(from_cam: CameraState, to_cam: CameraState, t: float) -> CameraPose`, where `CameraPose` is a small dataclass or tuple of the four recomposed fields.
- **`python/pluton/viewport/view_animator.py`** — the thin Qt shell. A `QVariantAnimation` (built-in easing, `InOutSine`, ~700 ms) driving `interpolate_pose` each tick, writing the pose into `viewport.camera` and calling `update()`. `start(from_cam, to_cam)`, `cancel()`; a `finished` signal. Any camera input (orbit/pan/zoom) or a new recall calls `cancel()`/retargets. Tag visibility and render style are applied instantly by `MainWindow` at recall time, **before** the animation starts — only the camera tweens.
- **`python/pluton/commands/view_commands.py`** — `CreateViewCommand`, `DeleteViewCommand`, `RenameViewCommand`, `ReorderViewCommand`, `UpdateViewCommand`, all `target=model`, identity-preserving undo. Precedent: `TagInstancesCommand` (the one existing non-geometry, model-targeted command).
- **`python/pluton/ui/scenes_dock.py`** — `ScenesDock(QDockWidget)`: a `QListWidget` of Scene names (id stashed on each item via `Qt.ItemDataRole.UserRole`, double-click to rename) + **Add / Update / Delete / ↑ / ↓** buttons. Signals: `create_requested`, `update_requested(id)`, `delete_requested(id)`, `rename_requested(id, name)`, `reorder_requested(id, direction)`, `recall_requested(id)`. `set_library(library)` rebinds after Open/New; `refresh()` rebuilds rows. A near-mechanical clone of `TagsDock`, tabified with Tags/Materials on the right.
- **`main_window.py`** — owns wiring: build the dock, route CRUD signals through `CommandStack` and recall through the animator; persist `RenderStyle` document-wide; adopt `scenes`/`style` on New/Open.

---

## Section 2 — Entity model & persistence

- **`SavedView`** — an immutable snapshot. Camera is a nested `CameraState`; `tag_visibility` is `{tag_id: bool}` covering the tags that existed at capture time; `face_style`/`xray` capture the render style. Nothing is derived at draw time — a Scene is a literal record of "put the view back exactly here."
- **`ViewLibrary` on `Model`** — `model.views`, initialized empty in `Model.__init__`, and copied by `Model.load_from` (`self.views = other.views`) alongside `materials`/`tags`.
- **Persistence** — `SCHEMA_VERSION` bumped by 1. Two new **top-level** codec keys in `document_to_dict`, both following the existing `{"next_id", "items"}` shape:
  - `"scenes"`: `{"next_id": int, "items": [{"id", "name", "camera": {…CameraState…}, "tag_visibility": {"3": true, …}, "face_style": "SHADED", "xray": false}, …]}`.
  - `"style"`: `{"face_style": "SHADED", "xray": false}` — the document's **live** render style, now persisted.
- **JSON key discipline** — `tag_visibility` keys are stringified ids (JSON objects require string keys); `from_dict` casts back to `int`, matching the codec's existing string-key handling.
- **Back-compat** — the version gate already accepts equal-or-older, so v2 files still open. Reading a document **without** `"scenes"` yields an empty `ViewLibrary`; without `"style"`, a default `RenderStyle`. Both via `data.get(...)`, exactly how `annotations` was added in the prior bump.
- **`LoadedDocument`** NamedTuple gains `scenes: ViewLibrary` and `style: RenderStyle`; `load_document`/`save_document` thread both through. `MainWindow._reset_document` adopts them: applies `style` to `self._render_style`, rebinds the dock via `set_library`, refreshes the viewport.
- **Codec conventions** — free functions `saved_view_to_dict(view) -> dict` / `saved_view_from_dict(record) -> SavedView` and `render_style_to_dict` / `render_style_from_dict`, matching the `annotation_to_dict`/`from_dict` house style; `ViewLibrary.to_records`/`from_records` on the library itself, matching `TagLibrary`.

---

## Section 3 — Recall & animation

- **Instant properties, animated camera.** On recall, `MainWindow` applies tag visibility and render style **immediately** (so the renderer's `traverse_visible` and face pass reflect the Scene at once), then hands `(current_camera_as_CameraState, target_view.camera)` to the animator. Only the camera flies — matching SketchUp, where geometry visibility snaps and the camera tweens.
- **Orbit-decomposition tween.** `interpolate.py` decomposes both endpoints to `(target, azimuth, elevation, distance, fov)`, interpolates each under an eased parameter, and recomposes. This keeps the eye orbiting the model rather than cutting a straight chord through it, and keeps distance-to-target monotonic between endpoints.
- **Easing & duration.** `QEasingCurve.InOutSine`, ~700 ms fixed. (Duration/curve are constants for M7e; a preference is a tracked follow-up.)
- **Interrupt handling.** The animation is cancellable and re-targetable:
  - Any camera input mid-tween (orbit/pan/zoom) cancels it, leaving the camera wherever the user took it.
  - Selecting another Scene mid-tween retargets from the current in-flight pose to the new Scene.
  - File New/Open or document reset cancels any in-flight animation.
- **Recall is not undoable.** It mutates only camera/visibility/style, never geometry or tool state, so it is safe mid-tool (same class of change as an orbit) and does not touch `CommandStack`.
- **Degenerate tween.** Identical from/to poses produce a constant camera at every `t` (no NaN from a zero-length orbit); the animation still runs to completion harmlessly (or is short-circuited — implementation detail, tested either way).

---

## Section 4 — Scene management (dock & commands)

- **The dock** lists Scenes top-to-bottom in library order. Selecting a row **recalls** that Scene. Buttons:
  - **Add** — captures the current view as a new Scene named "Scene N" (next ordinal), appended to the list and selected.
  - **Update** — re-captures the live camera/tags/style into the selected Scene, overwriting its snapshot.
  - **Delete** — removes the selected Scene.
  - **↑ / ↓** — moves the selected Scene one place up/down (clamped at ends).
  - **Double-click a row** — inline rename.
- **Commands (all undoable, `target=model`):**
  - `CreateViewCommand(view)` — appends `view`; undo removes it; redo re-appends the **same** `SavedView` object (cache-and-reattach, per the codebase lifecycle rule).
  - `DeleteViewCommand(vid)` — captures the view and its index on first `do`; undo restores it **at its original index**; redo removes again.
  - `RenameViewCommand(vid, new_name)` — captures the old name on first `do` only (guarded, like `EditLabelTextCommand`), so repeated undo/redo restores the true original.
  - `ReorderViewCommand(vid, direction)` — records the before/after positions; undo reverses the move.
  - `UpdateViewCommand(vid, new_view)` — captures the prior `SavedView` snapshot on first `do` only; undo restores the prior snapshot even if live state changed between do and undo (the absolute-capture lesson from M7d's Move command).
- **Dirty marking.** Every management command marks the document dirty via the existing `CommandStack` change-listener path. Recall does **not** dirty the document (it changes no persisted state).
- **Empty state.** With no Scenes, the list is empty and Update/Delete/↑/↓ are disabled until a row exists.

---

## Section 5 — MainWindow integration

- **Ownership.** `model.views` is the source of truth. `MainWindow` builds `ScenesDock(self._model.views, self)`, adds it to the right dock area, tabifies it with the Materials/Tags docks, and adds a `toggleViewAction()` entry to the **View** menu (matching the Materials/Tags dock-toggle precedent).
- **Signal routing.** `create_requested → capture_view + CreateViewCommand`; `update_requested → capture_view + UpdateViewCommand`; `delete_requested → DeleteViewCommand`; `rename_requested → RenameViewCommand`; `reorder_requested → ReorderViewCommand`; `recall_requested → apply tags/style instantly + animator.start(...)`. CRUD paths run through `CommandStack.execute`, then `dock.refresh()`.
- **Render style becomes persisted document state.** `MainWindow` continues to own `self._render_style`, but it is now written to / read from the codec (`"style"` key) and adopted on New/Open. Existing face-style / X-Ray menu toggles are unchanged; they simply now survive a save→load round-trip.
- **Animator lifetime.** `MainWindow` owns one `ViewAnimator` bound to `self._viewport.camera`. It connects viewport camera-input signals (or the viewport forwards a "camera moved by user" notification) to `animator.cancel()`. `animator.finished` is a no-op beyond a final `update()`.
- **`main_window.py` stays additive** — issue #48 finding count held at exactly 9. New wiring only; no refactor of existing lines.
- **Undo/redo of management commands** refreshes the dock (a `CommandStack` change-listener already fires on undo/redo; `MainWindow` calls `dock.refresh()` there).

---

## Section 6 — Testing strategy

**Pure core (plain `pytest`, no Qt, deterministic):**
- **`test_interpolate.py`** — `t=0` reproduces the *from* pose exactly; `t=1` the *to* pose exactly (tight tolerance). `t=0.5` **orbits, not lerps**: the interpolated eye's distance-to-target equals the interpolated distance (value-pinned, not a count). Azimuth takes the **short way** across the ±180° seam (170° → −170° passes through 180°, not 0°). Degenerate identical from/to yields a constant camera with no NaN.
- **`test_saved_view.py` / `test_capture.py`** — `capture_view` snapshots live camera+tags+style; `apply_view` restores each; round-trip through a mutated `TagLibrary` is order-independent; an unknown tag id in `tag_visibility` is a silent no-op (no raise).
- **`test_view_library.py`** — add/get/remove/rename/move/update; `move` clamps at both ends; `to_records`/`from_records` round-trip preserves order and `next_id`.

**Persistence:**
- **`test_document_codec.py`** — `saved_view_to_dict`/`from_dict` and `render_style_to_dict`/`from_dict` round-trip headlessly; `tag_visibility` string-key↔int-key survives; documents with 0 and with N scenes both round-trip.
- **`test_pluton_file.py`** — full `.pluton` save→load with scenes + style; a **v2 file (no `scenes`/`style` keys) still opens** with an empty `ViewLibrary` and default style (the back-compat guarantee, tested explicitly).

**Commands (undo/redo, `pytest`):**
- **`test_view_commands.py`** — each of the five commands do/undo/redo; Delete restores at original index; Create/redo re-attaches the **same** `SavedView` identity; Update/Rename undo restores the prior value even if live state was mutated between do and undo.

**Qt shells (`qtbot`, headless offscreen):**
- **`test_scenes_dock.py`** — Add/Update/Delete/↑/↓ emit the right signals; id round-trips on the list item; double-click enters rename; `set_library` rebinds after Open/New; Update/Delete/↑/↓ disabled on empty. (Named to avoid collision with the geometry `test_scene*.py` files.)
- **`test_main_window_scenes.py`** — dock wired, View-menu entry present, recall triggers an animation and lands on the target pose after it completes; persisted style survives a save→New→open cycle.
- **`test_view_animator.py`** — start→finish lands exactly on target; a camera-input signal mid-flight cancels (final pose ≠ target, animation stopped); a second recall mid-flight retargets cleanly.

**Regression gate:** full `pytest` well above the 977 baseline; `ctest` stays **79/79** (kernel untouched).

---

## Decisions log

- **D1 — Internal name `SavedView`, package `pluton.views`; UI says "Scenes".** Avoids the `pluton.scene.scene.Scene` collision while keeping SketchUp-faithful terminology for the user.
- **D2 — Capture = camera + tag visibility + render style; always restore all three.** The complete set of view state Pluton currently has; per-Scene property checkboxes deferred (cleanly additive as a `properties` record defaulting to all-true).
- **D3 — Animated recall (orbit-decomposition tween), camera only.** Faithful to SketchUp's signature transition; Qt drives timing so the new work is pure math. Tags/style snap.
- **D4 — Scene management is undoable; recall is not.** Deletion must be recoverable; view changes bypass the stack, matching SketchUp and existing convention.
- **D5 — Render style becomes persisted document state.** Required by capture, and fixes the latent bug where X-Ray/Wireframe is lost on save.
- **D6 — Reorder ships; "play animation through all Scenes" (slideshow) does not.** Scene order stays meaningful; the slideshow is a loop over the same recall machinery, addable later without touching storage.
- **D7 — Dock, not a scene tab bar.** Matches every existing panel (`TagsDock`/`MaterialsDock`); a top tab bar is a bespoke layout with no precedent, addable later without changing storage or recall.

---

## Out of scope (tracked follow-ups)

- Per-Scene "properties to save" checkboxes (camera/tags/style toggles per Scene).
- Slideshow / "play animation through all Scenes."
- Scene tab bar across the top of the viewport.
- Configurable tween duration / easing preference.
- Section planes, shadows, hidden-geometry, axes-location capture (no such engine features exist).
- Scene thumbnails.

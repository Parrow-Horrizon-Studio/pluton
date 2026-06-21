# M5a — Viewport Display Styles — Design Spec

- **Milestone:** M5a (first sub-milestone of M5 "Materials & viewport styles", Phase 2 "Modeling App")
- **Depends on:** the renderer/scene-graph pipeline (M4e — `SceneRenderer` over `model.traverse()`), the phong + line shaders (M1), the Qt menubar (M4d Units menu, M4e Edit menu).
- **Target release:** v0.1.5 (viewport display styles).
- **Date:** 2026-06-21

---

## 1. Overview & Goals

Give the architect SketchUp's **face-style** display modes so the same model can be viewed as a shaded solid, a clean line drawing, a see-through wireframe, or an uncolored study — plus an **X-Ray** toggle for seeing geometry hidden behind faces.

Five visible behaviors ship in M5a, modeled as **four mutually-exclusive face styles plus one orthogonal X-Ray toggle** (the SketchUp model — face style and X-Ray are independent, so "X-Ray + Shaded" and "X-Ray + Wireframe" both exist):

- **Shaded** — phong-lit faces (today's look) with edges on top. *Default.*
- **Hidden Line** — faces filled with the viewport background color (unlit) to occlude what's behind, dark edges on top → a clean line drawing.
- **Monochrome** — phong-lit faces in one uniform gray (ignoring materials), edges on top.
- **Wireframe** — no face pass at all; all edges visible (fully see-through).
- **X-Ray (toggle)** — when a style draws faces, they become semi-transparent so geometry behind shows through; **edges stay opaque** (the line shader is untouched); overlays Shaded / Hidden Line / Monochrome (a no-op on Wireframe).

**Guiding constraint — reuse, don't rebuild.** The existing `phong` shader already exposes `u_material_ambient/diffuse/specular/shininess` uniforms (a deliberate M5 plug-in point). Every face style is reachable by driving those uniforms plus GL state; the *only* shader change is one new `u_alpha` uniform for X-Ray transparency. No kernel changes, no model changes — M5a is renderer + a View menu.

**Pre-materials caveat.** M5a ships before the material system (M5b). Until materials exist, **Shaded and Monochrome render nearly identically** (both fill faces with a single default color). Monochrome is still built now — it becomes visually distinct the moment per-object/per-face materials land in M5b. This is expected, documented, and called out in the manual visual pass.

**Regression safety net.** The startup default is Shaded + X-Ray off, which drives the face pass exactly as today (`u_alpha = 1.0`, default material, no blend). With the default style, M5a output is pixel-identical to v0.1.4.

## 2. Non-goals / Deferrals

Explicitly **out of scope** for M5a (candidate follow-ups noted):

- **Profile / silhouette edges** (thicker outlines on silhouettes) — needs per-frame, view-dependent silhouette detection. Strong M5a follow-up; would most improve Hidden Line.
- **Display-Edges on/off toggle** (hide all edges for a pure shaded render) — deferred.
- **Sketchy / jittered edges** — deferred (substantially harder than the five core behaviors).
- **Back Edges** (dashed hidden edges shown through faces) — deferred.
- **Two-color Monochrome** (distinct front/back face colors for reversed-face detection) — deferred; M5a Monochrome is a single uniform color.
- **Shaded-with-Textures** and any per-face / per-material color — **M5b** (materials).
- **Persisting the chosen style** in the document / file format — **M6** (file I/O). The style is session-only window state in M5a.
- **Style affecting picking** (e.g. disabling face clicks in Wireframe) — deferred; picking stays decoupled from display style (see §6).

## 3. Data model

New module `python/pluton/viewport/render_style.py`. Pure Python, no GL imports — independently unit-testable.

```python
class FaceStyle(Enum):
    WIREFRAME
    HIDDEN_LINE
    MONOCHROME
    SHADED

class FaceShading(Enum):
    LIT       # phong lighting with the (default) material color   → Shaded
    UNIFORM   # phong lighting, but one fixed monochrome gray       → Monochrome
    FLAT_BG   # unlit; filled with the background color             → Hidden Line

@dataclass(frozen=True)
class FaceStyleDescriptor:
    draw_faces: bool
    shading: FaceShading | None        # None  ⇔  draw_faces is False

@dataclass
class RenderStyle:
    face_style: FaceStyle = FaceStyle.SHADED   # startup default
    xray: bool = False

_FACE_STYLE_TABLE: dict[FaceStyle, FaceStyleDescriptor] = {
    FaceStyle.WIREFRAME:   FaceStyleDescriptor(draw_faces=False, shading=None),
    FaceStyle.HIDDEN_LINE: FaceStyleDescriptor(draw_faces=True,  shading=FaceShading.FLAT_BG),
    FaceStyle.MONOCHROME:  FaceStyleDescriptor(draw_faces=True,  shading=FaceShading.UNIFORM),
    FaceStyle.SHADED:      FaceStyleDescriptor(draw_faces=True,  shading=FaceShading.LIT),
}
```

A pure helper maps a shading mode (+ the background color + the current default material) to the concrete phong material uniforms and alpha — the seam between the data model and the GL calls, and the most valuable unit-test target:

```python
def face_uniforms(shading: FaceShading, *, bg, material, xray: bool) -> FaceUniforms:
    """Return (ambient, diffuse, specular, shininess, alpha) for a face pass.
       LIT     → material colors;                       alpha = XRAY_ALPHA if xray else 1.0
       UNIFORM → MONO_COLOR as the lit material;        alpha = …
       FLAT_BG → ambient=bg, diffuse=specular=(0,0,0);  alpha = …  (flat, unlit fill)
    """
```

Constants live in `render_style.py`: `MONO_COLOR` (neutral light gray) and `XRAY_ALPHA` (≈ 0.35). The background color is the renderer's existing clear color `(0.15, 0.16, 0.18)`, passed in (not duplicated).

**Ownership & flow.** `MainWindow` holds the authoritative `RenderStyle` (one global setting — Pluton has a single viewport). View-menu handlers mutate it, forward a copy to the renderer via `ViewportWidget.set_render_style()`, and trigger a repaint. `SceneRenderer` stores the current `RenderStyle` and reads it each frame. No undo/redo involvement — a display style is view state, not a document edit.

## 4. Renderer application

Changes in `python/pluton/viewport/scene_renderer.py` and `python/pluton/viewport/shaders/phong.frag`.

**Shader (the one and only shader edit).** Add `uniform float u_alpha;` to `phong.frag`; change the output to `frag_color = vec4(color, u_alpha);`. Register `"u_alpha"` in the face-program uniform-location list. Default value `1.0` ⇒ identical to current output (regression-safe). `phong.vert` is untouched.

**Per-definition loop (`render`).** For each `(definition, world)` in `model.traverse()`:
- `desc = _FACE_STYLE_TABLE[self._render_style.face_style]`.
- Draw the face pass only when `desc.draw_faces and buf.face_count > 0`, passing `shading=desc.shading` and `xray=self._render_style.xray` into `_draw_definition_faces`.
- The edge pass is **always** drawn (unchanged) — in Wireframe it is the only geometry pass.

**`_draw_definition_faces(...)`** gains `shading` and `xray` parameters:
- Compute uniforms via `face_uniforms(shading, bg=CLEAR_COLOR, material=DEFAULT_MATERIAL, xray=xray)` and set them on the face program (ambient/diffuse/specular/shininess + `u_alpha`).
- **X-Ray on:** `glEnable(GL_BLEND)`; `glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)`; `glDepthMask(GL_FALSE)` so transparent faces neither occlude each other nor hide geometry behind. Draw. Then **restore**: `glDepthMask(GL_TRUE)`, `glDisable(GL_BLEND)`.
- **X-Ray off:** `u_alpha = 1.0`, opaque depth-writing draw as today.
- State-restoration is mandatory and modeled on the M4e Task-15 dim fix, which patched a real GL blend-func state leak — the face pass must leave depth-mask and blend in their default state so the subsequent edge pass, overlays, and the next frame are correct.

**Composition with the existing dim pass.** The M4e active-context dim already modulates the face draw for non-active definitions. Dim and X-Ray both lower effective face alpha; they stack (both fade) with no special-casing. Hidden-Line / Monochrome dimming continues to work because dimming acts on the same face pass.

**Hidden Line depth.** `FLAT_BG` faces draw with depth-writes **on** (X-Ray off), so they occlude geometry/grid/axes behind while rendering in the background color — i.e. invisible fills that leave only the front (visible) edges, which is exactly hidden-line. (Hidden Line + X-Ray is permitted: faces become transparent and non-occluding, so more edges show through — acceptable, matches SketchUp allowing the combination.)

## 5. UI wiring

Changes in `python/pluton/ui/main_window.py` and `python/pluton/viewport/viewport_widget.py`.

- **View menu** (added to the menubar after Units): a `QActionGroup` of four **exclusive, checkable** actions — Wireframe / Hidden Line / Monochrome / Shaded — with **Shaded checked by default**; a separator; one **checkable X-Ray** action (independent of the group).
- **Handlers:** `_on_set_face_style(style: FaceStyle)` and `_on_toggle_xray(checked: bool)` update `self._render_style`, call `self._viewport.set_render_style(self._render_style)`, and repaint.
- **`ViewportWidget.set_render_style(style)`** forwards to its `SceneRenderer.set_render_style(style)` and calls `self.update()` (the widget owns the renderer; `MainWindow` does not reach the renderer directly).
- No keyboard shortcuts in M5a (View-menu only, per scope decision).

## 6. Interactions & edge cases

- **Overlays are style-independent and always on top.** Selection highlight, hover silhouette, snap glyphs, tool overlays (rubber-bands, gizmos, face-fills), grid, axes, instance bounding boxes, and the breadcrumb render exactly as today, after the geometry passes. Selection-blue is visible in Wireframe and through X-Ray.
- **Picking is decoupled from display style (deliberate).** Ray-vs-face picking, snap, and every tool behave identically in all four styles — including Wireframe, where SketchUp would block face clicks. Coupling the input pipeline to a view setting is out of scope; "disable/alter face ops in Wireframe" is a noted follow-up.
- **X-Ray on Wireframe** is a no-op (no face pass to make transparent); the toggle still reflects state and is harmless.
- **Startup** is Shaded + X-Ray off ⇒ pixel-identical to v0.1.4 (regression safety).
- **Grid / axes** are drawn before geometry and are unaffected; in Hidden Line they are correctly occluded by bg-colored faces where geometry covers them.

## 7. Testing

- **Unit (headless, no GL context):**
  - `_FACE_STYLE_TABLE` — each `FaceStyle` maps to the expected `(draw_faces, shading)`.
  - `RenderStyle` defaults (`SHADED`, `xray=False`).
  - `face_uniforms(...)` — the pure shading→uniforms helper for all three shading modes × X-Ray on/off (asserts FLAT_BG zeroes diffuse/specular and uses bg as ambient; UNIFORM uses MONO_COLOR; LIT uses the material; alpha is XRAY_ALPHA only when xray).
- **pytest-qt (widget, no real GL output):** View-menu wiring — `QActionGroup` exclusivity (selecting one unchecks the rest), Shaded checked by default, X-Ray independently checkable; handlers mutate `MainWindow._render_style` and forward to the viewport. Use a captured/fake `set_render_style` (or assert the renderer's stored style) to avoid needing a GL context.
- **Manual visual verification (the GL pixels — not CI-testable):** the **4 × 2 matrix** {Wireframe, Hidden Line, Monochrome, Shaded} × {X-Ray off, on}, on a multi-object scene that includes a moved group and an active selection. Confirm: see-through Wireframe; Hidden-Line occlusion; Monochrome ≈ Shaded (expected pre-materials); X-Ray transparency; overlays/selection intact in every mode; and **no GL state leak** when switching styles repeatedly (toggle back and forth, confirm Shaded returns to baseline).
- GL pixel output itself is not unit-tested — consistent with the project's renderer-testing pattern (headless-testable seams + manual visual pass).

## 8. Files touched (summary)

- **New:** `python/pluton/viewport/render_style.py` (FaceStyle, FaceShading, FaceStyleDescriptor, RenderStyle, `_FACE_STYLE_TABLE`, `face_uniforms`, constants); `tests/test_render_style.py`; `tests/test_view_menu.py`.
- **Edited:** `python/pluton/viewport/scene_renderer.py` (store `RenderStyle`; descriptor-driven face pass; X-Ray blend/depth state + restore); `python/pluton/viewport/shaders/phong.frag` (`u_alpha`); `python/pluton/viewport/viewport_widget.py` (`set_render_style`); `python/pluton/ui/main_window.py` (View menu + handlers + `_render_style`).
- **No** changes to the C++ kernel, the model/scene graph, the command stack, or picking.

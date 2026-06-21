# M5a — Viewport Display Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SketchUp-style viewport display modes — four mutually-exclusive face styles (Wireframe / Hidden Line / Monochrome / Shaded) plus an orthogonal X-Ray toggle — switchable from a new View menu.

**Architecture:** A pure-data `render_style` module holds the state (`RenderStyle`), a descriptor table (`FACE_STYLE_TABLE`), and a pure resolver (`resolve_face_pass`) that turns `(style, dimmed)` into concrete face-pass parameters (material uniforms, alpha, blend, depth-write). The renderer consults the resolver each frame; `_draw_definition_faces` becomes a thin GL applicator. A new `u_alpha` uniform on `phong.frag` carries transparency (X-Ray and the existing dim pass unify through it). A View menu mutates the window's `RenderStyle` and forwards it to the renderer via the viewport.

**Tech Stack:** Python 3.13, PySide6 (Qt), PyOpenGL, numpy, pytest + pytest-qt. C++/nanobind kernel is **not** touched.

Spec: `docs/2026-06-21-M5a-viewport-styles-design.md`

## Global Constraints

- **Python interpreter:** always `.venv\Scripts\python.exe` (PowerShell) / `.venv/Scripts/python.exe` (bash) explicitly — bare `python`/`pytest` resolve to a drifting editable install.
- **No C++ kernel changes** in M5a (renderer + UI only). No model / command-stack / picking changes.
- **Version files** (`pyproject.toml`, `CMakeLists.txt`, `cpp/src/version.cpp`) are bumped **only** in the release task (Task 8). Do not touch them before then.
- **Git:** work on `main` directly (no feature branches). Stage **specific files only** — never `git add -A` / `git add .`. Never pass `--no-verify`, `--amend`, or `--no-gpg-sign` (SSH commit signing must stay enabled). End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Bash cwd resets between turns** — prefix commands with `cd /f/dev/00_Parrow-Horrizon-Studio/pluton &&`.
- **Outward-facing actions** (push, tag, CI watch, filing issues) require explicit user authorization per turn.
- **Renderer pixel output is visual-verification-only** — CI has no GL context. Each renderer task unit-tests its pure seam; actual pixels are confirmed in the Task 7 manual matrix.
- **Regression invariant:** with the startup default (Shaded + X-Ray off), face rendering must be byte-identical to v0.1.4 (`u_alpha = 1.0`, default material, no blend). The full suite (572 pytest + 76 ctest as of v0.1.4) must stay green.

---

### Task 1: render_style module — state + descriptor table

**Files:**
- Create: `python/pluton/viewport/render_style.py`
- Test: `tests/test_render_style.py`

**Interfaces:**
- Produces: `FaceStyle` (enum: `WIREFRAME`, `HIDDEN_LINE`, `MONOCHROME`, `SHADED`); `FaceShading` (enum: `LIT`, `UNIFORM`, `FLAT_BG`); `FaceStyleDescriptor(draw_faces: bool, shading: FaceShading | None)`; `RenderStyle(face_style: FaceStyle = FaceStyle.SHADED, xray: bool = False)`; `FACE_STYLE_TABLE: dict[FaceStyle, FaceStyleDescriptor]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render_style.py
from __future__ import annotations

from pluton.viewport.render_style import (
    FACE_STYLE_TABLE,
    FaceShading,
    FaceStyle,
    RenderStyle,
)


def test_render_style_defaults_to_shaded_no_xray():
    rs = RenderStyle()
    assert rs.face_style is FaceStyle.SHADED
    assert rs.xray is False


def test_face_style_table_covers_all_styles():
    assert set(FACE_STYLE_TABLE) == set(FaceStyle)


def test_face_style_table_draw_faces_and_shading():
    assert FACE_STYLE_TABLE[FaceStyle.WIREFRAME].draw_faces is False
    assert FACE_STYLE_TABLE[FaceStyle.WIREFRAME].shading is None
    assert FACE_STYLE_TABLE[FaceStyle.HIDDEN_LINE].shading is FaceShading.FLAT_BG
    assert FACE_STYLE_TABLE[FaceStyle.MONOCHROME].shading is FaceShading.UNIFORM
    assert FACE_STYLE_TABLE[FaceStyle.SHADED].shading is FaceShading.LIT
    for style in (FaceStyle.HIDDEN_LINE, FaceStyle.MONOCHROME, FaceStyle.SHADED):
        assert FACE_STYLE_TABLE[style].draw_faces is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pluton.viewport.render_style'`

- [ ] **Step 3: Write minimal implementation**

```python
# python/pluton/viewport/render_style.py
"""Viewport display-style state + descriptor table (M5a).

Pure Python — no GL imports — so it is fully unit-testable headlessly. The
renderer reads RenderStyle each frame and resolves it (see resolve_face_pass,
added in a later task) into concrete face-pass parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class FaceStyle(Enum):
    """Mutually-exclusive face display styles (the View > Face Style radio set)."""

    WIREFRAME = auto()
    HIDDEN_LINE = auto()
    MONOCHROME = auto()
    SHADED = auto()


class FaceShading(Enum):
    """How a drawn face pass is shaded."""

    LIT = auto()       # phong lighting with the (default) material color → Shaded
    UNIFORM = auto()   # phong lighting, but one fixed monochrome color    → Monochrome
    FLAT_BG = auto()   # unlit; filled with the background color           → Hidden Line


@dataclass(frozen=True)
class FaceStyleDescriptor:
    draw_faces: bool
    shading: FaceShading | None  # None iff draw_faces is False


@dataclass
class RenderStyle:
    """The viewport's current display style. One global setting per window."""

    face_style: FaceStyle = FaceStyle.SHADED
    xray: bool = False


FACE_STYLE_TABLE: dict[FaceStyle, FaceStyleDescriptor] = {
    FaceStyle.WIREFRAME: FaceStyleDescriptor(draw_faces=False, shading=None),
    FaceStyle.HIDDEN_LINE: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.FLAT_BG),
    FaceStyle.MONOCHROME: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.UNIFORM),
    FaceStyle.SHADED: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.LIT),
}

# Tunable look constants (revisited in the Task 7 visual pass).
MONO_COLOR = (0.72, 0.72, 0.74)  # uniform diffuse gray for Monochrome
XRAY_ALPHA = 0.35                # face opacity when X-Ray is on
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/render_style.py tests/test_render_style.py && git commit -m "$(cat <<'EOF'
feat(m5a): render_style module — FaceStyle/RenderStyle + descriptor table

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `face_uniforms()` — pure shading → phong-uniforms mapping

**Files:**
- Modify: `python/pluton/viewport/render_style.py`
- Test: `tests/test_render_style.py`

**Interfaces:**
- Consumes: `FaceShading`, `MONO_COLOR`, `XRAY_ALPHA` (Task 1).
- Produces: `Material(ambient, diffuse, specular, shininess)`; `FaceUniforms(ambient, diffuse, specular, shininess, alpha)`; `face_uniforms(shading: FaceShading, *, bg: tuple[float,float,float], material: Material, xray: bool) -> FaceUniforms`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_render_style.py
from pluton.viewport.render_style import (  # noqa: E402  (extend existing import)
    MONO_COLOR,
    XRAY_ALPHA,
    FaceUniforms,
    Material,
    face_uniforms,
)

_BG = (0.15, 0.15, 0.18)
_MAT = Material(
    ambient=(0.10, 0.10, 0.11),
    diffuse=(0.65, 0.65, 0.70),
    specular=(0.10, 0.10, 0.10),
    shininess=16.0,
)


def test_face_uniforms_lit_uses_material_opaque():
    fu = face_uniforms(FaceShading.LIT, bg=_BG, material=_MAT, xray=False)
    assert isinstance(fu, FaceUniforms)
    assert fu.diffuse == _MAT.diffuse
    assert fu.ambient == _MAT.ambient
    assert fu.specular == _MAT.specular
    assert fu.alpha == 1.0


def test_face_uniforms_uniform_uses_mono_diffuse():
    fu = face_uniforms(FaceShading.UNIFORM, bg=_BG, material=_MAT, xray=False)
    assert fu.diffuse == MONO_COLOR
    assert fu.ambient == _MAT.ambient        # keeps material ambient → still "lit"
    assert fu.alpha == 1.0


def test_face_uniforms_flat_bg_is_unlit_background_fill():
    fu = face_uniforms(FaceShading.FLAT_BG, bg=_BG, material=_MAT, xray=False)
    assert fu.ambient == _BG                 # output == background (unlit)
    assert fu.diffuse == (0.0, 0.0, 0.0)
    assert fu.specular == (0.0, 0.0, 0.0)
    assert fu.alpha == 1.0


def test_face_uniforms_xray_lowers_alpha_for_every_shading():
    for shading in (FaceShading.LIT, FaceShading.UNIFORM, FaceShading.FLAT_BG):
        fu = face_uniforms(shading, bg=_BG, material=_MAT, xray=True)
        assert fu.alpha == XRAY_ALPHA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -k face_uniforms -v`
Expected: FAIL — `ImportError: cannot import name 'face_uniforms'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to python/pluton/viewport/render_style.py

@dataclass(frozen=True)
class Material:
    """A phong material's color terms (the renderer's current default material)."""

    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float


@dataclass(frozen=True)
class FaceUniforms:
    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float
    alpha: float


def face_uniforms(
    shading: FaceShading,
    *,
    bg: tuple[float, float, float],
    material: Material,
    xray: bool,
) -> FaceUniforms:
    """Map a shading mode to concrete phong material uniforms + alpha.

    LIT     → the material's own colors (today's Shaded look).
    UNIFORM → material ambient/specular, but MONO_COLOR diffuse (Monochrome).
    FLAT_BG → unlit fill: ambient = bg, diffuse/specular = 0 (Hidden Line).
    X-Ray   → alpha = XRAY_ALPHA (else 1.0), orthogonal to shading.
    """
    alpha = XRAY_ALPHA if xray else 1.0
    if shading is FaceShading.LIT:
        return FaceUniforms(
            material.ambient, material.diffuse, material.specular, material.shininess, alpha
        )
    if shading is FaceShading.UNIFORM:
        return FaceUniforms(
            material.ambient, MONO_COLOR, material.specular, material.shininess, alpha
        )
    # FaceShading.FLAT_BG
    return FaceUniforms(bg, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), material.shininess, alpha)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -v`
Expected: PASS (all Task 1 + Task 2 tests)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/render_style.py tests/test_render_style.py && git commit -m "$(cat <<'EOF'
feat(m5a): face_uniforms() — pure shading-to-phong-uniforms mapping

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `resolve_face_pass()` — compose style + dim + X-Ray into a face-pass

**Files:**
- Modify: `python/pluton/viewport/render_style.py`
- Test: `tests/test_render_style.py`

**Interfaces:**
- Consumes: `RenderStyle`, `FACE_STYLE_TABLE`, `face_uniforms`, `Material` (Tasks 1–2).
- Produces: `ResolvedFacePass(draw_faces, ambient, diffuse, specular, shininess, alpha, blend, depth_write)`; `resolve_face_pass(style: RenderStyle, *, dimmed: bool, bg, material: Material, dim_ambient, dim_diffuse, dim_alpha) -> ResolvedFacePass`. This is the single source of truth the renderer applies — `draw_faces=False` ⇒ skip the face pass; `blend` ⇒ enable `SRC_ALPHA` blending; `depth_write=False` ⇒ `glDepthMask(GL_FALSE)` (X-Ray only).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_render_style.py
from pluton.viewport.render_style import (  # noqa: E402  (extend existing import)
    ResolvedFacePass,
    resolve_face_pass,
)

_DIM_AMBIENT = (0.30, 0.30, 0.31)
_DIM_DIFFUSE = (0.40, 0.40, 0.42)
_DIM_ALPHA = 0.35


def _resolve(style, dimmed=False):
    return resolve_face_pass(
        style, dimmed=dimmed, bg=_BG, material=_MAT,
        dim_ambient=_DIM_AMBIENT, dim_diffuse=_DIM_DIFFUSE, dim_alpha=_DIM_ALPHA,
    )


def test_resolve_shaded_default_is_opaque_depth_writing():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=False))
    assert rp.draw_faces is True
    assert rp.diffuse == _MAT.diffuse
    assert rp.alpha == 1.0
    assert rp.blend is False
    assert rp.depth_write is True


def test_resolve_wireframe_skips_face_pass():
    rp = _resolve(RenderStyle(FaceStyle.WIREFRAME))
    assert rp.draw_faces is False


def test_resolve_xray_enables_blend_and_disables_depth_write():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=True))
    assert rp.alpha == XRAY_ALPHA
    assert rp.blend is True
    assert rp.depth_write is False


def test_resolve_dim_only_matches_legacy_035_alpha():
    # dim (non-active context) with X-Ray off must reproduce the M4e dim look:
    # dim colors + 0.35 alpha + blend, depth writes preserved.
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=False), dimmed=True)
    assert rp.ambient == _DIM_AMBIENT
    assert rp.diffuse == _DIM_DIFFUSE
    assert rp.alpha == _DIM_ALPHA
    assert rp.blend is True
    assert rp.depth_write is True


def test_resolve_dim_and_xray_compose_alpha():
    rp = _resolve(RenderStyle(FaceStyle.SHADED, xray=True), dimmed=True)
    assert rp.alpha == XRAY_ALPHA * _DIM_ALPHA
    assert rp.depth_write is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -k resolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_face_pass'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to python/pluton/viewport/render_style.py

@dataclass(frozen=True)
class ResolvedFacePass:
    """Everything the renderer needs to draw (or skip) one definition's faces."""

    draw_faces: bool
    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float
    alpha: float
    blend: bool        # enable SRC_ALPHA blending (alpha < 1.0)
    depth_write: bool  # False ⇒ glDepthMask(GL_FALSE) (X-Ray only)


def resolve_face_pass(
    style: RenderStyle,
    *,
    dimmed: bool,
    bg: tuple[float, float, float],
    material: Material,
    dim_ambient: tuple[float, float, float],
    dim_diffuse: tuple[float, float, float],
    dim_alpha: float,
) -> ResolvedFacePass:
    """Compose face style + X-Ray + the M4e dim pass into one face-pass result.

    Dim overrides ambient/diffuse to the desaturated dim colors (preserving the
    M4e look at the Shaded default) and multiplies alpha; X-Ray sets alpha to
    XRAY_ALPHA and turns depth writes off so geometry behind shows through.
    """
    desc = FACE_STYLE_TABLE[style.face_style]
    if not desc.draw_faces:
        return ResolvedFacePass(
            draw_faces=False,
            ambient=(0.0, 0.0, 0.0), diffuse=(0.0, 0.0, 0.0), specular=(0.0, 0.0, 0.0),
            shininess=1.0, alpha=1.0, blend=False, depth_write=True,
        )
    fu = face_uniforms(desc.shading, bg=bg, material=material, xray=style.xray)
    if dimmed:
        ambient, diffuse, alpha = dim_ambient, dim_diffuse, fu.alpha * dim_alpha
    else:
        ambient, diffuse, alpha = fu.ambient, fu.diffuse, fu.alpha
    return ResolvedFacePass(
        draw_faces=True,
        ambient=ambient, diffuse=diffuse, specular=fu.specular, shininess=fu.shininess,
        alpha=alpha, blend=(alpha < 1.0), depth_write=(not style.xray),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render_style.py -v`
Expected: PASS (all render_style tests)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/render_style.py tests/test_render_style.py && git commit -m "$(cat <<'EOF'
feat(m5a): resolve_face_pass() — compose style + dim + X-Ray (pure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `phong.frag` gains `u_alpha`; register the uniform

**Files:**
- Modify: `python/pluton/viewport/shaders/phong.frag`
- Modify: `python/pluton/viewport/scene_renderer.py:118-123` (the `_PHONG_UNIFORMS` tuple)
- Test: `tests/test_phong_alpha_uniform.py`

**Interfaces:**
- Produces: `phong.frag` outputs `vec4(color, u_alpha)`; `"u_alpha"` is present in `scene_renderer._PHONG_UNIFORMS` (so its location is cached in `initialize_gl`).
- Regression-safe: `u_alpha` is unset on draws that don't set it would read 0 — so Task 5 sets it on **every** face draw. For this task the default-uniform value is irrelevant (no draw path exists yet that relies on it).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phong_alpha_uniform.py
from __future__ import annotations

from pluton.viewport.scene_renderer import _PHONG_UNIFORMS, _load_shader_source


def test_phong_uniforms_tuple_includes_u_alpha():
    assert "u_alpha" in _PHONG_UNIFORMS


def test_phong_fragment_declares_and_uses_u_alpha():
    src = _load_shader_source("phong.frag")
    assert "uniform float u_alpha;" in src
    assert "u_alpha" in src.split("frag_color")[1]  # used in the output statement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phong_alpha_uniform.py -v`
Expected: FAIL — `assert 'u_alpha' in _PHONG_UNIFORMS`

- [ ] **Step 3: Write minimal implementation**

In `python/pluton/viewport/shaders/phong.frag`, add the uniform declaration alongside the existing material uniforms:

```glsl
uniform float u_material_shininess;
uniform float u_alpha;            // M5a — face opacity (1.0 opaque; <1 for X-Ray / dim)
```

and change the final write from `frag_color = vec4(color, 1.0);` to:

```glsl
    frag_color = vec4(color, u_alpha);
```

In `python/pluton/viewport/scene_renderer.py`, extend `_PHONG_UNIFORMS`:

```python
_PHONG_UNIFORMS = (
    "u_view", "u_projection", "u_model", "u_camera_pos",
    "u_light_dir", "u_light_color",
    "u_material_ambient", "u_material_diffuse",
    "u_material_specular", "u_material_shininess",
    "u_alpha",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_phong_alpha_uniform.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/shaders/phong.frag python/pluton/viewport/scene_renderer.py tests/test_phong_alpha_uniform.py && git commit -m "$(cat <<'EOF'
feat(m5a): phong.frag u_alpha uniform for face transparency

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: renderer applies `RenderStyle` (descriptor-driven face pass + X-Ray state)

**Files:**
- Modify: `python/pluton/viewport/scene_renderer.py` (imports; `__init__`; new `set_render_style`; `render()` clear-color + per-definition face decision; rewrite `_draw_definition_faces`)
- Test: `tests/test_scene_renderer_style.py`

**Interfaces:**
- Consumes: `RenderStyle`, `Material`, `ResolvedFacePass`, `resolve_face_pass` (Tasks 1–3); `_PHONG_UNIFORMS` with `u_alpha` (Task 4).
- Produces: `SceneRenderer.set_render_style(style: RenderStyle) -> None`; `SceneRenderer._render_style` (defaults to `RenderStyle()`). `_draw_definition_faces(..., *, resolved: ResolvedFacePass)` replaces the `dimmed: bool` parameter. The View-menu UI (Task 6) calls `set_render_style` via the viewport.

**Note on testability:** `SceneRenderer()` constructs without a GL context (GL is created in `initialize_gl`, called separately). So storage of `_render_style` is unit-testable headlessly. The actual draw behavior (blend/depth/uniform values) is GL-bound and is verified in the Task 7 visual matrix.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scene_renderer_style.py
from __future__ import annotations

from pluton.viewport.render_style import FaceStyle, RenderStyle
from pluton.viewport.scene_renderer import SceneRenderer


def test_renderer_defaults_to_shaded_no_xray():
    r = SceneRenderer()
    assert r._render_style == RenderStyle()
    assert r._render_style.face_style is FaceStyle.SHADED
    assert r._render_style.xray is False


def test_set_render_style_stores_value():
    r = SceneRenderer()
    r.set_render_style(RenderStyle(FaceStyle.WIREFRAME, xray=True))
    assert r._render_style.face_style is FaceStyle.WIREFRAME
    assert r._render_style.xray is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scene_renderer_style.py -v`
Expected: FAIL — `AttributeError: 'SceneRenderer' object has no attribute '_render_style'`

- [ ] **Step 3: Write minimal implementation**

Add to the imports near the top of `scene_renderer.py`:

```python
from pluton.viewport.render_style import (
    Material,
    RenderStyle,
    ResolvedFacePass,
    resolve_face_pass,
)
```

Add a module constant beside the existing material constants (just after `_MATERIAL_SHININESS = 16.0`):

```python
_DEFAULT_MATERIAL = Material(
    ambient=_MATERIAL_AMBIENT,
    diffuse=_MATERIAL_DIFFUSE,
    specular=_MATERIAL_SPECULAR,
    shininess=_MATERIAL_SHININESS,
)
```

In `SceneRenderer.__init__` (near the other instance fields), add:

```python
        self._render_style = RenderStyle()
```

Add the setter (anywhere among the public methods, e.g. just after `resize`):

```python
    def set_render_style(self, style: RenderStyle) -> None:
        """Set the active display style (called by the viewport from the View menu)."""
        self._render_style = style
```

In `render()`, change the clear color so the Hidden-Line fill matches it exactly:

```python
        GL.glClearColor(*_BG_COLOR)
```

(replacing `GL.glClearColor(0.15, 0.16, 0.18, 1.0)`).

Replace the per-definition face-draw block in `render()`:

```python
                dimmed = definition_is_dimmed(definition, model)
                resolved = resolve_face_pass(
                    self._render_style,
                    dimmed=dimmed,
                    bg=_BG_COLOR[:3],
                    material=_DEFAULT_MATERIAL,
                    dim_ambient=_DIM_AMBIENT,
                    dim_diffuse=_DIM_DIFFUSE,
                    dim_alpha=_DIM_ALPHA_BLEND,
                )
                if resolved.draw_faces and buf.face_count > 0:
                    self._draw_definition_faces(
                        buf, view, projection, camera.position, model_mat, resolved=resolved
                    )
                if buf.edge_count > 0:
                    self._draw_definition_edges(buf, view, projection, model_mat, dimmed=dimmed)
```

Rewrite `_draw_definition_faces` to apply the resolved pass (replacing the old `dimmed`/`CONSTANT_ALPHA` body):

```python
    def _draw_definition_faces(
        self,
        buf: _DefBuffers,
        view: np.ndarray,
        projection: np.ndarray,
        camera_pos: np.ndarray,
        model_mat: np.ndarray,
        *,
        resolved: ResolvedFacePass,
    ) -> None:
        """Draw a definition's faces using a resolved face-pass (style + dim + X-Ray).

        ``resolved`` carries the material uniforms, alpha, and whether to blend /
        write depth. X-Ray turns depth writes off so geometry behind shows through;
        the dim pass and X-Ray both arrive here pre-composed as a reduced alpha.
        State (blend, depth mask) is restored after the draw — see the M4e Task-15
        blend-leak fix for why this hygiene is mandatory.
        """
        GL.glUseProgram(self._phong_program)
        locs = self._phong_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)
        _set_mat4(locs["u_model"], model_mat)
        _set_vec3(locs["u_camera_pos"], camera_pos)
        _set_vec3(locs["u_light_dir"], _LIGHT_DIR)
        _set_vec3(locs["u_light_color"], _LIGHT_COLOR)
        _set_vec3(locs["u_material_ambient"], resolved.ambient)
        _set_vec3(locs["u_material_diffuse"], resolved.diffuse)
        _set_vec3(locs["u_material_specular"], resolved.specular)
        _set_float(locs["u_material_shininess"], resolved.shininess)
        _set_float(locs["u_alpha"], resolved.alpha)

        if resolved.blend:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        if not resolved.depth_write:
            GL.glDepthMask(GL.GL_FALSE)

        GL.glBindVertexArray(buf.face_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, buf.face_count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

        if not resolved.depth_write:
            GL.glDepthMask(GL.GL_TRUE)
        if resolved.blend:
            GL.glDisable(GL.GL_BLEND)
```

- [ ] **Step 4: Run the new test + the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scene_renderer_style.py -v`
Expected: PASS (2 tests)

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — full suite still green (no regression from the `_draw_definition_faces` signature/clear-color change).

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/scene_renderer.py tests/test_scene_renderer_style.py && git commit -m "$(cat <<'EOF'
feat(m5a): renderer applies RenderStyle via resolve_face_pass; unify dim+X-Ray on u_alpha

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: View menu + viewport forwarding

**Files:**
- Modify: `python/pluton/viewport/viewport_widget.py` (add `set_render_style`)
- Modify: `python/pluton/ui/main_window.py` (imports; `_render_style` field; View menu + handlers)
- Test: `tests/test_view_menu.py`

**Interfaces:**
- Consumes: `RenderStyle`, `FaceStyle` (Task 1); `ViewportWidget.scene_renderer.set_render_style` (Task 5).
- Produces: `ViewportWidget.set_render_style(style: RenderStyle) -> None` (forwards to `self.scene_renderer.set_render_style` + `self.update()`); `MainWindow._render_style`; `MainWindow._face_style_actions: dict[FaceStyle, QAction]`; `MainWindow._xray_action: QAction`; handlers `_on_set_face_style(style: FaceStyle)` and `_on_toggle_xray(checked: bool)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_view_menu.py
from __future__ import annotations

import pytest

from pluton.ui.main_window import MainWindow
from pluton.viewport.render_style import FaceStyle


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def test_view_menu_defaults_to_shaded(win):
    assert win._render_style.face_style is FaceStyle.SHADED
    assert win._render_style.xray is False
    assert win._face_style_actions[FaceStyle.SHADED].isChecked()
    assert not win._xray_action.isChecked()


def test_face_style_actions_are_mutually_exclusive(win):
    win._on_set_face_style(FaceStyle.WIREFRAME)
    assert win._render_style.face_style is FaceStyle.WIREFRAME
    assert win._face_style_actions[FaceStyle.WIREFRAME].isChecked()
    assert not win._face_style_actions[FaceStyle.SHADED].isChecked()


def test_set_face_style_propagates_to_renderer(win):
    win._on_set_face_style(FaceStyle.HIDDEN_LINE)
    assert win._viewport.scene_renderer._render_style.face_style is FaceStyle.HIDDEN_LINE


def test_xray_toggle_is_independent_of_face_style(win):
    win._on_set_face_style(FaceStyle.MONOCHROME)
    win._on_toggle_xray(True)
    assert win._render_style.xray is True
    assert win._render_style.face_style is FaceStyle.MONOCHROME
    assert win._viewport.scene_renderer._render_style.xray is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_view_menu.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_render_style'`

- [ ] **Step 3: Write minimal implementation**

In `viewport_widget.py`, add the forwarder (e.g. just after `set_event_finished_callback`):

```python
    def set_render_style(self, style) -> None:  # noqa: ANN001
        """Set the viewport display style and repaint (called from the View menu)."""
        self.scene_renderer.set_render_style(style)
        self.update()
```

In `main_window.py`, extend the QtGui import:

```python
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
```

Add the render-style import alongside the other pluton imports:

```python
from pluton.viewport.render_style import FaceStyle, RenderStyle
```

In `__init__`, initialize the style field (near `self._model = Model()`):

```python
        self._render_style = RenderStyle()
```

After the Units-menu block (around `main_window.py:147`), add the View menu:

```python
        # View menu (M5a) — face-style radio group + independent X-Ray toggle.
        self._view_menu = menubar.addMenu("View")
        self._face_style_group = QActionGroup(self)
        self._face_style_group.setExclusive(True)
        self._face_style_actions: dict[FaceStyle, QAction] = {}
        for label, style in (
            ("Wireframe", FaceStyle.WIREFRAME),
            ("Hidden Line", FaceStyle.HIDDEN_LINE),
            ("Monochrome", FaceStyle.MONOCHROME),
            ("Shaded", FaceStyle.SHADED),
        ):
            action = QAction(label, self, checkable=True)
            action.setActionGroup(self._face_style_group)
            action.triggered.connect(lambda _checked, s=style: self._on_set_face_style(s))
            self._view_menu.addAction(action)
            self._face_style_actions[style] = action
        self._face_style_actions[self._render_style.face_style].setChecked(True)
        self._view_menu.addSeparator()
        self._xray_action = QAction("X-Ray", self, checkable=True)
        self._xray_action.toggled.connect(self._on_toggle_xray)
        self._view_menu.addAction(self._xray_action)
```

Add the handlers (with the other `_on_*` handlers in the class body):

```python
    def _on_set_face_style(self, style: FaceStyle) -> None:
        self._render_style.face_style = style
        self._viewport.set_render_style(self._render_style)

    def _on_toggle_xray(self, checked: bool) -> None:
        self._render_style.xray = bool(checked)
        self._viewport.set_render_style(self._render_style)
```

- [ ] **Step 4: Run the new test + the full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_view_menu.py -v`
Expected: PASS (4 tests)

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — full suite green.

- [ ] **Step 5: Commit**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/viewport_widget.py python/pluton/ui/main_window.py tests/test_view_menu.py && git commit -m "$(cat <<'EOF'
feat(m5a): View menu — face-style radio group + X-Ray toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: full regression + manual visual verification

**Files:**
- None (verification only). May produce small follow-up commits if the visual pass reveals a tuning need (e.g. `MONO_COLOR`, `XRAY_ALPHA`).

**Interfaces:** none.

- [ ] **Step 1: Full automated regression**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — all prior tests + the new `test_render_style.py`, `test_phong_alpha_uniform.py`, `test_scene_renderer_style.py`, `test_view_menu.py`.

Run: `ctest --test-dir build/tests --output-on-failure`
Expected: 76/76 pass (C++ untouched — sanity check only).

- [ ] **Step 2: Ruff on the new/changed files**

Run: `.venv/Scripts/python.exe -m ruff check python/pluton/viewport/render_style.py python/pluton/viewport/scene_renderer.py python/pluton/viewport/viewport_widget.py python/pluton/ui/main_window.py tests/test_render_style.py tests/test_view_menu.py tests/test_scene_renderer_style.py tests/test_phong_alpha_uniform.py`
Expected: no new errors introduced by M5a (pre-existing repo debt per issue #48 is out of scope).

- [ ] **Step 3: Launch the app and run the visual matrix**

Run: `.venv/Scripts/python.exe -m pluton`

Build a scene with several objects, including a **moved group** and an **active selection**. Then walk the View menu through the **4 × 2 matrix** and confirm each:

| Face style | X-Ray off | X-Ray on |
|---|---|---|
| **Shaded** | identical to v0.1.4 (regression baseline) | faces semi-transparent, edges opaque, geometry behind visible |
| **Hidden Line** | faces fill in background color → only front edges show (clean occlusion) | faces transparent, more edges show through |
| **Monochrome** | uniform gray, phong-lit; ≈ Shaded (expected pre-materials) | gray faces semi-transparent |
| **Wireframe** | no faces; all edges visible (see-through) | no visible change (X-Ray no-op) |

Confirm in every cell: selection-blue highlight, hover, snap glyphs, grid, axes, and tool overlays still render correctly; and switching styles back and forth repeatedly returns Shaded to the exact baseline (**no GL state leak** — depth mask / blend not left dirty).

- [ ] **Step 4: (If tuning needed) adjust constants and commit**

Only if the visual pass shows `MONO_COLOR` or `XRAY_ALPHA` need adjustment, edit `python/pluton/viewport/render_style.py` and:

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add python/pluton/viewport/render_style.py && git commit -m "$(cat <<'EOF'
fix(m5a): tune Monochrome color / X-Ray alpha from visual pass

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Report results to the user**

Summarize the matrix outcome (pass/fail per cell), any tuning applied, and confirm readiness for release. **Do not proceed to Task 8 without the user confirming the visual pass.**

---

### Task 8: release v0.1.5

**Files:**
- Modify: `pyproject.toml` (version), `CMakeLists.txt` (project VERSION), `cpp/src/version.cpp` (version string)
- Modify: `docs/2026-05-16-pluton-design.md` (annotate M5a row shipped)

**Interfaces:** none.

> Mirrors the established release flow (see v0.1.4 / commit history). The local steps are reversible; the **push / tag / CI / issues** steps require explicit user authorization per turn.

- [ ] **Step 1: Bump version `0.1.4 → 0.1.5` in all three files**

- `pyproject.toml`: `version = "0.1.4"` → `version = "0.1.5"`
- `CMakeLists.txt`: `VERSION 0.1.4` → `VERSION 0.1.5`
- `cpp/src/version.cpp`: `return "0.1.4";` → `return "0.1.5";`

- [ ] **Step 2: Annotate the master design doc**

In `docs/2026-05-16-pluton-design.md`, update the M5 line (Phase 2) so the viewport-styles piece is marked shipped, matching the existing `✅ *(shipped v0.1.x)*` convention used for M4a–M4e.

- [ ] **Step 3: Rebuild the editable install (recompiles `version.cpp`) and verify**

Run: `.venv/Scripts/python.exe -m pip install -e . --no-build-isolation`
Run: `.venv/Scripts/python.exe -c "import pluton, pluton._core as c; print(pluton.__version__, c.version())"`
Expected: `0.1.5 0.1.5`

- [ ] **Step 4: Full suite green at the new version**

Run: `.venv/Scripts/python.exe -m pytest -q`  → all pass
Run: `ctest --test-dir build/tests --output-on-failure`  → 76/76

- [ ] **Step 5: Commit the release (specific files only, signed)**

```bash
cd /f/dev/00_Parrow-Horrizon-Studio/pluton && git add pyproject.toml CMakeLists.txt cpp/src/version.cpp docs/2026-05-16-pluton-design.md && git commit -m "$(cat <<'EOF'
release: v0.1.5 (M5a — viewport display styles)

Four face styles (Wireframe / Hidden Line / Monochrome / Shaded) + an
orthogonal X-Ray toggle, switchable from a new View menu. Renderer-only:
a pure render_style resolver drives the existing phong shader (new u_alpha
uniform unifies dim + X-Ray transparency). No kernel/model/picking changes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Outward release (REQUIRES explicit user authorization this turn)**

With the user's go-ahead: push `main`; create + push annotated tag `v0.1.5-m5a`; watch CI (`gh run watch … --exit-status`) until Windows + Linux are green; file any carry-over issues surfaced during M5a. Do **not** run these without authorization.

---

## Self-Review

**1. Spec coverage** (each design section → task):
- §3 data model (FaceStyle / FaceShading / FaceStyleDescriptor / RenderStyle / FACE_STYLE_TABLE / constants) → Task 1. `face_uniforms` → Task 2. `resolve_face_pass` (the §3 resolver seam + §4 dim composition) → Task 3.
- §4 renderer application (`u_alpha` shader + registration) → Task 4; (clear-color reconcile, descriptor-driven face skip, X-Ray blend/depth state + restore, thin `_draw_definition_faces`) → Task 5.
- §5 UI wiring (ViewportWidget.set_render_style; View menu; QActionGroup; default Shaded; X-Ray) → Task 6.
- §6 interactions (overlays/dim/picking decoupling, regression default, no state leak) → verified in Task 7's matrix; the dim-compose + regression-default behaviors are unit-locked in Task 3 (`test_resolve_dim_only_matches_legacy_035_alpha`) and Task 5 (full-suite green).
- §7 testing (unit / pytest-qt / manual matrix) → Tasks 1–3 (pure), Task 6 (qt), Task 7 (matrix).
- §2 deferrals → none implemented (correct); no task adds profile edges / textures / persistence.
- §8 files-touched → exactly the files modified across Tasks 1–6. No C++ touched (Global Constraints).

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; the only "if needed" step (Task 7 Step 4) is explicitly conditional tuning, not a deferred requirement.

**3. Type consistency:** `RenderStyle`, `FaceStyle`, `FaceShading`, `Material`, `FaceUniforms`, `ResolvedFacePass` names and fields are identical across Tasks 1–6. `face_uniforms(shading, *, bg, material, xray)` and `resolve_face_pass(style, *, dimmed, bg, material, dim_ambient, dim_diffuse, dim_alpha)` signatures match their call sites in Task 5. `set_render_style` is spelled identically in `SceneRenderer` (Task 5), `ViewportWidget` (Task 6), and the handler call sites. `_draw_definition_faces(..., *, resolved=...)` matches its single call site in `render()` (Task 5).

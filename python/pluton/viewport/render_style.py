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


@dataclass(frozen=True)
class PhongMaterial:
    """A phong material's color terms (ambient/diffuse/specular/shininess)."""

    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float


@dataclass(frozen=True)
class FaceUniforms:
    """Resolved per-draw-call phong material uniforms + alpha, ready for the shader."""

    ambient: tuple[float, float, float]
    diffuse: tuple[float, float, float]
    specular: tuple[float, float, float]
    shininess: float
    alpha: float


def face_uniforms(
    shading: FaceShading,
    *,
    bg: tuple[float, float, float],
    material: PhongMaterial,
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
    material: PhongMaterial,
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


# --- M5b: painted-material -> phong uniforms -------------------------------
# These mirror scene_renderer._MATERIAL_SPECULAR / _MATERIAL_SHININESS so a
# painted face gets the same highlight character as the default look; only the
# hue varies. Duplicated here (not imported) to keep render_style import-free
# of the GL renderer. A guard test asserts they stay in sync.
_AMBIENT_FACTOR = 0.55
_DEFAULT_SPECULAR = (0.10, 0.10, 0.10)
_DEFAULT_SHININESS = 16.0


def phong_material_for(color: tuple[float, float, float]) -> PhongMaterial:
    """Map a painted base RGB to phong uniforms.

    diffuse = color; ambient = color * _AMBIENT_FACTOR; specular/shininess are
    the shared defaults. Does NOT reproduce _DEFAULT_MATERIAL (whose terms are
    hand-tuned); unpainted faces keep using _DEFAULT_MATERIAL directly.
    """
    r, g, b = float(color[0]), float(color[1]), float(color[2])
    return PhongMaterial(
        ambient=(r * _AMBIENT_FACTOR, g * _AMBIENT_FACTOR, b * _AMBIENT_FACTOR),
        diffuse=(r, g, b),
        specular=_DEFAULT_SPECULAR,
        shininess=_DEFAULT_SHININESS,
    )

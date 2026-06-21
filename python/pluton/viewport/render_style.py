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
class Material:
    """A phong material's color terms (the renderer's current default material)."""

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

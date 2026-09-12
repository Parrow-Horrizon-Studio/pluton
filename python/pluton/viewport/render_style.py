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

    LIT = auto()  # phong lighting with the (default) material color → Shaded
    UNIFORM = auto()  # phong lighting, but one fixed monochrome color    → Monochrome
    FLAT_BG = auto()  # unlit; filled with the background color           → Hidden Line


@dataclass(frozen=True)
class FaceStyleDescriptor:
    draw_faces: bool
    shading: FaceShading | None  # None iff draw_faces is False


@dataclass
class RenderStyle:
    """The viewport's current display style. One global setting per window."""

    face_style: FaceStyle = FaceStyle.SHADED
    xray: bool = False
    # M7.5a Task 11: when on, the render loop replaces each definition's
    # resolved diffuse with its owning instance's tag colour and bypasses
    # materials entirely -- resolved in scene_renderer.py (not here), since
    # tags are per-instance and this dataclass has no scene-graph access.
    color_by_tag: bool = False


FACE_STYLE_TABLE: dict[FaceStyle, FaceStyleDescriptor] = {
    FaceStyle.WIREFRAME: FaceStyleDescriptor(draw_faces=False, shading=None),
    FaceStyle.HIDDEN_LINE: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.FLAT_BG),
    FaceStyle.MONOCHROME: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.UNIFORM),
    FaceStyle.SHADED: FaceStyleDescriptor(draw_faces=True, shading=FaceShading.LIT),
}

# Tunable look constants (revisited in the Task 7 visual pass).
MONO_COLOR = (0.72, 0.72, 0.74)  # uniform diffuse gray for Monochrome
XRAY_ALPHA = 0.35  # face opacity when X-Ray is on


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
    material_alpha: float = 1.0,
) -> FaceUniforms:
    """Map a shading mode to concrete phong material uniforms + alpha.

    LIT     → the material's own colors (today's Shaded look).
    UNIFORM → material ambient/specular, but MONO_COLOR diffuse (Monochrome).
    FLAT_BG → unlit fill: ambient = bg, diffuse/specular = 0 (Hidden Line).
    X-Ray   → alpha = XRAY_ALPHA (else 1.0), orthogonal to shading.
    material_alpha → the material's own opacity; multiplies into the result
                      so a translucent material and X-Ray compose rather than
                      one winning outright.
    """
    alpha = (XRAY_ALPHA if xray else 1.0) * float(material_alpha)
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
    blend: bool  # enable SRC_ALPHA blending (alpha < 1.0)
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
    material_alpha: float = 1.0,
) -> ResolvedFacePass:
    """Compose face style + X-Ray + the M4e dim pass into one face-pass result.

    Dim overrides ambient/diffuse to the desaturated dim colors (preserving the
    M4e look at the Shaded default) and multiplies alpha; X-Ray sets alpha to
    XRAY_ALPHA and turns depth writes off so geometry behind shows through.
    A translucent material_alpha behaves like X-Ray for depth purposes: it
    also stops writing depth, since blended geometry drawn back-to-front
    should not occlude what is behind it.
    """
    desc = FACE_STYLE_TABLE[style.face_style]
    if not desc.draw_faces:
        return ResolvedFacePass(
            draw_faces=False,
            ambient=(0.0, 0.0, 0.0),
            diffuse=(0.0, 0.0, 0.0),
            specular=(0.0, 0.0, 0.0),
            shininess=1.0,
            alpha=1.0,
            blend=False,
            depth_write=True,
        )
    fu = face_uniforms(
        desc.shading, bg=bg, material=material, xray=style.xray, material_alpha=material_alpha
    )
    if dimmed:
        ambient, diffuse, alpha = dim_ambient, dim_diffuse, fu.alpha * dim_alpha
    else:
        ambient, diffuse, alpha = fu.ambient, fu.diffuse, fu.alpha
    return ResolvedFacePass(
        draw_faces=True,
        ambient=ambient,
        diffuse=diffuse,
        specular=fu.specular,
        shininess=fu.shininess,
        alpha=alpha,
        blend=(alpha < 1.0),
        depth_write=(not style.xray and float(material_alpha) >= 1.0),
    )


# --- M5b/M7.5a: painted-material -> phong uniforms --------------------------
# phong_material_for approximates a PBR (base_color/metallic/roughness) input
# with Blinn-Phong terms, so painted faces respond to every editable field
# instead of only hue. Duplicated math (not imported) to keep render_style
# import-free of the GL renderer and of pluton.model. Unpainted front faces
# keep using scene_renderer._DEFAULT_MATERIAL directly, unchanged, so its
# hand-tuned specular/shininess no longer need to match this derivation (see
# test_phong_material_for.py's guard for the one case that still ties them
# together).
_AMBIENT_FACTOR = 0.55
_DIELECTRIC_F0 = 0.04  # normal-incidence reflectance of a non-metal
_MIN_SHININESS = 1.0
_MAX_SHININESS = 256.0

# The unpainted back-face colour. A renderer constant rather than a library
# entry (spec D3), so it never appears as a swatch; its only job is to make a
# reversed face obvious.
BACK_DEFAULT_COLOR = (0.45, 0.50, 0.58)


def _mix(a: float, b: float, t: float) -> float:
    return a * (1.0 - t) + b * t


def phong_material_for(
    base_color: tuple[float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.5,
) -> PhongMaterial:
    """Approximate a PBR material with Blinn-Phong terms.

    diffuse  = base_color * (1 - metallic)      metals have no diffuse lobe
    specular = mix(0.04, base_color, metallic)  dielectric F0, tinted for metals
    shininess = clamp(2 / roughness**4 - 2)     the standard Blinn-Phong
                                                 to roughness equivalence
    ambient  = base_color * _AMBIENT_FACTOR * (1 - metallic)

    An approximation, not real PBR: M12's renderer will not match it pixel for
    pixel. What it buys is that every editable field changes what you see.
    """
    r, g, b = float(base_color[0]), float(base_color[1]), float(base_color[2])
    m = min(max(float(metallic), 0.0), 1.0)
    rough = min(max(float(roughness), 0.0), 1.0)

    kd = 1.0 - m
    alpha_r = max(rough, 1e-3) ** 4
    shininess = min(max(2.0 / alpha_r - 2.0, _MIN_SHININESS), _MAX_SHININESS)

    return PhongMaterial(
        ambient=(r * _AMBIENT_FACTOR * kd, g * _AMBIENT_FACTOR * kd, b * _AMBIENT_FACTOR * kd),
        diffuse=(r * kd, g * kd, b * kd),
        specular=(
            _mix(_DIELECTRIC_F0, r, m),
            _mix(_DIELECTRIC_F0, g, m),
            _mix(_DIELECTRIC_F0, b, m),
        ),
        shininess=shininess,
    )

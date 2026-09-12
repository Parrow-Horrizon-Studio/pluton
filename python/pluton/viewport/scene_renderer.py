"""Owns GL resources for the M2 scene: grid + axes + user geometry + tool overlay.

Lifecycle is driven by QOpenGLWidget:
  initialize_gl() -> first paintGL() call sets up VBOs and shader programs.
  resize(w, h)    -> called from resizeGL.
  render(camera, model, tool_overlay, selection) -> called from paintGL each frame.
"""

from __future__ import annotations

import ctypes
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from importlib.resources import files

import numpy as np
from OpenGL import GL

from pluton.geometry.transforms import apply_mat, is_identity_transform
from pluton.scene.scene import Side
from pluton.viewport.camera import Camera
from pluton.viewport.face_batches import BatchPlan, FaceBatch, plan_face_batches
from pluton.viewport.render_style import (
    BACK_DEFAULT_COLOR,
    PhongMaterial,
    RenderStyle,
    ResolvedFacePass,
    phong_material_for,
    resolve_face_pass,
)
from pluton.viewport.snap_engine import SnapKind
from pluton.viewport.translucency import (
    order_back_to_front,
    transform_points,
    triangle_centroids,
    triangle_order_to_vertex_order,
)


def definition_is_dimmed(definition, model) -> bool:
    """True when `definition` should render dimmed (recede) — i.e. you are
    inside a group (active_path is non-empty) and this definition is not the
    active editing context. At the root context, nothing is dimmed.

    Thin wrapper kept for back-compat with existing callers/tests; the single
    source of truth is now Model.definition_is_dimmed (#95), so annotations
    (draw_plan.collect_annotation_plans) dim by exactly the same rule as
    geometry."""
    return model.definition_is_dimmed(definition)


# --- AABB helpers (Task 15) -------------------------------------------------


def aabb_world_edges(lo, hi, world_transform) -> np.ndarray:
    """Return (24, 3) float32 array of 12 AABB edge endpoint pairs in world space.

    Builds the 8 corners of the axis-aligned box [lo, hi] and transforms each
    with ``world_transform`` using ``apply_mat``.  The 12 edges are returned as
    24 endpoints (two per edge, interleaved) suitable for GL_LINES.

    Args:
        lo: (3,) array-like — minimum corner in local space.
        hi: (3,) array-like — maximum corner in local space.
        world_transform: (4, 4) array-like — local-to-world matrix.

    Returns:
        np.ndarray of shape (24, 3), dtype float32.
    """
    from pluton.geometry.transforms import apply_mat

    lx, ly, lz = float(lo[0]), float(lo[1]), float(lo[2])
    hx, hy, hz = float(hi[0]), float(hi[1]), float(hi[2])

    # 8 corners of the box
    corners = np.array(
        [
            [lx, ly, lz],  # 0 — low-low-low
            [hx, ly, lz],  # 1 — high-low-low
            [hx, hy, lz],  # 2 — high-high-low
            [lx, hy, lz],  # 3 — low-high-low
            [lx, ly, hz],  # 4 — low-low-high
            [hx, ly, hz],  # 5 — high-low-high
            [hx, hy, hz],  # 6 — high-high-high
            [lx, hy, hz],  # 7 — low-high-high
        ],
        dtype=np.float64,
    )

    # Transform all corners at once
    world_corners = apply_mat(corners, world_transform)  # (8, 3) float32

    # 12 edges — each edge is a pair of corner indices
    _edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),  # bottom face
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),  # top face
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),  # vertical pillars
    ]

    out = np.empty((24, 3), dtype=np.float32)
    for i, (a, b) in enumerate(_edges):
        out[2 * i] = world_corners[a]
        out[2 * i + 1] = world_corners[b]
    return out


# --- Constants for the scene -----------------------------------------------

_GRID_HALF_EXTENT = 5.0  # meters, so grid is 10x10
_GRID_SPACING = 1.0
_GRID_COLOR = (0.40, 0.40, 0.40)
_GRID_CENTERLINE_COLOR = (0.60, 0.60, 0.60)

_AXIS_LENGTH = 5.0
_AXIS_X_COLOR = (0.90, 0.20, 0.20)
_AXIS_Y_COLOR = (0.20, 0.90, 0.20)
_AXIS_Z_COLOR = (0.20, 0.40, 0.90)

# Phong material + light — used for user geometry.
_LIGHT_DIR = (-1.0, +1.0, -2.0)
_LIGHT_COLOR = (1.00, 0.97, 0.92)
_MATERIAL_AMBIENT = (0.40, 0.40, 0.42)
_MATERIAL_DIFFUSE = (0.65, 0.65, 0.70)
_MATERIAL_SPECULAR = (0.10, 0.10, 0.10)
_MATERIAL_SHININESS = 16.0
_DEFAULT_MATERIAL = PhongMaterial(
    ambient=_MATERIAL_AMBIENT,
    diffuse=_MATERIAL_DIFFUSE,
    specular=_MATERIAL_SPECULAR,
    shininess=_MATERIAL_SHININESS,
)

_BG_COLOR = (0.15, 0.15, 0.18, 1.0)

# Edge / overlay colors (per-vertex, packed into the VBO alongside positions).
_USER_EDGE_COLOR = (0.85, 0.85, 0.85)
_SELECTION_FILL_COLOR = (0.20, 0.50, 0.95, 0.25)  # selected faces (blue, 25% alpha)
_SELECTION_EDGE_COLOR = (0.20, 0.55, 1.00)  # selected edges (bright blue)

# Task 15 — dim pass + instance bbox colors.
_DIM_AMBIENT = (0.30, 0.30, 0.31)  # desaturated ambient for dimmed definitions
_DIM_DIFFUSE = (0.40, 0.40, 0.42)  # desaturated diffuse for dimmed definitions
_DIM_ALPHA_BLEND = 0.35  # alpha for dimmed geometry (blended toward bg)
_INSTANCE_BBOX_COLOR = (0.30, 0.55, 0.95)  # selection-blue bbox for selected instances
_INSTANCE_BBOX_WIDTH = 2.0
# Uniform names looked up once per program in initialize_gl().
_PHONG_UNIFORMS = (
    "u_view",
    "u_projection",
    "u_model",
    "u_camera_pos",
    "u_light_dir",
    "u_light_color",
    "u_material_ambient",
    "u_material_diffuse",
    "u_material_specular",
    "u_material_shininess",
    "u_alpha",
    # M7.5a Task 6 — the back side's material set, selected in the fragment
    # shader by gl_FrontFacing. Must stay in lockstep with phong.frag's
    # declarations; tests/test_two_sided_shading.py asserts the two agree.
    "u_material_ambient_back",
    "u_material_diffuse_back",
    "u_material_specular_back",
    "u_material_shininess_back",
    "u_alpha_back",
)
_LINE_UNIFORMS = ("u_view", "u_projection")
_GHOST_FILL_UNIFORMS = ("u_view", "u_projection", "u_color")


def _empty_batch_plan() -> BatchPlan:
    """The plan for a definition with no triangles."""
    return plan_face_batches([], [])


# The face VBO's interleaved layout: (pos.xyz, normal.xyz) float32 per vertex.
# _alloc_def_buffers' vertex-attribute stride and _sort_translucent_slice's
# glBufferSubData byte offset are the same number, so they share one constant
# rather than each hard-coding 24 and drifting apart.
_FACE_VERTEX_FLOATS = 6
_FACE_VERTEX_BYTES = _FACE_VERTEX_FLOATS * 4


def _empty_face_interleaved() -> np.ndarray:
    return np.zeros((0, _FACE_VERTEX_FLOATS), dtype=np.float32)


@dataclass
class _DefBuffers:
    """Per-definition GL buffer handles and vertex counts."""

    face_vao: int = 0
    face_vbo: int = 0
    face_count: int = 0  # number of triangle vertices
    edge_vao: int = 0
    edge_vbo: int = 0
    edge_count: int = 0  # number of line-segment vertices
    # The batch plan the face VBO was uploaded under: its vertex_order is
    # already baked into the buffer, so `opaque` / `translucent` /
    # `translucent_first` index straight into it.
    plan: BatchPlan = field(default_factory=_empty_batch_plan)
    # The translucent ids the plan above was computed under. Editing a
    # material's alpha dirties no mesh, so this is the only thing that can tell
    # the renderer its opaque/translucent partition has gone stale (spec 1.7).
    translucent_ids: frozenset[int] = frozenset()

    # --- Task 7: state the translucent pass re-sorts each frame -------------
    #
    # The interleaved vertex data in its upload order (already permuted by
    # plan.vertex_order), so the translucent suffix can be re-permuted from a
    # stable base every time the view changes rather than accumulating
    # permutations. Kept ONLY for definitions that actually have translucent
    # faces — _sort_translucent_slice is the sole reader, and holding a CPU
    # copy of every opaque definition's faces alongside its VBO would roughly
    # double scene face memory for a pass those definitions never enter.
    face_interleaved: np.ndarray = field(default_factory=_empty_face_interleaved)
    # Local-space centroid of each translucent triangle, in upload order.
    translucent_centroids: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3), dtype=np.float64)
    )
    # This definition's own sort key for pass 2 — the mean of the above.
    translucent_local_centroid: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64)
    )
    # (front, back) material ids per translucent triangle, in upload order, so
    # the depth-sorted suffix can be re-cut into batches that still name the
    # right materials.
    translucent_pairs: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.int64))
    # The batches that currently describe the face VBO's translucent suffix.
    # Equal to plan.translucent until the first sort, then re-cut by
    # rebuild_translucent_batches to follow the permuted order.
    translucent_draw_batches: list[FaceBatch] = field(default_factory=list)
    # (camera_pos, world_transform) the suffix was last sorted for; None when
    # it has never been sorted, or when a re-upload invalidated the sort.
    translucent_sort_key: tuple | None = None

    def release(self) -> None:
        """Delete this definition's GL objects. Guarded so a zero handle
        (never-uploaded / already-released / headless test stand-in) never
        reaches a GL call — safe to call without a current context in that
        case, and correct GL hygiene in all cases.

        The FaceBatch entries in `plan` are metadata slices (front_material_id,
        back_material_id, first, count) into face_vbo — they hold no GL
        handles of their own, so there is nothing per-batch to release.
        """
        if self.face_vao:
            GL.glDeleteVertexArrays(1, [self.face_vao])
        if self.face_vbo:
            GL.glDeleteBuffers(1, [self.face_vbo])
        if self.edge_vao:
            GL.glDeleteVertexArrays(1, [self.edge_vao])
        if self.edge_vbo:
            GL.glDeleteBuffers(1, [self.edge_vbo])


# --- M7.5a Task 6: two-sided material resolution ----------------------------
#
# Module-level and GL-free on purpose: the resolution logic is where the
# per-side behaviour actually lives, and the fragment shader it feeds cannot
# be unit-tested. Keeping this importable without a GL context or a
# QApplication is what makes the shading testable at all.


def _translucent_ids(materials) -> frozenset[int]:
    """Ids of every translucent material in the library (empty when None)."""
    if materials is None:
        return frozenset()
    return frozenset(m.id for m in materials.materials() if m.is_translucent)


def _material_terms(materials, mid: int, side: Side) -> tuple[PhongMaterial, float]:
    """(PhongMaterial, alpha) for one side's material id.

    An unpainted FRONT keeps using the hand-tuned _DEFAULT_MATERIAL exactly as
    before, so unpainted front faces look unchanged. An unpainted BACK is new:
    it resolves to the distinct blue-grey BACK_DEFAULT_COLOR (spec D3) so a
    reversed face is obvious on screen.
    """
    if mid != 0 and materials is not None:
        m = materials.get(mid)
        return (
            phong_material_for(m.base_color, metallic=m.metallic, roughness=m.roughness),
            m.alpha,
        )
    if side is Side.BACK:
        return phong_material_for(BACK_DEFAULT_COLOR), 1.0
    return _DEFAULT_MATERIAL, 1.0


def resolve_batch_sides(
    batch: FaceBatch,
    materials,
    render_style: RenderStyle,
    *,
    dimmed: bool,
) -> tuple[ResolvedFacePass, ResolvedFacePass]:
    """Resolve one batch into its front and back face passes.

    blend and depth_write are per-batch rather than per-side (correction 4):
    both sides of a face reach the shader in one draw call, and blending and
    the depth mask are draw-call state, so a batch blends if EITHER side is
    translucent and both returned passes carry the same flags.
    """
    front_mat, front_alpha = _material_terms(materials, batch.front_material_id, Side.FRONT)
    back_mat, back_alpha = _material_terms(materials, batch.back_material_id, Side.BACK)

    def _resolve(mat: PhongMaterial, alpha: float) -> ResolvedFacePass:
        return resolve_face_pass(
            render_style,
            dimmed=dimmed,
            bg=_BG_COLOR[:3],
            material=mat,
            dim_ambient=_DIM_AMBIENT,
            dim_diffuse=_DIM_DIFFUSE,
            dim_alpha=_DIM_ALPHA_BLEND,
            material_alpha=alpha,
        )

    front = _resolve(front_mat, front_alpha)
    back = _resolve(back_mat, back_alpha)
    blend = front.blend or back.blend
    depth_write = front.depth_write and back.depth_write
    return (
        replace(front, blend=blend, depth_write=depth_write),
        replace(back, blend=blend, depth_write=depth_write),
    )


# --- M7.5a Task 11: Color-by-Tag --------------------------------------------
#
# Module-level and GL-free for the same reason as resolve_batch_sides above:
# tags are per-INSTANCE while resolve_batch_sides only ever sees a batch, so
# the override is decided here in the render loop instead of being threaded
# into that function. Keeping resolve_batch_sides about materials only.


def _definition_tag_ids(model) -> dict[int, int]:
    """Map id(child definition) -> the tag id of the Instance that places it.

    model.traverse()'s (definition, world) pairs do not carry the owning
    Instance (see Model._traverse) -- only the definition and its world
    transform -- so Color-by-Tag needs its own walk of the same tree to learn
    which instance placed a given definition. When a Definition is shared by
    more than one Instance carrying different tags, the last one visited
    wins: resolving per-occurrence instead of per-definition would need the
    Instance threaded through traverse() itself, out of scope for this task.
    """
    mapping: dict[int, int] = {}

    def walk(definition) -> None:
        for inst in definition.children:
            mapping[id(inst.definition)] = inst.tag_id
            walk(inst.definition)

    walk(model.root)
    return mapping


def resolve_definition_tag_color(
    tag_id: int, tags, render_style: RenderStyle
) -> tuple[float, float, float] | None:
    """The tag-colour override for one definition's draw, or None when
    Color-by-Tag is off.

    `tag_id` is looked up once per definition by the render loop (via
    _definition_tag_ids) and passed in here; this function decides only
    whether the mode is on and what colour results, so it is testable
    without a scene graph or a GL context.
    """
    if not render_style.color_by_tag:
        return None
    return tags.get(tag_id).color


def apply_tag_color_override(
    front: ResolvedFacePass,
    back: ResolvedFacePass,
    color: tuple[float, float, float] | None,
) -> tuple[ResolvedFacePass, ResolvedFacePass]:
    """Replace both sides' diffuse with `color`; a no-op when `color` is None.

    Everything else resolve_batch_sides already computed -- face style, the
    dim pass, X-Ray alpha, blend/depth flags -- passes through unchanged:
    Color-by-Tag bypasses material colour, not the rest of the shading
    pipeline. Both sides are replaced together so a reversed face does not
    give away the mode by keeping its old back-face colour (a front-only
    override would be a plausible, easy-to-miss bug here).
    """
    if color is None:
        return front, back
    return replace(front, diffuse=color), replace(back, diffuse=color)


# --- M7.5a Task 7: the translucent pass -------------------------------------
#
# Module-level and GL-free for the same reason as the block above: every
# ordering decision the pass makes is testable, and none of the GL calls are.


def order_definitions_for_translucent_pass(entries, *, camera_pos, centroid_of) -> list[int]:
    """Indices of (definition, world) entries, farthest definition first.

    Correction 1: face buffers are per-definition, so a scene-global face sort
    is not available. Faces sort within a definition; definitions sort among
    themselves here. Two interpenetrating translucent groups therefore sort by
    centroid rather than per face.
    """
    if not entries:
        return []
    world_centroids = np.stack(
        [
            transform_points(np.asarray(centroid_of(d), dtype=np.float64).reshape(1, 3), w)[0]
            for d, w in entries
        ]
    )
    return order_back_to_front(world_centroids, camera_pos).tolist()


def rebuild_translucent_batches(sorted_pairs, first_vertex: int) -> list[FaceBatch]:
    """Re-cut the depth-sorted translucent suffix into (front, back) batches.

    `sorted_pairs` is (T, 2) int64 — the (front, back) material id of each
    translucent triangle in the order it now occupies in the VBO. Runs of the
    same pair become one batch.

    This is what makes a whole-suffix depth sort safe. plan_face_batches groups
    the suffix by material pair, so a definition carrying two translucent
    materials has two batches inside it; sorting the suffix by depth moves
    triangles across those boundaries, and drawing with the original ranges
    would shade a triangle with the other material's uniforms. Re-cutting keeps
    the depth order AND the materials, at the cost of fragmentation: materials
    that alternate in depth degenerate to one batch per triangle. That bound is
    accepted rather than capped — a cap would reintroduce the wrong colours.
    """
    pairs = np.asarray(sorted_pairs, dtype=np.int64).reshape(-1, 2)
    if pairs.shape[0] == 0:
        return []
    changed = np.any(pairs[1:] != pairs[:-1], axis=1)
    starts = np.concatenate([np.zeros(1, dtype=np.int64), np.nonzero(changed)[0] + 1])
    ends = np.concatenate([starts[1:], np.array([pairs.shape[0]], dtype=np.int64)])
    return [
        FaceBatch(
            front_material_id=int(pairs[s, 0]),
            back_material_id=int(pairs[s, 1]),
            first=first_vertex + int(s) * 3,
            count=(int(e) - int(s)) * 3,
        )
        for s, e in zip(starts, ends, strict=True)
    ]


def _translucent_pairs(plan: BatchPlan) -> np.ndarray:
    """(T, 2) int64 (front, back) material id per translucent triangle, in the
    upload order `plan.vertex_order` baked into the VBO."""
    total = sum(b.count for b in plan.translucent) // 3
    pairs = np.zeros((total, 2), dtype=np.int64)
    for batch in plan.translucent:
        lo = (batch.first - plan.translucent_first) // 3
        pairs[lo : lo + batch.count // 3] = (batch.front_material_id, batch.back_material_id)
    return pairs


def _reset_translucent_state(buf: _DefBuffers, plan: BatchPlan, interleaved: np.ndarray) -> None:
    """Point `buf`'s translucent-pass state at freshly uploaded vertex data.

    Called from _upload_definition for both the has-triangles and no-triangles
    cases. Every field the pass caches is (re)set together here — in particular
    `translucent_sort_key` is cleared, because the buffer that a surviving key
    described has just been replaced under it. _DefBuffers instances are reused
    across re-uploads, so leaving a stale key would keep the previous frame's
    permutation and batch ranges over entirely different vertex data.
    """
    # Only the translucent pass reads face_interleaved, so an all-opaque
    # definition keeps nothing.
    buf.face_interleaved = interleaved if plan.translucent else _empty_face_interleaved()
    buf.translucent_centroids = triangle_centroids(interleaved[plan.translucent_first :, :3])
    buf.translucent_local_centroid = (
        buf.translucent_centroids.mean(axis=0)
        if buf.translucent_centroids.shape[0]
        else np.zeros(3, dtype=np.float64)
    )
    buf.translucent_pairs = _translucent_pairs(plan)
    buf.translucent_draw_batches = list(plan.translucent)
    buf.translucent_sort_key = None


def _load_shader_source(name: str) -> str:
    return (files("pluton.viewport") / "shaders" / name).read_text(encoding="utf-8")


def _compile_shader(source: str, shader_type: int) -> int:
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
        kind = "vertex" if shader_type == GL.GL_VERTEX_SHADER else "fragment"
        raise RuntimeError(f"{kind} shader compile failed:\n{log}")
    return shader


def _link_program(vert_src: str, frag_src: str) -> int:
    vs = _compile_shader(vert_src, GL.GL_VERTEX_SHADER)
    fs = _compile_shader(frag_src, GL.GL_FRAGMENT_SHADER)
    program = GL.glCreateProgram()
    GL.glAttachShader(program, vs)
    GL.glAttachShader(program, fs)
    GL.glLinkProgram(program)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(f"shader program link failed:\n{log}")
    GL.glDeleteShader(vs)
    GL.glDeleteShader(fs)
    return program


def _cache_uniform_locations(program: int, names: Sequence[str]) -> dict[str, int]:
    """Look up uniform locations once per program. Returned dict is read by
    every subsequent draw to avoid glGetUniformLocation in the hot path."""
    return {name: GL.glGetUniformLocation(program, name) for name in names}


def _build_grid_vertex_array() -> np.ndarray:
    """Return a (N, 6) float32 array of grid-line vertices: x,y,z, r,g,b."""
    verts: list[float] = []
    n = int(2 * _GRID_HALF_EXTENT / _GRID_SPACING) + 1
    for i in range(n):
        v = -_GRID_HALF_EXTENT + i * _GRID_SPACING
        is_centerline = abs(v) < 1e-5
        c = _GRID_CENTERLINE_COLOR if is_centerline else _GRID_COLOR
        # Line parallel to X (varying x at fixed y)
        verts.extend([-_GRID_HALF_EXTENT, v, 0.0, *c])
        verts.extend([+_GRID_HALF_EXTENT, v, 0.0, *c])
        # Line parallel to Y (varying y at fixed x)
        verts.extend([v, -_GRID_HALF_EXTENT, 0.0, *c])
        verts.extend([v, +_GRID_HALF_EXTENT, 0.0, *c])
    return np.array(verts, dtype=np.float32).reshape(-1, 6)


def _build_axes_vertex_array() -> np.ndarray:
    """Return a (6, 6) float32 array: 3 colored line segments through origin."""
    return np.array(
        [
            # X axis (red)
            [0.0, 0.0, 0.0, *_AXIS_X_COLOR],
            [_AXIS_LENGTH, 0.0, 0.0, *_AXIS_X_COLOR],
            # Y axis (green)
            [0.0, 0.0, 0.0, *_AXIS_Y_COLOR],
            [0.0, _AXIS_LENGTH, 0.0, *_AXIS_Y_COLOR],
            # Z axis (blue)
            [0.0, 0.0, 0.0, *_AXIS_Z_COLOR],
            [0.0, 0.0, _AXIS_LENGTH, *_AXIS_Z_COLOR],
        ],
        dtype=np.float32,
    )


def _snap_marker_vertices(kind: int, p) -> np.ndarray:
    """GL_LINES vertices (N, 3) for a snap marker centered at world point p.

    Shape per kind: triangle (Midpoint), diamond (On-Edge), X (Intersection),
    square (Endpoint / On-Face / Grid / Axis / default). Drawn flat in the XY
    plane at p.z (a billboard approximation, matching M2/M3b markers).
    """
    s = 0.05
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if kind == int(SnapKind.MIDPOINT):
        return np.array(
            [
                [x - s, y - s, z],
                [x + s, y - s, z],
                [x + s, y - s, z],
                [x, y + s, z],
                [x, y + s, z],
                [x - s, y - s, z],
            ],
            dtype=np.float32,
        )
    if kind == int(SnapKind.ON_EDGE):  # diamond
        return np.array(
            [
                [x, y + s, z],
                [x + s, y, z],
                [x + s, y, z],
                [x, y - s, z],
                [x, y - s, z],
                [x - s, y, z],
                [x - s, y, z],
                [x, y + s, z],
            ],
            dtype=np.float32,
        )
    if kind == int(SnapKind.INTERSECTION):  # X
        return np.array(
            [[x - s, y - s, z], [x + s, y + s, z], [x - s, y + s, z], [x + s, y - s, z]],
            dtype=np.float32,
        )
    # default: square
    return np.array(
        [
            [x - s, y - s, z],
            [x + s, y - s, z],
            [x + s, y - s, z],
            [x + s, y + s, z],
            [x + s, y + s, z],
            [x - s, y + s, z],
            [x - s, y + s, z],
            [x - s, y - s, z],
        ],
        dtype=np.float32,
    )


def _selection_face_polygons(scene, selection) -> list[np.ndarray]:
    """World-space loops (N,3 float32) for each LIVE selected face."""
    polys: list[np.ndarray] = []
    for f_id in selection.faces:
        try:
            loop = scene.face_loop(f_id)
        except KeyError:
            continue  # dead/stale id
        pts = np.array([scene.vertex(v).position for v in loop], dtype=np.float32)
        polys.append(pts)
    return polys


def _selection_edge_segments(scene, selection) -> np.ndarray:
    """(2E,3) float32 endpoint pairs for each LIVE selected edge."""
    out: list[np.ndarray] = []
    for e_id in selection.edges:
        try:
            e = scene.edge(e_id)
        except KeyError:
            continue
        out.append(np.asarray(scene.vertex(e.v1_id).position, dtype=np.float32))
        out.append(np.asarray(scene.vertex(e.v2_id).position, dtype=np.float32))
    if not out:
        return np.zeros((0, 3), dtype=np.float32)
    return np.array(out, dtype=np.float32)


def _box_rect_ndc_segments(box_rect, viewport_w, viewport_h) -> np.ndarray:
    """Convert a pixel-space rect (x0,y0,x1,y1) to (8,3) NDC GL_LINES segments
    (z=0) tracing its outline. y is flipped (screen y-down -> NDC y-up)."""
    x0, y0, x1, y1 = box_rect
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)

    def ndc(px, py):
        return ((2.0 * px / w) - 1.0, 1.0 - (2.0 * py / h))

    corners = [ndc(x0, y0), ndc(x1, y0), ndc(x1, y1), ndc(x0, y1)]
    out: list[list[float]] = []
    for i in range(4):
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        out.append([ax, ay, 0.0])
        out.append([bx, by, 0.0])
    return np.array(out, dtype=np.float32)


def _screen_marker_ndc_quad(
    sx: float, sy: float, size_px: float, width: int, height: int
) -> np.ndarray:
    """4 corner NDC points of a `size_px` square centred at pixel (sx, sy)."""
    w = max(int(width), 1)
    h = max(int(height), 1)
    half = size_px * 0.5
    corners_px = [
        (sx - half, sy - half),
        (sx + half, sy - half),
        (sx + half, sy + half),
        (sx - half, sy + half),
    ]
    out = np.empty((4, 2), dtype=np.float32)
    for i, (px, py) in enumerate(corners_px):
        out[i, 0] = (2.0 * px / w) - 1.0
        out[i, 1] = 1.0 - (2.0 * py / h)
    return out


class SceneRenderer:
    """Owns GL resources for the grid + axes + user geometry + tool overlay."""

    def __init__(self) -> None:
        self._initialized = False
        # Programs
        self._phong_program: int = 0
        self._line_program: int = 0
        # Uniform location caches (populated in initialize_gl)
        self._phong_locs: dict[str, int] = {}
        self._line_locs: dict[str, int] = {}
        # Grid + axes buffers
        self._grid_vao: int = 0
        self._grid_vbo: int = 0
        self._grid_vertex_count: int = 0
        self._axes_vao: int = 0
        self._axes_vbo: int = 0
        self._axes_vertex_count: int = 0
        # Per-definition GL buffer cache (M4e Task 11): keyed by id(definition).
        # Each entry is a _DefBuffers holding face/edge VAO+VBO+count.
        self._def_buffers: dict[int, _DefBuffers] = {}

        # Tool overlay buffers (rebuilt every frame)
        self._overlay_line_vao: int = 0
        self._overlay_line_vbo: int = 0
        self._overlay_marker_vao: int = 0
        self._overlay_marker_vbo: int = 0

        # Ghost-fill overlay (M3b)
        self._ghost_fill_program: int = 0
        self._ghost_fill_locs: dict[str, int] = {}
        self._ghost_fill_vao: int = 0
        self._ghost_fill_vbo: int = 0
        # View / projection matrices captured each frame so draw_face_fill_overlays
        # (called by tool overlays) can reuse them without re-deriving from camera.
        self._current_view_matrix: np.ndarray | None = None
        self._current_projection_matrix: np.ndarray | None = None

        # Viewport pixel size — updated in resize(); used by _draw_box_rect.
        self._viewport_w: int = 1
        self._viewport_h: int = 1

        # Active display style (Shaded/Wireframe/HiddenLine + X-Ray toggle).
        # Updated by set_render_style(), called by the View menu via the viewport.
        self._render_style = RenderStyle()

    # --- Lifecycle --------------------------------------------------------

    def initialize_gl(self) -> None:
        if self._initialized:
            return
        GL.glClearColor(*_BG_COLOR)
        GL.glEnable(GL.GL_DEPTH_TEST)

        self._phong_program = _link_program(
            _load_shader_source("phong.vert"),
            _load_shader_source("phong.frag"),
        )
        self._line_program = _link_program(
            _load_shader_source("line.vert"),
            _load_shader_source("line.frag"),
        )

        # Cache uniform locations once per program — uniform locations are
        # stable for the lifetime of a linked program, so doing the lookup
        # in the per-frame draw path is pure waste.
        self._phong_locs = _cache_uniform_locations(self._phong_program, _PHONG_UNIFORMS)
        self._line_locs = _cache_uniform_locations(self._line_program, _LINE_UNIFORMS)

        self._ghost_fill_program = _link_program(
            _load_shader_source("ghost_fill.vert"),
            _load_shader_source("ghost_fill.frag"),
        )
        self._ghost_fill_locs = _cache_uniform_locations(
            self._ghost_fill_program, _GHOST_FILL_UNIFORMS
        )

        self._init_grid_buffers()
        self._init_axes_buffers()
        self._init_overlay_buffers()
        self._init_ghost_fill_buffers()

        self._initialized = True

    def resize(self, w: int, h: int) -> None:
        self._viewport_w = int(w)
        self._viewport_h = int(h)
        if not self._initialized:
            return
        GL.glViewport(0, 0, w, h)

    def set_render_style(self, style: RenderStyle) -> None:
        """Set the active display style (called by the viewport from the View menu)."""
        self._render_style = replace(style)

    def render(self, camera: Camera, model=None, tool_overlay=None, selection=None) -> None:
        """Draw the full scene: grid + axes + user geometry (all definitions) + tool overlay.

        Iterates model.traverse() to draw each definition's geometry with its
        accumulated world transform as the model matrix. Per-definition GL
        buffers are cached in _def_buffers and re-uploaded only when the
        definition's mesh is dirty.
        """
        if not self._initialized:
            return

        GL.glClearColor(*_BG_COLOR)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glEnable(GL.GL_DEPTH_TEST)

        view = camera.view_matrix()
        projection = camera.projection_matrix()
        self._current_view_matrix = view
        self._current_projection_matrix = projection

        # 1. Grid (M1)
        self._draw_lines(self._grid_vao, self._grid_vertex_count, view, projection)
        # 2. Axes (M1)
        self._draw_lines(self._axes_vao, self._axes_vertex_count, view, projection)

        # 3 & 4. Draw all definitions in the scene graph with their world transforms.
        if model is not None:
            # Task 16 (#59): reconcile _def_buffers against the live model before
            # drawing so buffers for deleted/exploded definitions don't leak for
            # the rest of the session. Requires a current GL context, so this can
            # only run here in the render path (not from an arbitrary caller).
            self.evict_unreachable(model)
            materials = getattr(model, "materials", None)
            translucent_ids = _translucent_ids(materials)
            visible = list(model.traverse_visible())
            # Task 11: which tag placed each definition, so Color-by-Tag can
            # resolve a colour per definition below. Computed unconditionally
            # (like translucent_ids above) rather than gated on the style
            # flag -- resolve_definition_tag_color itself is the None-when-off
            # gate, and one tree walk per frame is cheap next to traversal.
            tag_ids_by_definition = _definition_tag_ids(model)

            # Correction 2: translucent faces must be drawn after ALL opaque
            # geometry across every definition, not merely after their own
            # definition's, so the traversal is split in two rather than
            # gaining a second inner loop.
            #
            # Pass 1: every definition's opaque batches, plus its edges.
            for definition, world in visible:
                buf = self._ensure_buffers(definition, translucent_ids)
                model_mat = world.astype(np.float32)
                # Task 15: dim pass — dim anything that is NOT the active context.
                # At root (active_path is empty), nothing is dimmed.
                dimmed = definition_is_dimmed(definition, model)
                # Task 11: resolved once per definition, not per batch, the
                # same way `dimmed` above is.
                tag_color = resolve_definition_tag_color(
                    tag_ids_by_definition.get(id(definition), model.tags.UNTAGGED_ID),
                    model.tags,
                    self._render_style,
                )
                for batch in buf.plan.opaque:
                    front, back = resolve_batch_sides(
                        batch, materials, self._render_style, dimmed=dimmed
                    )
                    front, back = apply_tag_color_override(front, back, tag_color)
                    # draw_faces comes from the face style alone, so it is the
                    # same on both sides; front is representative.
                    if front.draw_faces and batch.count > 0:
                        self._draw_definition_faces(
                            buf,
                            view,
                            projection,
                            camera.position,
                            model_mat,
                            front=front,
                            back=back,
                            first=batch.first,
                            count=batch.count,
                        )
                # Edges stay in pass 1 — they are opaque.
                if buf.edge_count > 0:
                    self._draw_definition_edges(buf, view, projection, model_mat, dimmed=dimmed)

            # Pass 2: translucent batches only, definitions back to front.
            # The filter names the same list the loop below draws, so the two
            # cannot disagree. Filtering on `plan.translucent` instead happens
            # to work only because _reset_translucent_state seeds both together.
            translucent_entries = [
                (d, w) for d, w in visible if self._def_buffers[id(d)].translucent_draw_batches
            ]
            order = order_definitions_for_translucent_pass(
                translucent_entries,
                camera_pos=camera.position,
                centroid_of=lambda d: self._def_buffers[id(d)].translucent_local_centroid,
            )
            for i in order:
                definition, world = translucent_entries[i]
                buf = self._def_buffers[id(definition)]
                self._sort_translucent_slice(buf, world, camera.position)
                model_mat = world.astype(np.float32)
                dimmed = definition_is_dimmed(definition, model)
                tag_color = resolve_definition_tag_color(
                    tag_ids_by_definition.get(id(definition), model.tags.UNTAGGED_ID),
                    model.tags,
                    self._render_style,
                )
                for batch in buf.translucent_draw_batches:
                    front, back = resolve_batch_sides(
                        batch, materials, self._render_style, dimmed=dimmed
                    )
                    front, back = apply_tag_color_override(front, back, tag_color)
                    if front.draw_faces and batch.count > 0:
                        self._draw_definition_faces(
                            buf,
                            view,
                            projection,
                            camera.position,
                            model_mat,
                            front=front,
                            back=back,
                            first=batch.first,
                            count=batch.count,
                        )

            # 4.5 Selection highlight (persistent, drawn on top of geometry).
            # Operates on the active context (root at identity, or entered context).
            if selection is not None:
                active_scene = model.active_scene
                self._draw_selection(
                    active_scene,
                    selection,
                    view,
                    projection,
                    world_transform=model.active_world_transform,
                )

            # 4.6 Task 15: Selected-instance bounding boxes (selection-blue).
            if selection is not None and selection.instances:
                active_world = model.active_world_transform
                for inst in model.active_context.children:
                    if inst.id in selection.instances and model.tags.is_visible(inst.tag_id):
                        aabb = inst.definition.local_aabb()
                        if aabb is not None:
                            lo, hi = aabb
                            world_t = active_world @ inst.transform
                            segs = aabb_world_edges(lo, hi, world_t)
                            self._draw_world_segments(
                                segs, _INSTANCE_BBOX_COLOR, _INSTANCE_BBOX_WIDTH, view, projection
                            )

        # 5. Tool overlay (NEW) — drawn on top with depth-test disabled
        if tool_overlay is not None:
            self._draw_tool_overlay(tool_overlay, view, projection)

        # 6. Face fills (M3b) — drawn last (on top of edges/markers).
        # Tools emit face_fill_polygons in WORLD coords already (each tool lifts
        # its own geometry), so we draw at identity — no world_transform here.
        if tool_overlay is not None and tool_overlay.face_fill_polygons:
            self.draw_face_fill_overlays(
                polygons=tool_overlay.face_fill_polygons,
                color=tool_overlay.face_fill_color,
            )

        # 7. Box-select rectangle (M4b) — screen space, on top.
        if tool_overlay is not None and tool_overlay.box_rect is not None:
            self._draw_box_rect(tool_overlay.box_rect, tool_overlay.box_rect_color)

        # 8. Generic gizmo primitives (M4c) — world polylines + screen markers.
        if tool_overlay is not None:
            if getattr(tool_overlay, "world_polylines", None):
                self._draw_world_polylines(tool_overlay.world_polylines, view, projection)
            if getattr(tool_overlay, "screen_markers", None):
                self._draw_screen_markers(
                    camera, tool_overlay.screen_markers, self._viewport_w, self._viewport_h
                )

    def evict_unreachable(self, model) -> None:
        """Drop + release GL buffers for definitions no longer reachable from `model`.

        Reachability is computed with model.traverse() (ALL instantiated
        definitions, root included) rather than traverse_visible(), so a
        definition that is merely on a hidden tag keeps its buffers —
        eviction only targets definitions with no instance anywhere
        (deleted or exploded), the actual leak described in #59.

        No-op-safe without a GL context: does not require self._initialized,
        and _DefBuffers.release() itself guards every delete call behind a
        zero-handle check, so an all-zero stand-in record releases cleanly.
        """
        reachable = {id(definition) for definition, _world in model.traverse()}
        reachable.add(id(model.root))  # defensive; traverse() already yields root first
        for key in [k for k in self._def_buffers if k not in reachable]:
            buf = self._def_buffers.pop(key)
            buf.release()

    # --- Init helpers -----------------------------------------------------

    def _init_grid_buffers(self) -> None:
        verts = _build_grid_vertex_array()
        self._grid_vertex_count = int(verts.shape[0])
        self._grid_vao, self._grid_vbo = self._upload_interleaved_lines(verts)

    def _init_axes_buffers(self) -> None:
        verts = _build_axes_vertex_array()
        self._axes_vertex_count = int(verts.shape[0])
        self._axes_vao, self._axes_vbo = self._upload_interleaved_lines(verts)

    def _alloc_def_buffers(self) -> _DefBuffers:
        """Allocate a new _DefBuffers: create empty VAO+VBO pairs for faces and edges."""
        buf = _DefBuffers()

        # Face buffers — interleaved (pos.xyz, normal.xyz), 24 bytes per vertex
        buf.face_vao = int(GL.glGenVertexArrays(1))
        buf.face_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(buf.face_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.face_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, _FACE_VERTEX_BYTES, None)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, _FACE_VERTEX_BYTES, ctypes.c_void_p(12)
        )
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

        # Edge buffers — interleaved (pos.xyz, color.rgb), 24 bytes per vertex
        buf.edge_vao = int(GL.glGenVertexArrays(1))
        buf.edge_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(buf.edge_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.edge_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)  # 24 bytes
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

        return buf

    def _init_overlay_buffers(self) -> None:
        """Create empty VBOs for tool-overlay lines and snap-marker quads.

        Both buffers use the line shader's (pos.xyz, color.rgb) layout.
        """
        # Rubber-band lines
        self._overlay_line_vao = int(GL.glGenVertexArrays(1))
        self._overlay_line_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._overlay_line_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

        # Snap marker — small world-aligned wireframe square re-uploaded per frame.
        self._overlay_marker_vao = int(GL.glGenVertexArrays(1))
        self._overlay_marker_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._overlay_marker_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_marker_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

    @staticmethod
    def _upload_interleaved_lines(verts: np.ndarray) -> tuple[int, int]:
        """Upload an (N, 6) float32 array (x,y,z, r,g,b per vertex). Returns (vao, vbo)."""
        vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(vao)
        vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)
        # position (vec3)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        # color (vec3) at offset 3 floats
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(
            1,
            3,
            GL.GL_FLOAT,
            GL.GL_FALSE,
            stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
        return vao, vbo

    # --- Draw helpers -----------------------------------------------------

    def _draw_lines(self, vao: int, count: int, view: np.ndarray, projection: np.ndarray) -> None:
        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)
        GL.glBindVertexArray(vao)
        GL.glDrawArrays(GL.GL_LINES, 0, count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _ensure_buffers(self, definition, translucent_ids: frozenset[int]) -> _DefBuffers:
        """The cached buffers for `definition`, re-uploading them if stale.

        Lifted out of the draw loop because pass 1 and pass 2 both need it and
        duplicating it would let the two drift.

        Staleness has two causes, not one. A dirty mesh is the familiar one.
        The other is spec 1.7's asymmetry: uniforms are read from the library
        per batch at draw time, so editing a material's COLOUR shows up with no
        buffer work at all — but the opaque/translucent partition is computed
        here, and editing a material's ALPHA dirties no mesh. Without the set
        comparison a material turned translucent would keep drawing in the
        opaque pass, writing depth and never sorting, which looks like the edit
        did nothing. Comparing the whole set rather than tracking a per-material
        boundary crossing is deliberate: it catches a material being added,
        removed, or edited in either direction, and the set is a handful of ints.
        """
        buf = self._def_buffers.get(id(definition))
        if buf is None or definition.mesh.dirty or buf.translucent_ids != translucent_ids:
            buf = self._upload_definition(definition, translucent_ids)
            definition.mesh.mark_clean()
            self._def_buffers[id(definition)] = buf
        return buf

    def _sort_translucent_slice(self, buf: _DefBuffers, world, camera_pos) -> None:
        """Re-order this definition's translucent suffix back to front.

        No-ops when neither the camera nor the geometry has moved since the
        last sort, so a static view costs nothing. Only the suffix is touched;
        the opaque prefix is never re-uploaded. The permutation is always
        computed against `face_interleaved`, which stays in upload order, so
        repeated sorts do not compose.

        The suffix may span several material pairs, so the batches that
        describe it are re-cut from the sorted order — see
        rebuild_translucent_batches for why drawing with the original ranges
        would be wrong.
        """
        if buf.translucent_centroids.shape[0] == 0:
            return
        key = (tuple(np.asarray(camera_pos, dtype=np.float64).tolist()), world.tobytes())
        if key == buf.translucent_sort_key:
            return

        world_centroids = transform_points(buf.translucent_centroids, world)
        tri_order = order_back_to_front(world_centroids, camera_pos)
        vertex_order = triangle_order_to_vertex_order(tri_order)

        first = buf.plan.translucent_first
        data = np.ascontiguousarray(buf.face_interleaved[first:][vertex_order], dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.face_vbo)
        GL.glBufferSubData(GL.GL_ARRAY_BUFFER, first * _FACE_VERTEX_BYTES, data.nbytes, data)

        buf.translucent_draw_batches = rebuild_translucent_batches(
            buf.translucent_pairs[tri_order], first
        )
        buf.translucent_sort_key = key

    def _upload_definition(self, definition, translucent_ids: frozenset[int]) -> _DefBuffers:
        """Build or update GL buffers for a single definition's mesh.

        Looks up (or allocates) a _DefBuffers entry for this definition,
        uploads fresh geometry data, and returns the updated _DefBuffers.
        The caller is responsible for calling definition.mesh.mark_clean()
        and storing the result back into self._def_buffers[id(definition)].

        `translucent_ids` is the set the batch planner needs in order to
        classify a batch as translucent. Passed in rather than derived from the
        model here because _ensure_buffers also compares it against the set the
        buffer was last built under, and both must see exactly the same value.
        """
        # Re-use existing GL objects if we already have them; allocate if not.
        buf = self._def_buffers.get(id(definition))
        if buf is None:
            buf = self._alloc_def_buffers()

        scene = definition.mesh

        # Faces: (3*T, 3) positions + (3*T, 3) normals -> interleaved (3*T, 6)
        positions, normals = scene.face_triangle_buffer()
        if positions.shape[0] > 0:
            interleaved = np.concatenate([positions, normals], axis=1).astype(np.float32)
            # Group triangles by (front, back) material so each pair draws as one
            # contiguous batch, with the translucent pairs as a contiguous suffix
            # that render()'s second pass depth-sorts.
            front_mats = scene.face_triangle_materials(Side.FRONT)
            back_mats = scene.face_triangle_materials(Side.BACK)
            plan = plan_face_batches(front_mats, back_mats, translucent_ids)
            interleaved = np.ascontiguousarray(interleaved[plan.vertex_order])
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.face_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL.GL_DYNAMIC_DRAW)
            buf.face_count = int(positions.shape[0])
            buf.plan = plan
        else:
            interleaved = _empty_face_interleaved()
            plan = _empty_batch_plan()
            buf.face_count = 0
            buf.plan = plan
        buf.translucent_ids = translucent_ids
        _reset_translucent_state(buf, plan, interleaved)

        # Edges: (2*E, 3) positions — pack constant color per vertex so the
        # line shader's attribute 1 (in_color) is always satisfied.
        edges = scene.edge_line_buffer()
        if edges.shape[0] > 0:
            n = int(edges.shape[0])
            colors = np.tile(np.array(_USER_EDGE_COLOR, dtype=np.float32), (n, 1))
            data = np.ascontiguousarray(np.concatenate([edges.astype(np.float32), colors], axis=1))
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buf.edge_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            buf.edge_count = n
        else:
            buf.edge_count = 0

        return buf

    def _draw_definition_faces(
        self,
        buf: _DefBuffers,
        view: np.ndarray,
        projection: np.ndarray,
        camera_pos: np.ndarray,
        model_mat: np.ndarray,
        *,
        front: ResolvedFacePass,
        back: ResolvedFacePass,
        first: int = 0,
        count: int | None = None,
    ) -> None:
        """Draw a definition's faces using resolved face-passes (style + dim + X-Ray).

        ``front`` and ``back`` carry the two sides' material uniforms and alphas;
        the fragment shader selects between them with gl_FrontFacing. Blend and
        depth-mask state is draw-call state rather than per-side, so it is taken
        from ``front`` — resolve_batch_sides gives both sides the same flags.
        X-Ray turns depth writes off so geometry behind shows through; the dim
        pass and X-Ray both arrive here pre-composed as a reduced alpha. State
        (blend, depth mask) is restored after the draw — see the M4e Task-15
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
        _set_vec3(locs["u_material_ambient"], front.ambient)
        _set_vec3(locs["u_material_diffuse"], front.diffuse)
        _set_vec3(locs["u_material_specular"], front.specular)
        _set_float(locs["u_material_shininess"], front.shininess)
        _set_float(locs["u_alpha"], front.alpha)
        _set_vec3(locs["u_material_ambient_back"], back.ambient)
        _set_vec3(locs["u_material_diffuse_back"], back.diffuse)
        _set_vec3(locs["u_material_specular_back"], back.specular)
        _set_float(locs["u_material_shininess_back"], back.shininess)
        _set_float(locs["u_alpha_back"], back.alpha)

        if front.blend:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        if not front.depth_write:
            GL.glDepthMask(GL.GL_FALSE)

        GL.glBindVertexArray(buf.face_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, first, buf.face_count if count is None else count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

        if not front.depth_write:
            GL.glDepthMask(GL.GL_TRUE)
        if front.blend:
            GL.glDisable(GL.GL_BLEND)

    def _draw_definition_edges(
        self,
        buf: _DefBuffers,
        view: np.ndarray,
        projection: np.ndarray,
        model_mat: np.ndarray,
        *,
        dimmed: bool = False,
    ) -> None:
        """Draw a definition's edge geometry with the given model matrix.

        Note: the line shader does not have a u_model uniform (it uses only
        u_view and u_projection), so edges are always drawn in local space
        transformed to world space by the line vertex shader via the view
        matrix. For the root definition at identity this is equivalent to
        the previous hardcoded behaviour. For child definitions the geometry
        is already in local space; the model matrix must be folded into the
        view or the edges drawn in world space. Since the line shader has no
        u_model, we pre-multiply view by model_mat for this draw call only.

        When ``dimmed`` is True (Task 15), lines are drawn at reduced opacity
        using the constant-alpha blend so the geometry recedes.

        Note (#61): the face dim/transparency path migrated to the
        `u_alpha` phong uniform + standard GL_SRC_ALPHA blending back in
        M5a (commit 5a3bc65); this edge path still uses the older
        glBlendColor + GL_CONSTANT_ALPHA idiom. That's intentional-on-record
        rather than an oversight: the line shader has no alpha uniform, and
        every other blended pass already sets its own glBlendFunc to
        GL_SRC_ALPHA before drawing, so the divergence has no visible
        effect today. Giving the line shader a u_alpha uniform to unify the
        two paths would mean auditing every other draw call that shares
        `self._line_program` (_draw_lines, _draw_tool_overlay,
        _draw_world_segments, _draw_screen_space_lines) so none of them
        silently render at GLSL's zero-initialized alpha; left as a
        follow-up rather than risking a blast-radius change here.
        """
        # Pre-multiply: view_for_edges = view @ model_mat (transforms local→clip).
        # Both are float32; the result is float32.
        view_x_model = (view.astype(np.float64) @ model_mat.astype(np.float64)).astype(np.float32)

        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view_x_model)
        _set_mat4(locs["u_projection"], projection)

        if dimmed:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendColor(0.0, 0.0, 0.0, _DIM_ALPHA_BLEND)
            GL.glBlendFunc(GL.GL_CONSTANT_ALPHA, GL.GL_ONE_MINUS_CONSTANT_ALPHA)

        GL.glBindVertexArray(buf.edge_vao)
        GL.glLineWidth(1.5)
        GL.glDrawArrays(GL.GL_LINES, 0, buf.edge_count)
        GL.glLineWidth(1.0)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

        if dimmed:
            GL.glDisable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            # Restore the blend color too, not just the blend func — a leftover
            # non-default GL_CONSTANT_ALPHA color is harmless today only because
            # every subsequent blended pass overwrites glBlendFunc before use;
            # reset it so that invariant isn't required to hold.
            GL.glBlendColor(0.0, 0.0, 0.0, 1.0)

    def _draw_tool_overlay(
        self,
        overlay,
        view: np.ndarray,
        projection: np.ndarray,
    ) -> None:
        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)

        # Disable depth test so the overlay always wins.
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            # Rubber-band segments — each segment is two vertices with pos + color.
            segs = overlay.rubber_band_segments
            if segs.shape[0] > 0:
                n = int(segs.shape[0])
                colors = np.tile(np.array(overlay.rubber_band_color, dtype=np.float32), (n, 1))
                data = np.ascontiguousarray(
                    np.concatenate([segs.astype(np.float32), colors], axis=1)
                )
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
                GL.glBindVertexArray(self._overlay_line_vao)
                GL.glLineWidth(2.0)
                GL.glDrawArrays(GL.GL_LINES, 0, n)
                GL.glLineWidth(1.0)
                GL.glBindVertexArray(0)

            # Snap marker — small wireframe shape at the snap point.
            # Shape depends on snap kind: see _snap_marker_vertices.
            if overlay.snap_marker_position is not None:
                p = overlay.snap_marker_position
                pos = _snap_marker_vertices(overlay.snap_marker_kind, p)

                n = pos.shape[0]
                cr, cg, cb = overlay.snap_marker_color
                colors = np.tile(np.array([cr, cg, cb], dtype=np.float32), (n, 1))
                data = np.ascontiguousarray(
                    np.concatenate([pos, colors], axis=1).astype(np.float32)
                )

                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_marker_vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
                GL.glBindVertexArray(self._overlay_marker_vao)
                GL.glLineWidth(2.0)
                GL.glDrawArrays(GL.GL_LINES, 0, n)
                GL.glLineWidth(1.0)
                GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def _draw_world_segments(self, segs, color, width, view, projection) -> None:
        """Draw (2N,3) world-space GL_LINES in a flat color, on top (depth off).
        Reuses the overlay line VBO."""
        if segs.shape[0] == 0:
            return
        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)
        n = int(segs.shape[0])
        colors = np.tile(np.array(color, dtype=np.float32), (n, 1))
        data = np.ascontiguousarray(np.concatenate([segs.astype(np.float32), colors], axis=1))
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            GL.glBindVertexArray(self._overlay_line_vao)
            GL.glLineWidth(width)
            GL.glDrawArrays(GL.GL_LINES, 0, n)
            GL.glLineWidth(1.0)
            GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def _draw_screen_space_lines(self, segs, color, width) -> None:
        """Draw (2N,3) NDC GL_LINES with identity view/projection (NDC positions
        render directly); depth test off, line width restored to 1.0 afterward.

        Shared by _draw_box_rect and _draw_screen_markers so both go through one
        VBO-upload-and-draw path on the line shader."""
        n = int(segs.shape[0])
        if n == 0:
            return
        identity = np.eye(4, dtype=np.float32)
        colors = np.tile(np.array(color, dtype=np.float32), (n, 1))
        data = np.ascontiguousarray(np.concatenate([segs, colors], axis=1).astype(np.float32))
        GL.glUseProgram(self._line_program)
        _set_mat4(self._line_locs["u_view"], identity)
        _set_mat4(self._line_locs["u_projection"], identity)
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._overlay_line_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            GL.glBindVertexArray(self._overlay_line_vao)
            GL.glLineWidth(width)
            GL.glDrawArrays(GL.GL_LINES, 0, n)
            GL.glLineWidth(1.0)
            GL.glBindVertexArray(0)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    def _draw_box_rect(self, box_rect, color) -> None:
        """Draw the screen-space box-select outline using identity view/projection
        (NDC positions render directly); depth test off."""
        segs = _box_rect_ndc_segments(box_rect, self._viewport_w, self._viewport_h)
        self._draw_screen_space_lines(segs, color, 1.5)

    def _draw_world_polylines(self, polylines, view, projection) -> None:
        """Draw each (segments, color, width) as world-space line segments."""
        for segs, color, width in polylines:
            arr = np.asarray(segs, dtype=np.float32).reshape(-1, 3)
            if arr.shape[0] >= 2:
                self._draw_world_segments(arr, color, float(width), view, projection)

    def _draw_screen_markers(self, camera, markers, width, height) -> None:
        """Project each (world_pos, size_px, color) and draw an outlined square
        in screen space (identity matrices), like the box-select rectangle."""
        if not markers:
            return
        for world_pos, size_px, color in markers:
            proj = camera.world_to_screen(world_pos, width, height)
            if proj is None:
                continue
            sx, sy, _depth = proj
            quad = _screen_marker_ndc_quad(sx, sy, size_px, width, height)
            # 4 edges as (2*N,3) GL_LINES at z=0.
            loop = np.zeros((8, 3), dtype=np.float32)
            for i in range(4):
                loop[2 * i, 0:2] = quad[i]
                loop[2 * i + 1, 0:2] = quad[(i + 1) % 4]
            self._draw_screen_space_lines(loop, color, 1.5)

    def _draw_selection(self, scene, selection, view, projection, world_transform=None) -> None:
        if selection is None:
            return
        need_transform = not is_identity_transform(world_transform)
        polys = _selection_face_polygons(scene, selection)
        if polys:
            if need_transform:
                polys = [apply_mat(p, world_transform) for p in polys]
            self.draw_face_fill_overlays(polygons=polys, color=_SELECTION_FILL_COLOR)
        segs = _selection_edge_segments(scene, selection)
        if need_transform and segs.shape[0] > 0:
            segs = apply_mat(segs, world_transform)
        self._draw_world_segments(segs, _SELECTION_EDGE_COLOR, 3.0, view, projection)

    def _init_ghost_fill_buffers(self) -> None:
        """Create the (empty) VAO/VBO for the ghost-fill overlay pass.

        Layout: position-only (vec3) at attribute 0. Buffer is re-uploaded
        on every draw_face_fill_overlays call.
        """
        self._ghost_fill_vao = int(GL.glGenVertexArrays(1))
        self._ghost_fill_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._ghost_fill_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._ghost_fill_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        stride = 3 * ctypes.sizeof(ctypes.c_float)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glBindVertexArray(0)

    def draw_face_fill_overlays(
        self,
        polygons: list[np.ndarray],
        color: tuple[float, float, float, float] = (0.4, 0.7, 1.0, 0.15),
        world_transform=None,
    ) -> None:
        """Draw alpha-blended filled polygons on top of the scene.

        Each polygon is an (N, 3) float32 ndarray (a closed loop in world
        coords). Earcut-triangulates each by projecting onto its dominant
        axis-aligned plane (XY / XZ / YZ — picked from the polygon's geometric
        normal). Depth-test enabled (overlays behind opaque geometry are
        occluded), depth-write disabled (successive overlay passes don't
        z-fight against each other), standard alpha blend.

        Empty polygon list is a no-op (and avoids touching GL state if the
        renderer wasn't initialized — useful for unit tests).

        world_transform: optional 4x4 float64 to convert local-space polygon
        coords to world space before drawing.  Identity (or None) is a no-op.
        """
        if not polygons:
            return
        if not self._initialized:
            return  # tests may call before initialize_gl; no-op
        if self._current_view_matrix is None or self._current_projection_matrix is None:
            return

        import mapbox_earcut

        # Apply world transform when non-identity (entered-instance context).
        if not is_identity_transform(world_transform):
            polygons = [apply_mat(p, world_transform) for p in polygons]

        triangle_vertices: list[float] = []
        for loop in polygons:
            if loop.shape[0] < 3:
                continue
            e1 = loop[1] - loop[0]
            e2 = loop[-1] - loop[0]
            n = np.cross(e1, e2)
            ax, ay, az = abs(float(n[0])), abs(float(n[1])), abs(float(n[2]))
            if az >= ax and az >= ay:
                xy = loop[:, :2].astype(np.float32)
            elif ax >= ay:
                xy = np.stack([loop[:, 1], loop[:, 2]], axis=1).astype(np.float32)
            else:
                xy = np.stack([loop[:, 0], loop[:, 2]], axis=1).astype(np.float32)
            ring_ends = np.array([len(loop)], dtype=np.uint32)
            tri_indices = mapbox_earcut.triangulate_float32(xy, ring_ends)
            tri_indices = np.asarray(tri_indices, dtype=np.int32).reshape(-1, 3)
            for tri in tri_indices:
                for vi in tri:
                    triangle_vertices.extend(
                        [float(loop[vi, 0]), float(loop[vi, 1]), float(loop[vi, 2])]
                    )

        if not triangle_vertices:
            return

        verts = np.array(triangle_vertices, dtype=np.float32)

        GL.glBindVertexArray(self._ghost_fill_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._ghost_fill_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_DYNAMIC_DRAW)

        GL.glUseProgram(self._ghost_fill_program)
        GL.glUniformMatrix4fv(
            self._ghost_fill_locs["u_view"], 1, GL.GL_TRUE, self._current_view_matrix
        )
        GL.glUniformMatrix4fv(
            self._ghost_fill_locs["u_projection"], 1, GL.GL_TRUE, self._current_projection_matrix
        )
        GL.glUniform4f(self._ghost_fill_locs["u_color"], *color)

        # GL state: alpha-blended, depth-test on (LEQUAL so coplanar overlays
        # don't z-fight against source-face geometry already in the depth buffer),
        # depth-write off (successive overlay passes don't z-fight each other),
        # no cull (overlay polygons may be viewed from either side during orbit).
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDepthFunc(GL.GL_LEQUAL)  # fixes hover-highlight on coplanar source face

        GL.glDrawArrays(GL.GL_TRIANGLES, 0, verts.shape[0] // 3)

        GL.glDepthFunc(GL.GL_LESS)  # restore default
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_BLEND)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)


# --- Uniform helpers --------------------------------------------------------
#
# These take a uniform `loc` (pre-cached via _cache_uniform_locations) instead
# of looking it up per-call. A `loc` of -1 means the uniform isn't present in
# the linked program (e.g., optimized out) — silently skipped.


def _set_mat4(loc: int, m: np.ndarray) -> None:
    if loc < 0:
        return
    # GLSL is column-major; numpy is row-major. Transpose flag handles it.
    GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, np.asarray(m, dtype=np.float32))


def _set_vec3(loc: int, v: np.ndarray | tuple[float, float, float]) -> None:
    if loc < 0:
        return
    arr = np.asarray(v, dtype=np.float32)
    GL.glUniform3f(loc, float(arr[0]), float(arr[1]), float(arr[2]))


def _set_float(loc: int, x: float) -> None:
    if loc < 0:
        return
    GL.glUniform1f(loc, float(x))

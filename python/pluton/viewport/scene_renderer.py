"""Owns GL resources for the M2 scene: grid + axes + user geometry + tool overlay.

Lifecycle is driven by QOpenGLWidget:
  initialize_gl() -> first paintGL() call sets up VBOs and shader programs.
  resize(w, h)    -> called from resizeGL.
  render(camera, scene, tool_overlay, selection) -> called from paintGL each frame.
"""

from __future__ import annotations

import ctypes
from collections.abc import Sequence
from importlib.resources import files

import numpy as np
from OpenGL import GL

from pluton.viewport.camera import Camera
from pluton.viewport.snap_engine import SnapKind


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

_BG_COLOR = (0.15, 0.15, 0.18, 1.0)

# Edge / overlay colors (per-vertex, packed into the VBO alongside positions).
_USER_EDGE_COLOR = (0.85, 0.85, 0.85)
_SELECTION_FILL_COLOR = (0.20, 0.50, 0.95, 0.25)   # selected faces (blue, 25% alpha)
_SELECTION_EDGE_COLOR = (0.20, 0.55, 1.00)         # selected edges (bright blue)
# Uniform names looked up once per program in initialize_gl().
_PHONG_UNIFORMS = (
    "u_view", "u_projection", "u_model", "u_camera_pos",
    "u_light_dir", "u_light_color",
    "u_material_ambient", "u_material_diffuse",
    "u_material_specular", "u_material_shininess",
)
_LINE_UNIFORMS = ("u_view", "u_projection")
_GHOST_FILL_UNIFORMS = ("u_view", "u_projection", "u_color")


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
            [[x - s, y - s, z], [x + s, y - s, z],
             [x + s, y - s, z], [x, y + s, z],
             [x, y + s, z], [x - s, y - s, z]],
            dtype=np.float32,
        )
    if kind == int(SnapKind.ON_EDGE):  # diamond
        return np.array(
            [[x, y + s, z], [x + s, y, z],
             [x + s, y, z], [x, y - s, z],
             [x, y - s, z], [x - s, y, z],
             [x - s, y, z], [x, y + s, z]],
            dtype=np.float32,
        )
    if kind == int(SnapKind.INTERSECTION):  # X
        return np.array(
            [[x - s, y - s, z], [x + s, y + s, z],
             [x - s, y + s, z], [x + s, y - s, z]],
            dtype=np.float32,
        )
    # default: square
    return np.array(
        [[x - s, y - s, z], [x + s, y - s, z],
         [x + s, y - s, z], [x + s, y + s, z],
         [x + s, y + s, z], [x - s, y + s, z],
         [x - s, y + s, z], [x - s, y - s, z]],
        dtype=np.float32,
    )


def _selection_face_polygons(scene, selection) -> list[np.ndarray]:  # noqa: ANN001
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


def _selection_edge_segments(scene, selection) -> np.ndarray:  # noqa: ANN001
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
        # User-geometry buffers (filled by Scene.dirty refresh path)
        self._user_face_vao: int = 0
        self._user_face_vbo: int = 0  # interleaved (pos.xyz, normal.xyz)
        self._user_face_count: int = 0  # number of vertices to draw

        self._user_edge_vao: int = 0
        self._user_edge_vbo: int = 0  # interleaved (pos.xyz, color.rgb), 24 bytes per vertex
        self._user_edge_count: int = 0

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
        self._init_user_buffers()
        self._init_overlay_buffers()
        self._init_ghost_fill_buffers()

        self._initialized = True

    def resize(self, w: int, h: int) -> None:
        self._viewport_w = int(w)
        self._viewport_h = int(h)
        if not self._initialized:
            return
        GL.glViewport(0, 0, w, h)

    def render(self, camera: Camera, scene=None, tool_overlay=None, selection=None) -> None:  # noqa: ANN001
        """Draw the full scene: grid + axes + user faces + user edges + tool overlay."""
        if not self._initialized:
            return

        GL.glClearColor(0.15, 0.16, 0.18, 1.0)
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

        # 3 & 4. User faces / edges (NEW) — re-upload if scene is dirty
        if scene is not None:
            if scene.dirty:
                self._refresh_user_buffers(scene)
                scene.mark_clean()
            if self._user_face_count > 0:
                self._draw_user_faces(view, projection, camera.position)
            if self._user_edge_count > 0:
                self._draw_user_edges(view, projection)

            # 4.5 Selection highlight (persistent, drawn on top of geometry).
            if selection is not None:
                self._draw_selection(scene, selection, view, projection)

        # 5. Tool overlay (NEW) — drawn on top with depth-test disabled
        if tool_overlay is not None:
            self._draw_tool_overlay(tool_overlay, view, projection)

        # 6. Face fills (M3b) — drawn last (on top of edges/markers).
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
                self._draw_screen_markers(camera, tool_overlay.screen_markers,
                                          self._viewport_w, self._viewport_h)

    # --- Init helpers -----------------------------------------------------

    def _init_grid_buffers(self) -> None:
        verts = _build_grid_vertex_array()
        self._grid_vertex_count = int(verts.shape[0])
        self._grid_vao, self._grid_vbo = self._upload_interleaved_lines(verts)

    def _init_axes_buffers(self) -> None:
        verts = _build_axes_vertex_array()
        self._axes_vertex_count = int(verts.shape[0])
        self._axes_vao, self._axes_vbo = self._upload_interleaved_lines(verts)

    def _init_user_buffers(self) -> None:
        """Create empty VBOs for user-face and user-edge geometry.

        We allocate VAOs/VBOs here but leave them empty until the first
        scene-dirty refresh fills them with real data.
        """
        # User faces — interleaved (pos.xyz, normal.xyz), 24 bytes per vertex
        self._user_face_vao = int(GL.glGenVertexArrays(1))
        self._user_face_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._user_face_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_face_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 24, None)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 24, ctypes.c_void_p(12))
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

        # User edges — interleaved (pos.xyz, color.rgb), 24 bytes per vertex
        # The line shader reads per-vertex color from attribute 1, so we pack
        # a constant edge color alongside each position.
        self._user_edge_vao = int(GL.glGenVertexArrays(1))
        self._user_edge_vbo = int(GL.glGenBuffers(1))
        GL.glBindVertexArray(self._user_edge_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_edge_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, 0, None, GL.GL_DYNAMIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)  # 24 bytes
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
            ctypes.c_void_p(3 * ctypes.sizeof(ctypes.c_float)),
        )
        GL.glEnableVertexAttribArray(1)
        GL.glBindVertexArray(0)

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
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
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
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
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
            1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
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

    def _refresh_user_buffers(self, scene) -> None:  # noqa: ANN001
        """Re-upload face and edge geometry from the scene to the GPU."""
        # User faces: (3*T, 3) positions + (3*T, 3) normals → interleaved (3*T, 6)
        positions, normals = scene.face_triangle_buffer()
        if positions.shape[0] > 0:
            interleaved = np.concatenate([positions, normals], axis=1).astype(np.float32)
            data = np.ascontiguousarray(interleaved)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_face_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            self._user_face_count = int(positions.shape[0])
        else:
            self._user_face_count = 0

        # User edges: (2*E, 3) positions — pack constant color per vertex so the
        # line shader's attribute 1 (in_color) is always satisfied.
        edges = scene.edge_line_buffer()
        if edges.shape[0] > 0:
            n = int(edges.shape[0])
            colors = np.tile(np.array(_USER_EDGE_COLOR, dtype=np.float32), (n, 1))
            data = np.ascontiguousarray(
                np.concatenate([edges.astype(np.float32), colors], axis=1)
            )
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._user_edge_vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
            self._user_edge_count = n
        else:
            self._user_edge_count = 0

    def _draw_user_faces(
        self,
        view: np.ndarray,
        projection: np.ndarray,
        camera_pos: np.ndarray,
    ) -> None:
        GL.glUseProgram(self._phong_program)
        locs = self._phong_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)
        # User geometry is already in world space — identity model matrix.
        _set_mat4(locs["u_model"], np.eye(4, dtype=np.float32))
        _set_vec3(locs["u_camera_pos"], camera_pos)
        # Same lighting / material as the old M1 cube.
        _set_vec3(locs["u_light_dir"], _LIGHT_DIR)
        _set_vec3(locs["u_light_color"], _LIGHT_COLOR)
        _set_vec3(locs["u_material_ambient"], _MATERIAL_AMBIENT)
        _set_vec3(locs["u_material_diffuse"], _MATERIAL_DIFFUSE)
        _set_vec3(locs["u_material_specular"], _MATERIAL_SPECULAR)
        _set_float(locs["u_material_shininess"], _MATERIAL_SHININESS)

        GL.glBindVertexArray(self._user_face_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, self._user_face_count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _draw_user_edges(self, view: np.ndarray, projection: np.ndarray) -> None:
        GL.glUseProgram(self._line_program)
        locs = self._line_locs
        _set_mat4(locs["u_view"], view)
        _set_mat4(locs["u_projection"], projection)

        GL.glBindVertexArray(self._user_edge_vao)
        GL.glLineWidth(1.5)
        GL.glDrawArrays(GL.GL_LINES, 0, self._user_edge_count)
        GL.glLineWidth(1.0)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _draw_tool_overlay(
        self,
        overlay,  # noqa: ANN001
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
                colors = np.tile(
                    np.array(overlay.rubber_band_color, dtype=np.float32), (n, 1)
                )
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
                data = np.ascontiguousarray(np.concatenate([pos, colors], axis=1).astype(np.float32))

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

    def _draw_world_segments(self, segs, color, width, view, projection) -> None:  # noqa: ANN001
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

    def _draw_screen_space_lines(self, segs, color, width) -> None:  # noqa: ANN001
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

    def _draw_box_rect(self, box_rect, color) -> None:  # noqa: ANN001
        """Draw the screen-space box-select outline using identity view/projection
        (NDC positions render directly); depth test off."""
        segs = _box_rect_ndc_segments(box_rect, self._viewport_w, self._viewport_h)
        self._draw_screen_space_lines(segs, color, 1.5)

    def _draw_world_polylines(self, polylines, view, projection) -> None:  # noqa: ANN001
        """Draw each (segments, color, width) as world-space line segments."""
        for segs, color, width in polylines:
            arr = np.asarray(segs, dtype=np.float32).reshape(-1, 3)
            if arr.shape[0] >= 2:
                self._draw_world_segments(arr, color, float(width), view, projection)

    def _draw_screen_markers(self, camera, markers, width, height) -> None:  # noqa: ANN001
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

    def _draw_selection(self, scene, selection, view, projection) -> None:  # noqa: ANN001
        if selection is None:
            return
        polys = _selection_face_polygons(scene, selection)
        if polys:
            self.draw_face_fill_overlays(polygons=polys, color=_SELECTION_FILL_COLOR)
        segs = _selection_edge_segments(scene, selection)
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
        """
        if not polygons:
            return
        if not self._initialized:
            return  # tests may call before initialize_gl; no-op
        if self._current_view_matrix is None or self._current_projection_matrix is None:
            return

        import mapbox_earcut

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

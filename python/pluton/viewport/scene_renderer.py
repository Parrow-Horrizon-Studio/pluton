"""Owns GL resources for the M1 scene: cube + grid + axes.

Lifecycle is driven by QOpenGLWidget:
  initialize_gl() -> first paintGL() call sets up VBOs and shader programs.
  resize(w, h)    -> called from resizeGL.
  render(camera) -> called from paintGL each frame.
"""

from __future__ import annotations

import ctypes
from importlib.resources import files

import numpy as np
from OpenGL import GL

import pluton
from pluton.viewport.camera import Camera


# --- Constants for the scene -----------------------------------------------

_GRID_HALF_EXTENT = 5.0  # meters, so grid is 10x10
_GRID_SPACING = 1.0
_GRID_COLOR = (0.40, 0.40, 0.40)
_GRID_CENTERLINE_COLOR = (0.60, 0.60, 0.60)

_AXIS_LENGTH = 5.0
_AXIS_X_COLOR = (0.90, 0.20, 0.20)
_AXIS_Y_COLOR = (0.20, 0.90, 0.20)
_AXIS_Z_COLOR = (0.20, 0.40, 0.90)

# Phong material + light — hardcoded for M1.
_LIGHT_DIR = (-1.0, +1.0, -2.0)
_LIGHT_COLOR = (1.00, 0.97, 0.92)
_MATERIAL_AMBIENT = (0.15, 0.15, 0.17)
_MATERIAL_DIFFUSE = (0.65, 0.65, 0.70)
_MATERIAL_SPECULAR = (0.10, 0.10, 0.10)
_MATERIAL_SHININESS = 16.0

_BG_COLOR = (0.15, 0.15, 0.18, 1.0)


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


class SceneRenderer:
    """Owns GL resources for the cube + grid + axes scene."""

    def __init__(self) -> None:
        self._initialized = False
        # Programs
        self._phong_program: int = 0
        self._line_program: int = 0
        # Cube buffers
        self._cube_vao: int = 0
        self._cube_position_vbo: int = 0
        self._cube_normal_vbo: int = 0
        self._cube_ibo: int = 0
        self._cube_index_count: int = 0
        # Grid + axes buffers
        self._grid_vao: int = 0
        self._grid_vbo: int = 0
        self._grid_vertex_count: int = 0
        self._axes_vao: int = 0
        self._axes_vbo: int = 0
        self._axes_vertex_count: int = 0

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

        self._init_cube_buffers()
        self._init_grid_buffers()
        self._init_axes_buffers()

        self._initialized = True

    def resize(self, w: int, h: int) -> None:
        # Skip the GL call if initialize_gl hasn't run yet (e.g., tests that
        # call resizeGL on an unshown widget). glViewport without a current
        # GL context would raise GL_INVALID_OPERATION.
        if not self._initialized:
            return
        GL.glViewport(0, 0, w, h)

    def render(self, camera: Camera) -> None:
        if not self._initialized:
            return
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        view = camera.view_matrix()
        projection = camera.projection_matrix()
        model = np.eye(4, dtype=np.float32)  # cube model matrix is identity

        # Draw grid + axes first so they don't z-fight on top of the cube.
        self._draw_lines(self._grid_vao, self._grid_vertex_count, view, projection)
        self._draw_lines(self._axes_vao, self._axes_vertex_count, view, projection)
        self._draw_cube(view, projection, model, camera.position)

    # --- Init helpers -----------------------------------------------------

    def _init_cube_buffers(self) -> None:
        mesh = pluton.make_cube(1.0)
        positions = np.ascontiguousarray(mesh.positions, dtype=np.float32)
        normals = np.ascontiguousarray(mesh.normals, dtype=np.float32)
        indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32)
        self._cube_index_count = int(indices.size)

        self._cube_vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._cube_vao)

        self._cube_position_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._cube_position_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, positions.nbytes, positions, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self._cube_normal_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._cube_normal_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, normals.nbytes, normals, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self._cube_ibo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self._cube_ibo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)

        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)

    def _init_grid_buffers(self) -> None:
        verts = _build_grid_vertex_array()
        self._grid_vertex_count = int(verts.shape[0])
        self._grid_vao, self._grid_vbo = self._upload_interleaved_lines(verts)

    def _init_axes_buffers(self) -> None:
        verts = _build_axes_vertex_array()
        self._axes_vertex_count = int(verts.shape[0])
        self._axes_vao, self._axes_vbo = self._upload_interleaved_lines(verts)

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
        _set_mat4(self._line_program, "u_view", view)
        _set_mat4(self._line_program, "u_projection", projection)
        GL.glBindVertexArray(vao)
        GL.glDrawArrays(GL.GL_LINES, 0, count)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _draw_cube(
        self,
        view: np.ndarray,
        projection: np.ndarray,
        model: np.ndarray,
        camera_pos: np.ndarray,
    ) -> None:
        GL.glUseProgram(self._phong_program)
        _set_mat4(self._phong_program, "u_view", view)
        _set_mat4(self._phong_program, "u_projection", projection)
        _set_mat4(self._phong_program, "u_model", model)
        _set_vec3(self._phong_program, "u_camera_pos", camera_pos)
        _set_vec3(self._phong_program, "u_light_dir", _LIGHT_DIR)
        _set_vec3(self._phong_program, "u_light_color", _LIGHT_COLOR)
        _set_vec3(self._phong_program, "u_material_ambient", _MATERIAL_AMBIENT)
        _set_vec3(self._phong_program, "u_material_diffuse", _MATERIAL_DIFFUSE)
        _set_vec3(self._phong_program, "u_material_specular", _MATERIAL_SPECULAR)
        _set_float(self._phong_program, "u_material_shininess", _MATERIAL_SHININESS)

        GL.glBindVertexArray(self._cube_vao)
        GL.glDrawElements(GL.GL_TRIANGLES, self._cube_index_count, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)


# --- Uniform helpers --------------------------------------------------------

def _set_mat4(program: int, name: str, m: np.ndarray) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    # GLSL is column-major; numpy is row-major. Transpose flag handles it.
    GL.glUniformMatrix4fv(loc, 1, GL.GL_TRUE, np.ascontiguousarray(m, dtype=np.float32))


def _set_vec3(program: int, name: str, v) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    arr = np.asarray(v, dtype=np.float32)
    GL.glUniform3f(loc, float(arr[0]), float(arr[1]), float(arr[2]))


def _set_float(program: int, name: str, x: float) -> None:
    loc = GL.glGetUniformLocation(program, name)
    if loc < 0:
        return
    GL.glUniform1f(loc, float(x))

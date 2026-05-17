"""The 3D viewport widget — a QOpenGLWidget that draws via raw OpenGL.

For M0 this draws a single static triangle to verify the rendering pipeline.
In M1 this will be replaced with ModernGL-based rendering through a swappable
Renderer abstraction.
"""

import ctypes
from array import array

from OpenGL import GL
from PySide6.QtOpenGLWidgets import QOpenGLWidget


VERTEX_SHADER_SRC = """
#version 330 core

layout(location = 0) in vec2 in_position;
layout(location = 1) in vec3 in_color;

out vec3 v_color;

void main() {
    v_color = in_color;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_SRC = """
#version 330 core

in vec3 v_color;
out vec4 frag_color;

void main() {
    frag_color = vec4(v_color, 1.0);
}
"""

# Triangle vertices: (x, y, r, g, b) per vertex
TRIANGLE_VERTICES = array("f", [
    # x      y      r     g     b
     0.0,   0.6,   1.0,  0.0,  0.0,   # top vertex (red)
    -0.6,  -0.4,   0.0,  1.0,  0.0,   # bottom-left (green)
     0.6,  -0.4,   0.0,  0.0,  1.0,   # bottom-right (blue)
])


class ViewportWidget(QOpenGLWidget):
    """An OpenGL viewport. For M0, draws a static triangle."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._program: int = 0
        self._vao: int = 0
        self._vbo: int = 0

    def initializeGL(self) -> None:
        """Called once when the GL context is first created."""
        self._program = _compile_shader_program(VERTEX_SHADER_SRC, FRAGMENT_SHADER_SRC)
        self._vao, self._vbo = _create_triangle_buffers()
        GL.glClearColor(0.15, 0.15, 0.18, 1.0)

    def resizeGL(self, w: int, h: int) -> None:
        """Called when the widget is resized."""
        GL.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        """Called each frame to redraw."""
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glUseProgram(self._program)
        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)


def _compile_shader_program(vertex_src: str, fragment_src: str) -> int:
    """Compile a shader program from vertex and fragment sources.

    Raises RuntimeError if compilation or linking fails.
    """
    vertex_shader = _compile_shader(vertex_src, GL.GL_VERTEX_SHADER)
    fragment_shader = _compile_shader(fragment_src, GL.GL_FRAGMENT_SHADER)

    program = GL.glCreateProgram()
    GL.glAttachShader(program, vertex_shader)
    GL.glAttachShader(program, fragment_shader)
    GL.glLinkProgram(program)

    link_status = GL.glGetProgramiv(program, GL.GL_LINK_STATUS)
    if not link_status:
        log = GL.glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(f"Shader program link failed:\n{log}")

    GL.glDeleteShader(vertex_shader)
    GL.glDeleteShader(fragment_shader)
    return program


def _compile_shader(source: str, shader_type: int) -> int:
    """Compile a single shader. Raises RuntimeError on failure."""
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)

    compile_status = GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS)
    if not compile_status:
        log = GL.glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
        kind = "vertex" if shader_type == GL.GL_VERTEX_SHADER else "fragment"
        raise RuntimeError(f"{kind} shader compile failed:\n{log}")
    return shader


def _create_triangle_buffers() -> tuple[int, int]:
    """Create the VAO and VBO containing the triangle. Returns (vao, vbo)."""
    vao = GL.glGenVertexArrays(1)
    GL.glBindVertexArray(vao)

    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    GL.glBufferData(
        GL.GL_ARRAY_BUFFER,
        TRIANGLE_VERTICES.tobytes(),
        GL.GL_STATIC_DRAW,
    )

    stride = 5 * ctypes.sizeof(ctypes.c_float)  # 5 floats per vertex
    # Attribute 0: position (vec2)
    GL.glEnableVertexAttribArray(0)
    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
    # Attribute 1: color (vec3), offset by 2 floats
    GL.glEnableVertexAttribArray(1)
    GL.glVertexAttribPointer(
        1, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
        ctypes.c_void_p(2 * ctypes.sizeof(ctypes.c_float)),
    )

    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
    GL.glBindVertexArray(0)
    return vao, vbo

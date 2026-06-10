"""M3c PushPullTool: end-to-end closed-manifold extrusion (Case 1 + Case 2)."""

from __future__ import annotations

import numpy as np

from pluton.commands.command_stack import CommandStack
from pluton.scene.scene import Scene
from pluton.tools.push_pull_tool import PushPullTool


def _draw_rectangle(scene: Scene, w: float = 1.0, h: float = 1.0) -> int:
    """Draw a w×h rectangle on the ground plane (z=0), return the face id."""
    v0 = scene.add_vertex(np.array([0, 0, 0], dtype=np.float32))
    v1 = scene.add_vertex(np.array([w, 0, 0], dtype=np.float32))
    v2 = scene.add_vertex(np.array([w, h, 0], dtype=np.float32))
    v3 = scene.add_vertex(np.array([0, h, 0], dtype=np.float32))
    scene.add_edge(v0, v1)
    scene.add_edge(v1, v2)
    scene.add_edge(v2, v3)
    scene.add_edge(v3, v0)
    return scene.add_face_from_loop([v0, v1, v2, v3])


def _draw_pentagon(scene: Scene) -> int:
    """Draw a regular pentagon centred at origin on z=0, return the face id."""
    import math

    verts = []
    for i in range(5):
        a = 2 * math.pi * i / 5
        v = scene.add_vertex(np.array([math.cos(a), math.sin(a), 0], dtype=np.float32))
        verts.append(v)
    for i in range(5):
        scene.add_edge(verts[i], verts[(i + 1) % 5])
    return scene.add_face_from_loop(verts)


def _commit_pp_directly(scene: Scene, face_id: int, depth: float) -> CommandStack:
    """Skip the click-move-click state machine: directly invoke _commit_extrusion
    with armed-face state populated, simulating a user gesture."""
    tool = PushPullTool()
    stack = CommandStack()
    tool._scene = scene
    tool._command_stack = stack
    tool._armed_face_id = face_id
    tool._armed_face_loop = list(scene.face(face_id).loop_vertex_ids)
    tool._armed_face_normal = scene.face_normal(face_id)
    tool._armed_face_center = scene.face_center(face_id)
    tool._current_depth = depth
    tool._commit_extrusion()
    return stack


# ---- Case 1 — standalone source produces closed manifold ------------------

def test_case1_standalone_rect_produces_closed_prism():
    """P/P on a standalone rectangle → 6 faces total (4 sides + top + bottom)."""
    scene = Scene()
    f = _draw_rectangle(scene)
    _commit_pp_directly(scene, f, depth=2.0)

    live_face_count = sum(1 for _ in scene.faces_iter())
    assert live_face_count == 6


def test_case1_bottom_face_normal_points_down():
    """Bottom cap's normal must oppose the extrusion direction. Else
    backface culling, lighting, and pickability all break — exactly the
    regression that surfaced in M3b without a normal-direction check."""
    scene = Scene()
    f_src = _draw_rectangle(scene)
    src_normal = scene.face_normal(f_src).copy()  # before removal
    _commit_pp_directly(scene, f_src, depth=1.5)

    # Find the bottom face — it's the one whose normal opposes src_normal.
    bottoms = [
        f
        for f in scene.faces_iter()
        if float(np.dot(scene.face_normal(f.id), src_normal)) < 0
    ]
    assert len(bottoms) == 1, "Expected exactly one face with normal opposing src"


def test_case1_pentagon_source_produces_7_faces():
    """N-gon source → N+2 faces (N sides + top + bottom)."""
    scene = Scene()
    f = _draw_pentagon(scene)
    _commit_pp_directly(scene, f, depth=0.5)

    assert sum(1 for _ in scene.faces_iter()) == 7

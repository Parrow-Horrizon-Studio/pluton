"""Tests for selection picking (pure screen-space)."""

from __future__ import annotations

import numpy as np


def _camera(w, h):
    from pluton.viewport.camera import Camera

    cam = Camera()
    cam.aspect = float(w) / float(h)
    return cam


def test_pick_returns_edge_near_its_screen_projection():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    e = scene.add_edge(a, b)

    mid = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    sx, sy, _ = cam.world_to_screen(mid, w, h)
    hit = pick_selectable((sx, sy), (w, h), cam, scene)
    assert hit == ("edge", e)


def test_pick_far_from_everything_is_none():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, 0.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    scene.add_edge(a, b)
    hit = pick_selectable((2.0, 2.0), (w, h), cam, scene)
    assert hit is None


def test_pick_prefers_edge_over_face_behind_it():
    from pluton.scene import Scene
    from pluton.viewport.picking import pick_selectable

    w, h = 800, 600
    cam = _camera(w, h)
    scene = Scene()
    a = scene.add_vertex(np.array([-1.0, -1.0, 0.0], dtype=np.float32))
    b = scene.add_vertex(np.array([1.0, -1.0, 0.0], dtype=np.float32))
    c = scene.add_vertex(np.array([1.0, 1.0, 0.0], dtype=np.float32))
    d = scene.add_vertex(np.array([-1.0, 1.0, 0.0], dtype=np.float32))
    fid = scene.add_face_from_loop((a, b, c, d))

    mid_ab = np.array([0.0, -1.0, 0.0], dtype=np.float32)
    sx, sy, _ = cam.world_to_screen(mid_ab, w, h)
    hit = pick_selectable((sx, sy), (w, h), cam, scene)
    assert hit[0] == "edge"

    center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    cx, cy, _ = cam.world_to_screen(center, w, h)
    hit2 = pick_selectable((cx, cy), (w, h), cam, scene)
    assert hit2 == ("face", fid)

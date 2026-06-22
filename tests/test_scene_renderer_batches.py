from __future__ import annotations

import numpy as np
from pluton.scene.scene import Scene
from pluton.viewport.face_batches import plan_face_batches


def _two_face_scene():
    s = Scene()
    a = [
        s.add_vertex(np.array([0.0, 0.0, 0.0])),
        s.add_vertex(np.array([1.0, 0.0, 0.0])),
        s.add_vertex(np.array([0.0, 1.0, 0.0])),
    ]
    fa = s.add_face_from_loop(a)
    b = [a[1], s.add_vertex(np.array([1.0, 1.0, 0.0])), a[2]]
    fb = s.add_face_from_loop(b)
    return s, fa, fb


def test_unpainted_scene_yields_single_default_batch():
    s, _, _ = _two_face_scene()
    order, batches = plan_face_batches(s.face_triangle_materials())
    assert len(batches) == 1
    assert batches[0].material_id == 0
    assert batches[0].first == 0
    # identity reorder => byte-identical draw path
    assert order.tolist() == list(range(order.shape[0]))


def test_painted_scene_splits_into_per_material_batches():
    s, _fa, fb = _two_face_scene()
    s.set_face_material(fb, 7)
    order, batches = plan_face_batches(s.face_triangle_materials())
    assert [b.material_id for b in batches] == [0, 7]
    assert sum(b.count for b in batches) * 1 == order.shape[0]

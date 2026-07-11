from __future__ import annotations

import numpy as np
from pluton.io.gltf_export import export_gltf
from pluton.io.gltf_import import build_gltf_into_model, read_gltf_scene
from pluton.model.model import Model


def _up_quad_model():
    model = Model()
    mesh = model.root.mesh
    ids = [
        mesh.add_vertex(np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 0.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([1.0, 1.0, 1.0], dtype=np.float32)),
        mesh.add_vertex(np.array([0.0, 1.0, 1.0], dtype=np.float32)),
    ]
    fid = mesh.add_face_from_loop(ids)
    red = model.materials.add_custom("Red", (1.0, 0.0, 0.0))
    mesh.set_face_material(fid, red.id)
    return model


def test_glb_roundtrip_preserves_geometry_orientation_and_color(tmp_path):
    export_gltf(_up_quad_model(), str(tmp_path / "rt.glb"))
    scene = read_gltf_scene(str(tmp_path / "rt.glb"))
    assert len(scene.meshes) >= 1
    assert any(m.color == (1.0, 0.0, 0.0) or np.allclose(m.color, (1.0, 0.0, 0.0), atol=1e-4)
               for m in scene.materials)

    # Rebuild into a fresh model; the up face must land back on Pluton z ~ 1.
    model = Model()
    build_gltf_into_model(scene, model, model.active_context)
    zs = [w @ np.append(v.position, 1.0)
          for d, w in model.traverse()
          for v in d.mesh.vertices_iter()]
    assert zs, "no vertices imported"
    assert max(pt[2] for pt in zs) > 0.9        # up preserved (Z-up)


def test_gltf_roundtrip_writes_and_reads(tmp_path):
    export_gltf(_up_quad_model(), str(tmp_path / "rt.gltf"))
    scene = read_gltf_scene(str(tmp_path / "rt.gltf"))
    assert len(scene.meshes) >= 1

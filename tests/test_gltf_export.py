from __future__ import annotations

import struct

import numpy as np
from pluton.io.gltf_export import export_gltf, model_to_gltf
from pluton.model.model import Model


def _painted_quad_model():
    """A model with one quad face at Pluton z=1 (up), painted red."""
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


def test_model_to_gltf_has_mesh_material_and_root():
    asset = model_to_gltf(_painted_quad_model())
    assert len(asset.meshes) == 1
    assert len(asset.scene_roots) == 1
    assert len(asset.materials) == 1
    assert asset.materials[0]["pbrMetallicRoughness"]["baseColorFactor"] == [1.0, 0.0, 0.0, 1.0]
    # a quad -> 2 triangles -> 6 indices in the (single-material) primitive
    prim = asset.meshes[0]["primitives"][0]
    idx_acc = asset.accessors[prim["indices"]]
    assert idx_acc["count"] == 6


def test_root_matrix_is_zup_to_yup_column_major():
    asset = model_to_gltf(_painted_quad_model())
    root = asset.nodes[asset.scene_roots[0]]
    m = np.array(root["matrix"], dtype=np.float64).reshape(4, 4, order="F")  # column-major
    # Z-up point (0,0,1) -> Y-up (0,1,0)
    assert np.allclose((m @ np.array([0.0, 0.0, 1.0, 1.0]))[:3], [0.0, 1.0, 0.0], atol=1e-6)


def test_export_glb_writes_magic(tmp_path):
    p = tmp_path / "out.glb"
    export_gltf(_painted_quad_model(), str(p))
    data = p.read_bytes()
    assert struct.unpack_from("<I", data, 0)[0] == 0x46546C67


def test_export_gltf_writes_sidecar_bin(tmp_path):
    p = tmp_path / "out.gltf"
    export_gltf(_painted_quad_model(), str(p))
    assert p.exists()
    assert (tmp_path / "out.bin").exists()

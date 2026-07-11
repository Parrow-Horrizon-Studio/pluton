"""End-to-end glTF bridge integration (needs the compiled kernel + Assimp).

Includes the PERMANENT Draco CI gate — do NOT add skip/xfail markers here. If
a vcpkg assimp bump drops Draco, this must fail CI rather than degrade silently.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pluton._core as core
from pluton.io.gltf_export import export_gltf
from pluton.model.model import Model

DATA = Path(__file__).parent / "data" / "gltf"


def test_plain_box_decodes():
    s = core.import_gltf(str(DATA / "plain_box.glb"))
    assert len(s.meshes) >= 1
    assert len(s.meshes[0].triangles) > 0


def test_draco_box_decodes_CI_GATE():  # noqa: N802 (name is the permanent CI gate marker)
    """PERMANENT GATE: Assimp must decode KHR_draco_mesh_compression. Never skip."""
    s = core.import_gltf(str(DATA / "draco_box.glb"))
    assert len(s.meshes) >= 1
    assert len(s.meshes[0].triangles) > 0, "Draco decode produced no geometry"


def _shared_component_model():
    """A model with one component instanced twice (mesh-level instancing)."""
    model = Model()
    comp = model.new_definition("Widget", is_group=False)
    ids = [
        comp.mesh.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        comp.mesh.add_vertex(np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        comp.mesh.add_vertex(np.array([0.0, 1.0, 0.0], dtype=np.float32)),
    ]
    comp.mesh.add_face_from_loop(ids)
    i1 = model.new_instance(comp)
    i2 = model.new_instance(comp, transform=np.eye(4, dtype=np.float64))
    model.root.children.extend([i1, i2])
    return model


def test_export_preserves_mesh_level_instancing(tmp_path):
    export_gltf(_shared_component_model(), str(tmp_path / "inst.glb"))
    s = core.import_gltf(str(tmp_path / "inst.glb"))
    # one shared mesh, referenced by two nodes
    mesh_refs = [n for n in s.nodes if len(n.mesh_indices) > 0]
    used = {mi for n in s.nodes for mi in n.mesh_indices}
    assert len(used) == 1                      # exactly one distinct mesh
    assert len(mesh_refs) == 2                 # referenced by two nodes


def test_gltf_sidecar_roundtrips(tmp_path):
    export_gltf(_shared_component_model(), str(tmp_path / "h.gltf"))
    assert (tmp_path / "h.bin").exists()
    s = core.import_gltf(str(tmp_path / "h.gltf"))
    assert len(s.meshes) >= 1

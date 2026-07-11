"""glTF export: Model -> GltfAsset mapping + atomic filesystem write (M6c).

Mirrors the import mapping: shared Definitions -> one shared glTF mesh
(mesh-level instancing), each Instance -> a glTF node with its transform,
n-gon faces fan-triangulated and grouped by material into primitives, and a
Z-up -> Y-up conversion baked at the export root. This is the only glTF export
module that knows about Model/Scene.
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from pluton.io.gltf_codec import GltfAsset


def _zup_to_yup() -> np.ndarray:
    """Rx(-90°): Pluton Z-up -> glTF Y-up. (x, y, z) -> (x, z, -y)."""
    return np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 1.0, 0.0],
         [0.0, -1.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _definition_primitives(defn, gltf_material_for):
    """Fan-triangulate the definition's faces, grouped by material into
    (positions, indices, gltf_material_index|None) primitives."""
    mesh = defn.mesh
    verts = list(mesh.vertices_iter())
    if not verts:
        return []
    idmap: dict = {}
    positions: list = []
    for v in verts:
        idmap[v.id] = len(positions)
        positions.append((float(v.position[0]), float(v.position[1]), float(v.position[2])))
    by_mat: dict = defaultdict(list)
    for f in mesh.faces_iter():
        loop = [idmap[vid] for vid in f.loop_vertex_ids]
        if len(loop) < 3:
            continue
        gmat = gltf_material_for(mesh.face_material(f.id))
        for k in range(1, len(loop) - 1):        # fan
            by_mat[gmat].extend([loop[0], loop[k], loop[k + 1]])
    return [(positions, indices, gmat) for gmat, indices in by_mat.items()]


def model_to_gltf(model) -> GltfAsset:
    asset = GltfAsset()
    default_id = model.materials.DEFAULT_ID
    mat_index: dict = {}
    mesh_index: dict = {}

    def gltf_material_for(mid):
        if mid == default_id:
            return None
        if mid not in mat_index:
            m = model.materials.get(mid)
            mat_index[mid] = asset.add_material(m.name, m.color)
        return mat_index[mid]

    def mesh_for(defn):
        if defn.id in mesh_index:
            return mesh_index[defn.id]
        prims = _definition_primitives(defn, gltf_material_for)
        if not prims:
            return None
        idx = asset.add_mesh(prims)
        mesh_index[defn.id] = idx
        return idx

    def emit(inst):
        defn = inst.definition
        m = mesh_for(defn)
        children = [emit(child) for child in defn.children]
        matrix = np.asarray(inst.transform, dtype=np.float64).flatten(order="F")
        return asset.add_node(name=defn.name, matrix=matrix, mesh=m,
                              children=children or None)

    root_mesh = mesh_for(model.root)
    root_children = [emit(inst) for inst in model.root.children]
    root_node = asset.add_node(
        name="Pluton",
        matrix=_zup_to_yup().flatten(order="F"),
        mesh=root_mesh,
        children=root_children or None,
    )
    asset.scene_roots.append(root_node)
    return asset


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def export_gltf(model, path) -> None:
    """Write the whole model to `path`. `.gltf` -> JSON + a sibling `.bin`;
    any other suffix (incl. `.glb`) -> a single binary GLB. Atomic writes."""
    path = Path(path)
    asset = model_to_gltf(model)
    if path.suffix.lower() == ".gltf":
        bin_name = path.stem + ".bin"
        json_text, bin_bytes = asset.write_gltf(bin_name)
        _atomic_write_bytes(path, json_text.encode("utf-8"))
        _atomic_write_bytes(path.with_name(bin_name), bin_bytes)
    else:
        _atomic_write_bytes(path, asset.write_glb())

"""glTF import: bridge adapter + model builder (M6c).

read_gltf_scene adapts the _core.import_gltf bridge into the neutral IR;
build_gltf_into_model (Tasks 4-5) maps the IR into the Model. This is the only
glTF module that imports Model/Scene.
"""
from __future__ import annotations

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.io.gltf_scene import GltfMaterial, GltfMesh, GltfNode, GltfSceneData


def read_gltf_scene(path) -> GltfSceneData:
    """Read a .glb/.gltf via the Assimp bridge into a GltfSceneData.

    Raises PlutonFormatError if the file cannot be decoded. OSError from a
    genuinely missing/unreadable path propagates.
    """
    import pluton._core as core

    try:
        raw = core.import_gltf(str(path))
    except RuntimeError as e:  # bridge raises std::runtime_error -> RuntimeError
        raise PlutonFormatError(f"Could not import glTF: {e}") from e

    materials = tuple(
        GltfMaterial(name=m.name, color=(m.base_color[0], m.base_color[1], m.base_color[2]))
        for m in raw.materials
    )
    meshes = tuple(
        GltfMesh(
            positions=tuple((p[0], p[1], p[2]) for p in m.positions),
            triangles=tuple((t[0], t[1], t[2]) for t in m.triangles),
            material_index=m.material_index,
        )
        for m in raw.meshes
    )
    nodes = tuple(
        GltfNode(
            name=n.name,
            parent=n.parent,
            transform=tuple(n.transform),
            mesh_indices=tuple(n.mesh_indices),
        )
        for n in raw.nodes
    )
    return GltfSceneData(nodes=nodes, meshes=meshes, materials=materials)


_DEFAULT_MATERIAL_NAMES = {"", "DefaultMaterial"}


def _is_default_material(m) -> bool:
    return m.name in _DEFAULT_MATERIAL_NAMES


def _ensure_gltf_materials(materials, model) -> list:
    """Material id per glTF material index (None for default/unpainted). Real
    materials deduped by (name, color); add_custom otherwise."""
    result: list = []
    existing = {(m.name, tuple(m.color)): m for m in model.materials.materials()}
    for gm in materials:
        if _is_default_material(gm):
            result.append(None)
            continue
        key = (gm.name, tuple(gm.color))
        m = existing.get(key)
        if m is not None:
            result.append(m.id)
        else:
            new = model.materials.add_custom(gm.name, tuple(gm.color))
            existing[key] = new
            result.append(new.id)
    return result


def _add_triangles(mesh, triangles, localmap, material_id) -> tuple[int, int]:
    """Best-effort: build each triangle, skipping+counting kernel rejects."""
    imported = skipped = 0
    for tri in triangles:
        try:
            loop = [localmap[gi] for gi in tri]
            if len(set(loop)) < 3:
                skipped += 1
                continue
            fid = mesh.add_face_from_loop(loop)
        except (KeyError, ValueError, IndexError, RuntimeError):
            skipped += 1
            continue
        if material_id is not None:
            mesh.set_face_material(fid, material_id)
        imported += 1
    return imported, skipped


def _build_mesh_components(scene, model, mat_id_by_index):
    """Build each GltfMesh into a shared Component Definition (built once, later
    instanced). Returns (meshdefs, imported, skipped, built). meshdefs[i] is a
    Definition or None (empty or all-faces-skipped mesh)."""
    meshdefs: list = []
    imported = skipped = built = 0
    for i, gmesh in enumerate(scene.meshes):
        if not gmesh.positions:
            meshdefs.append(None)
            continue
        defn = model.new_definition(f"Mesh.{i:03d}", is_group=False)
        localmap = {}
        for gi, (x, y, z) in enumerate(gmesh.positions):
            localmap[gi] = defn.mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
        mid = None
        if 0 <= gmesh.material_index < len(mat_id_by_index):
            mid = mat_id_by_index[gmesh.material_index]
        imp, skp = _add_triangles(defn.mesh, gmesh.triangles, localmap, mid)
        imported += imp
        skipped += skp
        if imp == 0:
            meshdefs.append(None)  # unreferenced def is GC'd
            continue
        meshdefs.append(defn)
        built += 1
    return meshdefs, imported, skipped, built

"""glTF import: bridge adapter + model builder (M6c).

read_gltf_scene adapts the _core.import_gltf bridge into the neutral IR;
build_gltf_into_model (Tasks 4-5) maps the IR into the Model. This is the only
glTF module that imports Model/Scene.
"""
from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class GltfImportSummary:
    nodes: int          # glTF nodes mapped (one object each)
    meshes: int         # distinct Component meshes built
    faces_imported: int  # faces built into Component meshes (per distinct mesh)
    faces_skipped: int


@dataclass
class GltfBuildResult:
    summary: GltfImportSummary
    root_instance: object   # the single Instance appended to target_context.children


def _yup_to_zup() -> np.ndarray:
    """Rx(+90°): glTF Y-up -> Pluton Z-up. (x, y, z) -> (x, -z, y)."""
    return np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, -1.0, 0.0],
         [0.0, 1.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def build_gltf_into_model(scene, model, target_context, root_name="glTF") -> GltfBuildResult:
    """Build a GltfSceneData into the model under target_context. Preserves the
    node hierarchy (each node -> one object; single-mesh childless nodes collapse
    to a direct shared-Component instance), converts Y-up -> Z-up at the file
    wrapper, and is best-effort. Returns the single wrapper Instance for undo."""
    mat_id_by_index = _ensure_gltf_materials(scene.materials, model)
    meshdefs, imported, skipped, built = _build_mesh_components(scene, model, mat_id_by_index)

    wrapper = model.new_definition(root_name or "glTF", is_group=True)
    has_children = {n.parent for n in scene.nodes if n.parent >= 0}
    container_def: dict = {}

    for idx, node in enumerate(scene.nodes):
        local = np.array(node.transform, dtype=np.float64).reshape(4, 4)
        mesh_idxs = [mi for mi in node.mesh_indices
                     if 0 <= mi < len(meshdefs) and meshdefs[mi] is not None]
        collapsible = (len(mesh_idxs) == 1) and (idx not in has_children)
        if collapsible:
            inst = model.new_instance(meshdefs[mesh_idxs[0]], transform=local)
        else:
            g = model.new_definition(node.name or "Node", is_group=True)
            for mi in mesh_idxs:
                g.children.append(model.new_instance(meshdefs[mi]))
            inst = model.new_instance(g, transform=local)
            container_def[idx] = g
        parent = wrapper if node.parent == -1 else container_def[node.parent]
        parent.children.append(inst)

    root_instance = model.new_instance(wrapper, transform=_yup_to_zup())
    target_context.children.append(root_instance)

    summary = GltfImportSummary(
        nodes=len(scene.nodes), meshes=built,
        faces_imported=imported, faces_skipped=skipped)
    return GltfBuildResult(summary=summary, root_instance=root_instance)

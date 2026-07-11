"""glTF import: bridge adapter + model builder (M6c).

read_gltf_scene adapts the _core.import_gltf bridge into the neutral IR;
build_gltf_into_model (Tasks 4-5) maps the IR into the Model. This is the only
glTF module that imports Model/Scene.
"""
from __future__ import annotations

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
    except Exception as e:  # bridge raises std::runtime_error -> RuntimeError
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

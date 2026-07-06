"""Pure dict <-> document codec for the native .pluton format (M6a).

No Qt, GL, zip, or filesystem here — just dict <-> in-memory objects, so the
whole round-trip is headlessly unit-testable. Geometry is index-based (edges and
faces reference a vertex's POSITION in `vertices[]`, not its kernel id), which
compacts id gaps and lets load replay add_vertex/add_edge/add_face_from_loop.
"""

from __future__ import annotations

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.scene.scene import Scene

_DEFAULT_MATERIAL_ID = 0  # mirrors MaterialLibrary.DEFAULT_ID


def geometry_to_dict(scene: Scene) -> dict:
    """Serialize a Scene's geometry with index-based edges/faces."""
    idmap: dict[int, int] = {}
    vertices: list[list[float]] = []
    for v in scene.vertices_iter():
        idmap[v.id] = len(vertices)
        vertices.append([float(v.position[0]), float(v.position[1]), float(v.position[2])])

    edges = [[idmap[e.v1_id], idmap[e.v2_id]] for e in scene.edges_iter()]

    faces: list[list[int]] = []
    face_materials: dict[str, int] = {}
    for face_index, f in enumerate(scene.faces_iter()):
        faces.append([idmap[vid] for vid in f.loop_vertex_ids])
        mat = scene.face_material(f.id)
        if mat != _DEFAULT_MATERIAL_ID:
            face_materials[str(face_index)] = int(mat)

    return {"vertices": vertices, "edges": edges, "faces": faces,
            "face_materials": face_materials}


def geometry_from_dict(scene: Scene, data: dict) -> None:
    """Replay geometry into an empty `scene`. Raises PlutonFormatError on bad indices."""
    new_vids: list[int] = []
    for pos in data["vertices"]:
        new_vids.append(scene.add_vertex(np.asarray(pos, dtype=np.float32)))
    n = len(new_vids)

    def _vid(i: int) -> int:
        if not (0 <= i < n):
            raise PlutonFormatError(f"vertex index {i} out of range (0..{n - 1})")
        return new_vids[i]

    for a, b in data["edges"]:
        scene.add_edge(_vid(int(a)), _vid(int(b)))

    new_fids: list[int] = []
    for loop in data["faces"]:
        new_fids.append(scene.add_face_from_loop([_vid(int(i)) for i in loop]))

    for face_index_str, mat in data.get("face_materials", {}).items():
        fi = int(face_index_str)
        if not (0 <= fi < len(new_fids)):
            raise PlutonFormatError(f"face index {fi} out of range (0..{len(new_fids) - 1})")
        scene.set_face_material(new_fids[fi], int(mat))

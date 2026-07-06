"""Pure dict <-> document codec for the native .pluton format (M6a).

No Qt, GL, zip, or filesystem here — just dict <-> in-memory objects, so the
whole round-trip is headlessly unit-testable. Geometry is index-based (edges and
faces reference a vertex's POSITION in `vertices[]`, not its kernel id), which
compacts id gaps and lets load replay add_vertex/add_edge/add_face_from_loop.
"""

from __future__ import annotations

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.model.definition import Definition
from pluton.model.instance import Instance
from pluton.model.model import Model
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


def model_to_dict(model: Model) -> dict:
    """Serialize the scene graph. Definitions reachable from root are emitted once."""
    defs_by_id: dict[int, Definition] = {}
    stack = [model.root]
    while stack:
        d = stack.pop()
        if d.id in defs_by_id:
            continue
        defs_by_id[d.id] = d
        for inst in d.children:
            stack.append(inst.definition)

    definitions = []
    for d in defs_by_id.values():
        definitions.append({
            "id": d.id,
            "name": d.name,
            "is_group": d.is_group,
            "geometry": geometry_to_dict(d.mesh),
            "children": [
                {"id": inst.id,
                 "definition_id": inst.definition.id,
                 "transform": [float(x) for x in inst.transform.flatten()],
                 "tag_id": int(inst.tag_id)}
                for inst in d.children
            ],
        })

    return {
        "next_def_id": model._next_def_id,
        "next_inst_id": model._next_inst_id,
        "root_id": model.root.id,
        "definitions": definitions,
    }


def model_from_dict(data: dict) -> Model:
    """Rebuild a Model (two-pass: skeleton, then geometry + children)."""
    model = Model()  # throwaway root/libraries get replaced below

    # Pass 1: empty definitions, keyed by id.
    defs_by_id: dict[int, Definition] = {}
    for rec in data["definitions"]:
        d = Definition(int(rec["id"]), str(rec["name"]), bool(rec["is_group"]))
        defs_by_id[d.id] = d

    # Pass 2: geometry + child instances.
    for rec in data["definitions"]:
        d = defs_by_id[rec["id"]]
        geometry_from_dict(d.mesh, rec["geometry"])
        for crec in rec["children"]:
            def_id = int(crec["definition_id"])
            if def_id not in defs_by_id:
                raise PlutonFormatError(f"child references unknown definition {def_id}")
            transform = crec["transform"]
            if len(transform) != 16:
                raise PlutonFormatError(f"transform must have 16 numbers, got {len(transform)}")
            inst = Instance(int(crec["id"]), defs_by_id[def_id],
                            np.asarray(transform, dtype=np.float64).reshape(4, 4))
            inst.tag_id = int(crec["tag_id"])
            d.children.append(inst)
            inst.definition.instances.append(inst)

    root_id = int(data["root_id"])
    if root_id not in defs_by_id:
        raise PlutonFormatError(f"root_id {root_id} not found among definitions")
    model.root = defs_by_id[root_id]
    model.active_path = []
    model._next_def_id = int(data["next_def_id"])
    model._next_inst_id = int(data["next_inst_id"])
    return model

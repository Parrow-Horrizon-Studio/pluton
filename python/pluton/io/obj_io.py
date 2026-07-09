"""OBJ filesystem + model mapping (M6b).

export_obj / read_obj_document touch the filesystem; model_to_objdoc and
build_obj_into_model map between the model and the pure ObjDocument IR. This is
the only OBJ module that knows about Model/Scene.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from pluton.io.obj_codec import ObjDocument, ObjFace, ObjObject, sanitize_material_name, write_obj


def _unique_name(base: str, used: set[str]) -> str:
    name = base if base else "object"
    candidate = name
    n = 1
    while candidate in used:
        candidate = f"{name}.{n:03d}"
        n += 1
    used.add(candidate)
    return candidate


def model_to_objdoc(model) -> ObjDocument:  # noqa: ANN001
    """Flatten the scene graph to a world-space ObjDocument (one object per node
    with geometry). Never mutates the model."""
    vertices: list[tuple[float, float, float]] = []
    objects: list[ObjObject] = []
    materials: dict[str, tuple[float, float, float]] = {}
    used_names: set[str] = set()
    default_id = model.materials.DEFAULT_ID

    for definition, world in model.traverse():
        mesh = definition.mesh
        verts = list(mesh.vertices_iter())
        if not verts:
            continue  # skip empty definitions (e.g. an empty root)
        idmap: dict[int, int] = {}
        for v in verts:
            local = np.array([v.position[0], v.position[1], v.position[2], 1.0], dtype=np.float64)
            wp = world @ local
            idmap[v.id] = len(vertices)
            vertices.append((float(wp[0]), float(wp[1]), float(wp[2])))
        faces: list[ObjFace] = []
        for f in mesh.faces_iter():
            loop = tuple(idmap[vid] for vid in f.loop_vertex_ids)
            mat_id = mesh.face_material(f.id)
            if mat_id != default_id:
                mat = model.materials.get(mat_id)
                mname = sanitize_material_name(mat.name)
                materials[mname] = mat.color
                faces.append(ObjFace(loop, mname))
            else:
                faces.append(ObjFace(loop, None))
        objects.append(ObjObject(_unique_name(definition.name, used_names), tuple(faces)))

    return ObjDocument(
        vertices=tuple(vertices),
        objects=tuple(objects),
        materials=materials,
        has_object_tags=bool(objects),
    )


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def export_obj(path, model) -> None:  # noqa: ANN001
    """Write the model to `path` as OBJ, with a sibling `<stem>.mtl` if it has
    painted materials. Each file is written atomically (temp + os.replace)."""
    path = Path(path)
    doc = model_to_objdoc(model)
    mtl_name = path.stem + ".mtl"
    obj_text, mtl_text = write_obj(doc, mtl_name)
    _atomic_write_text(path, obj_text)
    if mtl_text is not None:
        _atomic_write_text(path.with_name(mtl_name), mtl_text)

"""OBJ filesystem + model mapping (M6b).

export_obj / read_obj_document touch the filesystem; model_to_objdoc and
build_obj_into_model map between the model and the pure ObjDocument IR. This is
the only OBJ module that knows about Model/Scene.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pluton.io.obj_codec import (
    ObjDocument,
    ObjFace,
    ObjObject,
    parse_obj,
    sanitize_material_name,
    write_obj,
)


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


def read_obj_document(path) -> ObjDocument:  # noqa: ANN001
    """Read a .obj (and its `mtllib` sidecar, if present next to it) and parse to
    an ObjDocument. Raises PlutonFormatError on malformed content; OSError on a
    missing/unreadable .obj propagates. A missing sidecar .mtl is non-fatal."""
    path = Path(path)
    obj_text = path.read_text(encoding="utf-8")
    mtl_text: str | None = None
    for raw in obj_text.splitlines():
        s = raw.strip()
        if s.startswith("mtllib"):
            parts = s.split()
            if len(parts) > 1:
                mtl_path = path.with_name(parts[1])
                if mtl_path.exists():
                    mtl_text = mtl_path.read_text(encoding="utf-8")
            break
    return parse_obj(obj_text, mtl_text)


@dataclass(frozen=True)
class ImportSummary:
    objects: int          # groups created (0 for the merge case)
    faces_imported: int
    faces_skipped: int


@dataclass
class BuildResult:
    summary: ImportSummary
    created_instances: list          # Instances added to target_context (group case)
    created_geometry: tuple          # (vertex_ids, edge_ids, face_ids) added to the scene (merge)


def _ensure_materials(materials, model) -> dict:  # noqa: ANN001
    """Add each OBJ material to the library, reusing an existing one when name AND
    color already match. Returns name -> material_id."""
    name_to_id: dict[str, int] = {}
    existing = {m.name: m for m in model.materials.materials()}
    for name, color in materials.items():
        m = existing.get(name)
        if m is not None and tuple(m.color) == tuple(color):
            name_to_id[name] = m.id
        else:
            new = model.materials.add_custom(name, color)
            name_to_id[name] = new.id
            existing[new.name] = new
    return name_to_id


def _add_faces(mesh, faces, localmap, name_to_id) -> tuple[int, int]:  # noqa: ANN001
    """Best-effort: build each face, skipping+counting any the kernel rejects
    or any that references an unknown/out-of-range vertex index."""
    imported = skipped = 0
    for face in faces:
        try:
            loop = [localmap[gi] for gi in face.vertex_indices]
            if len(set(loop)) < 3:                       # degenerate: < 3 unique verts
                skipped += 1
                continue
            fid = mesh.add_face_from_loop(loop)
        except (KeyError, ValueError, IndexError, RuntimeError):
            skipped += 1
            continue
        if face.material is not None:
            mid = name_to_id.get(face.material)
            if mid is not None:
                mesh.set_face_material(fid, mid)
        imported += 1
    return imported, skipped


def _snapshot_ids(mesh):  # noqa: ANN001
    return (
        {v.id for v in mesh.vertices_iter()},
        {e.id for e in mesh.edges_iter()},
        {f.id for f in mesh.faces_iter()},
    )


def build_obj_into_model(doc: ObjDocument, model, target_context) -> BuildResult:  # noqa: ANN001
    """Build an ObjDocument into the model. Adaptive: has_object_tags -> one group
    per object in target_context; else merge into target_context.mesh. Best-effort
    face building. Returns the created ids for undo."""
    name_to_id = _ensure_materials(doc.materials, model)

    if doc.has_object_tags:
        created_instances: list = []
        imported = skipped = 0
        for obj in doc.objects:
            used = sorted({gi for f in obj.faces for gi in f.vertex_indices})
            defn = model.new_definition(obj.name or "Imported", is_group=True)
            localmap = {}
            for gi in used:
                x, y, z = doc.vertices[gi]
                localmap[gi] = defn.mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
            i, s = _add_faces(defn.mesh, obj.faces, localmap, name_to_id)
            imported += i
            skipped += s
            inst = model.new_instance(defn)
            target_context.children.append(inst)
            created_instances.append(inst)
        summary = ImportSummary(len(doc.objects), imported, skipped)
        return BuildResult(summary, created_instances, ([], [], []))

    # merge case
    mesh = target_context.mesh
    before = _snapshot_ids(mesh)
    localmap = {}
    for gi, (x, y, z) in enumerate(doc.vertices):
        localmap[gi] = mesh.add_vertex(np.array([x, y, z], dtype=np.float32))
    all_faces = [f for o in doc.objects for f in o.faces]
    imported, skipped = _add_faces(mesh, all_faces, localmap, name_to_id)
    after = _snapshot_ids(mesh)
    created = tuple(sorted(after[i] - before[i]) for i in range(3))  # (vids, eids, fids)
    return BuildResult(ImportSummary(0, imported, skipped), [], created)

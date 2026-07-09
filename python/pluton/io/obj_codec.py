"""Pure OBJ/MTL text <-> ObjDocument IR (M6b).

No Qt, GL, filesystem, or model here — just text <-> a neutral intermediate
representation, so the whole round-trip is headlessly unit-testable. OBJ is a
world-space polygon soup with a shared global vertex pool (`v` global, `f`
references 1-based global indices) + optional `o`/`g` objects + a sidecar `.mtl`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObjFace:
    vertex_indices: tuple[int, ...]      # 0-based, into ObjDocument.vertices
    material: str | None = None          # sanitized material name, or None (unpainted)


@dataclass(frozen=True)
class ObjObject:
    name: str
    faces: tuple[ObjFace, ...]


@dataclass(frozen=True)
class ObjDocument:
    vertices: tuple[tuple[float, float, float], ...]
    objects: tuple[ObjObject, ...]
    materials: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    has_object_tags: bool = False


def sanitize_material_name(name: str) -> str:
    """OBJ names are whitespace-delimited tokens; collapse whitespace to '_'."""
    return "_".join(str(name).split()) or "material"


def write_obj(doc: ObjDocument, mtl_filename: str = "model.mtl") -> tuple[str, str | None]:
    """Serialize an ObjDocument to (obj_text, mtl_text|None). mtl_text is None
    when there are no materials (and no `mtllib` line is written)."""
    obj: list[str] = ["# Pluton OBJ export"]
    if doc.materials:
        obj.append(f"mtllib {mtl_filename}")
    for vx, vy, vz in doc.vertices:
        obj.append(f"v {vx:.6f} {vy:.6f} {vz:.6f}")
    for o in doc.objects:
        obj.append(f"o {o.name}")
        # Sort faces so unpainted (None) come first, then grouped by material,
        # giving clean `usemtl` runs (OBJ has no "unset material" directive).
        faces_sorted = sorted(o.faces, key=lambda f: (f.material is not None, f.material or ""))
        current = None
        for face in faces_sorted:
            if face.material is not None and face.material != current:
                obj.append(f"usemtl {face.material}")
            current = face.material
            obj.append("f " + " ".join(str(i + 1) for i in face.vertex_indices))
    obj_text = "\n".join(obj) + "\n"

    mtl_text: str | None = None
    if doc.materials:
        m: list[str] = ["# Pluton MTL export"]
        for name, (r, g, b) in doc.materials.items():
            m.append(f"newmtl {name}")
            m.append(f"Kd {r:.6f} {g:.6f} {b:.6f}")
            m.append("Ka 0.000000 0.000000 0.000000")
            m.append("Ns 10.000000")
            m.append("d 1.000000")
        mtl_text = "\n".join(m) + "\n"
    return obj_text, mtl_text

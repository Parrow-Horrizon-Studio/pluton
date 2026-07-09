"""Pure OBJ/MTL text <-> ObjDocument IR (M6b).

No Qt, GL, filesystem, or model here — just text <-> a neutral intermediate
representation, so the whole round-trip is headlessly unit-testable. OBJ is a
world-space polygon soup with a shared global vertex pool (`v` global, `f`
references 1-based global indices) + optional `o`/`g` objects + a sidecar `.mtl`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pluton.io.errors import PlutonFormatError


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


def _parse_mtl(mtl_text: str) -> dict[str, tuple[float, float, float]]:
    materials: dict[str, tuple[float, float, float]] = {}
    current: str | None = None
    for raw in mtl_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "newmtl":
            current = " ".join(parts[1:]) if len(parts) > 1 else "material"
            materials.setdefault(current, (0.8, 0.8, 0.8))
        elif parts[0] == "Kd" and current is not None:
            try:
                materials[current] = (float(parts[1]), float(parts[2]), float(parts[3]))
            except (IndexError, ValueError):
                pass  # keep the default grey
    return materials


def parse_obj(obj_text: str, mtl_text: str | None) -> ObjDocument:
    """Parse OBJ (+ optional MTL) text to an ObjDocument. Raises PlutonFormatError
    on a structurally invalid face index."""
    materials = _parse_mtl(mtl_text) if mtl_text else {}
    vertices: list[tuple[float, float, float]] = []
    objects: list[ObjObject] = []
    has_object_tags = False
    current_name: str | None = None
    current_faces: list[ObjFace] = []
    current_material: str | None = None

    def flush() -> None:
        nonlocal current_faces
        if current_faces or current_name is not None:
            name = current_name if current_name is not None else "default"
            objects.append(ObjObject(name=name, faces=tuple(current_faces)))
            current_faces = []

    for raw in obj_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v":
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except (IndexError, ValueError) as e:
                raise PlutonFormatError(f"bad vertex line: {line!r}") from e
        elif tag in ("o", "g"):
            flush()
            has_object_tags = True
            current_name = " ".join(parts[1:]) if len(parts) > 1 else "object"
            current_material = None
        elif tag == "usemtl":
            current_material = parts[1] if len(parts) > 1 else None
        elif tag == "f":
            idx: list[int] = []
            for token in parts[1:]:
                vtok = token.split("/")[0]
                try:
                    vi = int(vtok)
                except ValueError as e:
                    raise PlutonFormatError(f"bad face index {token!r}") from e
                vi = len(vertices) + vi if vi < 0 else vi - 1  # relative or 1-based
                if not (0 <= vi < len(vertices)):
                    raise PlutonFormatError(f"face index out of range: {token!r}")
                idx.append(vi)
            current_faces.append(ObjFace(vertex_indices=tuple(idx), material=current_material))
        # mtllib / vn / vt / s / everything else: ignored
    flush()
    if not objects:
        objects.append(ObjObject(name="default", faces=()))
    return ObjDocument(
        vertices=tuple(vertices),
        objects=tuple(objects),
        materials=materials,
        has_object_tags=has_object_tags,
    )

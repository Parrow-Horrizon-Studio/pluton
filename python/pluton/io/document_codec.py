"""Pure dict <-> document codec for the native .pluton format (M6a).

No Qt, GL, zip, or filesystem here — just dict <-> in-memory objects, so the
whole round-trip is headlessly unit-testable. Geometry is index-based (edges and
faces reference a vertex's POSITION in `vertices[]`, not its kernel id), which
compacts id gaps and lets load replay add_vertex/add_edge/add_face_from_loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.model.annotation import Dimension, Label
from pluton.model.definition import Definition
from pluton.model.instance import Instance
from pluton.model.material import MaterialLibrary
from pluton.model.model import Model
from pluton.model.tag import TagLibrary
from pluton.scene.scene import Scene
from pluton.units import Units, units_from_dict, units_to_dict
from pluton.viewport.render_style import FaceStyle, RenderStyle

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


def annotation_to_dict(ann: Dimension | Label) -> dict:
    """Serialize a Dimension or Label, discriminated by `ann.kind`."""
    if ann.kind == "dimension":
        return {
            "kind": "dimension",
            "id": ann.id,
            "p1": list(ann.p1),
            "p2": list(ann.p2),
            "offset": list(ann.offset),
        }
    return {
        "kind": "label",
        "id": ann.id,
        "anchor": list(ann.anchor),
        "text_pos": list(ann.text_pos),
        "text": ann.text,
    }


def annotation_from_dict(record: dict) -> Dimension | Label:
    """Rebuild the Dimension or Label produced by `annotation_to_dict`.

    Raises PlutonFormatError if 'kind' is missing or unrecognized.
    """
    kind = record.get("kind")
    if kind == "dimension":
        return Dimension(
            record["id"], tuple(record["p1"]), tuple(record["p2"]), tuple(record["offset"])
        )
    if kind == "label":
        return Label(
            record["id"], tuple(record["anchor"]), tuple(record["text_pos"]), record["text"]
        )
    raise PlutonFormatError(f"annotation has unknown kind: {kind!r}")


def model_to_dict(model: Model) -> dict:
    """Serialize the scene graph. Definitions reachable from root are emitted once."""
    # Walks only definitions reachable from root via placed instances — an unplaced
    # / orphan definition would not persist. Fine today (every definition is placed);
    # relevant once a future component browser (M7+) allows library-only definitions.
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
            "annotations": [annotation_to_dict(a) for a in d.annotations],
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
        d.annotations = [annotation_from_dict(r) for r in rec.get("annotations", [])]
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

    max_ann_id = -1
    for d in defs_by_id.values():
        for ann in d.annotations:
            max_ann_id = max(max_ann_id, ann.id)
    model._next_annotation_id = max_ann_id + 1

    return model


def render_style_to_dict(style: RenderStyle) -> dict:
    """Serialize the document's render style (face style name + X-Ray)."""
    return {"face_style": style.face_style.name, "xray": bool(style.xray)}


def render_style_from_dict(d: dict | None) -> RenderStyle:
    """Rebuild a RenderStyle; missing/empty data yields the default (SHADED)."""
    if not d:
        return RenderStyle()
    return RenderStyle(face_style=FaceStyle[d["face_style"]], xray=bool(d.get("xray", False)))


@dataclass(frozen=True)
class CameraState:
    """Snapshot of the viewport Camera's user-facing state (not aspect/near/far,
    which are re-derived from the viewport on load)."""

    position: tuple
    target: tuple
    up: tuple
    fov_y_deg: float

    @classmethod
    def from_camera(cls, cam) -> CameraState:
        return cls(
            position=tuple(float(x) for x in cam.position),
            target=tuple(float(x) for x in cam.target),
            up=tuple(float(x) for x in cam.up),
            fov_y_deg=float(cam.fov_y_deg),
        )

    def to_dict(self) -> dict:
        return {"position": list(self.position), "target": list(self.target),
                "up": list(self.up), "fov_y_deg": self.fov_y_deg}

    @classmethod
    def from_dict(cls, d: dict) -> CameraState:
        return cls(
            position=tuple(float(x) for x in d["position"]),
            target=tuple(float(x) for x in d["target"]),
            up=tuple(float(x) for x in d["up"]),
            fov_y_deg=float(d["fov_y_deg"]),
        )

    def apply_to(self, cam) -> None:
        cam.position = np.array(self.position, dtype=np.float32)
        cam.target = np.array(self.target, dtype=np.float32)
        cam.up = np.array(self.up, dtype=np.float32)
        cam.fov_y_deg = float(self.fov_y_deg)


class LoadedDocument(NamedTuple):
    """Result of loading a .pluton document: model + camera + units + render style."""

    model: Model
    camera_state: CameraState
    units: Units
    style: RenderStyle


def document_to_dict(model: Model, camera, doc, render_style) -> dict:
    """Serialize the top-level document: units, camera, libraries, scenes, style, model."""
    return {
        "units": units_to_dict(doc.units),
        "camera": CameraState.from_camera(camera).to_dict(),
        "materials": {"next_id": model.materials.next_id,
                      "items": model.materials.to_records()},
        "tags": {"next_id": model.tags.next_id, "items": model.tags.to_records()},
        "scenes": {"next_id": model.views.next_id, "items": model.views.to_records()},
        "style": render_style_to_dict(render_style),
        "model": model_to_dict(model),
    }


def document_from_dict(data: dict) -> LoadedDocument:
    """Rebuild a LoadedDocument. Any structural malformation anywhere in the
    document (including in nested geometry/model data) is normalized into
    PlutonFormatError — the only exception callers need to catch."""
    from pluton.views.view_library import ViewLibrary  # function-level: breaks import cycle
    try:
        model = model_from_dict(data["model"])
        model.materials = MaterialLibrary.from_records(
            data["materials"]["items"], data["materials"]["next_id"])
        model.tags = TagLibrary.from_records(
            data["tags"]["items"], data["tags"]["next_id"])
        scenes = data.get("scenes", {})
        model.views = ViewLibrary.from_records(
            scenes.get("items", []), scenes.get("next_id", 0))
        camera_state = CameraState.from_dict(data["camera"])
        units = units_from_dict(data["units"])
        style = render_style_from_dict(data.get("style"))
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise PlutonFormatError(f"malformed document: {e}") from e
    return LoadedDocument(model=model, camera_state=camera_state, units=units, style=style)

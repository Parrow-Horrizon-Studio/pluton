"""glTF import: bridge adapter + model builder (M6c).

read_gltf_scene adapts the _core.import_gltf bridge into the neutral IR;
build_gltf_into_model (Tasks 4-5) maps the IR into the Model. This is the only
glTF module that imports Model/Scene.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pluton.io.errors import PlutonFormatError
from pluton.io.gltf_scene import GltfMaterial, GltfMesh, GltfNode, GltfSceneData

# glTF import is an untrusted-input path (Assimp has a real CVE history): a
# file someone emailed you is a normal thing to import. Everything below runs
# BEFORE the file reaches Assimp, so a hostile file is rejected deterministically
# rather than risking a native crash/hang/OOM (#84).

# On-disk size ceiling. Protects against simply reading/parsing a gigantic
# file (whether or not its *declared* counts are absurd) before Assimp is
# even invoked. Checked via stat(), never by reading the file into memory.
# A few hundred MiB comfortably covers any legitimate architectural asset.
_MAX_GLTF_BYTES = 512 * 1024 * 1024  # 512 MiB

# Ceiling for any declared "how many of these" number in the glTF JSON:
# accessors[].count, and the number of accessors/meshes/primitives. Protects
# against the #84 CVE class where a tiny JSON payload declares an
# astronomical count (e.g. 10**12 vertices) that a naive parser tries to
# honor, driving unbounded allocation in native code. 50M is far beyond any
# real mesh (millions of vertices is already an extreme architectural model)
# while comfortably rejecting hostile counts.
_MAX_ELEMENT_COUNT = 50_000_000

# GLB (binary glTF) container layout: magic + version + total length, then
# one or more length-prefixed chunks; the first chunk is conventionally JSON.
_GLB_MAGIC = b"glTF"
_GLB_HEADER_SIZE = 12
_GLB_CHUNK_HEADER_SIZE = 8
_GLB_JSON_CHUNK_TYPE = b"JSON"


def read_gltf_scene(path) -> GltfSceneData:
    """Read a .glb/.gltf via the Assimp bridge into a GltfSceneData.

    Raises PlutonFormatError if the file cannot be decoded, is larger than
    _MAX_GLTF_BYTES, or declares element counts larger than
    _MAX_ELEMENT_COUNT. OSError from a genuinely missing/unreadable path
    propagates.
    """
    _validate_gltf_file_before_parse(path)

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


def _validate_gltf_file_before_parse(path) -> None:
    """Pre-parse validation that runs before Assimp ever sees the file.

    Checks size first (cheap, no file content read), then for JSON-based
    .gltf files parses and validates the document; for binary .glb files at
    minimum the size ceiling applies, plus a best-effort JSON-chunk check
    when the GLB header is well-formed enough to extract one.
    """
    p = Path(path)
    # os.path.getsize/.stat() reads only filesystem metadata, not file
    # content, so this is cheap even for a maliciously huge file.
    size = p.stat().st_size  # OSError propagates for missing/unreadable path
    if size > _MAX_GLTF_BYTES:
        raise PlutonFormatError(
            f"glTF file is {size} bytes, exceeding the {_MAX_GLTF_BYTES} byte ceiling"
        )

    if p.suffix.lower() == ".glb":
        doc = _read_glb_json_chunk(p)
    else:
        doc = _read_gltf_json(p)

    if doc is not None:
        _validate_gltf_element_counts(doc)


def _read_gltf_json(p: Path) -> dict:
    """Read+parse a .gltf (JSON) file. A truncated or non-JSON file surfaces
    as PlutonFormatError deterministically, rather than being handed to
    Assimp's native parser first."""
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise PlutonFormatError(f"glTF file is not valid UTF-8 text: {e}") from e
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PlutonFormatError(f"glTF file is not valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise PlutonFormatError("glTF file JSON root is not an object")
    return doc


def _read_glb_json_chunk(p: Path) -> dict | None:
    """Best-effort extraction of the JSON chunk from a .glb container.

    Returns None (deferring to Assimp + the existing exception wrapping)
    when the header doesn't look like a well-formed GLB we can safely parse
    ourselves -- we never want our own parsing here to be a *new* source of
    crashes on malformed input.
    """
    with p.open("rb") as f:
        header = f.read(_GLB_HEADER_SIZE)
        if len(header) < _GLB_HEADER_SIZE or header[:4] != _GLB_MAGIC:
            return None
        chunk_header = f.read(_GLB_CHUNK_HEADER_SIZE)
        if len(chunk_header) < _GLB_CHUNK_HEADER_SIZE:
            return None
        chunk_length = int.from_bytes(chunk_header[0:4], "little")
        chunk_type = chunk_header[4:8]
        if chunk_type != _GLB_JSON_CHUNK_TYPE:
            return None
        if chunk_length > _MAX_GLTF_BYTES:
            raise PlutonFormatError(
                f"glTF GLB JSON chunk declares {chunk_length} bytes, "
                f"exceeding the {_MAX_GLTF_BYTES} byte ceiling"
            )
        json_bytes = f.read(chunk_length)
        if len(json_bytes) < chunk_length:
            raise PlutonFormatError("glTF GLB JSON chunk is truncated")

    try:
        doc = json.loads(json_bytes)
    except json.JSONDecodeError as e:
        raise PlutonFormatError(f"glTF GLB JSON chunk is not valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise PlutonFormatError("glTF GLB JSON chunk root is not an object")
    return doc


def _validate_gltf_element_counts(doc: dict) -> None:
    """Reject declared accessor/mesh/primitive counts (and out-of-range
    accessor/bufferView/attribute references) that exceed a sane ceiling,
    before Assimp allocates anything on their behalf. This is the guard for
    the #84 CVE class: a tiny JSON payload can declare an astronomically
    large accessor.count that a parser may try to honor."""
    accessors = doc.get("accessors") or []
    if not isinstance(accessors, list):
        raise PlutonFormatError("glTF 'accessors' is not an array")
    if len(accessors) > _MAX_ELEMENT_COUNT:
        raise PlutonFormatError(
            f"glTF declares {len(accessors)} accessors, exceeding the {_MAX_ELEMENT_COUNT} ceiling"
        )
    buffer_views = doc.get("bufferViews") or []
    for i, accessor in enumerate(accessors):
        if not isinstance(accessor, dict):
            raise PlutonFormatError(f"glTF accessors[{i}] is not an object")
        count = accessor.get("count")
        is_int_count = isinstance(count, int) and not isinstance(count, bool)
        if not (is_int_count and 0 <= count <= _MAX_ELEMENT_COUNT):
            raise PlutonFormatError(
                f"glTF accessors[{i}].count={count!r} exceeds the "
                f"{_MAX_ELEMENT_COUNT} element ceiling"
            )
        buffer_view = accessor.get("bufferView")
        if buffer_view is not None and not (
            isinstance(buffer_view, int) and 0 <= buffer_view < len(buffer_views)
        ):
            raise PlutonFormatError(
                f"glTF accessors[{i}] references out-of-range bufferView {buffer_view!r}"
            )

    meshes = doc.get("meshes") or []
    if not isinstance(meshes, list):
        raise PlutonFormatError("glTF 'meshes' is not an array")
    if len(meshes) > _MAX_ELEMENT_COUNT:
        raise PlutonFormatError(
            f"glTF declares {len(meshes)} meshes, exceeding the {_MAX_ELEMENT_COUNT} ceiling"
        )
    for mi, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise PlutonFormatError(f"glTF meshes[{mi}] is not an object")
        primitives = mesh.get("primitives") or []
        if not isinstance(primitives, list):
            raise PlutonFormatError(f"glTF meshes[{mi}].primitives is not an array")
        if len(primitives) > _MAX_ELEMENT_COUNT:
            raise PlutonFormatError(
                f"glTF meshes[{mi}] declares {len(primitives)} primitives, "
                f"exceeding the {_MAX_ELEMENT_COUNT} ceiling"
            )
        for pi, prim in enumerate(primitives):
            if not isinstance(prim, dict):
                raise PlutonFormatError(f"glTF meshes[{mi}].primitives[{pi}] is not an object")
            attributes = prim.get("attributes") or {}
            for attr_name, accessor_index in attributes.items():
                if not (isinstance(accessor_index, int) and 0 <= accessor_index < len(accessors)):
                    raise PlutonFormatError(
                        f"glTF meshes[{mi}].primitives[{pi}] attribute {attr_name!r} "
                        f"references out-of-range accessor {accessor_index!r}"
                    )
            indices = prim.get("indices")
            if indices is not None and not (
                isinstance(indices, int) and 0 <= indices < len(accessors)
            ):
                raise PlutonFormatError(
                    f"glTF meshes[{mi}].primitives[{pi}] references out-of-range "
                    f"indices accessor {indices!r}"
                )


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
    nodes: int  # glTF nodes mapped (one object each)
    meshes: int  # distinct Component meshes built
    faces_imported: int  # faces built into Component meshes (per distinct mesh)
    faces_skipped: int


@dataclass
class GltfBuildResult:
    summary: GltfImportSummary
    root_instance: object  # the single Instance appended to target_context.children


def _yup_to_zup() -> np.ndarray:
    """Rx(+90°): glTF Y-up -> Pluton Z-up. (x, y, z) -> (x, -z, y)."""
    return np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
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
        mesh_idxs = [
            mi for mi in node.mesh_indices if 0 <= mi < len(meshdefs) and meshdefs[mi] is not None
        ]
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
        nodes=len(scene.nodes), meshes=built, faces_imported=imported, faces_skipped=skipped
    )
    return GltfBuildResult(summary=summary, root_instance=root_instance)

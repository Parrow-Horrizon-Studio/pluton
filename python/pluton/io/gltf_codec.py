"""Pure glTF 2.0 buffer/JSON assembly (M6c export codec).

No Model, no filesystem. Assemble a GltfAsset (nodes/meshes/materials, with
accessors packed into one binary buffer) and serialize to .glb bytes or
(.gltf json, .bin bytes). Positions are VEC3/FLOAT (with min/max); indices are
SCALAR/UNSIGNED_INT. Node matrices are glTF column-major 16-float arrays
(the caller supplies column-major order).
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

_FLOAT = 5126
_UINT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


@dataclass
class GltfAsset:
    _buffer: bytearray = field(default_factory=bytearray)
    accessors: list = field(default_factory=list)
    buffer_views: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    meshes: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    scene_roots: list = field(default_factory=list)

    def add_material(self, name, color) -> int:
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [float(color[0]), float(color[1]), float(color[2]), 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
        })
        return len(self.materials) - 1

    def _add_buffer_view(self, data: bytes, target: int) -> int:
        self._buffer.extend(b"\x00" * _pad4(len(self._buffer)))
        offset = len(self._buffer)
        self._buffer.extend(data)
        self.buffer_views.append({
            "buffer": 0, "byteOffset": offset,
            "byteLength": len(data), "target": target,
        })
        return len(self.buffer_views) - 1

    def _add_position_accessor(self, positions) -> int:
        data = bytearray()
        for x, y, z in positions:
            data += struct.pack("<3f", x, y, z)
        bv = self._add_buffer_view(bytes(data), _ARRAY_BUFFER)
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        self.accessors.append({
            "bufferView": bv, "componentType": _FLOAT, "count": len(positions),
            "type": "VEC3",
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        })
        return len(self.accessors) - 1

    def _add_index_accessor(self, indices) -> int:
        data = struct.pack(f"<{len(indices)}I", *indices)
        bv = self._add_buffer_view(data, _ELEMENT_ARRAY_BUFFER)
        self.accessors.append({
            "bufferView": bv, "componentType": _UINT, "count": len(indices),
            "type": "SCALAR",
        })
        return len(self.accessors) - 1

    def add_mesh(self, primitives) -> int:
        prims = []
        for positions, indices, mat in primitives:
            p = {
                "attributes": {"POSITION": self._add_position_accessor(positions)},
                "indices": self._add_index_accessor(indices),
            }
            if mat is not None:
                p["material"] = mat
            prims.append(p)
        self.meshes.append({"primitives": prims})
        return len(self.meshes) - 1

    def add_node(self, name=None, matrix=None, mesh=None, children=None) -> int:
        node: dict = {}
        if name:
            node["name"] = name
        if matrix is not None:
            node["matrix"] = [float(v) for v in matrix]
        if mesh is not None:
            node["mesh"] = mesh
        if children:
            node["children"] = list(children)
        self.nodes.append(node)
        return len(self.nodes) - 1

    def _json(self, buffer_obj) -> dict:
        doc = {
            "asset": {"version": "2.0", "generator": "Pluton"},
            "scene": 0,
            "scenes": [{"nodes": list(self.scene_roots)}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [buffer_obj],
        }
        if self.materials:
            doc["materials"] = self.materials
        return doc

    def write_glb(self) -> bytes:
        bin_blob = bytes(self._buffer) + b"\x00" * _pad4(len(self._buffer))
        doc = self._json({"byteLength": len(bin_blob)})
        json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * _pad4(len(json_bytes))
        total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
        out = bytearray()
        out += struct.pack("<III", _GLB_MAGIC, 2, total)
        out += struct.pack("<II", len(json_bytes), _CHUNK_JSON) + json_bytes
        out += struct.pack("<II", len(bin_blob), _CHUNK_BIN) + bin_blob
        return bytes(out)

    def write_gltf(self, bin_name: str):
        bin_blob = bytes(self._buffer)
        doc = self._json({"byteLength": len(bin_blob), "uri": bin_name})
        return json.dumps(doc, indent=2), bin_blob

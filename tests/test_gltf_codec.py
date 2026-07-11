from __future__ import annotations

import json
import struct

from pluton.io.gltf_codec import GltfAsset

TRI_POS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
TRI_IDX = [0, 1, 2]
IDENT16 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _parse_glb(blob: bytes):
    magic, version, total = struct.unpack_from("<III", blob, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(blob)
    jlen, jtype = struct.unpack_from("<II", blob, 12)
    assert jtype == 0x4E4F534A
    json_bytes = blob[20:20 + jlen]
    blen, btype = struct.unpack_from("<II", blob, 20 + jlen)
    assert btype == 0x004E4942
    return json.loads(json_bytes), blen


def _asset_with_triangle():
    a = GltfAsset()
    mat = a.add_material("Red", (1.0, 0.0, 0.0))
    mesh = a.add_mesh([(TRI_POS, TRI_IDX, mat)])
    node = a.add_node(name="tri", matrix=IDENT16, mesh=mesh, children=None)
    a.scene_roots.append(node)
    return a


def test_glb_framing_and_structure():
    blob = _asset_with_triangle().write_glb()
    assert len(blob) % 4 == 0
    doc, blen = _parse_glb(blob)
    assert doc["asset"]["version"] == "2.0"
    assert doc["scenes"][0]["nodes"] == [0]
    assert len(doc["meshes"]) == 1
    assert len(doc["materials"]) == 1
    assert doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] == [1.0, 0.0, 0.0, 1.0]
    # POSITION accessor has correct min/max
    pos_acc = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert pos_acc["type"] == "VEC3" and pos_acc["componentType"] == 5126
    assert pos_acc["count"] == 3
    assert pos_acc["min"] == [0.0, 0.0, 0.0] and pos_acc["max"] == [1.0, 1.0, 0.0]
    assert doc["buffers"][0]["byteLength"] == blen


def test_gltf_has_external_buffer_uri():
    a = _asset_with_triangle()
    json_text, bin_bytes = a.write_gltf("model.bin")
    doc = json.loads(json_text)
    assert doc["buffers"][0]["uri"] == "model.bin"
    assert doc["buffers"][0]["byteLength"] == len(bin_bytes)

    glb_doc, _ = _parse_glb(a.write_glb())
    assert "uri" not in glb_doc["buffers"][0]

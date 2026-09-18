"""Regenerate the glTF test fixtures. Run from the repo root:

    .venv/Scripts/python tests/data/gltf/make_fixtures.py

Fixtures are committed, so this only needs running when a recipe changes. It
is committed alongside them so a fixture is never a binary blob nobody can
reproduce or explain.

Every image here is asymmetric under BOTH a horizontal and a vertical flip.
glTF's TEXCOORD_0 origin is the image's upper left and Pluton's v = 0 is the
image's bottom, but the V conversion is deliberately asymmetric (D14): import
performs NO flip, because Assimp's glTF2 importer already applies 1 - v
before the bridge ever sees a coordinate, and export performs ONE flip,
because it writes through Pluton's own gltf_codec rather than through Assimp.
A fixture symmetric under a vertical flip cannot tell a correct flip (or its
absence) from a missing one, on either side of that asymmetry.
"""

from __future__ import annotations

import json
import struct
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).parent

_FLOAT = 5126
_UINT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def _png(width: int, height: int, rows) -> bytes:
    """A minimal RGBA PNG. `rows` is height lists of width (r, g, b, a) tuples."""
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0 (None) for this scanline
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def uvgrid_png() -> bytes:
    """A 4x4 marker image with a unique colour in each corner.

    Top-left is RED, top-right GREEN, bottom-left BLUE, bottom-right WHITE, and
    the interior is black. Any flip, mirror or transpose moves a distinct colour
    to a distinct place, so a test can name which corner it sampled.
    """
    black = (0, 0, 0, 255)
    rows = [[black] * 4 for _ in range(4)]
    rows[0][0] = (255, 0, 0, 255)  # top-left     RED
    rows[0][3] = (0, 255, 0, 255)  # top-right    GREEN
    rows[3][0] = (0, 0, 255, 255)  # bottom-left  BLUE
    rows[3][3] = (255, 255, 255, 255)  # bottom-right WHITE
    return _png(4, 4, rows)


# A unit quad in the XY plane, two triangles, textured from the image. v runs
# 0.25..1.0 rather than the full 0..1 so a missing flip lands the seam
# somewhere a full square could not distinguish.
_QUAD_POSITIONS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
_QUAD_UVS = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.25), (0.0, 0.25)]
_QUAD_INDICES = [0, 1, 2, 0, 2, 3]


def _quad_buffer() -> tuple[bytes, list, list]:
    """The quad's binary blob plus its bufferViews and accessors."""
    pos = b"".join(struct.pack("<3f", *p) for p in _QUAD_POSITIONS)
    uv = b"".join(struct.pack("<2f", *t) for t in _QUAD_UVS)
    idx = struct.pack(f"<{len(_QUAD_INDICES)}I", *_QUAD_INDICES)
    blob = pos + uv + idx  # every part is a multiple of 4 bytes, so no padding
    views = [
        {"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": _ARRAY_BUFFER},
        {"buffer": 0, "byteOffset": len(pos), "byteLength": len(uv), "target": _ARRAY_BUFFER},
        {
            "buffer": 0,
            "byteOffset": len(pos) + len(uv),
            "byteLength": len(idx),
            "target": _ELEMENT_ARRAY_BUFFER,
        },
    ]
    xs = [p[0] for p in _QUAD_POSITIONS]
    ys = [p[1] for p in _QUAD_POSITIONS]
    zs = [p[2] for p in _QUAD_POSITIONS]
    accessors = [
        {
            "bufferView": 0,
            "componentType": _FLOAT,
            "count": len(_QUAD_POSITIONS),
            "type": "VEC3",
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        },
        {"bufferView": 1, "componentType": _FLOAT, "count": len(_QUAD_UVS), "type": "VEC2"},
        {"bufferView": 2, "componentType": _UINT, "count": len(_QUAD_INDICES), "type": "SCALAR"},
    ]
    return blob, views, accessors


def _textured_box_doc(views, accessors, image_entry) -> dict:
    """The shared glTF JSON for both textured_box variants.

    `image_entry` is images[0]: a bufferView reference for the GLB, a uri for
    the .gltf. Everything else is identical, which is the point: the two
    fixtures differ only in where the image lives.
    """
    return {
        "asset": {"version": "2.0", "generator": "Pluton test fixtures"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Quad", "mesh": 0}],
        "meshes": [
            {
                "name": "Quad",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "Grid",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
            }
        ],
        "textures": [{"source": 0}],
        "images": [image_entry],
        "accessors": accessors,
        "bufferViews": views,
    }


def _glb(doc: dict, blob: bytes) -> bytes:
    """Pack a glTF JSON document and its binary chunk into a .glb."""
    bin_blob = blob + b"\x00" * _pad4(len(blob))
    doc = dict(doc)
    doc["buffers"] = [{"byteLength": len(bin_blob)}]
    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * _pad4(len(json_bytes))
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    out = bytearray()
    out += struct.pack("<III", _GLB_MAGIC, 2, total)
    out += struct.pack("<II", len(json_bytes), _CHUNK_JSON) + json_bytes
    out += struct.pack("<II", len(bin_blob), _CHUNK_BIN) + bin_blob
    return bytes(out)


def build_textured_box_glb() -> bytes:
    """The quad with its image EMBEDDED in the buffer. Self-contained."""
    blob, views, accessors = _quad_buffer()
    png = uvgrid_png()
    blob += b"\x00" * _pad4(len(blob))
    views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(png)})
    blob += png
    image = {"name": "uvgrid", "bufferView": len(views) - 1, "mimeType": "image/png"}
    return _glb(_textured_box_doc(views, accessors, image), blob)


def build_textured_box_gltf(bin_name: str) -> tuple[str, bytes]:
    """The same quad with its image referenced as a SIBLING file by uri."""
    blob, views, accessors = _quad_buffer()
    doc = _textured_box_doc(views, accessors, {"name": "uvgrid", "uri": "uvgrid.png"})
    doc["buffers"] = [{"byteLength": len(blob), "uri": bin_name}]
    return json.dumps(doc, indent=2), blob


_AVOCADO_BASE = (
    "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets"
    # Pinned to a commit rather than /main/: the module docstring above and
    # tests/data/gltf/README.md both claim these fixtures are reproducible
    # from this committed recipe, which a moving ref would make false the
    # day upstream edits this path. Confirmed to serve byte-identical
    # Avocado.gltf/Avocado.bin to /main/ as of 2026-09-18.
    "/2c541692872556495b23320527def2268b4c69a5/Models/Avocado/glTF-Draco/"
)


def _fetch(name: str) -> bytes:
    with urllib.request.urlopen(_AVOCADO_BASE + name, timeout=60) as r:
        return r.read()


def build_avocado_draco_glb(fetch=_fetch) -> bytes:
    """Repack Khronos' Draco Avocado as a self-contained GLB with our own image.

    Keeps the Draco-compressed geometry and its TEXCOORD_0 exactly as Khronos
    published them, and replaces the three multi-megabyte PBR maps with the
    single 4x4 uvgrid.png, which is the only one Pluton reads. The result is
    about 12 KB instead of 8 MB.

    extensionsUsed, extensionsRequired and the primitive's
    KHR_draco_mesh_compression block are left untouched: they are what makes
    this asset a Draco gate at all.
    """
    doc = json.loads(fetch("Avocado.gltf"))
    blob = bytearray(fetch("Avocado.bin"))

    png = uvgrid_png()
    blob += b"\x00" * _pad4(len(blob))
    doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(png)})
    blob += png

    doc["images"] = [
        {"name": "uvgrid", "bufferView": len(doc["bufferViews"]) - 1, "mimeType": "image/png"}
    ]
    doc["textures"] = [{"source": 0}]
    doc.pop("samplers", None)

    for material in doc["materials"]:
        pbr = material.get("pbrMetallicRoughness", {})
        material["pbrMetallicRoughness"] = {
            "baseColorTexture": {"index": 0},
            "baseColorFactor": pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0]),
            "metallicFactor": 0.0,
            "roughnessFactor": 1.0,
        }
        for dropped in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            material.pop(dropped, None)

    return _glb(doc, bytes(blob))


def main() -> None:
    (HERE / "uvgrid.png").write_bytes(uvgrid_png())
    (HERE / "textured_box.glb").write_bytes(build_textured_box_glb())
    gltf_text, bin_bytes = build_textured_box_gltf("textured_box.bin")
    (HERE / "textured_box.gltf").write_text(gltf_text, encoding="utf-8")
    (HERE / "textured_box.bin").write_bytes(bin_bytes)
    (HERE / "avocado_draco.glb").write_bytes(build_avocado_draco_glb())
    print("wrote uvgrid.png, textured_box.{glb,gltf,bin}, avocado_draco.glb")


if __name__ == "__main__":
    main()

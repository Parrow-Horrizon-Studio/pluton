"""Hostile-input hardening for glTF import (#84).

glTF import goes through Assimp, which has a real CVE history. Importing a
file someone sent you is a normal thing for an architect to do, so this is an
untrusted-input path. The bar: a malformed file raises PlutonFormatError; it
never crashes the process, hangs, or exhausts memory.
"""

import json

import pytest

from pluton.io.errors import PlutonFormatError


def _import(path):
    from pluton.io import read_gltf_scene  # the real public entry point

    return read_gltf_scene(str(path))


def test_truncated_file_raises_format_error(tmp_path):
    p = tmp_path / "truncated.gltf"
    p.write_text('{"asset": {"version": "2.0"}, "meshes": [')  # cut off mid-JSON
    with pytest.raises(PlutonFormatError):
        _import(p)


def test_absurd_declared_counts_are_rejected(tmp_path):
    doc = {
        "asset": {"version": "2.0"},
        "accessors": [{"componentType": 5126, "count": 10**12, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    p = tmp_path / "huge.gltf"
    p.write_text(json.dumps(doc))
    with pytest.raises(PlutonFormatError):
        _import(p)


def test_not_gltf_at_all_raises_format_error(tmp_path):
    p = tmp_path / "nonsense.gltf"
    p.write_bytes(b"\x00\x01\x02 this is not a gltf file \xff\xfe")
    with pytest.raises(PlutonFormatError):
        _import(p)

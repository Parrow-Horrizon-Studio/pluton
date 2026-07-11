"""Neutral glTF import IR (M6c).

Pure dataclasses mirroring the C++ bridge structs 1:1 — no Model, no _core, no
Assimp. This lets the import-mapping layer be unit-tested with hand-built
fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GltfMaterial:
    name: str
    color: tuple[float, float, float]  # RGB; alpha dropped


@dataclass(frozen=True)
class GltfMesh:
    positions: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    material_index: int  # -1 = none


@dataclass(frozen=True)
class GltfNode:
    name: str
    parent: int  # -1 = root
    transform: tuple[float, ...]  # 16 floats, row-major
    mesh_indices: tuple[int, ...]


@dataclass(frozen=True)
class GltfSceneData:
    nodes: tuple[GltfNode, ...]
    meshes: tuple[GltfMesh, ...]
    materials: tuple[GltfMaterial, ...]

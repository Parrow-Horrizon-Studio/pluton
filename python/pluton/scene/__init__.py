"""Python scene data model: Vertex / Edge / Face / Scene.

Pure-Python topology for M2 drawing. Half-edge structure is deferred to M3,
where push/pull is the first consumer that justifies it (per the M1 design
doc rationale).
"""

from __future__ import annotations

from pluton.scene.edge import Edge
from pluton.scene.face import Face
from pluton.scene.scene import Scene
from pluton.scene.vertex import Vertex

__all__ = ["Edge", "Face", "Scene", "Vertex"]

"""Pluton — polygonal 3D modeler for architecture."""

from pluton._core import Mesh, make_cube, version

__version__ = version()

__all__ = ["Mesh", "__version__", "make_cube", "version"]

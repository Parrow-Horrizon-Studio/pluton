"""Solid-color materials + the per-Model material library (M5b).

Pure Python — no GL, no Qt — so it is fully unit-testable headlessly. A
Material is a named base RGB color; faces reference materials by id (see
Scene._face_materials). The library owns the canonical colors and is
serialization-ready for M6 file I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Material:
    """A named solid-color material. `color` is base RGB in 0..1 (opaque)."""

    id: int
    name: str
    color: tuple[float, float, float]


# The Default swatch color mirrors the renderer's default diffuse
# (scene_renderer._MATERIAL_DIFFUSE). Duplicated as a literal to avoid a
# viewport -> model import; used only for the dock swatch / hover preview,
# never for face shading (the renderer shades the Default batch with
# _DEFAULT_MATERIAL directly).
_DEFAULT_SWATCH_COLOR = (0.65, 0.65, 0.70)

# Built-in palette seeded into every MaterialLibrary (stable ids 1..N).
_BUILTIN_PALETTE: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("White", (0.92, 0.92, 0.92)),
    ("Warm Gray", (0.66, 0.63, 0.60)),
    ("Concrete", (0.74, 0.73, 0.71)),
    ("Brick Red", (0.70, 0.27, 0.22)),
    ("Wood Tan", (0.78, 0.62, 0.40)),
    ("Slate Blue", (0.36, 0.45, 0.60)),
    ("Forest Green", (0.27, 0.50, 0.31)),
    ("Charcoal", (0.22, 0.22, 0.24)),
)


class MaterialLibrary:
    """Owns the model's Material objects: Default first, then builtins, then customs."""

    DEFAULT_ID = 0

    def __init__(self) -> None:
        self._default = Material(self.DEFAULT_ID, "Default", _DEFAULT_SWATCH_COLOR)
        self._materials: dict[int, Material] = {self.DEFAULT_ID: self._default}
        self._order: list[int] = [self.DEFAULT_ID]
        self._next_id = 1
        for name, color in _BUILTIN_PALETTE:
            self._add(name, color)

    def _add(self, name: str, color: tuple[float, float, float]) -> Material:
        mat = Material(self._next_id, name, (float(color[0]), float(color[1]), float(color[2])))
        self._materials[mat.id] = mat
        self._order.append(mat.id)
        self._next_id += 1
        return mat

    def add_custom(self, name: str, color: tuple[float, float, float]) -> Material:
        """Append a new material with a fresh monotonic id and return it."""
        return self._add(name, color)

    def get(self, mid: int) -> Material:
        """Return the material for `mid`, or the Default material if unknown."""
        return self._materials.get(mid, self._default)

    def materials(self) -> list[Material]:
        """All materials in display order (Default first)."""
        return [self._materials[i] for i in self._order]

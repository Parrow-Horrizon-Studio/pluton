"""Material commands (M5b): PaintFaceCommand."""

from __future__ import annotations

from pluton.commands.command import Command

_DEFAULT_MATERIAL_ID = 0  # == MaterialLibrary.DEFAULT_ID (the unpainted sentinel)


def _apply(scene, f_id: int, material_id: int) -> None:  # noqa: ANN001
    if material_id == _DEFAULT_MATERIAL_ID:
        scene.clear_face_material(f_id)
    else:
        scene.set_face_material(f_id, material_id)


class PaintFaceCommand(Command):
    """Assign a material to one face; undo restores the prior material.

    Captures the previous material at do() time (id-preserving undo). Painting
    the Default material (id 0) clears any paint; undo restores it exactly.
    """

    name = "Paint Face"

    def __init__(self, face_id: int, new_material_id: int) -> None:
        self._fid = face_id
        self._new = new_material_id
        self._old: int | None = None

    def do(self, scene) -> None:  # noqa: ANN001
        self._old = scene.face_material(self._fid)
        _apply(scene, self._fid, self._new)

    def undo(self, scene) -> None:  # noqa: ANN001
        _apply(scene, self._fid, self._old if self._old is not None else _DEFAULT_MATERIAL_ID)

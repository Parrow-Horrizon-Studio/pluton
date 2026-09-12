"""Material commands (M7.5a): add, edit, delete, and per-side paint."""

from __future__ import annotations

from pluton.commands.command import Command
from pluton.scene.scene import Side

_DEFAULT_MATERIAL_ID = 0  # == MaterialLibrary.DEFAULT_ID (the unpainted sentinel)


def _apply(scene, f_id: int, material_id: int, side: Side) -> None:
    if material_id == _DEFAULT_MATERIAL_ID:
        scene.clear_face_material(f_id, side)
    else:
        scene.set_face_material(f_id, material_id, side)


class PaintFaceCommand(Command):
    """Assign a material to one side of one face; undo restores the prior one.

    Captures the previous material at do() time (id-preserving undo). Painting
    the Default material (id 0) clears any paint; undo restores it exactly.
    """

    name = "Paint Face"

    def __init__(self, face_id: int, new_material_id: int, side: Side = Side.FRONT) -> None:
        self._fid = face_id
        self._new = new_material_id
        self._side = side
        self._old: int | None = None

    def do(self, scene) -> None:
        self._old = scene.face_material(self._fid, self._side)
        _apply(scene, self._fid, self._new, self._side)

    def undo(self, scene) -> None:
        _apply(
            scene,
            self._fid,
            self._old if self._old is not None else _DEFAULT_MATERIAL_ID,
            self._side,
        )


class AddMaterialCommand(Command):
    """Add a custom material. Undo removes it again."""

    name = "Add Material"

    def __init__(self, library, name: str, base_color: tuple[float, float, float]) -> None:
        self._lib = library
        self._name = name
        self._color = base_color
        self._mid: int | None = None
        self._removed = None

    @property
    def material_id(self) -> int:
        assert self._mid is not None, "material_id read before do()"
        return self._mid

    def do(self, scene) -> None:
        if self._mid is None:
            self._mid = self._lib.add_custom(self._name, self._color).id
        else:
            # redo: put the same record back at the end, preserving its id
            self._lib.restore(self._removed, len(self._lib.materials()))

    def undo(self, scene) -> None:
        self._removed = self._lib.remove(self._mid)


class EditMaterialCommand(Command):
    """Edit any subset of a material's fields; undo restores the whole record."""

    name = "Edit Material"

    def __init__(self, library, material_id: int, **fields) -> None:
        self._lib = library
        self._mid = material_id
        self._fields = fields
        self._before = None

    def do(self, scene) -> None:
        self._before = self._lib.get(self._mid)
        self._lib.edit(self._mid, **self._fields)

    def undo(self, scene) -> None:
        self._lib.edit(
            self._mid,
            name=self._before.name,
            base_color=self._before.base_color,
            alpha=self._before.alpha,
            metallic=self._before.metallic,
            roughness=self._before.roughness,
        )


class DeleteMaterialCommand(Command):
    """Remove a material and repaint every side using it back to Default.

    `affected_count` is readable before do() so the confirmation dialog can
    quote it and the user can still cancel.
    """

    name = "Delete Material"

    def __init__(self, library, material_id: int, scene) -> None:
        if material_id == 0:
            raise ValueError("the Default material cannot be deleted")
        self._lib = library
        self._mid = material_id
        self._affected = scene.faces_with_material(material_id)
        self._record = None
        self._index = -1

    @property
    def affected_count(self) -> int:
        return len(self._affected)

    def do(self, scene) -> None:
        self._index = self._lib.index_of(self._mid)
        self._record = self._lib.remove(self._mid)
        for f_id, side in self._affected:
            scene.clear_face_material(f_id, side)

    def undo(self, scene) -> None:
        self._lib.restore(self._record, self._index)
        for f_id, side in self._affected:
            scene.set_face_material(f_id, self._mid, side)

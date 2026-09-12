"""M7.5a Task 8: material lifecycle under undo."""

from __future__ import annotations

import numpy as np
import pytest
from pluton.commands.material_commands import (
    AddMaterialCommand,
    DeleteMaterialCommand,
    EditMaterialCommand,
    PaintFaceCommand,
)
from pluton.model.material import MaterialLibrary
from pluton.scene.scene import Scene, Side


def _square(scene, z=0.0):
    v = [
        scene.add_vertex(np.array([0.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 0.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([1.0, 1.0, z], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, 1.0, z], dtype=np.float32)),
    ]
    for a, b in zip(v, v[1:] + v[:1], strict=True):
        scene.add_edge(a, b)
    return scene.add_face_from_loop(v)


def test_paint_targets_the_named_side_and_undoes_only_that_side():
    s = Scene()
    f = _square(s)
    s.set_face_material(f, 4, Side.FRONT)
    cmd = PaintFaceCommand(f, 7, Side.BACK)
    cmd.do(s)
    assert s.face_material(f, Side.BACK) == 7
    assert s.face_material(f, Side.FRONT) == 4  # discriminating
    cmd.undo(s)
    assert s.face_material(f, Side.BACK) == 0
    assert s.face_material(f, Side.FRONT) == 4


def test_paint_defaults_to_the_front():
    s = Scene()
    f = _square(s)
    PaintFaceCommand(f, 7).do(s)
    assert s.face_material(f, Side.FRONT) == 7
    assert s.face_material(f, Side.BACK) == 0


def test_add_then_undo_leaves_the_library_as_it_was():
    lib = MaterialLibrary()
    before = [m.id for m in lib.materials()]
    cmd = AddMaterialCommand(lib, "Glass", (0.5, 0.6, 0.7))
    cmd.do(Scene())
    assert lib.get(cmd.material_id).name == "Glass"
    cmd.undo(Scene())
    assert [m.id for m in lib.materials()] == before


def test_edit_undo_restores_every_field_not_just_the_changed_one():
    lib = MaterialLibrary()
    m = lib.add_custom("Glass", (0.5, 0.6, 0.7))
    lib.edit(m.id, alpha=0.8, metallic=0.3)
    cmd = EditMaterialCommand(lib, m.id, base_color=(1.0, 0.0, 0.0), alpha=0.2)
    cmd.do(Scene())
    assert lib.get(m.id).base_color == (1.0, 0.0, 0.0)
    cmd.undo(Scene())
    restored = lib.get(m.id)
    assert restored.base_color == (0.5, 0.6, 0.7)
    assert restored.alpha == 0.8  # the untouched-by-this-edit field
    assert restored.metallic == 0.3


def test_edit_can_rename():
    lib = MaterialLibrary()
    m = lib.add_custom("Glass", (0.5, 0.6, 0.7))
    EditMaterialCommand(lib, m.id, name="Frosted").do(Scene())
    assert lib.get(m.id).name == "Frosted"


def test_delete_counts_affected_sides_before_it_runs():
    s = Scene()
    a, b = _square(s, 0.0), _square(s, 1.0)
    lib = MaterialLibrary()
    m = lib.add_custom("Brick", (0.7, 0.3, 0.2))
    s.set_face_material(a, m.id, Side.FRONT)
    s.set_face_material(b, m.id, Side.BACK)
    cmd = DeleteMaterialCommand(lib, m.id, s)
    assert cmd.affected_count == 2  # readable BEFORE do()
    assert lib.get(m.id).name == "Brick"


def test_delete_repaints_affected_sides_to_default():
    s = Scene()
    f = _square(s)
    lib = MaterialLibrary()
    m = lib.add_custom("Brick", (0.7, 0.3, 0.2))
    s.set_face_material(f, m.id, Side.BACK)
    DeleteMaterialCommand(lib, m.id, s).do(s)
    assert s.face_material(f, Side.BACK) == 0
    assert m.id not in [x.id for x in lib.materials()]


def test_delete_undo_restores_the_material_and_the_paint():
    s = Scene()
    f = _square(s)
    lib = MaterialLibrary()
    m = lib.add_custom("Brick", (0.7, 0.3, 0.2))
    s.set_face_material(f, m.id, Side.BACK)
    cmd = DeleteMaterialCommand(lib, m.id, s)
    cmd.do(s)
    cmd.undo(s)
    assert lib.get(m.id).name == "Brick"
    assert s.face_material(f, Side.BACK) == m.id  # both halves


def test_delete_undo_restores_display_order():
    s = Scene()
    lib = MaterialLibrary()
    lib.add_custom("A", (1.0, 0.0, 0.0))
    target = lib.add_custom("B", (0.0, 1.0, 0.0))
    lib.add_custom("C", (0.0, 0.0, 1.0))
    before = [m.id for m in lib.materials()]
    cmd = DeleteMaterialCommand(lib, target.id, s)
    cmd.do(s)
    cmd.undo(s)
    # appending on undo would put B last and still "restore" it
    assert [m.id for m in lib.materials()] == before


def test_delete_refuses_the_default():
    with pytest.raises(ValueError):
        DeleteMaterialCommand(MaterialLibrary(), 0, Scene())

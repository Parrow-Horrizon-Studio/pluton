from __future__ import annotations

from pluton.commands.annotation_commands import (
    CreateAnnotationCommand,
    DeleteAnnotationsCommand,
    EditLabelTextCommand,
    MoveAnnotationsCommand,
)
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def _dim(model):
    return Dimension(model.new_annotation_id(), (0, 0, 0), (4, 0, 0), (0, -1, 0))


def _label(model, text="note"):
    return Label(model.new_annotation_id(), (0, 0, 0), (2, 2, 0), text)


def test_create_adds_and_undo_removes():
    model = Model()
    ctx = model.active_context
    cmd = CreateAnnotationCommand(_dim(model), ctx)
    cmd.do(model)
    assert len(ctx.annotations) == 1
    cmd.undo(model)
    assert len(ctx.annotations) == 0
    cmd.do(model)   # redo re-adds the same object
    assert len(ctx.annotations) == 1


def test_delete_removes_and_undo_restores():
    model = Model()
    ctx = model.active_context
    ann = _dim(model)
    ctx.annotations.append(ann)
    cmd = DeleteAnnotationsCommand([ann.id], ctx)
    cmd.do(model)
    assert ctx.annotations == []
    cmd.undo(model)
    assert len(ctx.annotations) == 1
    assert ctx.annotations[0].id == ann.id


def test_edit_label_text_and_undo_restores_old_text():
    model = Model()
    ctx = model.active_context
    lab = _label(model, "before")
    ctx.annotations.append(lab)
    cmd = EditLabelTextCommand(lab.id, "after", ctx)
    cmd.do(model)
    assert ctx.annotations[0].text == "after"
    cmd.undo(model)
    assert ctx.annotations[0].text == "before"


def test_move_shifts_dimension_offset_and_label_text_pos():
    model = Model()
    ctx = model.active_context
    dim = _dim(model)
    lab = _label(model)
    ctx.annotations.extend([dim, lab])
    cmd = MoveAnnotationsCommand([dim.id, lab.id], (0.0, 0.0, 1.0), ctx)
    cmd.do(model)
    assert ctx.annotations[0].offset == (0.0, -1.0, 1.0)
    assert ctx.annotations[1].text_pos == (2.0, 2.0, 1.0)
    assert ctx.annotations[1].anchor == (0.0, 0.0, 0.0)   # anchor stays put
    cmd.undo(model)
    assert ctx.annotations[0].offset == (0.0, -1.0, 0.0)
    assert ctx.annotations[1].text_pos == (2.0, 2.0, 0.0)


def test_delete_middle_element_restores_at_original_index():
    """Verify deletion of non-last element restores at correct index."""
    model = Model()
    ctx = model.active_context
    ann1 = _dim(model)
    ann2 = _dim(model)
    ann3 = _dim(model)
    ctx.annotations.extend([ann1, ann2, ann3])
    cmd = DeleteAnnotationsCommand([ann2.id], ctx)
    cmd.do(model)
    assert len(ctx.annotations) == 2
    assert ctx.annotations[0].id == ann1.id
    assert ctx.annotations[1].id == ann3.id
    cmd.undo(model)
    assert len(ctx.annotations) == 3
    assert ctx.annotations[0].id == ann1.id
    assert ctx.annotations[1].id == ann2.id
    assert ctx.annotations[2].id == ann3.id
    cmd.do(model)
    assert len(ctx.annotations) == 2
    cmd.undo(model)
    assert len(ctx.annotations) == 3
    assert ctx.annotations[1].id == ann2.id  # restored at index 1

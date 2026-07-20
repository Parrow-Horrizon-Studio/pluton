from __future__ import annotations

from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model


def test_dimension_holds_local_points():
    d = Dimension(id=1, p1=(0.0, 0.0, 0.0), p2=(3.0, 0.0, 0.0), offset=(0.0, -0.5, 0.0))
    assert d.p1 == (0.0, 0.0, 0.0)
    assert d.p2 == (3.0, 0.0, 0.0)
    assert d.offset == (0.0, -0.5, 0.0)
    assert d.kind == "dimension"


def test_label_holds_anchor_text_pos_and_text():
    lab = Label(id=2, anchor=(1.0, 0.0, 0.0), text_pos=(2.0, 1.0, 0.0), text="Load-bearing")
    assert lab.anchor == (1.0, 0.0, 0.0)
    assert lab.text_pos == (2.0, 1.0, 0.0)
    assert lab.text == "Load-bearing"
    assert lab.kind == "label"


def test_definition_starts_with_no_annotations():
    model = Model()
    assert model.active_context.annotations == []


def test_annotation_ids_are_unique_and_increasing():
    model = Model()
    a = model.new_annotation_id()
    b = model.new_annotation_id()
    assert isinstance(a, int) and b == a + 1


def test_annotations_are_stored_per_context():
    model = Model()
    root = model.active_context
    grp = model.new_definition("G", is_group=True)
    inst = model.new_instance(grp)
    root.children.append(inst)
    root.annotations.append(Dimension(model.new_annotation_id(), (0, 0, 0), (1, 0, 0), (0, -1, 0)))
    grp.annotations.append(Label(model.new_annotation_id(), (0, 0, 0), (1, 1, 0), "inside"))
    assert len(root.annotations) == 1
    assert len(grp.annotations) == 1
    assert root.annotations[0].id != grp.annotations[0].id

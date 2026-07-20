"""Persistence tests for M7d annotations.

Covers the per-Definition "annotations" array in the .pluton codec, back-compat
with documents saved before annotations existed, field-fidelity for both
Dimension and Label (no swapped/transposed fields), and the id-counter
regression guard on Model.load_from.
"""

from __future__ import annotations

import pytest
from pluton.document import DocumentSettings
from pluton.io.document_codec import document_from_dict, document_to_dict
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model
from pluton.viewport.camera import Camera


def _roundtrip(model, camera, doc):
    data = document_to_dict(model, camera, doc)
    return document_from_dict(data)


def test_annotations_round_trip_in_the_root_context():
    model = Model()
    model.active_context.annotations.append(
        Dimension(model.new_annotation_id(), (0, 0, 0), (4, 0, 0), (0, -1, 0))
    )
    model.active_context.annotations.append(
        Label(model.new_annotation_id(), (0, 0, 0), (2, 2, 0), "Load-bearing")
    )
    restored, _cam, _units = _roundtrip(model, Camera(), DocumentSettings())
    anns = restored.active_context.annotations
    assert len(anns) == 2
    assert anns[0].kind == "dimension" and anns[0].p2 == pytest.approx((4.0, 0.0, 0.0))
    assert anns[1].kind == "label" and anns[1].text == "Load-bearing"


def test_annotations_round_trip_inside_a_group():
    model = Model()
    grp = model.new_definition("G", is_group=True)
    model.active_context.children.append(model.new_instance(grp))
    grp.annotations.append(Label(model.new_annotation_id(), (0, 0, 0), (1, 1, 0), "inside"))
    restored, _cam, _units = _roundtrip(model, Camera(), DocumentSettings())
    inner = restored.active_context.children[0].definition
    assert len(inner.annotations) == 1
    assert inner.annotations[0].text == "inside"


def test_document_without_annotations_key_still_loads():
    """A document saved before annotations existed (genuinely missing the key,
    not merely empty) must still load, yielding an empty annotation list."""
    model = Model()
    data = document_to_dict(model, Camera(), DocumentSettings())
    for defn in data["model"]["definitions"]:
        assert "annotations" in defn  # sanity: codec does emit the key normally
        defn.pop("annotations")
    restored, _cam, _units = document_from_dict(data)
    assert restored.active_context.annotations == []


def test_dimension_and_label_round_trip_all_fields_without_transposition():
    """Every field of both kinds must survive distinctly. A codec that swapped
    p1/p2/offset, or anchor/text_pos, would still pass a length check but must
    fail here."""
    model = Model()
    dim = Dimension(
        model.new_annotation_id(),
        p1=(1.0, 2.0, 3.0),
        p2=(4.0, 5.0, 6.0),
        offset=(0.5, -0.25, 7.0),
    )
    label = Label(
        model.new_annotation_id(),
        anchor=(10.0, 11.0, 12.0),
        text_pos=(13.0, 14.0, 15.0),
        text="Beam A",
    )
    model.active_context.annotations.append(dim)
    model.active_context.annotations.append(label)

    restored, _cam, _units = _roundtrip(model, Camera(), DocumentSettings())
    r_dim, r_label = restored.active_context.annotations

    assert r_dim.kind == "dimension"
    assert r_dim.id == dim.id
    assert r_dim.p1 == pytest.approx((1.0, 2.0, 3.0))
    assert r_dim.p2 == pytest.approx((4.0, 5.0, 6.0))
    assert r_dim.offset == pytest.approx((0.5, -0.25, 7.0))
    # offset must be preserved distinctly -- not collapsed into / swapped with p1 or p2
    assert r_dim.offset != pytest.approx(r_dim.p1)
    assert r_dim.offset != pytest.approx(r_dim.p2)

    assert r_label.kind == "label"
    assert r_label.id == label.id
    assert r_label.anchor == pytest.approx((10.0, 11.0, 12.0))
    assert r_label.text_pos == pytest.approx((13.0, 14.0, 15.0))
    assert r_label.text == "Beam A"
    # anchor and text_pos must not be transposed
    assert r_label.anchor != pytest.approx(r_label.text_pos)


def test_load_from_resets_next_annotation_id_after_document_load():
    """Regression guard for the M7d equivalent of the opening_definitions bug:
    Model.load_from must copy `_next_annotation_id` from the freshly-loaded
    model. Without the fix, a newly created annotation after Open/New would be
    allocated an id that collides with one already present in the document."""
    model = Model()
    model.active_context.annotations.append(
        Dimension(model.new_annotation_id(), (0, 0, 0), (1, 0, 0), (0, -1, 0))
    )
    model.active_context.annotations.append(
        Label(model.new_annotation_id(), (0, 0, 0), (1, 1, 0), "note")
    )
    existing_ids = {a.id for a in model.active_context.annotations}

    data = document_to_dict(model, Camera(), DocumentSettings())
    loaded, _cam, _units = document_from_dict(data)

    # Mirrors how MainWindow/DocumentController actually swap contents: a
    # long-lived Model object has its contents replaced in place via load_from.
    target = Model()
    target.load_from(loaded)

    new_id = target.new_annotation_id()
    assert new_id not in existing_ids

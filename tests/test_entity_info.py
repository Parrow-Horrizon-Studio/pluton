"""Entity Info summaries, selection bounds, and area formatting (M7.3 Task 6)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pluton.model.entity_info import entity_summary
from pluton.model.model_queries import selection_bounds
from pluton.selection import Selection
from pluton.units import Units, UnitSystem, format_area


def _square(model, size=1.0):
    scene = model.active_context.mesh
    v = [
        scene.add_vertex(np.array([0.0, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([size, 0.0, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([size, size, 0.0], dtype=np.float32)),
        scene.add_vertex(np.array([0.0, size, 0.0], dtype=np.float32)),
    ]
    return scene.add_face_from_loop(v)


def test_nothing_selected(model_factory):
    summary = entity_summary(model_factory(), Selection())
    assert summary.kind == "Nothing"
    assert summary.count == 0


def test_one_face_reports_its_area_and_material(model_factory):
    model = model_factory()
    face_id = _square(model, size=2.0)
    selection = Selection()
    selection.replace(faces=[face_id])

    summary = entity_summary(model, selection)

    assert summary.kind == "Face"
    assert summary.count == 1
    assert summary.area == pytest.approx(4.0)
    assert summary.material_id == model.active_context.mesh.face_material(face_id)
    assert summary.length is None


def test_one_edge_reports_its_length(model_factory):
    model = model_factory()
    _square(model, size=3.0)
    scene = model.active_context.mesh
    edge_id = next(iter(scene.edges_iter())).id
    selection = Selection()
    selection.replace(edges=[edge_id])

    summary = entity_summary(model, selection)

    assert summary.kind == "Edge"
    assert summary.length == pytest.approx(3.0)
    assert summary.area is None


def test_one_group_reports_name_definition_and_counts(model_factory, group_factory):
    model = model_factory()
    _square(model)
    instance = group_factory(model)
    instance.definition.name = "Wall"
    instance.name = "North"
    selection = Selection()
    selection.replace(instances=[instance.id])

    summary = entity_summary(model, selection)

    assert summary.kind == "Group"
    assert summary.name == "North"
    assert summary.definition_name == "Wall"
    assert summary.edge_count == 4
    assert summary.face_count == 1
    assert summary.child_count == 0
    assert summary.hidden is False
    assert summary.tag_id == instance.tag_id


def test_mixed_kinds_report_mixed(model_factory, group_factory):
    model = model_factory()
    face_id = _square(model)
    instance = group_factory(model)
    _square(model)
    selection = Selection()
    selection.replace(faces=[face_id], instances=[instance.id])

    assert entity_summary(model, selection).kind == "Mixed"


def test_hidden_is_none_when_the_selection_disagrees(model_factory, group_factory):
    model = model_factory()
    _square(model)
    first = group_factory(model)
    _square(model)
    second = group_factory(model)
    second.hidden = True
    selection = Selection()
    selection.replace(instances=[first.id, second.id])

    summary = entity_summary(model, selection)

    assert summary.count == 2
    assert summary.hidden is None
    # Name is single-instance only: a shared name across a multi-selection has
    # no meaning, so the field must report nothing rather than pick one.
    assert summary.name is None


def test_tag_id_is_none_when_the_selection_disagrees(model_factory, group_factory):
    model = model_factory()
    _square(model)
    first = group_factory(model)
    _square(model)
    second = group_factory(model)
    second.tag_id = model.tags.add("Walls").id
    selection = Selection()
    selection.replace(instances=[first.id, second.id])

    assert entity_summary(model, selection).tag_id is None


def test_selection_bounds_is_none_without_instances(model_factory):
    assert selection_bounds(model_factory(), Selection()) is None


def test_selection_bounds_measures_transformed_extents(model_factory, group_factory):
    # A rotated instance is exactly where scaling a local AABB goes wrong, so
    # the bounds must come from actual transformed vertices.
    model = model_factory()
    _square(model, size=2.0)
    instance = group_factory(model)
    angle = math.radians(45.0)
    rotation = np.eye(4, dtype=np.float64)
    rotation[0, 0] = math.cos(angle)
    rotation[0, 1] = -math.sin(angle)
    rotation[1, 0] = math.sin(angle)
    rotation[1, 1] = math.cos(angle)
    instance.transform = rotation
    selection = Selection()
    selection.replace(instances=[instance.id])

    lo, hi = selection_bounds(model, selection)

    # A 2x2 square turned 45 degrees spans 2*sqrt(2) on both X and Y.
    assert float(hi[0] - lo[0]) == pytest.approx(2.0 * math.sqrt(2.0), abs=1e-4)
    assert float(hi[1] - lo[1]) == pytest.approx(2.0 * math.sqrt(2.0), abs=1e-4)


def test_summary_size_comes_from_selection_bounds(model_factory, group_factory):
    model = model_factory()
    _square(model, size=2.0)
    instance = group_factory(model)
    selection = Selection()
    selection.replace(instances=[instance.id])

    summary = entity_summary(model, selection)

    assert summary.size == pytest.approx((2.0, 2.0, 0.0), abs=1e-5)


def test_format_area_metric_is_always_square_metres():
    # mm2 / cm2 produce unreadable magnitudes for architectural faces, so the
    # metric unit setting deliberately does not apply here.
    assert format_area(4.0, Units(system=UnitSystem.METRIC, metric_unit="mm")) == "4.00 m²"


def test_format_area_imperial_is_square_feet():
    assert format_area(1.0, Units(system=UnitSystem.IMPERIAL)) == "10.76 ft²"

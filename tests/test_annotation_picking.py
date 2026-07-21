from __future__ import annotations

import numpy as np
from pluton.annotations.picking import pick_annotation
from pluton.model.annotation import Dimension, Label
from pluton.model.model import Model
from pluton.selection import Selection
from pluton.units import Units


class _FlatCamera:
    def world_to_screen(self, world_xyz, width, height):
        x, y, z = float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2])
        if z < 0.0:
            return None
        return (100.0 + x * 10.0, 200.0 - y * 10.0, 1.0 + z)


def _pick(cursor, anns):
    return pick_annotation(cursor, anns, np.eye(4), _FlatCamera(), 640, 480, Units())


def test_click_on_the_dimension_line_hits_it():
    d = Dimension(5, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    # dimension line runs at world y=-2 -> screen y=220, x from 100 to 140
    assert _pick((120.0, 220.0), [d]) == 5


def test_click_far_away_hits_nothing():
    d = Dimension(5, (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0))
    assert _pick((600.0, 50.0), [d]) is None


def test_click_on_label_text_hits_the_label():
    lab = Label(9, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    # text sits at the projected text_pos -> (150, 170)
    assert _pick((152.0, 168.0), [lab]) == 9


def test_selection_tracks_annotations():
    sel = Selection()
    assert sel.annotations == set()
    sel.replace(annotations=[1, 2])
    assert sel.annotations == {1, 2}
    sel.add(annotations=[3])
    assert sel.annotations == {1, 2, 3}
    sel.clear()
    assert sel.annotations == set()


def test_nearest_hit_wins_when_boxes_overlap():
    """Two labels whose text boxes overlap; the click sits inside both but
    genuinely closer to `near`'s box centre -> nearest-hit resolution, not a
    tie, and the winner does not depend on list order."""
    near = Label(1, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    far = Label(2, (0.0, 0.0, 0.0), (5.5, 3.0, 0.0), "note")
    assert _pick((160.0, 162.0), [near, far]) == 1
    assert _pick((160.0, 162.0), [far, near]) == 1


def test_tie_break_is_deterministic_by_list_order():
    """Two annotations with identical geometry (an exact distance tie) --
    the first one encountered in `annotations` wins, deterministically."""
    a = Label(11, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "dup")
    b = Label(12, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "dup")
    assert _pick((160.0, 162.0), [a, b]) == 11
    assert _pick((160.0, 162.0), [b, a]) == 12


def test_degenerate_annotation_is_skipped_without_error():
    """A zero-length dimension has no valid plan (plan_annotation returns
    None); pick_annotation must skip it silently rather than raising, and
    still find a genuinely hittable annotation later in the list."""
    degenerate = Dimension(21, (1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (0.0, -1.0, 0.0))
    good = Label(22, (0.0, 0.0, 0.0), (5.0, 3.0, 0.0), "note")
    assert _pick((152.0, 168.0), [degenerate, good]) == 22
    assert _pick((600.0, 50.0), [degenerate]) is None


def test_active_context_scoping_with_nested_group():
    """Picking only ever sees the annotations list it is handed -- exactly
    like edge/face selection operates on the active scene. Entering a nested
    group changes which annotations are pickable at the same screen point."""
    model = Model()
    root_ann = Dimension(
        model.new_annotation_id(), (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0)
    )
    model.root.annotations.append(root_ann)

    group_def = model.new_definition("Group", is_group=True)
    nested_ann = Dimension(
        model.new_annotation_id(), (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (0.0, -2.0, 0.0)
    )
    group_def.annotations.append(nested_ann)
    inst = model.new_instance(group_def)
    model.root.children.append(inst)

    camera = _FlatCamera()
    cursor = (120.0, 220.0)  # same math as the dimension-line hit above

    picked_at_root = pick_annotation(
        cursor,
        model.active_context.annotations,
        model.active_world_transform,
        camera,
        640,
        480,
        Units(),
    )
    assert picked_at_root == root_ann.id

    model.enter(inst)
    picked_inside_group = pick_annotation(
        cursor,
        model.active_context.annotations,
        model.active_world_transform,
        camera,
        640,
        480,
        Units(),
    )
    assert picked_inside_group == nested_ann.id
    assert picked_inside_group != root_ann.id


def test_selection_annotations_round_trip_and_leaves_others_untouched():
    sel = Selection()
    sel.replace(edges=[1], faces=[2], instances=[3], annotations=[10, 11])
    assert sel.annotations == {10, 11}
    assert sel.edges == {1}
    assert sel.faces == {2}
    assert sel.instances == {3}
    assert sel.counts() == (1, 1, 1, 2)  # edges/faces/instances counts unaffected

    sel.add(annotations=[12])
    assert sel.annotations == {10, 11, 12}
    assert sel.edges == {1}
    assert sel.faces == {2}
    assert sel.instances == {3}

    sel.remove(annotations=[10])
    assert sel.annotations == {11, 12}
    assert sel.edges == {1}
    assert sel.faces == {2}
    assert sel.instances == {3}

    sel.clear()
    assert sel.annotations == set()
    assert sel.is_empty()


def test_selection_toggle_and_contains_annotation_mirrors_instance():
    sel = Selection()
    sel.toggle_annotation(7)
    assert sel.contains_annotation(7)
    assert sel.annotations == {7}
    sel.toggle_annotation(7)
    assert not sel.contains_annotation(7)
    assert sel.annotations == set()

import numpy as np

from pluton.model.model import Model
from pluton.ui.document_controller import DocumentController


def test_controller_dirty_transitions_and_title():
    c = DocumentController()
    assert c.current_path is None
    assert c.dirty is False
    assert c.display_title() == "Untitled — Pluton"

    c.mark_dirty()
    assert c.display_title() == "Untitled* — Pluton"

    c.set_path("/tmp/house.pluton")
    c.mark_clean()
    assert c.display_title() == "house.pluton — Pluton"
    c.mark_dirty()
    assert c.display_title() == "house.pluton* — Pluton"


def test_model_load_from_keeps_identity_swaps_contents():
    target = Model()
    target_id = id(target)
    other = Model()
    g = other.new_definition("Grp", is_group=True)
    inst = other.new_instance(g)
    other.root.children.append(inst)

    target.load_from(other)
    assert id(target) == target_id           # same object
    assert target.root is other.root         # contents swapped
    assert target.materials is other.materials
    assert target.tags is other.tags
    assert target.active_path == []

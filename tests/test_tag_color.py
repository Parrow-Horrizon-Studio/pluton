"""M7.5a Task 11: per-tag colour and the Color-by-Tag mode."""

from __future__ import annotations

import pytest
from pluton.commands.tag_commands import SetTagColorCommand
from pluton.model.model import Model
from pluton.model.tag import TagLibrary
from pluton.viewport.render_style import RenderStyle
from pluton.viewport.scene_renderer import (
    _definition_tag_ids,
    apply_tag_color_override,
    resolve_definition_tag_color,
)


def test_a_new_tag_gets_a_colour():
    lib = TagLibrary()
    t = lib.add("Walls")
    assert len(t.color) == 3
    assert all(0.0 <= c <= 1.0 for c in t.color)


def test_consecutive_tags_do_not_share_a_colour():
    lib = TagLibrary()
    a = lib.add("Walls")
    b = lib.add("Roof")
    assert a.color != b.color


def test_set_colour_replaces_it():
    lib = TagLibrary()
    t = lib.add("Walls")
    lib.set_color(t.id, (0.1, 0.2, 0.3))
    assert lib.get(t.id).color == (0.1, 0.2, 0.3)


def test_colour_round_trips_through_records():
    lib = TagLibrary()
    t = lib.add("Walls")
    lib.set_color(t.id, (0.1, 0.2, 0.3))
    rebuilt = TagLibrary.from_records(lib.to_records(), lib.next_id)
    assert rebuilt.get(t.id).color == (0.1, 0.2, 0.3)


def test_records_without_a_colour_still_load():
    # Schema <= 4 wrote no tag colour. Task 12's migration relies on this.
    rebuilt = TagLibrary.from_records([{"id": 0, "name": "Untagged", "visible": True}], 1)
    assert len(rebuilt.get(0).color) == 3


def test_color_by_tag_defaults_off():
    assert RenderStyle().color_by_tag is False


def test_color_by_tag_is_independent_of_face_style():
    from pluton.viewport.render_style import FaceStyle

    s = RenderStyle(face_style=FaceStyle.MONOCHROME, color_by_tag=True)
    assert s.face_style is FaceStyle.MONOCHROME
    assert s.color_by_tag is True


# --- The palette: cycling and its wrap ---------------------------------


def test_the_palette_wraps_back_to_the_first_colour():
    # Kills an implementation that indexes _PALETTE without a modulo (crashes
    # or clamps at the last entry once the cycle runs out) rather than
    # deliberately wrapping. Also kills a clamp-at-the-end implementation:
    # a clamp would make the wrapped tag equal its IMMEDIATE predecessor too,
    # which the second assertion catches.
    lib = TagLibrary()
    n = len(TagLibrary._PALETTE)
    tags = [lib.add(f"Tag {i}") for i in range(n + 1)]
    assert tags[0].color == tags[n].color
    assert tags[n - 1].color != tags[n].color


# --- SetTagColorCommand: undo restores the right tag, not just A colour -


def test_set_tag_color_command_is_undoable_and_tag_specific():
    # A test that only checks "the colour came back" cannot tell a command
    # that recolors every tag, or one whose undo restores the wrong tag's
    # colour, from a correct one. Two tags make both bugs visible.
    lib = TagLibrary()
    a = lib.add("Walls")
    b = lib.add("Roof")
    a_before, b_before = a.color, b.color

    cmd = SetTagColorCommand(lib, a.id, (0.9, 0.1, 0.1))
    cmd.do(None)
    assert lib.get(a.id).color == (0.9, 0.1, 0.1)
    assert lib.get(b.id).color == b_before  # kills a command that recolors every tag

    cmd.undo(None)
    assert lib.get(a.id).color == a_before  # kills undo restoring the wrong tag
    assert lib.get(b.id).color == b_before


# --- Color-by-Tag reaching the draw: the decision seams --------------------
#
# resolve_definition_tag_color and apply_tag_color_override are the GL-free
# seams the render loop composes (scene_renderer.render); _definition_tag_ids
# is the tree walk that supplies the tag id in the first place, since
# Model.traverse()'s (definition, world) pairs do not carry the owning
# Instance. Together these three cover "does Color-by-Tag actually change
# what a definition draws with" without a GL context.


def _face_pass(diffuse=(0.5, 0.5, 0.5)):
    from pluton.viewport.render_style import ResolvedFacePass

    return ResolvedFacePass(
        draw_faces=True,
        ambient=(0.1, 0.1, 0.1),
        diffuse=diffuse,
        specular=(0.2, 0.2, 0.2),
        shininess=8.0,
        alpha=1.0,
        blend=False,
        depth_write=True,
    )


def test_resolve_definition_tag_color_is_none_when_the_mode_is_off():
    # Kills an implementation that always returns a colour regardless of the
    # style flag -- a materials-bypassing override that never turns off.
    lib = TagLibrary()
    t = lib.add("Walls")
    assert resolve_definition_tag_color(t.id, lib, RenderStyle(color_by_tag=False)) is None


def test_resolve_definition_tag_color_returns_the_tags_own_colour():
    # Kills an implementation that ignores tag_id and returns some fixed or
    # default colour instead of the specific tag's.
    lib = TagLibrary()
    t = lib.add("Walls")
    lib.set_color(t.id, (0.3, 0.4, 0.5))
    color = resolve_definition_tag_color(t.id, lib, RenderStyle(color_by_tag=True))
    assert color == (0.3, 0.4, 0.5)


def test_apply_tag_color_override_replaces_both_sides_diffuse():
    # The brief calls out a front-only override as a plausible, easy-to-miss
    # bug -- asserting only the front side would not catch it. This checks
    # both, and that the rest of each pass (ambient/specular/alpha/etc.) is
    # left alone, so the override cannot be implemented by rebuilding the
    # whole ResolvedFacePass from scratch.
    front = _face_pass(diffuse=(0.5, 0.5, 0.5))
    back = _face_pass(diffuse=(0.2, 0.2, 0.2))
    color = (0.9, 0.1, 0.1)

    new_front, new_back = apply_tag_color_override(front, back, color)

    assert new_front.diffuse == color
    assert new_back.diffuse == color
    assert new_front.ambient == front.ambient
    assert new_back.specular == back.specular
    assert new_front.alpha == front.alpha


def test_apply_tag_color_override_is_a_noop_when_color_is_none():
    # Kills an implementation that always overrides, ignoring the None sentinel
    # that means "Color-by-Tag is off".
    front = _face_pass(diffuse=(0.5, 0.5, 0.5))
    back = _face_pass(diffuse=(0.2, 0.2, 0.2))
    new_front, new_back = apply_tag_color_override(front, back, None)
    assert new_front == front
    assert new_back == back


def test_definition_tag_ids_maps_a_child_definition_to_its_instances_tag():
    m = Model()
    d = m.new_definition("Wall", is_group=True)
    inst = m.new_instance(d)
    inst.tag_id = 5
    m.root.children.append(inst)

    ids = _definition_tag_ids(m)
    assert ids[id(d)] == 5


def test_definition_tag_ids_has_no_entry_for_the_root():
    # The root definition is never placed by an Instance, so it must not
    # appear -- a lookup that defaulted a missing key to 0 would be
    # indistinguishable from "explicitly Untagged" without this.
    m = Model()
    ids = _definition_tag_ids(m)
    assert id(m.root) not in ids


def test_the_full_chain_from_instance_tag_to_resolved_diffuse():
    # An end-to-end composition of the three seams above: an instance's tag
    # colour reaches BOTH sides' diffuse when Color-by-Tag is on, and neither
    # side is touched when it is off -- the actual behaviour a GL draw call
    # would show, minus the GL context.
    m = Model()
    d = m.new_definition("Wall", is_group=True)
    inst = m.new_instance(d)
    m.root.children.append(inst)
    walls = m.tags.add("Walls")
    m.tags.set_color(walls.id, (0.9, 0.2, 0.2))
    inst.tag_id = walls.id

    tag_ids = _definition_tag_ids(m)
    front, back = _face_pass((0.1, 0.1, 0.1)), _face_pass((0.2, 0.2, 0.2))

    off_color = resolve_definition_tag_color(
        tag_ids[id(d)], m.tags, RenderStyle(color_by_tag=False)
    )
    off_front, off_back = apply_tag_color_override(front, back, off_color)
    assert (off_front.diffuse, off_back.diffuse) == (front.diffuse, back.diffuse)

    on_color = resolve_definition_tag_color(tag_ids[id(d)], m.tags, RenderStyle(color_by_tag=True))
    on_front, on_back = apply_tag_color_override(front, back, on_color)
    assert on_front.diffuse == (0.9, 0.2, 0.2)
    assert on_back.diffuse == (0.9, 0.2, 0.2)


# --- TagsPage: recoloring goes through the command stack, and is undoable --
#
# Mirrors tests/test_materials_editor.py's pattern for MaterialsPage: patch
# QColorDialog.getColor (never let the modal dialog actually open) and drive
# the page's own handler.


def test_editing_tag_color_goes_through_the_command_stack(main_window, monkeypatch):
    from pluton.ui import tags_page as tags_page_module
    from PySide6.QtGui import QColor

    win = main_window
    lib = win._model.tags
    walls = lib.add("Walls")
    win._tags_page.refresh()
    win._tags_page.set_active(walls.id)
    depth = len(win._command_stack._undo)

    monkeypatch.setattr(
        tags_page_module.QColorDialog,
        "getColor",
        staticmethod(lambda *a, **k: QColor(10, 20, 30)),
    )

    win._tags_page._on_edit_color()

    assert len(win._command_stack._undo) == depth + 1, "recoloring must be undoable"
    assert lib.get(walls.id).color == pytest.approx((10 / 255, 20 / 255, 30 / 255), abs=1e-6)

    win._command_stack.undo()
    assert lib.get(walls.id).color != pytest.approx((10 / 255, 20 / 255, 30 / 255), abs=1e-6)


def test_picking_the_same_tag_colour_pushes_no_undo_entry(main_window, monkeypatch):
    from pluton.ui import tags_page as tags_page_module
    from PySide6.QtGui import QColor

    win = main_window
    lib = win._model.tags
    walls = lib.add("Walls")
    win._tags_page.refresh()
    win._tags_page.set_active(walls.id)
    depth = len(win._command_stack._undo)

    r, g, b = (round(c * 255) for c in lib.get(walls.id).color)
    monkeypatch.setattr(
        tags_page_module.QColorDialog,
        "getColor",
        staticmethod(lambda *a, **k: QColor(r, g, b)),
    )

    win._tags_page._on_edit_color()

    assert len(win._command_stack._undo) == depth, "an unchanged colour is not an edit"


def test_edit_color_is_a_noop_without_an_injected_command_stack(qtbot):
    # Kills a version that crashes (or silently mutates the library without
    # undo support) when used standalone -- the shape every pre-Task-11
    # TagsPage(lib) test in test_tags_page.py already constructs.
    from pluton.ui.tags_page import TagsPage

    lib = TagLibrary()
    walls = lib.add("Walls")
    page = TagsPage(lib)
    qtbot.addWidget(page)
    page.set_active(walls.id)
    before = lib.get(walls.id).color

    page._on_edit_color()  # no command_stack injected -> must not raise or mutate

    assert lib.get(walls.id).color == before

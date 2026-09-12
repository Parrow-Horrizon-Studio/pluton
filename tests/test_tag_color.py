"""M7.5a Task 11: per-tag colour and the Color-by-Tag mode."""

from __future__ import annotations

import pytest
from pluton.commands.tag_commands import SetTagColorCommand
from pluton.model.model import Model
from pluton.model.tag import TagLibrary
from pluton.viewport.render_style import RenderStyle
from pluton.viewport.scene_renderer import (
    apply_tag_color_override,
    resolve_tag_color,
    traverse_visible_tagged,
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
    # Asserting WHICH colour, not merely that there are three floats: keying
    # the fallback on record position alone hands Untagged (always record 0)
    # _PALETTE[0] -- bright red -- so every untagged face in a pre-Task-11
    # file reads as a real red tag under Color-by-Tag.
    rebuilt = TagLibrary.from_records(
        [
            {"id": 0, "name": "Untagged", "visible": True},
            {"id": 1, "name": "Walls", "visible": True},
        ],
        2,
    )
    assert rebuilt.get(0).color == TagLibrary._UNTAGGED_COLOR
    assert rebuilt.get(1).color == TagLibrary._PALETTE[0]


def test_untagged_consumes_no_palette_hue_after_a_load():
    # Untagged occupies a record slot but no hue, so the first tag added
    # after a load must continue the cycle at the next UNUSED entry --
    # seeding _next_palette_index from len(records) skips one.
    lib = TagLibrary()
    lib.add("Walls")
    rebuilt = TagLibrary.from_records(lib.to_records(), lib.next_id)
    assert rebuilt.add("Roof").color == TagLibrary._PALETTE[1]


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
# resolve_tag_color and apply_tag_color_override are the GL-free seams the
# render loop composes (scene_renderer.render); traverse_visible_tagged is
# the walk that supplies the tag id in the first place, since
# Model.traverse_visible()'s (definition, world) pairs do not carry the
# owning Instance. Together these three cover "does Color-by-Tag actually
# change what an occurrence draws with" without a GL context.


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


def test_resolve_tag_color_is_none_when_the_mode_is_off():
    # Kills an implementation that always returns a colour regardless of the
    # style flag -- a materials-bypassing override that never turns off.
    lib = TagLibrary()
    t = lib.add("Walls")
    assert resolve_tag_color(t.id, lib, RenderStyle(color_by_tag=False)) is None


def test_resolve_tag_color_returns_the_tags_own_colour():
    # Kills an implementation that ignores tag_id and returns some fixed or
    # default colour instead of the specific tag's.
    lib = TagLibrary()
    t = lib.add("Walls")
    lib.set_color(t.id, (0.3, 0.4, 0.5))
    color = resolve_tag_color(t.id, lib, RenderStyle(color_by_tag=True))
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


def _tagged_occurrences(model, definition):
    """The tag id of every visible occurrence of `definition`, in draw order."""
    return [tid for d, _, tid in traverse_visible_tagged(model) if d is definition]


def test_traverse_visible_tagged_carries_the_placing_instances_tag():
    m = Model()
    d = m.new_definition("Wall", is_group=True)
    inst = m.new_instance(d)
    inst.tag_id = 5
    m.root.children.append(inst)

    assert _tagged_occurrences(m, d) == [5]


def test_the_root_occurrence_is_reported_untagged():
    # The root definition is placed by no Instance, so the walk has no tag to
    # carry for it and must report UNTAGGED_ID -- the render loop draws the
    # root's own geometry and needs a real tag id for it, which is why this
    # is a documented value rather than a missing entry.
    m = Model()
    root_entry = next(iter(traverse_visible_tagged(m)))
    assert root_entry[0] is m.root
    assert root_entry[2] == TagLibrary.UNTAGGED_ID


def test_two_instances_of_one_definition_on_two_tags_resolve_to_two_colours():
    # THE per-definition bug: a component placed twice, on two tags, is the
    # ordinary case Color-by-Tag exists to serve. A map keyed by
    # id(definition) collapses both placements onto whichever instance was
    # visited last, so both draw in one colour.
    m = Model()
    chair = m.new_definition("Chair", is_group=False)
    walls = m.tags.add("Walls")
    roof = m.tags.add("Roof")
    m.tags.set_color(walls.id, (0.90, 0.25, 0.25))
    m.tags.set_color(roof.id, (0.95, 0.60, 0.15))
    for tag in (walls, roof):
        inst = m.new_instance(chair)
        inst.tag_id = tag.id
        m.root.children.append(inst)

    style = RenderStyle(color_by_tag=True)
    colors = [resolve_tag_color(tid, m.tags, style) for tid in _tagged_occurrences(m, chair)]

    assert colors == [(0.90, 0.25, 0.25), (0.95, 0.60, 0.15)]


def test_a_hidden_instance_does_not_supply_the_colour_a_visible_one_draws_with():
    # The aggravating half of the same bug: a walk of the whole tree sees
    # instances the draw never does, so a hidden placement visited later
    # could hand its colour to the visible one. The hidden instance is
    # appended SECOND on purpose -- last-write-wins is what it would win.
    m = Model()
    chair = m.new_definition("Chair", is_group=False)
    walls = m.tags.add("Walls")
    roof = m.tags.add("Roof")
    m.tags.set_color(walls.id, (0.90, 0.25, 0.25))
    m.tags.set_color(roof.id, (0.95, 0.60, 0.15))

    shown = m.new_instance(chair)
    shown.tag_id = walls.id
    hidden = m.new_instance(chair)
    hidden.tag_id = roof.id
    hidden.hidden = True
    m.root.children.extend([shown, hidden])

    style = RenderStyle(color_by_tag=True)
    colors = [resolve_tag_color(tid, m.tags, style) for tid in _tagged_occurrences(m, chair)]

    assert colors == [(0.90, 0.25, 0.25)]


def test_an_instance_on_a_hidden_tag_does_not_supply_a_colour_either():
    # Same aggravation via the other pruning rule traverse_visible applies.
    m = Model()
    chair = m.new_definition("Chair", is_group=False)
    walls = m.tags.add("Walls")
    roof = m.tags.add("Roof")
    m.tags.set_color(walls.id, (0.90, 0.25, 0.25))
    m.tags.set_color(roof.id, (0.95, 0.60, 0.15))
    m.tags.set_visible(roof.id, False)

    shown = m.new_instance(chair)
    shown.tag_id = walls.id
    off_tag = m.new_instance(chair)
    off_tag.tag_id = roof.id
    m.root.children.extend([shown, off_tag])

    style = RenderStyle(color_by_tag=True)
    colors = [resolve_tag_color(tid, m.tags, style) for tid in _tagged_occurrences(m, chair)]

    assert colors == [(0.90, 0.25, 0.25)]


def test_traverse_visible_tagged_visits_exactly_what_traverse_visible_does():
    # traverse_visible_tagged repeats traverse_visible's pruning rule inside
    # scene_renderer (so Model.traverse_visible keeps its two-tuple shape).
    # This pins the two walks together -- same entries, same order -- so the
    # copy cannot drift from the walk the rest of the renderer uses.
    m = Model()
    outer = m.new_definition("Outer", is_group=True)
    inner = m.new_definition("Inner", is_group=True)
    hidden_tag = m.tags.add("Hidden")
    m.tags.set_visible(hidden_tag.id, False)

    child = m.new_instance(inner)
    outer.children.append(child)
    a = m.new_instance(outer)
    b = m.new_instance(outer)
    b.hidden = True
    c = m.new_instance(inner)
    c.tag_id = hidden_tag.id
    m.root.children.extend([a, b, c])

    plain = [(id(d), w.tobytes()) for d, w in m.traverse_visible()]
    tagged = [(id(d), w.tobytes()) for d, w, _ in traverse_visible_tagged(m)]
    assert tagged == plain


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

    (tag_id,) = _tagged_occurrences(m, d)
    front, back = _face_pass((0.1, 0.1, 0.1)), _face_pass((0.2, 0.2, 0.2))

    off_color = resolve_tag_color(tag_id, m.tags, RenderStyle(color_by_tag=False))
    off_front, off_back = apply_tag_color_override(front, back, off_color)
    assert (off_front.diffuse, off_back.diffuse) == (front.diffuse, back.diffuse)

    on_color = resolve_tag_color(tag_id, m.tags, RenderStyle(color_by_tag=True))
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


def test_a_library_recolor_repaints_the_viewport(main_window):
    # library_changed marks the document dirty and retitles the window, which
    # is not enough: a recolored tag under Color-by-Tag (and a recolored
    # material under any face style) changes what is on screen right now, so
    # the viewport must repaint instead of waiting for an incidental one.
    # PySide's disconnect() only warns ("Failed to disconnect ...") when the
    # connection is absent, so the warning is promoted to an error -- that
    # promotion IS the assertion. Each page is reconnected immediately.
    import warnings

    win = main_window
    for page in (win._tags_page, win._materials_page):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            page.library_changed.disconnect(win._viewport.update)
        page.library_changed.connect(win._viewport.update)


def test_edit_color_is_a_noop_without_an_injected_command_stack(qtbot, monkeypatch):
    # Kills a version that crashes (or silently mutates the library without
    # undo support) when used standalone -- the shape every pre-Task-11
    # TagsPage(lib) test in test_tags_page.py already constructs.
    #
    # QColorDialog is patched even though the None guard should return first:
    # unpatched, a regressed guard opens a real modal and HANGS the suite
    # instead of failing it. Patched, the same regression fails this
    # assertion in milliseconds.
    from pluton.ui import tags_page as tags_page_module
    from pluton.ui.tags_page import TagsPage
    from PySide6.QtGui import QColor

    monkeypatch.setattr(
        tags_page_module.QColorDialog,
        "getColor",
        staticmethod(lambda *a, **k: QColor(10, 20, 30)),
    )

    lib = TagLibrary()
    walls = lib.add("Walls")
    page = TagsPage(lib)
    qtbot.addWidget(page)
    page.set_active(walls.id)
    before = lib.get(walls.id).color

    page._on_edit_color()  # no command_stack injected -> must not raise or mutate

    assert lib.get(walls.id).color == before

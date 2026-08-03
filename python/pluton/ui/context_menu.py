"""Right-click menu composition (M7.2).

context_menu_ids and is_enabled are pure: given what is under the cursor and
a little model state, they say what the menu contains and which entries are
live. Task 14 (resolve_context_target / build_context_menu below) turns that
into a hit-test and a QMenu.

Entries are disabled rather than hidden when they do not apply. A menu whose
items keep their position is learnable; one that reflows between right-clicks
is not.

build_context_menu reuses the menu bar's own QAction objects (see
ui_builder.ACTION_REGISTRY_ATTR), so it mutates their shared enabled state.
MainWindow._on_context_menu_requested is responsible for unconditionally
re-enabling every action once the menu closes -- see the comment there for
why that must not be conditional.
"""

from __future__ import annotations

from pluton.ui.actions import CONTEXT_MENUS, ContextTarget


def resolve_context_target(
    model, camera, x: int, y: int, width: int, height: int, units
) -> tuple[ContextTarget, int | None]:
    """What is under the cursor: (ContextTarget, entity_id or None).

    Uses the exact picking calls SelectTool.on_mouse_release makes --
    pick_annotation, Model.pick_instance, pick_selectable -- so a right-click
    hits exactly what a left-click would hit. The correspondence is
    guaranteed by sharing the code, not by keeping two implementations in
    step.

    Precedence mirrors SelectTool: annotations draw on top of everything, so
    they are hit-tested first; then whole instances; then the active
    context's own edges/faces.
    """
    from pluton.annotations.picking import pick_annotation
    from pluton.viewport.picking import pick_selectable

    annotation_id = pick_annotation(
        (x, y),
        model.active_context.annotations,
        model.active_world_transform,
        camera,
        width,
        height,
        units,
    )
    if annotation_id is not None:
        return ContextTarget.ANNOTATION, annotation_id

    origin, direction = camera.ray_from_screen(x, y, width, height)

    instance = model.pick_instance(origin, direction)
    if instance is not None:
        return ContextTarget.INSTANCE, instance.id

    hit = pick_selectable(
        (x, y),
        (width, height),
        camera,
        model.active_scene,
        world_transform=model.active_world_transform,
    )
    if hit is not None:
        kind, entity_id = hit
        if kind == "face":
            return ContextTarget.FACE, entity_id
        return ContextTarget.EDGE, entity_id

    return ContextTarget.EMPTY, None


def _entity_is_component(window, target: ContextTarget, entity_id) -> bool:
    """True only for a component instance -- a plain group cannot be made
    unique, so Make Unique must be disabled for one.

    Definition has no separate is_component flag: MakeComponentCommand sets
    is_group=False and MakeGroupCommand sets is_group=True (see
    pluton.commands.group_commands), so "is a component" is `not is_group`.
    """
    if target is not ContextTarget.INSTANCE or entity_id is None:
        return False
    for child in window._model.active_context.children:
        if child.id == entity_id:
            return not child.definition.is_group
    return False


def _add_assign_tag_submenu(window, menu, entity_id) -> None:
    """One checkable entry per tag, assigning it to the current selection."""
    submenu = menu.addMenu("Assign Tag")
    current = None
    for child in window._model.active_context.children:
        if child.id == entity_id:
            current = child.tag_id
            break

    for tag in window._model.tags.tags():
        entry = submenu.addAction(tag.name)
        entry.setCheckable(True)
        entry.setChecked(tag.id == current)
        entry.triggered.connect(lambda _checked=False, tag_id=tag.id: window._assign_tag(tag_id))


def build_context_menu(window, target: ContextTarget, entity_id):
    """A QMenu for `target`, reusing the window's existing QActions.

    Reusing the same QAction objects the menu bar and toolbars hold means an
    entry cannot drift in label, icon, or shortcut between surfaces. It also
    means this function mutates their shared enabled state -- the caller
    (MainWindow._on_context_menu_requested) must re-enable everything once
    the menu closes.
    """
    from PySide6.QtWidgets import QMenu

    menu = QMenu(window)
    in_group = bool(window._model.active_path)
    has_selection = not window._selection.is_empty()
    is_component = _entity_is_component(window, target, entity_id)

    for action_id in context_menu_ids(target, in_group=in_group, has_selection=has_selection):
        if action_id is None:
            menu.addSeparator()
            continue
        action = window._actions[action_id]
        action.setEnabled(
            is_enabled(
                action_id,
                target=target,
                in_group=in_group,
                is_component=is_component,
                has_selection=has_selection,
            )
        )
        menu.addAction(action)

    if target is ContextTarget.INSTANCE:
        _add_assign_tag_submenu(window, menu, entity_id)

    return menu


def context_menu_ids(
    target: ContextTarget, *, in_group: bool, has_selection: bool
) -> tuple[str | None, ...]:
    """The entries for a right-click on `target`. None is a separator.

    The composition is fixed per target; in_group and has_selection affect
    enablement (see is_enabled), not membership.
    """
    del in_group, has_selection  # Membership is fixed; only enablement varies.
    return CONTEXT_MENUS[target]


def is_enabled(
    action_id: str,
    *,
    target: ContextTarget,
    in_group: bool,
    is_component: bool,
    has_selection: bool,
) -> bool:
    """Whether a context-menu entry should be clickable.

    is_component distinguishes a component instance (which can be made
    unique) from a plain group (which cannot).
    """
    if action_id == "edit_close_group":
        return in_group
    if action_id == "edit_make_unique":
        return is_component
    if action_id in ("edit_select_none", "edit_erase", "edit_paint_selection", "edit_label_text"):
        return has_selection
    return True

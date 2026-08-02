"""Right-click menu composition (M7.2).

context_menu_ids and is_enabled are pure: given what is under the cursor and
a little model state, they say what the menu contains and which entries are
live. Task 14 turns that into a QMenu.

Entries are disabled rather than hidden when they do not apply. A menu whose
items keep their position is learnable; one that reflows between right-clicks
is not.
"""

from __future__ import annotations

from pluton.ui.actions import CONTEXT_MENUS, ContextTarget


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

"""Undoable annotation commands (M7d)."""
from __future__ import annotations

from pluton.commands.command import Command


def _find(context, annotation_id):
    for ann in context.annotations:
        if ann.id == annotation_id:
            return ann
    return None


def _shift(point, delta):
    return (point[0] + delta[0], point[1] + delta[1], point[2] + delta[2])


class CreateAnnotationCommand(Command):
    """Append one annotation to a context; undo detaches the same object."""

    name = "Create Annotation"

    def __init__(self, annotation, target_context) -> None:
        self._annotation = annotation
        self._target = target_context

    def do(self, model) -> None:
        if self._annotation not in self._target.annotations:
            self._target.annotations.append(self._annotation)

    def undo(self, model) -> None:
        if self._annotation in self._target.annotations:
            self._target.annotations.remove(self._annotation)


class DeleteAnnotationsCommand(Command):
    """Remove annotations by id; undo restores them at their original indices."""

    name = "Delete Annotations"

    def __init__(self, annotation_ids, target_context) -> None:
        self._ids = list(annotation_ids)
        self._target = target_context
        self._removed = []   # (index, annotation), ascending by index

    def do(self, model) -> None:
        self._removed = []
        wanted = set(self._ids)
        for index, ann in enumerate(list(self._target.annotations)):
            if ann.id in wanted:
                self._removed.append((index, ann))
        for _index, ann in self._removed:
            self._target.annotations.remove(ann)

    def undo(self, model) -> None:
        for index, ann in self._removed:
            self._target.annotations.insert(index, ann)
        self._removed = []


class EditLabelTextCommand(Command):
    """Replace a Label's text; undo restores the previous string."""

    name = "Edit Label Text"

    def __init__(self, annotation_id, new_text, target_context) -> None:
        self._id = int(annotation_id)
        self._new_text = str(new_text)
        self._target = target_context
        self._old_text = None

    def do(self, model) -> None:
        ann = _find(self._target, self._id)
        if ann is None or getattr(ann, "kind", None) != "label":
            return
        self._old_text = ann.text
        ann.text = self._new_text

    def undo(self, model) -> None:
        if self._old_text is None:
            return
        ann = _find(self._target, self._id)
        if ann is not None:
            ann.text = self._old_text


class MoveAnnotationsCommand(Command):
    """Translate annotations by a local delta.

    A Dimension's `offset` shifts (moving the dimension line); a Label's
    `text_pos` shifts while its `anchor` stays put so the leader re-aims.
    """

    name = "Move Annotations"

    def __init__(self, annotation_ids, delta, target_context) -> None:
        self._ids = list(annotation_ids)
        self._delta = (float(delta[0]), float(delta[1]), float(delta[2]))
        self._target = target_context

    def _apply(self, delta) -> None:
        wanted = set(self._ids)
        for ann in self._target.annotations:
            if ann.id not in wanted:
                continue
            if getattr(ann, "kind", None) == "dimension":
                ann.offset = _shift(ann.offset, delta)
            elif getattr(ann, "kind", None) == "label":
                ann.text_pos = _shift(ann.text_pos, delta)

    def do(self, model) -> None:
        self._apply(self._delta)

    def undo(self, model) -> None:
        self._apply((-self._delta[0], -self._delta[1], -self._delta[2]))

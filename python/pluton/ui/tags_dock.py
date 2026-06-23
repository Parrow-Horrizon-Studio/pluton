# python/pluton/ui/tags_dock.py
"""The Tags dock (M5c): a list panel for object tags + per-tag visibility."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pluton.model.tag import TagLibrary


class TagsDock(QDockWidget):
    """Tag list (checkbox = visibility, selected row = active tag) + Add/Assign buttons."""

    active_tag_changed = Signal(int)
    visibility_changed = Signal()
    assign_to_selection_requested = Signal()

    def __init__(self, library: TagLibrary, parent=None) -> None:
        super().__init__("Tags", parent)
        self._library = library
        self._active_id = TagLibrary.UNTAGGED_ID
        self._rebuilding = False

        container = QWidget(self)
        layout = QVBoxLayout(container)
        self._list = QListWidget(container)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self._list)
        add_btn = QPushButton("Add Tag", container)
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)
        assign_btn = QPushButton("Assign to Selection", container)
        assign_btn.clicked.connect(self._on_assign)
        layout.addWidget(assign_btn)
        self.setWidget(container)

        self._rebuild()

    def _rebuild(self) -> None:
        self._rebuilding = True
        self._list.clear()
        for tag in self._library.tags():
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            if tag.id == TagLibrary.UNTAGGED_ID:
                # Untagged: always visible — checkbox shown checked, not user-toggleable.
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if tag.visible else Qt.CheckState.Unchecked
                )
            self._list.addItem(item)
            if tag.id == self._active_id:
                self._list.setCurrentItem(item)
        self._rebuilding = False

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._rebuilding:
            return
        tid = int(item.data(Qt.ItemDataRole.UserRole))
        tag = self._library.get(tid)
        # Visibility (checkbox). Untagged stays always-visible.
        visible = item.checkState() == Qt.CheckState.Checked
        if self._library.is_visible(tid) != visible:
            self._library.set_visible(tid, visible)
            self.visibility_changed.emit()
        # Rename (inline text edit). Untagged is not renamable; empty is rejected.
        new_name = item.text().strip()
        if tid != TagLibrary.UNTAGGED_ID and new_name and new_name != tag.name:
            self._library.rename(tid, new_name)
        elif item.text() != tag.name:
            # Reject empty/invalid edit -> restore display without re-triggering.
            self._list.blockSignals(True)
            item.setText(tag.name)
            self._list.blockSignals(False)

    def _on_current_changed(self, current, _previous) -> None:
        if self._rebuilding or current is None:
            return
        self._active_id = int(current.data(Qt.ItemDataRole.UserRole))
        self.active_tag_changed.emit(self._active_id)

    def _on_add(self) -> None:
        tag = self._library.add(f"Tag {len(self._library.tags())}")
        self._rebuild()
        self.set_active(tag.id)

    def _on_assign(self) -> None:
        self.assign_to_selection_requested.emit()

    def set_active(self, tag_id: int) -> None:
        """Select the row for `tag_id` (used to set the active tag programmatically)."""
        self._active_id = tag_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            if int(item.data(Qt.ItemDataRole.UserRole)) == tag_id:
                self._list.setCurrentItem(item)
                break

    @property
    def active_tag_id(self) -> int:
        return self._active_id

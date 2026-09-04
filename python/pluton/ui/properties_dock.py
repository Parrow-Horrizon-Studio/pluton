"""The M7.3 right panel: an Outliner over an icon-tabbed Properties editor.

One dock, split vertically. The Outliner and every Properties page are
INJECTED (set_outliner / set_page) rather than constructed here, so this shell
is testable on its own and the pages that replace three former docks can land
one task at a time.

An un-injected tab shows a placeholder, which is also what a tab with nothing
to show looks like -- so the empty state needed no extra machinery.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pluton.ui.icons import icon
from pluton.ui.panels import PROPERTIES_TABS

_TAB_ICON_SIZE = 20


class PropertiesDock(QDockWidget):
    """Outliner (top) + icon-tabbed Properties editor (bottom)."""

    tab_changed = Signal(str)

    # QMainWindow.saveState() silently drops docks without an object name.
    # This is a persistence key: never rename it, or saved layouts silently
    # lose this dock's state.
    OBJECT_NAME = "properties_dock"

    def __init__(self, parent=None) -> None:
        super().__init__("Properties", parent)
        self.setObjectName(self.OBJECT_NAME)

        self._buttons: dict[str, QToolButton] = {}
        self._page_index: dict[str, int] = {}
        self._outliner: QWidget | None = None

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)

        self._outliner_host = QWidget(self._splitter)
        self._outliner_layout = QVBoxLayout(self._outliner_host)
        self._outliner_layout.setContentsMargins(0, 0, 0, 0)
        self._outliner_placeholder: QWidget | None = QLabel("Outliner", self._outliner_host)
        self._outliner_layout.addWidget(self._outliner_placeholder)
        self._splitter.addWidget(self._outliner_host)

        properties = QWidget(self._splitter)
        properties_layout = QVBoxLayout(properties)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.setSpacing(0)

        strip = QWidget(properties)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(2, 2, 2, 2)
        strip_layout.setSpacing(2)
        # Exclusive without being a QActionGroup: these are view switches, not
        # commands, so they never belong in the action registry.
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._stack = QStackedWidget(properties)

        palette_color = self.palette().windowText().color()
        for spec in PROPERTIES_TABS:
            button = QToolButton(strip)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(spec.title)
            button.setAccessibleName(spec.title)
            button.setIconSize(QSize(_TAB_ICON_SIZE, _TAB_ICON_SIZE))
            button.setIcon(icon(spec.icon, palette_color))
            button.clicked.connect(lambda _checked=False, tid=spec.id: self.show_tab(tid))
            strip_layout.addWidget(button)
            self._group.addButton(button)
            self._buttons[spec.id] = button

            placeholder = QLabel(spec.title, self._stack)
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._page_index[spec.id] = self._stack.addWidget(placeholder)

        strip_layout.addStretch(1)
        properties_layout.addWidget(strip, stretch=0)
        properties_layout.addWidget(self._stack, stretch=1)
        self._splitter.addWidget(properties)

        self.setWidget(self._splitter)

        self._current = PROPERTIES_TABS[0].id
        self._buttons[self._current].setChecked(True)
        self._stack.setCurrentIndex(self._page_index[self._current])

    # --- tabs ------------------------------------------------------------
    def tab_ids(self) -> tuple[str, ...]:
        return tuple(self._buttons)

    def tab_button(self, tab_id: str) -> QToolButton:
        return self._buttons[tab_id]

    @property
    def current_tab_id(self) -> str:
        return self._current

    def current_page(self) -> QWidget:
        return self._stack.currentWidget()

    def show_tab(self, tab_id: str) -> None:
        """Switch to `tab_id`. An unknown id is ignored, not an error: a stale
        saved id or a typo must not take the panel down."""
        if tab_id not in self._page_index:
            return
        self._current = tab_id
        self._buttons[tab_id].setChecked(True)
        self._stack.setCurrentIndex(self._page_index[tab_id])
        self.tab_changed.emit(tab_id)

    def set_page(self, tab_id: str, widget: QWidget) -> None:
        """Replace a tab's placeholder (or prior page) with `widget`.

        Safe to call more than once for the same id: the widget currently
        installed there -- placeholder or a previous real page -- is removed
        and scheduled for deletion first.
        """
        if tab_id not in self._page_index:
            raise KeyError(f"unknown properties tab {tab_id!r}")
        old_index = self._page_index[tab_id]
        old = self._stack.widget(old_index)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._page_index[tab_id] = self._stack.insertWidget(old_index, widget)
        if self._current == tab_id:
            self._stack.setCurrentIndex(self._page_index[tab_id])

    # --- outliner --------------------------------------------------------
    def outliner(self) -> QWidget | None:
        return self._outliner

    def set_outliner(self, widget: QWidget) -> None:
        """Install the Outliner above the tab strip (Task 9)."""
        if self._outliner_placeholder is not None:
            self._outliner_layout.removeWidget(self._outliner_placeholder)
            self._outliner_placeholder.deleteLater()
            self._outliner_placeholder = None
        if self._outliner is not None:
            self._outliner_layout.removeWidget(self._outliner)
            self._outliner.deleteLater()
        self._outliner = widget
        self._outliner_layout.addWidget(widget)

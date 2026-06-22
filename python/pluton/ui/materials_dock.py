"""The Materials dock (M5b): a swatch grid for choosing the active material."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QColorDialog,
    QDockWidget,
    QGridLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pluton.model.material import MaterialLibrary

_COLUMNS = 4


def _swatch_style(color: tuple[float, float, float], active: bool) -> str:
    r, g, b = (round(c * 255) for c in color)
    border = "3px solid #2f8fff" if active else "1px solid #555"
    return (
        f"background-color: rgb({r},{g},{b}); border: {border}; "
        f"min-width: 36px; min-height: 28px;"
    )


class MaterialsDock(QDockWidget):
    """Swatch grid + custom-color button. Emits active_material_changed(Material)."""

    active_material_changed = Signal(object)  # emits a Material

    def __init__(self, library: MaterialLibrary, parent=None) -> None:
        super().__init__("Materials", parent)
        self._library = library
        self._active_id = MaterialLibrary.DEFAULT_ID
        self._buttons: dict[int, QPushButton] = {}

        container = QWidget(self)
        outer = QVBoxLayout(container)
        self._grid = QGridLayout()
        outer.addLayout(self._grid)
        custom = QPushButton("Custom color…", container)
        custom.clicked.connect(self._on_custom)
        outer.addWidget(custom)
        outer.addStretch(1)
        self.setWidget(container)

        self._rebuild_swatches()

    def _rebuild_swatches(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._buttons.clear()
        for idx, mat in enumerate(self._library.materials()):
            btn = QPushButton(self)
            btn.setToolTip(mat.name)
            btn.setStyleSheet(_swatch_style(mat.color, mat.id == self._active_id))
            btn.clicked.connect(lambda _checked=False, mid=mat.id: self._on_pick(mid))
            self._grid.addWidget(btn, idx // _COLUMNS, idx % _COLUMNS)
            self._buttons[mat.id] = btn

    def _restyle(self) -> None:
        for mid, btn in self._buttons.items():
            mat = self._library.get(mid)
            btn.setStyleSheet(_swatch_style(mat.color, mid == self._active_id))

    def _on_pick(self, material_id: int) -> None:
        self._active_id = material_id
        self._restyle()
        self.active_material_changed.emit(self._library.get(material_id))

    def _on_custom(self) -> None:
        qc = QColorDialog.getColor(parent=self)
        if not qc.isValid():
            return
        color = (qc.redF(), qc.greenF(), qc.blueF())
        mat = self._library.add_custom(qc.name(), color)  # name == hex "#rrggbb"
        self._rebuild_swatches()
        self._on_pick(mat.id)

    def set_active(self, material_id: int) -> None:
        """Update the highlighted swatch (used by the Paint tool's eyedropper)."""
        self._active_id = material_id
        self._restyle()
        self.active_material_changed.emit(self._library.get(material_id))

    @property
    def active_material_id(self) -> int:
        return self._active_id

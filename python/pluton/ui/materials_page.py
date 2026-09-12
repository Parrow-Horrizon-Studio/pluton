"""The Materials page (M5b, a Properties tab since M7.3; editor added M7.5a
Task 9): a swatch grid for choosing the active material, plus an editor below
it for the active material's fields.

Every mutation (add / edit / delete) goes through a command on the command
stack -- never MaterialLibrary directly -- so it is undoable. The stack and
the model (for the current scene) are injected by MainWindow after
construction the same way ToolContext injects them into a Tool; when neither
is supplied (as in the standalone MaterialsPage(lib) tests) every mutating
method below is a documented no-op, and the widget behaves exactly as the
M5b swatch-only page did.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pluton.commands.material_commands import (
    AddMaterialCommand,
    DeleteMaterialCommand,
    EditMaterialCommand,
)
from pluton.model.material import MaterialLibrary

_COLUMNS = 4


def _swatch_style(color: tuple[float, float, float], alpha: float, active: bool) -> str:
    """Stylesheet for one swatch, alpha-composited over whatever is behind it.

    Qt style sheet rgba() alpha is 0..255, not the CSS3 0..1 -- using
    `alpha` directly here would make every translucent material nearly
    invisible instead of see-through.
    """
    r, g, b = (round(c * 255) for c in color)
    a = round(max(0.0, min(1.0, alpha)) * 255)
    border = "3px solid #2f8fff" if active else "1px solid #555"
    return (
        f"background-color: rgba({r},{g},{b},{a}); border: {border}; "
        "min-width: 36px; min-height: 28px;"
    )


class MaterialsPage(QWidget):
    """Swatch grid + editor for the active material. Emits
    active_material_changed(Material)."""

    active_material_changed = Signal(object)  # emits a Material
    library_changed = Signal()

    def __init__(
        self,
        library: MaterialLibrary,
        parent=None,
        *,
        command_stack=None,
        model=None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._command_stack = command_stack
        self._model = model
        self._active_id = MaterialLibrary.DEFAULT_ID
        self._buttons: dict[int, QPushButton] = {}
        self._syncing = False

        container = self
        outer = QVBoxLayout(container)
        self._grid = QGridLayout()
        outer.addLayout(self._grid)
        custom = QPushButton("Custom color…", container)
        custom.clicked.connect(self._on_custom)
        outer.addWidget(custom)

        outer.addLayout(self._build_editor(container))
        outer.addStretch(1)

        self._rebuild_swatches()
        self._sync_editor()

    def _build_editor(self, container: QWidget) -> QFormLayout:
        form = QFormLayout()

        self._name_edit = QLineEdit(container)
        self._name_edit.editingFinished.connect(self._on_name_committed)
        form.addRow("Name", self._name_edit)

        self._color_btn = QPushButton(container)
        self._color_btn.clicked.connect(self._on_edit_color)
        form.addRow("Base color", self._color_btn)

        self._alpha_spin = self._make_unit_spin(container, self._on_alpha_changed)
        form.addRow("Alpha", self._alpha_spin)

        self._metallic_spin = self._make_unit_spin(container, self._on_metallic_changed)
        form.addRow("Metallic", self._metallic_spin)

        self._roughness_spin = self._make_unit_spin(container, self._on_roughness_changed)
        form.addRow("Roughness", self._roughness_spin)

        self._delete_btn = QPushButton("Delete Material", container)
        self._delete_btn.clicked.connect(lambda: self._delete_active())
        form.addRow(self._delete_btn)

        return form

    def _make_unit_spin(self, container: QWidget, on_changed) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(container)
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        spin.valueChanged.connect(on_changed)
        return spin

    # --- swatch grid -------------------------------------------------------

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
            btn.setStyleSheet(_swatch_style(mat.base_color, mat.alpha, mat.id == self._active_id))
            btn.clicked.connect(lambda _checked=False, mid=mat.id: self._on_pick(mid))
            self._grid.addWidget(btn, idx // _COLUMNS, idx % _COLUMNS)
            self._buttons[mat.id] = btn

    def _restyle(self) -> None:
        for mid, btn in self._buttons.items():
            mat = self._library.get(mid)
            btn.setStyleSheet(_swatch_style(mat.base_color, mat.alpha, mid == self._active_id))

    def _on_pick(self, material_id: int) -> None:
        self._active_id = material_id
        self._restyle()
        self._sync_editor()
        self.active_material_changed.emit(self._library.get(material_id))

    def _on_custom(self) -> None:
        qc = QColorDialog.getColor(parent=self)
        if not qc.isValid():
            return
        color = (qc.redF(), qc.greenF(), qc.blueF())
        self._add_material(qc.name(), color)  # name == hex "#rrggbb"

    def set_active(self, material_id: int) -> None:
        """Update the highlighted swatch (used by the Paint tool's eyedropper)."""
        self._active_id = material_id
        self._restyle()
        self._sync_editor()
        self.active_material_changed.emit(self._library.get(material_id))

    def set_library(self, library: MaterialLibrary) -> None:
        """Rebind to a new library (after file Open / New) and rebuild swatches."""
        self._library = library
        self._active_id = MaterialLibrary.DEFAULT_ID
        self._rebuild_swatches()
        self._sync_editor()

    @property
    def active_material_id(self) -> int:
        return self._active_id

    # --- editor: read side ---------------------------------------------------

    def _sync_editor(self) -> None:
        """Repopulate the editor fields from the active material. Guarded by
        `_syncing` so setValue()/setText() below don't loop back into the
        `_on_*_changed` handlers and re-issue a command for a value we
        just read from the library."""
        mat = self._library.get(self._active_id)
        self._syncing = True
        try:
            self._name_edit.setText(mat.name)
            self._color_btn.setStyleSheet(_swatch_style(mat.base_color, 1.0, False))
            self._alpha_spin.setValue(mat.alpha)
            self._metallic_spin.setValue(mat.metallic)
            self._roughness_spin.setValue(mat.roughness)
        finally:
            self._syncing = False
        self._delete_btn.setEnabled(self._can_delete_active())

    def _current_scene(self):
        return None if self._model is None else self._model.active_scene

    # --- editor: write side (commands only) -----------------------------

    def _apply_edit(self, **fields) -> None:
        """Edit the active material through the command stack."""
        mid = self.active_material_id
        if mid is None or self._command_stack is None:
            return
        cmd = EditMaterialCommand(self._library, mid, **fields)
        self._command_stack.execute(cmd, self._current_scene())
        self._rebuild_swatches()
        self._sync_editor()
        self.library_changed.emit()

    def _add_material(self, name: str, color: tuple[float, float, float]) -> None:
        """Add a material through the command stack."""
        if self._command_stack is None:
            return
        cmd = AddMaterialCommand(self._library, name, color)
        self._command_stack.execute(cmd, self._current_scene())
        self._rebuild_swatches()
        self.library_changed.emit()
        self.set_active(cmd.material_id)

    def _can_delete_active(self) -> bool:
        return self.active_material_id != MaterialLibrary.DEFAULT_ID

    def _delete_active(self, confirm=None) -> None:
        """Delete the active material through the command stack.

        `confirm` lets tests supply a stub instead of a modal QMessageBox.
        DeleteMaterialCommand snapshots the affected faces at construction,
        below, and that snapshot is what do() acts on -- so nothing may
        mutate the scene between constructing `cmd` and calling do(). The
        `ask(...)` call in between is a modal QMessageBox.question by
        default: it blocks this widget's event loop for user input only,
        the same way any modal dialog blocks the rest of the application,
        so no paint gesture can land on the canvas while it is open.
        """
        mid = self.active_material_id
        if not self._can_delete_active() or self._command_stack is None or self._model is None:
            return
        scene = self._current_scene()
        cmd = DeleteMaterialCommand(self._library, mid, scene)
        ask = confirm if confirm is not None else self._confirm_delete
        if not ask(cmd.affected_count):
            return
        self._command_stack.execute(cmd, scene)
        self.set_active(MaterialLibrary.DEFAULT_ID)
        self._rebuild_swatches()
        self.library_changed.emit()

    def _confirm_delete(self, count: int) -> bool:
        mat = self._library.get(self.active_material_id)
        noun = "face side" if count == 1 else "face sides"
        text = (
            f'Delete material "{mat.name}"? {count} {noun} painted with it will revert to Default.'
        )
        result = QMessageBox.question(
            self,
            "Delete Material",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    # --- editor: signal handlers (thin wrappers over the seams above) ------

    def _on_name_committed(self) -> None:
        if self._syncing:
            return
        name = self._name_edit.text().strip()
        mat = self._library.get(self.active_material_id)
        if name and name != mat.name:
            self._apply_edit(name=name)

    def _on_edit_color(self) -> None:
        mat = self._library.get(self.active_material_id)
        r, g, b = (round(c * 255) for c in mat.base_color)
        qc = QColorDialog.getColor(QColor(r, g, b), self)
        if not qc.isValid():
            return
        self._apply_edit(base_color=(qc.redF(), qc.greenF(), qc.blueF()))

    def _on_alpha_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._apply_edit(alpha=value)

    def _on_metallic_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._apply_edit(metallic=value)

    def _on_roughness_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._apply_edit(roughness=value)

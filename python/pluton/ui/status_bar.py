"""Bottom-of-viewport status bar.

Two text slots: tool name and current snap label, joined by `·`. When no
tool is active, the bar shows nothing. When a tool is active but there's
no snap, the bar shows `<tool> · —`. M4 will add a third slot for the
Measurements Box value.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBar(QLabel):
    """Single-label status bar — the tool and snap text rendered together."""

    def __init__(self) -> None:
        super().__init__()
        self._tool: str = ""
        self._snap: str = ""
        self.setText("")
        self.setMinimumHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "QLabel { background-color: rgba(0, 0, 0, 0.5); color: #dddddd;"
            " padding: 4px 10px; font-family: sans-serif; font-size: 11px; }"
        )

    def set_tool(self, name: str) -> None:
        self._tool = name
        self._refresh()

    def set_snap(self, label: str) -> None:
        self._snap = label
        self._refresh()

    def _refresh(self) -> None:
        if not self._tool:
            self.setText("")
            return
        snap = self._snap if self._snap else "—"
        self.setText(f"{self._tool} · {snap}")

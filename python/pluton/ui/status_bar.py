"""Bottom-of-viewport status bar.

Three text slots: tool name, current snap label, and an optional status segment
(used by M3b's PushPullTool to show the current extrusion depth). Joined by `·`.
M4 will repurpose the status slot for the Measurements Box.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBar(QLabel):
    """Single-label status bar — joins tool / snap / status text."""

    def __init__(self) -> None:
        super().__init__()
        self._tool: str = ""
        self._snap: str = ""
        self._status: str = ""
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

    def set_status(self, text: str) -> None:
        self._status = text or ""
        self._refresh()

    def _refresh(self) -> None:
        if not self._tool:
            self.setText("")
            return
        snap = self._snap if self._snap else "—"
        if self._status:
            self.setText(f"{self._tool} · {snap} · {self._status}")
        else:
            self.setText(f"{self._tool} · {snap}")

"""Bottom-of-viewport status bar.

Three text slots: tool name, current snap label, and an optional status segment
(used by M3b's PushPullTool to show the current extrusion depth). Joined by `·`.
M4 will repurpose the status slot for the Measurements Box.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusBar(QLabel):
    """Single-label status bar — joins breadcrumb / tool / snap / status text."""

    def __init__(self) -> None:
        super().__init__()
        self._tool: str = ""
        self._snap: str = ""
        self._status: str = ""
        self._selection: str = ""
        self._breadcrumb: str = ""  # Task 15: active editing path, e.g. "Model ▸ Group #3"
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

    def set_selection(self, text: str) -> None:
        self._selection = text or ""
        self._refresh()

    def set_breadcrumb(self, text: str) -> None:
        """Task 15: set the active editing path breadcrumb (e.g. 'Model ▸ Group #3')."""
        self._breadcrumb = text or ""
        self._refresh()

    def _refresh(self) -> None:
        if not self._tool:
            # No active tool — show breadcrumb (if inside a group) and selection count.
            parts = []
            if self._breadcrumb:
                parts.append(self._breadcrumb)
            if self._selection:
                parts.append(self._selection)
            self.setText(" · ".join(parts) if parts else "")
            return
        snap = self._snap if self._snap else "—"
        parts = [f"{self._tool} · {snap}"]
        if self._breadcrumb:
            parts.append(self._breadcrumb)
        if self._status:
            parts.append(self._status)
        if self._selection:
            parts.append(self._selection)
        self.setText(" · ".join(parts))

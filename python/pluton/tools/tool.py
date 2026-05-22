"""Tool abstraction for drawing/modeling tools.

A Tool owns a small state machine, receives Qt events from the active
ViewportWidget, mutates the Scene, and emits a per-frame ToolOverlay
containing transient preview geometry (rubber-band, snap marker).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from PySide6.QtGui import QKeyEvent, QMouseEvent


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Handed to Tool.activate(); gives the tool a handle to the live Scene."""

    scene: object  # forward-typed to avoid circular import; really a pluton.scene.Scene


@dataclass(frozen=True, slots=True)
class ToolOverlay:
    """Transient preview geometry rebuilt every frame by the active tool."""

    rubber_band_segments: np.ndarray  # shape (2*N, 3), float32
    rubber_band_color: tuple[float, float, float]
    snap_marker_position: np.ndarray | None
    snap_marker_color: tuple[float, float, float]
    snap_marker_kind: int = 0  # SnapKind value (0=NONE/no marker); stored as int to avoid circular import


class Tool(ABC):
    """Base class for all M2+ tools."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def shortcut(self) -> str: ...

    @property
    @abstractmethod
    def has_active_gesture(self) -> bool:
        """True if the tool is in the middle of a multi-click gesture.

        MainWindow uses this to decide whether ESC should cancel the gesture
        (forward to tool.on_key_press) or deactivate the tool entirely
        (ToolManager.deactivate_current).
        """

    @abstractmethod
    def activate(self, ctx: ToolContext) -> None: ...

    @abstractmethod
    def deactivate(self) -> None: ...

    def on_mouse_move(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing. Tools override as needed."""

    def on_mouse_press(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing."""

    def on_key_press(self, event: QKeyEvent) -> None:
        """Default: do nothing."""

    @abstractmethod
    def overlay(self) -> ToolOverlay: ...

    @property
    @abstractmethod
    def anchor_or_none(self) -> np.ndarray | None:
        """Rubber-band anchor used by the SnapEngine for axis-lock."""

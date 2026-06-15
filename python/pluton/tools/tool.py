"""Tool abstraction for drawing/modeling tools.

A Tool owns a small state machine, receives Qt events from the active
ViewportWidget, mutates the Scene, and emits a per-frame ToolOverlay
containing transient preview geometry (rubber-band, snap marker).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtGui import QKeyEvent, QMouseEvent


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Handed to Tool.activate(); gives the tool a handle to the live Scene,
    CommandStack, Camera, and a viewport-size accessor."""

    scene: object
    command_stack: object = None  # M3a-introduced — pluton.commands.CommandStack
    camera: object = None  # M3b-introduced — pluton.viewport.camera.Camera
    widget_size_provider: object = None  # M3b-introduced — callable () -> tuple[int, int] returning (width, height)
    selection: object = None  # M4b — pluton.selection.Selection (shared)


@dataclass(frozen=True, slots=True)
class ToolOverlay:
    """Transient preview geometry rebuilt every frame by the active tool."""

    rubber_band_segments: np.ndarray  # shape (2*N, 3), float32
    rubber_band_color: tuple[float, float, float]
    snap_marker_position: np.ndarray | None
    snap_marker_color: tuple[float, float, float]
    snap_marker_kind: int = 0  # SnapKind value (0=NONE/no marker); stored as int to avoid circular import

    # M3b: filled face overlays (hover-highlight / armed face / ghost prism faces).
    face_fill_polygons: list[np.ndarray] = field(default_factory=list)
    # List of (N, 3) float32 world-space vertex loops. Renderer earcut-triangulates each at draw time.

    face_fill_color: tuple[float, float, float, float] = (0.4, 0.7, 1.0, 0.15)
    # RGBA. Default is M3b's "ghost prism" color (light blue, 15% alpha).

    # M4b: screen-space box-select rectangle (pixels: x0,y0,x1,y1) or None.
    box_rect: tuple[float, float, float, float] | None = None
    box_rect_color: tuple[float, float, float] = (0.30, 0.55, 0.95)


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

    def on_mouse_release(self, event: QMouseEvent, snap) -> None:  # noqa: ANN001
        """Default: do nothing. Tools that need drag-release (e.g. box-select)
        override this."""

    def on_key_press(self, event: QKeyEvent) -> None:
        """Default: do nothing."""

    @abstractmethod
    def overlay(self) -> ToolOverlay: ...

    @property
    @abstractmethod
    def anchor_or_none(self) -> np.ndarray | None:
        """Rubber-band anchor used by the SnapEngine for axis-lock."""

    @property
    def status_text(self) -> str | None:
        """Optional third text segment for the status bar.

        Default None means this tool contributes nothing extra to the status
        bar beyond `<name> · <snap>`. PushPullTool overrides this to show the
        current extrusion depth during DRAGGING.
        """
        return None

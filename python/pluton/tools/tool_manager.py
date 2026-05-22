"""ToolManager: holds the registered tool roster and the currently-active tool."""

from __future__ import annotations

from pluton.tools.tool import Tool, ToolContext


class ToolManager:
    """One active tool at a time, switched by single-letter keyboard shortcut."""

    def __init__(self, ctx: ToolContext | None = None) -> None:
        self._ctx = ctx
        self._tools: dict[str, Tool] = {}
        self._active: Tool | None = None

    def set_context(self, ctx: ToolContext) -> None:
        """MainWindow calls this once the Scene exists."""
        self._ctx = ctx

    def register(self, tool: Tool) -> None:
        self._tools[tool.shortcut.upper()] = tool

    def activate_by_shortcut(self, key: str) -> bool:
        target = self._tools.get(key.upper())
        if target is None:
            return False
        if self._active is target:
            return True
        if self._active is not None:
            self._active.deactivate()
        if self._ctx is None:
            raise RuntimeError("ToolManager has no ToolContext; call set_context() first")
        target.activate(self._ctx)
        self._active = target
        return True

    def deactivate_current(self) -> None:
        if self._active is not None:
            self._active.deactivate()
            self._active = None

    @property
    def active(self) -> Tool | None:
        return self._active

"""The main application window — hosts the viewport, status bar, ToolManager, and CommandStack."""

from __future__ import annotations

import math
from pathlib import Path
from typing import ClassVar

import numpy as np
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from pluton.commands import CommandStack
from pluton.commands.scene_commands import ClearSceneCommand
from pluton.commands.view_commands import (
    CreateViewCommand,
    DeleteViewCommand,
    RenameViewCommand,
    ReorderViewCommand,
    UpdateViewCommand,
)
from pluton.document import DocumentSettings
from pluton.io import (
    PlutonIOError,
    export_gltf,
    export_obj,
    load_document,
    read_gltf_scene,
    read_obj_document,
    save_document,
)
from pluton.io.document_codec import CameraState
from pluton.model import Model
from pluton.model.model_queries import instance_path
from pluton.model.tag import TagLibrary
from pluton.selection import Selection
from pluton.tools import (
    ArcTool,
    CircleTool,
    EraserTool,
    LineTool,
    MoveTool,
    PolygonTool,
    PushPullTool,
    RectangleTool,
    RotateTool,
    ScaleTool,
    SelectTool,
    TapeMeasureTool,
    ToolContext,
    ToolManager,
)
from pluton.tools.dimension_tool import DimensionTool
from pluton.tools.opening_tool import DoorWindowTool
from pluton.tools.paint_tool import PaintTool
from pluton.tools.roof_tool import RoofTool
from pluton.tools.text_tool import TextTool
from pluton.tools.wall_tool import WallTool
from pluton.ui import selection_controller
from pluton.ui.cursors import cursor_for
from pluton.ui.document_controller import DocumentController
from pluton.ui.entity_info_page import EntityInfoPage
from pluton.ui.materials_page import MaterialsPage
from pluton.ui.opening_options_bar import OpeningOptionsBar
from pluton.ui.outliner_tree import OutlinerTree
from pluton.ui.properties_dock import PropertiesDock
from pluton.ui.roof_options_bar import RoofOptionsBar
from pluton.ui.scenes_page import ScenesPage
from pluton.ui.status_bar import StatusBar
from pluton.ui.tags_page import TagsPage
from pluton.ui.tool_settings_page import ToolSettingsPage
from pluton.ui.value_control_box import ValueControlBox
from pluton.ui.wall_options_bar import WallOptionsBar
from pluton.ui.window_state import (
    WINDOW_STATE_VERSION,
    reset_window_state,
    restore_window_state,
    save_window_state,
)
from pluton.viewport.render_style import FaceStyle, RenderStyle
from pluton.viewport.view_animator import ViewAnimator
from pluton.viewport.viewport_widget import ViewportWidget
from pluton.views.capture import apply_tags_and_style, capture_view


class MainWindow(QMainWindow):
    """Top-level Pluton window."""

    # Maps the current render style back to the registry action id that
    # represents it (M7.2, Task 10) -- used to seed the face-style radio
    # group's initial checked state from self._render_style.
    _FACE_STYLE_ACTION_IDS: ClassVar[dict[FaceStyle, str]] = {
        FaceStyle.WIREFRAME: "view_style_wireframe",
        FaceStyle.HIDDEN_LINE: "view_style_hidden_line",
        FaceStyle.MONOCHROME: "view_style_monochrome",
        FaceStyle.SHADED: "view_style_shaded",
    }

    def _face_style_action_id(self) -> str:
        return self._FACE_STYLE_ACTION_IDS[self._render_style.face_style]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pluton")
        self.resize(1280, 800)

        # Per-document settings (units etc.)
        self._doc = DocumentSettings()

        # Measurements box (VCB) — pure state, no Qt dependency.
        self._vcb = ValueControlBox()

        # Scene graph + tool manager + command stack
        self._model = Model()
        self._render_style = RenderStyle()
        self._selection = Selection()
        self._command_stack = CommandStack()
        self._tool_manager = ToolManager()
        self._tool_manager.register(LineTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(PushPullTool())
        self._tool_manager.register(CircleTool())
        self._tool_manager.register(PolygonTool())
        self._tool_manager.register(ArcTool())
        self._tool_manager.register(SelectTool())
        self._tool_manager.register(EraserTool())
        self._tool_manager.register(PaintTool())
        self._tool_manager.register(MoveTool())
        self._tool_manager.register(RotateTool())
        self._tool_manager.register(ScaleTool())
        self._tool_manager.register(TapeMeasureTool())
        self._wall_tool = WallTool()
        self._tool_manager.register(self._wall_tool)
        self._opening_tool = DoorWindowTool()
        self._tool_manager.register(self._opening_tool)
        self._roof_tool = RoofTool()
        self._tool_manager.register(self._roof_tool)
        self._dimension_tool = DimensionTool()
        self._tool_manager.register(self._dimension_tool)
        self._text_tool = TextTool()
        self._tool_manager.register(self._text_tool)

        # Viewport + status bar (created BEFORE setting ToolContext so we can
        # wire the camera + widget_size_provider into the context).
        self._viewport = ViewportWidget(self._model, self._tool_manager, self)
        self._viewport.selection = self._selection
        # M7d, Task 13 (Part B): wire the annotation units provider (Task 4
        # carry-over) -- without this, _paint_annotations silently falls back
        # to a default Units() regardless of the document's unit setting.
        self._viewport.set_units_provider(lambda: self._doc.units)
        self._status_bar = StatusBar()

        # Materials page — must exist BEFORE _rebuild_tool_context() so the
        # lambda `set_active_material=self._materials_page.set_active` captures
        # a live reference.
        self._active_material_id = self._model.materials.DEFAULT_ID
        self._materials_page = MaterialsPage(self._model.materials, self)
        self._materials_page.active_material_changed.connect(self._on_active_material_changed)

        # Tags page. Not referenced by the ToolContext (tag assignment uses the
        # existing Select tool + Selection).
        self._active_tag_id = TagLibrary.UNTAGGED_ID
        self._tags_page = TagsPage(self._model.tags, self)
        self._tags_page.active_tag_changed.connect(self._on_active_tag_changed)
        self._tags_page.visibility_changed.connect(self._viewport.update)
        # Spec 1.7: "Tag visibility toggled -> full rebuild (tag_hidden
        # moved)" -- a highlight-only sync would never move the dimming.
        self._tags_page.visibility_changed.connect(self._rebuild_outliner)
        self._tags_page.assign_to_selection_requested.connect(self._on_assign_tag)

        # Scenes page (M7e).
        self._scenes_page = ScenesPage(self._model.views, self)
        self._scenes_page.create_requested.connect(self._on_create_view)
        self._scenes_page.update_requested.connect(self._on_update_view)
        self._scenes_page.delete_requested.connect(self._on_delete_view)
        self._scenes_page.rename_requested.connect(self._on_rename_view)
        self._scenes_page.reorder_requested.connect(self._on_reorder_view)
        self._scenes_page.recall_requested.connect(self._on_recall_view)

        # Properties panel (M7.3) — Outliner over an icon-tabbed editor.
        # Must be added BEFORE restore_window_state() below: restoreState()
        # only reattaches docks it can find by object name at the time it runs.
        self._properties_dock = PropertiesDock(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties_dock)
        self._outliner = OutlinerTree(self._properties_dock)
        self._properties_dock.set_outliner(self._outliner)
        self._outliner.instance_clicked.connect(self._on_outliner_clicked)
        self._outliner.instance_activated.connect(self._on_outliner_activated)
        self._outliner.hide_toggled.connect(self._on_outliner_hide_toggled)
        self._outliner.rename_requested.connect(self._on_outliner_rename)
        self._command_stack.add_change_listener(self._rebuild_outliner)
        self._rebuild_outliner()

        # Materials/Tags/Scenes pages (M7.3, Task 11) — installed into the
        # Properties panel's tab stack right after the Outliner above.
        self._properties_dock.set_page("material", self._materials_page)
        self._properties_dock.set_page("tags", self._tags_page)
        self._properties_dock.set_page("scenes", self._scenes_page)

        # Entity Info page (M7.3, Task 13) -- reports what is selected and
        # edits the few properties that already have commands behind them.
        # The page emits intent only; MainWindow routes each signal through
        # the command stack below, exactly as the pages above do.
        self._entity_info_page = EntityInfoPage(self._properties_dock)
        self._properties_dock.set_page("entity_info", self._entity_info_page)
        self._entity_info_page.rename_requested.connect(self._on_entity_rename)
        self._entity_info_page.hidden_requested.connect(self._on_entity_hidden)
        self._entity_info_page.tag_requested.connect(self._assign_tag)
        self._entity_info_page.material_requested.connect(self._on_entity_material)

        # Camera tween animator (M7e). Owns the same live camera object the
        # viewport mutates in place; a manual camera move cancels a running tween.
        self._view_animator = ViewAnimator(self._viewport.camera, self._viewport.update, self)
        self._viewport.set_camera_input_callback(self._view_animator.cancel)

        # Document session state (path / dirty / title) + dirty signal sources.
        self._doc_controller = DocumentController()
        self._command_stack.add_change_listener(self._on_document_changed)
        self._materials_page.library_changed.connect(self._on_document_changed)
        self._tags_page.library_changed.connect(self._on_document_changed)
        self._tags_page.visibility_changed.connect(self._on_document_changed)

        # NOW we can build the ToolContext that includes the viewport refs.
        self._rebuild_tool_context()
        # Task 15: initialize breadcrumb (clears it since we start at root).
        # _status_bar exists — it was created just above.
        self._refresh_breadcrumb()

        # Wall options bar (M7a, Task 5) — thickness/height fields for the Wall
        # tool; shown only while the Wall tool is active (see _refresh_tool_options).
        self._wall_options_bar = WallOptionsBar(
            self._wall_tool, units_provider=lambda: self._doc.units
        )

        # Opening options bar (M7b, Task 7) — Door/Window toggle + size fields
        # for the Door/Window tool; shown only while that tool is active (see
        # _refresh_tool_options).
        self._opening_options_bar = OpeningOptionsBar(
            self._opening_tool, units_provider=lambda: self._doc.units
        )

        # Roof options bar (M7c, Task 6) — kind toggle + slope field for the
        # Roof tool (M7c is flush; no overhang field); shown only while that
        # tool is active (see _refresh_tool_options).
        self._roof_options_bar = RoofOptionsBar(
            self._roof_tool, units_provider=lambda: self._doc.units
        )

        # Tool Settings tab (M7.3, Task 12) — hosts the three option bars
        # above in a QStackedWidget; _refresh_tool_options picks which one
        # (if any) is visible.
        self._tool_settings_page = ToolSettingsPage(self._properties_dock)
        self._tool_settings_page.add_bar("wall", self._wall_options_bar)
        self._tool_settings_page.add_bar("opening", self._opening_options_bar)
        self._tool_settings_page.add_bar("roof", self._roof_options_bar)
        self._properties_dock.set_page("tool_settings", self._tool_settings_page)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._viewport, stretch=1)
        layout.addWidget(self._status_bar, stretch=0)
        self.setCentralWidget(container)

        self._viewport.set_status_bar(self._status_bar)
        self._viewport.set_event_finished_callback(self._refresh_status_text)
        # M7.2 Task 14: real right-clicks always show the menu (exec_menu=True);
        # _on_context_menu_requested defaults exec_menu to False so tests can
        # call it directly without entering QMenu.exec()'s modal loop.
        self._viewport.context_menu_requested.connect(
            lambda x, y: self._on_context_menu_requested(x, y, exec_menu=True)
        )

        # Clear selection after any undo or redo.
        self._command_stack.add_undo_listener(self._on_after_undo_redo)
        self._command_stack.add_redo_listener(self._on_after_undo_redo)

        # Keyboard shortcuts not covered by the action registry (M7.2, Task 10)
        # -- these are not commands and have no menu entry.
        QShortcut(
            QKeySequence(Qt.Key.Key_Up), self, activated=lambda: self._on_tool_key(Qt.Key.Key_Up)
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Down),
            self,
            activated=lambda: self._on_tool_key(Qt.Key.Key_Down),
        )
        QShortcut(QKeySequence("Esc"), self, activated=self._on_escape)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._on_finish_gesture)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._on_finish_gesture)

        # Install the VCB event filter on the QApplication so it intercepts
        # key events (and ShortcutOverride) before any QShortcut fires.
        # Guard for None so headless unit tests without a QApplication still work.
        from PySide6.QtWidgets import QApplication

        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

        # Menu bar + actions + shortcuts, built from the declarative registry
        # in pluton.ui.actions (M7.2, Task 10).
        from pluton.ui.ui_builder import build_all_actions, build_menubar, build_shortcuts

        build_all_actions(self)
        self._menus = build_menubar(self)
        build_shortcuts(self)

        # Reflect current document state in the exclusive groups.
        self._actions[self._face_style_action_id()].setChecked(True)
        self._face_style_actions = {
            style: self._actions[action_id]
            for style, action_id in self._FACE_STYLE_ACTION_IDS.items()
        }
        self._xray_action = self._actions["view_xray"]

        # Dynamic View entries: the Properties panel is still a real dock, so
        # it keeps a genuine toggleViewAction. Materials/Tags/Scenes are now
        # tabs inside it and are declared actions instead (see actions.py).
        self._view_menu = self._menus["View"]
        self._view_menu.addSeparator()
        self._properties_dock_action = self._properties_dock.toggleViewAction()
        self._properties_dock_action.setText("Properties Panel")
        self._view_menu.addAction(self._properties_dock_action)

        # Seven dockable toolbars (M7.2, Task 11), sharing the same QAction
        # objects the menus above were built from.
        from pluton.ui.ui_builder import build_toolbars

        self._toolbars = build_toolbars(self)

        # View ▸ Toolbars -- one checkbox per toolbar, plus the escape hatch.
        # Reset Toolbars lives in this menu (not on a toolbar) because
        # restoreState() can hide every toolbar but cannot touch the menu bar.
        self._view_menu.addSeparator()
        self._toolbars_menu = self._view_menu.addMenu("Toolbars")
        for toolbar in self._toolbars.values():
            self._toolbars_menu.addAction(toolbar.toggleViewAction())
        self._toolbars_menu.addSeparator()
        self._toolbars_menu.addAction(self._actions["view_reset_toolbars"])

        # Window/toolbar-layout persistence (M7.2, Task 8 + 11). Must run
        # AFTER every toolbar and dock above exists: QMainWindow.restoreState()
        # only reattaches toolbars/docks it can find by object name at the
        # time it runs, so restoring any earlier would silently restore
        # nothing. `_default_window_state` captures the just-built default
        # arrangement before any saved layout is applied, so Reset Toolbars
        # has a known-good state to fall back to.
        self._settings = QSettings()
        self._default_window_state = self.saveState(WINDOW_STATE_VERSION)
        restore_window_state(self, self._settings)

        # Back-compat aliases for tests that read a named menu by attribute.
        self._file_menu = self._menus["File"]
        self._units_menu = self._menus["Units"]

        self._update_window_title()

    # --- Material slot ---------------------------------------------------

    def _on_active_material_changed(self, material) -> None:
        self._active_material_id = material.id

    # --- Tag slots -------------------------------------------------------

    def _on_active_tag_changed(self, tag_id: int) -> None:
        self._active_tag_id = tag_id

    def _update_selection_tag_indicator(self) -> None:
        self._tags_page.set_selection_tag(
            selection_controller.selection_tag_label(self._model, self._selection)
        )

    def _on_assign_tag(self) -> None:
        """TagsPage's "Assign to Selection" button -- assigns the page's active tag."""
        self._assign_tag(self._active_tag_id)

    def _assign_tag(self, tag_id: int) -> None:
        """Assign `tag_id` to every selected instance via TagInstancesCommand.

        Shared by the Tags panel's "Assign to Selection" button (_on_assign_tag)
        and the right-click Assign Tag submenu -- one command construction, not
        two. The controller decides; this method owns the Qt half.
        """
        did_assign, message = selection_controller.assign_tag(
            self._model, self._selection, self._command_stack, tag_id
        )
        self._status_bar.set_message(message)
        if did_assign:
            self._update_selection_tag_indicator()
            self._viewport.update()

    # --- Scene graph back-compat property --------------------------------

    @property
    def scene(self):
        """Back-compat: the active scene from the model (root mesh by default)."""
        return self._model.active_scene

    # --- Tool context -----------------------------------------------------

    def _rebuild_tool_context(self) -> None:
        """Build a fresh ToolContext pointing at the active scene and install it.

        Called from __init__ and after any active-context change (undo/redo,
        enter/exit group).  If a tool is already active it is re-activated so
        it picks up the new scene reference.
        """
        ctx = ToolContext(
            scene=self._model.active_scene,
            command_stack=self._command_stack,
            camera=self._viewport.camera,
            widget_size_provider=lambda: (self._viewport.width(), self._viewport.height()),
            selection=self._selection,
            units_provider=lambda: self._doc.units,
            model=self._model,
            request_context_rebuild=self._on_active_context_changed,
            active_material_provider=lambda: self._model.materials.get(self._active_material_id),
            set_active_material=self._materials_page.set_active,
        )
        self._tool_manager.set_context(ctx)
        # Re-activate the current tool so it picks up the new context/scene.
        active = self._tool_manager.active
        if active is not None:
            active.deactivate()
            active.activate(ctx)

    # --- Slots -----------------------------------------------------------

    def _refresh_status_text(self) -> None:
        active = self._tool_manager.active
        if self._vcb.active:
            self._status_bar.set_status(self._vcb.text + "▏")
        elif active is None:
            self._status_bar.set_status("")
        else:
            self._status_bar.set_status(active.status_text or "")
        self._refresh_selection_status()
        self._update_selection_tag_indicator()

    def _vcb_handle_key(self, event) -> bool:
        """Pure VCB key logic. Returns True if the key was consumed."""
        active_tool = self._tool_manager.active
        if active_tool is None:
            return False
        key = event.key()
        text = event.text()
        if self._vcb.active:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._vcb.text:
                    active_tool.apply_typed_value(self._vcb.text, self._doc.units)
                self._vcb.clear()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if key == Qt.Key.Key_Escape:
                self._vcb.clear()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if key == Qt.Key.Key_Backspace:
                self._vcb.backspace()
                self._refresh_status_text()
                self._viewport.update()
                return True
            if text and text.isprintable() and text not in ("\r", "\n"):
                self._vcb.feed(text)
                self._refresh_status_text()
                self._viewport.update()
                return True
            return False
        # inactive: only a digit activates the box.
        if text in set("0123456789"):
            self._vcb.feed(text)
            self._refresh_status_text()
            self._viewport.update()
            return True
        return False

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent

        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
            if self._vcb.active or (
                event.type() == QEvent.Type.KeyPress and event.text() in set("0123456789")
            ):
                if self._vcb_handle_key(event):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _activate(self, shortcut: str) -> None:
        if self._tool_manager.activate_by_shortcut(shortcut):
            active = self._tool_manager.active
            self._status_bar.set_tool(active.name if active else "")
            self._status_bar.set_snap("")
            self._refresh_status_text()
            self._refresh_tool_options()
            self._viewport.update()
            # Keep the toolbar/menu button in sync when the tool was armed by
            # a raw keyboard shortcut rather than by triggering its QAction
            # (Qt only auto-checks a QActionGroup member when the action
            # itself fires) -- otherwise the toolbar would lie about which
            # tool is active (M7.2, Task 11).
            if active is not None:
                action_id = self._tool_action_id_for_shortcut(active.shortcut)
                if action_id is not None:
                    self._actions[action_id].setChecked(True)
                    # Viewport only: the tool cursor must not leak over docks,
                    # the menu bar, or the per-tool option bars. The ratio
                    # comes from the widget itself (not a global) since a
                    # window can move between monitors with different
                    # scaling (M7.2, Task 12).
                    dpr = self._viewport.devicePixelRatioF()
                    self._viewport.setCursor(cursor_for(action_id, dpr=dpr))

    def _disarm_tool_ui(self) -> None:
        """Undo _activate's visible effects when no tool is armed.

        Arming a tool checks its action (depressing the toolbar button) and
        puts that tool's cursor on the viewport. Disarming has to undo both,
        or the toolbar and the cursor keep advertising a tool that is no
        longer active -- the exact ambiguity the toolbars exist to remove.
        QActionGroup is exclusive, so nothing unchecks the member for us.
        """
        from pluton.ui.actions import TOOL_GROUP

        group = self._action_groups.get(TOOL_GROUP)
        if group is not None and group.checkedAction() is not None:
            group.setExclusive(False)
            group.checkedAction().setChecked(False)
            group.setExclusive(True)
        self._viewport.unsetCursor()

    @staticmethod
    def _tool_action_id_for_shortcut(shortcut: str) -> str | None:
        from pluton.ui.actions import ACTIONS, TOOL_GROUP

        for spec in ACTIONS:
            if (
                spec.group == TOOL_GROUP
                and spec.shortcut
                and spec.shortcut.upper() == shortcut.upper()
            ):
                return spec.id
        return None

    def _refresh_tool_options(self) -> None:
        """Point the Tool Settings tab at the active tool's option bar.

        Arming a tool that HAS settings also focuses the tab: before M7.3 the
        Wall tool's thickness and height simply appeared, and a panel sitting
        on another tab would silently not show them. Tools without settings
        never steal the tab -- otherwise every tool switch would yank the user
        out of whatever they were inspecting.

        This SWITCHES the tab (spec 1.6) rather than calling
        _show_properties_tab, which also un-hides the whole dock -- arming a
        tool must not reopen a panel the user deliberately closed.
        """
        active = self._tool_manager.active
        key = None
        if isinstance(active, WallTool):
            key = "wall"
        elif isinstance(active, DoorWindowTool):
            key = "opening"
        elif isinstance(active, RoofTool):
            key = "roof"

        if key == "wall":
            self._wall_options_bar.refresh()
        elif key == "opening":
            self._opening_options_bar.refresh()
        elif key == "roof":
            self._roof_options_bar.refresh()

        self._tool_settings_page.show_bar(key)
        if key is not None:
            self._properties_dock.show_tab("tool_settings")

    def _on_escape(self) -> None:
        active = self._tool_manager.active
        if active is None:
            return
        if active.has_active_gesture:
            from PySide6.QtGui import QKeyEvent

            ev = QKeyEvent(
                QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
            )
            active.on_key_press(ev)
        elif self._model.active_path:
            # M4e: inside a group/component with no active gesture — Esc exits one
            # level. Handled here (not in the tool) so Esc exits regardless of which
            # tool is active and even when the selection is empty (entering clears it).
            self._model.exit_one()
            self._selection.clear()
            self._on_active_context_changed()
        else:
            self._tool_manager.deactivate_current()
            self._status_bar.set_tool("")
            self._status_bar.set_snap("")
            self._status_bar.set_coordinates("")
            self._disarm_tool_ui()
            self._refresh_tool_options()
        self._refresh_status_text()
        self._viewport.update()

    def _on_finish_gesture(self) -> None:
        active = self._tool_manager.active
        if active is None or not active.has_active_gesture:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._refresh_status_text()
        self._viewport.update()

    def _on_tool_key(self, qt_key) -> None:
        """Forward a non-text key (e.g. Up/Down for polygon sides) to the active
        tool, but only while it has a live gesture (so arrows are inert otherwise)."""
        active = self._tool_manager.active
        if active is None or not active.has_active_gesture:
            return
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QKeyEvent.Type.KeyPress, qt_key, Qt.KeyboardModifier.NoModifier)
        active.on_key_press(ev)
        self._refresh_status_text()
        self._viewport.update()

    def _on_clear_scene(self) -> None:
        self._command_stack.execute(ClearSceneCommand(), self._model.active_scene)
        self._refresh_status_text()
        self._viewport.update()

    # --- Edit-menu handlers -----------------------------------------------

    def _on_make_group(self) -> None:
        from pluton.commands.group_commands import MakeGroupCommand
        from pluton.tools.transform_support import selection_vertices

        sel = self._selection
        if not (sel.edges or sel.faces):
            self._status_bar.set_message("Select edges or faces to group.")
            return
        vertex_ids = selection_vertices(self._model.active_scene, sel)
        edge_ids = list(sel.edges)
        face_ids = list(sel.faces)
        cmd = MakeGroupCommand(
            self._model.active_context, vertex_ids, edge_ids, face_ids, tag_id=self._active_tag_id
        )
        self._command_stack.execute(cmd, self._model)
        sel.replace(instances=[cmd.created_instance.id])
        self._refresh_selection_status()
        self._refresh_breadcrumb()
        self._viewport.update()

    def _prompt_component_name(self, default: str) -> str | None:
        """Show a dialog to get a component name. Overridable for testing."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Make Component", "Component name:", text=default)
        return name if ok else None

    def _on_make_component(self) -> None:
        from pluton.commands.group_commands import MakeComponentCommand
        from pluton.tools.transform_support import selection_vertices

        sel = self._selection
        if not (sel.edges or sel.faces):
            self._status_bar.set_message("Select edges or faces to make a component.")
            return
        default = f"Component #{self._model._next_def_id}"
        name = self._prompt_component_name(default)
        if name is None:
            return
        vertex_ids = selection_vertices(self._model.active_scene, sel)
        edge_ids = list(sel.edges)
        face_ids = list(sel.faces)
        cmd = MakeComponentCommand(
            self._model.active_context,
            vertex_ids,
            edge_ids,
            face_ids,
            name=name,
            tag_id=self._active_tag_id,
        )
        self._command_stack.execute(cmd, self._model)
        sel.replace(instances=[cmd.created_instance.id])
        self._refresh_selection_status()
        self._refresh_breadcrumb()
        self._viewport.update()

    def _on_explode(self) -> None:
        from pluton.commands import CompositeCommand
        from pluton.commands.explode_command import ExplodeInstanceCommand
        from pluton.commands.instance_lifecycle_commands import MakeUniqueCommand

        sel = self._selection
        if not sel.instances:
            self._status_bar.set_message("Select an instance to explode.")
            return
        inst_id = next(iter(sel.instances))
        inst = next((c for c in self._model.active_context.children if c.id == inst_id), None)
        if inst is None:
            return
        if len(inst.definition.instances) > 1:
            cmd = CompositeCommand(
                name="Explode",
                children=[
                    MakeUniqueCommand(inst),
                    ExplodeInstanceCommand(self._model.active_context, inst),
                ],
            )
        else:
            cmd = ExplodeInstanceCommand(self._model.active_context, inst)
        self._command_stack.execute(cmd, self._model)
        sel.clear()
        self._refresh_selection_status()
        self._rebuild_tool_context()
        self._viewport.update()

    def _on_make_unique(self) -> None:
        from pluton.commands.instance_lifecycle_commands import MakeUniqueCommand

        sel = self._selection
        if not sel.instances:
            self._status_bar.set_message("Select an instance to make unique.")
            return
        inst_id = next(iter(sel.instances))
        inst = next((c for c in self._model.active_context.children if c.id == inst_id), None)
        if inst is None:
            return
        cmd = MakeUniqueCommand(inst)
        self._command_stack.execute(cmd, self._model)
        self._refresh_selection_status()
        self._viewport.update()

    def _on_delete_selection(self) -> None:
        from pluton.commands import CompositeCommand
        from pluton.commands.annotation_commands import DeleteAnnotationsCommand
        from pluton.commands.instance_lifecycle_commands import DeleteInstanceCommand
        from pluton.commands.scene_commands import RemoveEdgeCommand, RemoveFaceCommand

        sel = self._selection
        if sel.is_empty():
            return

        # Fix wave: build the annotation delete up front but do NOT execute it
        # standalone -- it must ride along as one child of whichever single
        # command below ends up on the undo stack, so a mixed selection (any
        # combination of annotations + instances/edges/faces) is always
        # exactly ONE undo-stack entry instead of two. DeleteAnnotationsCommand
        # ignores the `target` argument passed to do()/undo() (it operates on
        # the target_context captured here), so it composes safely whether the
        # enclosing command executes against self._model (instance branch) or
        # self._model.active_scene (edge/face branch below).
        ann_cmd = None
        if sel.annotations:
            ann_cmd = DeleteAnnotationsCommand(list(sel.annotations), self._model.active_context)

        # Instance delete takes priority when instances are selected.
        if sel.instances:
            children_by_id = {c.id: c for c in self._model.active_context.children}
            cmds = []
            for inst_id in list(sel.instances):
                inst = children_by_id.get(inst_id)
                if inst is None:
                    continue
                cmds.append(DeleteInstanceCommand(self._model.active_context, inst))
            if ann_cmd is not None:
                cmds.append(ann_cmd)
            if not cmds:
                sel.clear()
                return
            if len(cmds) == 1:
                cmd = cmds[0]
            else:
                cmd = CompositeCommand(name="Delete Instances")
                cmd.children = cmds
            self._command_stack.execute(cmd, self._model)
            sel.clear()
            self._refresh_selection_status()
            self._viewport.update()
            return

        composite = CompositeCommand(name="Delete Selection")
        removed_faces: set[int] = set()
        for e_id in list(sel.edges):
            try:
                self._model.active_scene.edge(e_id)
            except KeyError:
                continue
            for f_id in self._model.active_scene.edge_faces(e_id):
                if f_id is None or f_id in removed_faces:
                    continue
                fc = RemoveFaceCommand(f_id)
                fc.do(self._model.active_scene)
                composite.children.append(fc)
                removed_faces.add(f_id)
            ec = RemoveEdgeCommand(e_id)
            ec.do(self._model.active_scene)
            composite.children.append(ec)
        for f_id in list(sel.faces):
            if f_id in removed_faces:
                continue
            try:
                self._model.active_scene.face_loop(f_id)
            except KeyError:
                continue
            fc = RemoveFaceCommand(f_id)
            fc.do(self._model.active_scene)
            composite.children.append(fc)
            removed_faces.add(f_id)
        if ann_cmd is not None:
            ann_cmd.do(self._model.active_scene)
            composite.children.append(ann_cmd)
        if composite.children:
            self._command_stack.push_executed(composite, self._model.active_scene)
        sel.clear()
        self._refresh_selection_status()
        self._viewport.update()

    # --- M7.2 selection + view commands ------------------------------------

    def _on_select_all(self) -> None:
        """Select every entity in the active editing context."""
        selection_controller.select_all(self._model, self._selection)
        self._refresh_selection_status()
        self._viewport.update()

    def _on_select_none(self) -> None:
        """Clear the selection."""
        selection_controller.select_none(self._selection)
        self._refresh_selection_status()
        self._viewport.update()

    def _on_zoom_extents(self) -> None:
        """Frame everything visible without changing the view direction."""
        from pluton.model.model_queries import model_bounds
        from pluton.viewport.camera_framing import frame_bounds

        bounds = model_bounds(self._model)
        if bounds is None:
            return  # Nothing visible -- leave the camera exactly where it is.

        camera = self._viewport.camera
        width, height = self._viewport.width(), self._viewport.height()
        aspect = width / height if height else 1.0

        position = np.asarray(camera.position, dtype=np.float64)
        target = np.asarray(camera.target, dtype=np.float64)
        new_position, new_target = frame_bounds(
            bounds[0], bounds[1], target - position, aspect, math.radians(camera.fov_y_deg)
        )
        camera.position = new_position.astype(np.float32)
        camera.target = new_target.astype(np.float32)
        self._viewport.update()

    def _on_edit_group(self) -> None:
        """Enter the selected group/component for editing."""
        instance_ids = set(self._selection.instances)
        if len(instance_ids) != 1:
            return
        target_id = next(iter(instance_ids))
        for child in self._model.active_context.children:
            if child.id == target_id:
                self._model.enter(child)
                self._selection.clear()
                self._on_active_context_changed()
                self._refresh_selection_status()
                return

    def _on_close_group(self) -> None:
        """Step out one editing context. A no-op at the root."""
        if not self._model.active_path:
            return
        self._model.exit_one()
        self._selection.clear()
        self._on_active_context_changed()
        self._refresh_selection_status()

    def _on_paint_selection(self) -> None:
        """Apply the active material to every selected face."""
        from pluton.commands import CompositeCommand
        from pluton.commands.material_commands import PaintFaceCommand

        face_ids = sorted(self._selection.faces)
        if not face_ids:
            return
        children = [PaintFaceCommand(f_id, self._active_material_id) for f_id in face_ids]
        composite = CompositeCommand(name="Paint Selection", children=children)
        self._command_stack.execute(composite, self._model.active_scene)
        self._viewport.update()

    def _on_edit_label_text(self) -> None:
        """Retype the selected text annotation's label."""
        from PySide6.QtWidgets import QInputDialog

        from pluton.commands.annotation_commands import EditLabelTextCommand

        annotation_ids = sorted(self._selection.annotations)
        if len(annotation_ids) != 1:
            return
        context = self._model.active_context
        ann = next((a for a in context.annotations if a.id == annotation_ids[0]), None)
        if ann is None or getattr(ann, "kind", None) != "label":
            return
        text, ok = QInputDialog.getText(self, "Text", "Label:", text=ann.text)
        if not ok or not text.strip() or text.strip() == ann.text:
            return
        self._command_stack.execute(
            EditLabelTextCommand(annotation_ids[0], text.strip(), context), self._model
        )
        self._viewport.update()

    # --- Context menu (M7.2 Task 14) --------------------------------------

    def _on_context_menu_requested(self, x: int, y: int, exec_menu: bool = False) -> None:
        """Resolve a right-click at viewport pixel (x, y), select the target
        (if any), and show its context menu.

        exec_menu defaults to False so tests can drive resolution and the
        selection guard directly without entering QMenu.exec()'s modal event
        loop; the real signal connection (see __init__) always passes
        exec_menu=True.
        """
        from pluton.ui.actions import ContextTarget
        from pluton.ui.context_menu import build_context_menu, resolve_context_target

        target, entity_id = resolve_context_target(
            self._model,
            self._viewport.camera,
            x,
            y,
            self._viewport.width(),
            self._viewport.height(),
            self._doc.units,
        )

        # Right-clicking an unselected entity selects it first (SketchUp's
        # behaviour); right-clicking empty space leaves the selection alone --
        # Select None is right there for the explicit case. An already-selected
        # entity keeps a multi-entity selection intact rather than collapsing it.
        if target is not ContextTarget.EMPTY and entity_id is not None:
            if not self._selection_contains(target, entity_id):
                self._select_only(target, entity_id)

        enablement = {aid: a.isEnabled() for aid, a in self._actions.items()}
        try:
            # Inside the try, not before it: build_context_menu disables
            # entries as it goes, so a raise partway through would otherwise
            # leave whatever it had already disabled stuck that way.
            menu = build_context_menu(self, target, entity_id)
            if exec_menu:
                self._exec_context_menu(menu, self._viewport.mapToGlobal(QPoint(x, y)))
        finally:
            # build_context_menu disables entries on the SAME QAction objects
            # the menu bar holds (Task 13's design: context menus, the menu
            # bar, and the toolbars all share one action registry so label /
            # icon / shortcut can never drift between surfaces). Re-enabling
            # unconditionally in a finally -- not a step after menu.exec()
            # that an early return could skip -- is what stops a disabled
            # context entry from leaving the matching menu-bar item
            # permanently greyed out.
            self._restore_action_enablement(enablement)

    def _exec_context_menu(self, menu, global_pos) -> None:
        """Pop the context menu modally at `global_pos`.

        Its own method purely so a test can replace it on the instance.
        QMenu.exec cannot be monkeypatched: PySide6 dispatches the call
        straight to C++, so assigning QMenu.exec is accepted but has no
        effect, and the real modal loop runs. Under the offscreen platform
        CI uses there is nothing to dismiss it, so such a test hangs
        forever rather than failing.
        """
        menu.exec(global_pos)

    def _select_only(self, target, entity_id: int) -> None:
        """Replace the selection with the single right-clicked entity."""
        from pluton.ui.actions import ContextTarget

        self._selection.clear()
        if target is ContextTarget.FACE:
            self._selection.toggle_face(entity_id)
        elif target is ContextTarget.EDGE:
            self._selection.toggle_edge(entity_id)
        elif target is ContextTarget.INSTANCE:
            self._selection.toggle_instance(entity_id)
        elif target is ContextTarget.ANNOTATION:
            self._selection.toggle_annotation(entity_id)
        self._refresh_selection_status()
        self._viewport.update()

    def _selection_contains(self, target, entity_id: int) -> bool:
        """Whether the right-clicked entity is already part of the selection
        (dispatches to the matching Selection.contains_* predicate the same
        way _select_only dispatches to toggle_*)."""
        from pluton.ui.actions import ContextTarget

        if target is ContextTarget.FACE:
            return self._selection.contains_face(entity_id)
        if target is ContextTarget.EDGE:
            return self._selection.contains_edge(entity_id)
        if target is ContextTarget.INSTANCE:
            return self._selection.contains_instance(entity_id)
        if target is ContextTarget.ANNOTATION:
            return self._selection.contains_annotation(entity_id)
        return False

    def _restore_action_enablement(self, snapshot: dict[str, bool]) -> None:
        """Undo build_context_menu's per-entry disabling.

        Context menus reuse the same QAction objects the menu bar holds, so a
        disabled context entry would otherwise leave the matching menu-bar
        item permanently greyed out.

        This restores the state captured before the menu was built rather
        than forcing everything enabled. Forcing works only while nothing
        else in the app ever disables a registry action -- true today, but
        it would break silently the moment something reasonable (greying out
        Undo on an empty stack, Save when the document is clean) arrives,
        and any right-click would be the trigger.
        """
        for action_id, was_enabled in snapshot.items():
            self._actions[action_id].setEnabled(was_enabled)

    def _refresh_selection_status(self) -> None:
        self._status_bar.set_selection(selection_controller.selection_status_text(self._selection))
        self._sync_outliner_selection()
        self._refresh_entity_info()

    def _refresh_breadcrumb(self) -> None:
        """Task 15: rebuild the breadcrumb from model.active_path and push to status bar.

        Format: ``Model ▸ <name> ▸ …``  Built from the root definition's name
        (model.root.name) followed by each entered instance's definition name.
        When at root (active_path is empty), the breadcrumb is cleared so the
        status bar is uncluttered.
        """
        if not self._model.active_path:
            self._status_bar.set_breadcrumb("")
            return
        parts = [self._model.root.name]
        for inst in self._model.active_path:
            parts.append(inst.definition.name)
        self._status_bar.set_breadcrumb(" ▸ ".join(parts))

    def _on_active_context_changed(self) -> None:
        """Called by SelectTool after enter/exit to rebuild the tool context
        for the new active editing context and update the breadcrumb."""
        self._rebuild_tool_context()
        self._refresh_breadcrumb()
        self._rebuild_outliner()
        self._viewport.update()

    # --- Outliner (M7.3, Task 10) ----------------------------------------

    def _rebuild_outliner(self) -> None:
        """Repopulate the tree from the model. Structural changes only."""
        from pluton.model.model_queries import outliner_rows

        self._outliner.set_rows(outliner_rows(self._model), self._model.root.name)
        self._sync_outliner_selection()

    def _sync_outliner_selection(self) -> None:
        """Push the current selection into the tree as highlight, no rebuild."""
        self._outliner.set_selected_ids(self._selection.instances)

    def _outliner_instance(self, instance_id: int):
        """The Instance for a row id, or None if it no longer resolves."""
        path = instance_path(self._model, instance_id)
        return path[-1] if path else None

    def _on_outliner_clicked(self, instance_id: int) -> None:
        """Select the row's instance, re-rooting the active path to its parents.

        Selection is only meaningful inside the active context -- every tool,
        the dim pass and pick_selectable assume it -- so selecting a nested row
        without moving the context would leave a highlighted object no tool
        could touch. The breadcrumb and dim pass both update, so the context
        change is visible rather than silent.
        """
        path = instance_path(self._model, instance_id)
        if path is None:
            return
        parents = list(path[:-1])
        if [i.id for i in self._model.active_path] != [i.id for i in parents]:
            self._model.active_path = parents
            self._on_active_context_changed()
        self._selection.replace(instances=[instance_id])
        self._refresh_selection_status()
        self._viewport.update()

    def _on_outliner_activated(self, instance_id: int) -> None:
        """Double-click: enter that instance, like double-clicking it in 3D."""
        path = instance_path(self._model, instance_id)
        if path is None:
            return
        self._model.active_path = list(path)
        self._selection.clear()
        # _on_active_context_changed() already rebuilds the outliner -- a
        # second explicit rebuild here just repopulated the same tree twice.
        self._on_active_context_changed()
        self._refresh_selection_status()

    def _on_outliner_hide_toggled(self, instance_id: int, hidden: bool) -> None:
        from pluton.commands.visibility_commands import HideInstancesCommand

        instance = self._outliner_instance(instance_id)
        if instance is None:
            return
        self._command_stack.execute(HideInstancesCommand([instance], hidden), self._model)
        self._viewport.update()

    def _on_outliner_rename(self, instance_id: int, new_name: str) -> None:
        from pluton.commands.naming_commands import RenameInstanceCommand

        instance = self._outliner_instance(instance_id)
        if instance is None:
            return
        if instance.name == new_name.strip():
            # No command runs, so nothing fires _rebuild_outliner -- without
            # this, the row keeps whatever raw text the user typed (padding
            # whitespace included) instead of the canonical stored name.
            self._rebuild_outliner()
            return
        self._command_stack.execute(RenameInstanceCommand(instance, new_name), self._model)

    # --- Hide / Unhide (M7.3, Task 14) ------------------------------------

    def _set_hidden_on_selection(self, hidden: bool) -> None:
        from pluton.commands.visibility_commands import HideInstancesCommand

        instances = selection_controller.selected_instances(self._model, self._selection)
        if not instances:
            self._status_bar.set_message("Select objects to hide or unhide.")
            return
        self._command_stack.execute(HideInstancesCommand(instances, hidden), self._model)
        self._viewport.update()

    def _on_hide(self) -> None:
        self._set_hidden_on_selection(True)

    def _on_unhide(self) -> None:
        self._set_hidden_on_selection(False)

    def _on_unhide_all(self) -> None:
        """Reveal everything hidden in the active context.

        Without this there is no way back for an object you cannot
        right-click, other than the Outliner -- which the user may have closed.
        """
        from pluton.commands.visibility_commands import HideInstancesCommand

        hidden = [inst for inst in self._model.active_context.children if inst.hidden]
        if not hidden:
            self._status_bar.set_message("Nothing is hidden here.")
            return
        self._command_stack.execute(HideInstancesCommand(hidden, False), self._model)
        self._viewport.update()

    # --- Entity Info (M7.3, Task 13) --------------------------------------

    def _refresh_entity_info(self) -> None:
        from pluton.model.entity_info import entity_summary

        self._entity_info_page.refresh(
            entity_summary(self._model, self._selection),
            self._doc.units,
            self._model.tags,
            self._model.materials,
        )

    def _on_entity_rename(self, new_name: str) -> None:
        from pluton.commands.naming_commands import RenameInstanceCommand

        instances = selection_controller.selected_instances(self._model, self._selection)
        if len(instances) != 1 or instances[0].name == new_name.strip():
            # No command runs on a no-op commit, so nothing repopulates the
            # page -- without this, the Name field keeps whatever raw text
            # the user typed (padding whitespace included).
            self._refresh_entity_info()
            return
        self._command_stack.execute(RenameInstanceCommand(instances[0], new_name), self._model)

    def _on_entity_hidden(self, hidden: bool) -> None:
        from pluton.commands.visibility_commands import HideInstancesCommand

        instances = selection_controller.selected_instances(self._model, self._selection)
        if not instances:
            return
        self._command_stack.execute(HideInstancesCommand(instances, hidden), self._model)
        self._viewport.update()

    def _on_entity_material(self, material_id: int) -> None:
        from pluton.commands import CompositeCommand
        from pluton.commands.material_commands import PaintFaceCommand

        face_ids = sorted(self._selection.faces)
        if not face_ids:
            return
        # PaintFaceCommand targets the SCENE, not the model, and paints one
        # face -- so a multi-face selection composes into a single undo step.
        composite = CompositeCommand(
            name="Paint", children=[PaintFaceCommand(f_id, material_id) for f_id in face_ids]
        )
        self._command_stack.execute(composite, self._model.active_scene)
        self._viewport.update()

    def _on_after_undo_redo(self) -> None:
        """Called by CommandStack listeners after every successful undo or redo."""
        # revalidate_active_path() must run FIRST: _prune_selection() reads
        # self._model.active_context, which is only meaningful once the active
        # path has been walked back to the nearest still-reachable instance.
        self._model.revalidate_active_path()
        self._prune_selection()
        self._refresh_selection_status()
        self._rebuild_tool_context()
        self._refresh_breadcrumb()
        self._scenes_page.refresh()

    def _prune_selection(self) -> None:
        """Keep only selected entities still live in the active context (#46)."""
        selection_controller.prune_to_live(self._model, self._selection)

    def _on_set_face_style(self, style: FaceStyle) -> None:
        self._render_style.face_style = style
        self._face_style_actions[style].setChecked(True)
        self._viewport.set_render_style(self._render_style)

    def _on_toggle_xray(self, checked: bool) -> None:
        self._render_style.xray = bool(checked)
        self._viewport.set_render_style(self._render_style)

    # --- Toolbars (M7.2, Task 11) -----------------------------------------

    def _on_reset_toolbars(self) -> None:
        """Forget the saved layout and reapply the default arrangement live."""
        reset_window_state(self._settings)
        self.restoreState(self._default_window_state, WINDOW_STATE_VERSION)

    # --- Properties tabs (M7.3, Task 11) ----------------------------------

    def _show_properties_tab(self, tab_id: str) -> None:
        """Reveal the panel (it may be closed) and focus one tab."""
        self._properties_dock.show()
        self._properties_dock.raise_()
        self._properties_dock.show_tab(tab_id)

    def _on_show_material_tab(self) -> None:
        self._show_properties_tab("material")

    def _on_show_tags_tab(self) -> None:
        self._show_properties_tab("tags")

    def _on_show_scenes_tab(self) -> None:
        self._show_properties_tab("scenes")

    # --- Scenes (M7e) ----------------------------------------------------

    def _sync_render_style_ui(self) -> None:
        """Reflect self._render_style in the View menu + viewport (no signal echo)."""
        for st, action in self._face_style_actions.items():
            action.setChecked(st == self._render_style.face_style)
        self._xray_action.blockSignals(True)
        self._xray_action.setChecked(self._render_style.xray)
        self._xray_action.blockSignals(False)
        self._viewport.set_render_style(self._render_style)

    def _on_create_view(self) -> None:
        name = f"Scene {len(self._model.views.views()) + 1}"
        view = capture_view(
            self._model.views.next_id,
            name,
            self._viewport.camera,
            self._model.tags,
            self._render_style,
        )
        self._command_stack.execute(CreateViewCommand(view), self._model)
        self._scenes_page.refresh(select_id=view.id)

    def _on_update_view(self, view_id: int) -> None:
        old = self._model.views.get(int(view_id))
        if old is None:
            return
        new_view = capture_view(
            old.id, old.name, self._viewport.camera, self._model.tags, self._render_style
        )
        self._command_stack.execute(UpdateViewCommand(old.id, new_view), self._model)
        self._scenes_page.refresh(select_id=old.id)

    def _on_delete_view(self, view_id: int) -> None:
        if self._model.views.get(int(view_id)) is None:
            return
        self._command_stack.execute(DeleteViewCommand(int(view_id)), self._model)
        self._scenes_page.refresh()

    def _on_rename_view(self, view_id: int, name: str) -> None:
        name = str(name).strip()
        old = self._model.views.get(int(view_id))
        if old is None or not name or name == old.name:
            self._scenes_page.refresh(select_id=int(view_id))
            return
        self._command_stack.execute(RenameViewCommand(int(view_id), name), self._model)
        self._scenes_page.refresh(select_id=int(view_id))

    def _on_reorder_view(self, view_id: int, direction: int) -> None:
        vid = int(view_id)
        index = self._model.views.index_of(vid)
        target = index + (1 if int(direction) > 0 else -1)
        if index < 0 or target < 0 or target >= len(self._model.views.views()):
            return
        self._command_stack.execute(ReorderViewCommand(vid, int(direction)), self._model)
        self._scenes_page.refresh(select_id=vid)

    def _on_recall_view(self, view_id: int) -> None:
        view = self._model.views.get(int(view_id))
        if view is None:
            return
        apply_tags_and_style(view, self._model.tags, self._render_style)
        self._sync_render_style_ui()
        self._tags_page.refresh()
        from_state = CameraState.from_camera(self._viewport.camera)
        self._view_animator.start(from_state, view.camera)

    def _on_undo(self) -> None:
        if self._command_stack.undo():
            self._refresh_status_text()
            self._viewport.update()

    def _on_redo(self) -> None:
        if self._command_stack.redo():
            self._refresh_status_text()
            self._viewport.update()

    def _set_units_metric(self, unit: str) -> None:
        self._doc.set_metric(unit)
        self._refresh_status_text()
        self._refresh_tool_options()
        self._viewport.update()
        self._on_document_changed()

    def _set_units_imperial(self) -> None:
        self._doc.set_imperial()
        self._refresh_status_text()
        self._refresh_tool_options()
        self._viewport.update()
        self._on_document_changed()

    # --- File I/O --------------------------------------------------------

    def _on_document_changed(self) -> None:
        self._doc_controller.mark_dirty()
        self._update_window_title()

    def _update_window_title(self) -> None:
        self.setWindowTitle(self._doc_controller.display_title())

    def _on_export_obj(self) -> None:
        path = self._prompt_save_path("OBJ files (*.obj)", "Export OBJ")
        if not path:
            return
        path = str(path)
        if not path.endswith(".obj"):
            path += ".obj"
        try:
            export_obj(path, self._model)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._status_bar.set_message(f"Exported {Path(path).name}")

    def _on_import_obj(self) -> None:
        path = self._prompt_open_path("OBJ files (*.obj)", "Import OBJ")
        if not path:
            return
        try:
            doc = read_obj_document(path)
        except (PlutonIOError, OSError) as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Import failed", str(e))
            return
        from pluton.commands.obj_commands import ImportObjCommand

        cmd = ImportObjCommand(doc, self._model.active_context)
        self._command_stack.execute(cmd, self._model)
        s = cmd.summary
        msg = f"Imported {s.faces_imported} faces"
        if s.objects:
            msg += f" in {s.objects} object(s)"
        if s.faces_skipped:
            msg += f" (skipped {s.faces_skipped} faces)"
        self._status_bar.set_message(msg)
        self._refresh_breadcrumb()
        self._viewport.update()

    def _on_export_gltf(self) -> None:
        path = self._prompt_save_path("glTF Binary (*.glb);;glTF (*.gltf)", "Export glTF")
        if not path:
            return
        path = str(path)
        if not (path.endswith(".glb") or path.endswith(".gltf")):
            path += ".glb"
        try:
            export_gltf(self._model, path)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._status_bar.set_message(f"Exported {Path(path).name}")

    def _on_import_gltf(self) -> None:
        path = self._prompt_open_path("glTF (*.glb *.gltf)", "Import glTF")
        if not path:
            return
        try:
            scene = read_gltf_scene(path)
        except (PlutonIOError, OSError) as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Import failed", str(e))
            return
        from pluton.commands.gltf_commands import ImportGltfCommand

        cmd = ImportGltfCommand(scene, self._model.active_context, root_name=Path(path).stem)
        self._command_stack.execute(cmd, self._model)
        s = cmd.summary
        msg = f"Imported {s.faces_imported} faces in {s.nodes} object(s)"
        if s.faces_skipped:
            msg += f" (skipped {s.faces_skipped} faces)"
        self._status_bar.set_message(msg)
        self._refresh_breadcrumb()
        self._viewport.update()

    def _prompt_save_path(
        self, file_filter: str = "Pluton files (*.pluton)", title: str = "Save As"
    ) -> str | None:
        """Return a chosen save path (or None). Overridable for testing."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self, title, "", file_filter)
        return path or None

    def _save_to(self, path) -> bool:
        path = str(path)
        if not path.endswith(".pluton"):
            path += ".pluton"
        try:
            save_document(path, self._model, self._viewport.camera, self._doc, self._render_style)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Save failed", str(e))
            return False
        self._doc_controller.set_path(path)
        self._doc_controller.mark_clean()
        self._update_window_title()
        self._status_bar.set_message(f"Saved {Path(path).name}")
        return True

    def _on_file_save(self) -> bool:
        if self._doc_controller.current_path is None:
            return self._on_file_save_as()
        return self._save_to(self._doc_controller.current_path)

    def _on_file_save_as(self) -> bool:
        path = self._prompt_save_path()
        if not path:
            return False
        return self._save_to(path)

    def _prompt_discard(self) -> str:
        """Return 'save' | 'discard' | 'cancel'. Overridable for testing."""
        from PySide6.QtWidgets import QMessageBox

        name = (
            self._doc_controller.current_path.name
            if self._doc_controller.current_path
            else "Untitled"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Save changes to {name}?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        choice = box.exec()
        if choice == QMessageBox.StandardButton.Save:
            return "save"
        if choice == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _confirm_discard_if_dirty(self) -> bool:
        """True if it's safe to proceed (discard a New/Open/close)."""
        if not self._doc_controller.dirty:
            return True
        choice = self._prompt_discard()
        if choice == "save":
            return self._on_file_save()
        if choice == "discard":
            return True
        return False

    def closeEvent(self, event):
        # Persist before the unsaved-changes guard runs, so the layout is
        # remembered even if the user then cancels the close.
        save_window_state(self, self._settings)
        if self._confirm_discard_if_dirty():
            event.accept()
        else:
            event.ignore()

    def _reset_document(self, model, camera_state, units, style, path) -> None:
        """Adopt a (model, camera, units, render style) into the live window, in place."""
        from dataclasses import replace

        self._model.load_from(model)
        self._materials_page.set_library(self._model.materials)
        self._tags_page.set_library(self._model.tags)
        self._scenes_page.set_library(self._model.views)
        camera_state.apply_to(self._viewport.camera)
        self._view_animator.cancel()
        self._render_style = replace(style)
        self._sync_render_style_ui()
        self._doc.set_units(units)
        self._active_material_id = self._model.materials.DEFAULT_ID
        self._active_tag_id = self._model.tags.UNTAGGED_ID
        self._selection.clear()
        self._command_stack.clear()
        self._doc_controller.set_path(path)
        self._doc_controller.mark_clean()
        self._rebuild_tool_context()
        self._refresh_breadcrumb()
        # CommandStack.clear() fires no listeners (by design -- it is not an
        # undoable edit), so without this the Outliner keeps showing the
        # PREVIOUS document's hierarchy under the previous root label (spec
        # 1.7: "Document New / Open -> rebuild and rebind libraries").
        self._rebuild_outliner()
        self._refresh_status_text()
        self._update_window_title()
        self._viewport.update()

    def _on_file_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        from pluton.units import Units
        from pluton.viewport.camera import Camera

        self._reset_document(
            Model(), CameraState.from_camera(Camera()), Units(), RenderStyle(), None
        )

    def _prompt_open_path(
        self, file_filter: str = "Pluton files (*.pluton)", title: str = "Open"
    ) -> str | None:
        """Return a chosen open path (or None). Overridable for testing."""
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, title, "", file_filter)
        return path or None

    def _on_file_open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        path = self._prompt_open_path()
        if not path:
            return
        try:
            loaded = load_document(path)
        except (PlutonIOError, OSError) as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Open failed", str(e))
            return
        self._reset_document(loaded.model, loaded.camera_state, loaded.units, loaded.style, path)

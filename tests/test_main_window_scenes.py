from pluton.viewport.render_style import FaceStyle


def _make_window(qtbot):
    from pluton.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_create_scene_adds_to_library_and_dock(qtbot):
    win = _make_window(qtbot)
    win._on_create_view()
    assert len(win._model.views.views()) == 1
    assert win._scenes_dock._list.count() == 1


def test_recall_applies_style_and_starts_animation(qtbot):
    win = _make_window(qtbot)
    # Save a scene while in WIREFRAME:
    win._render_style.face_style = FaceStyle.WIREFRAME
    win._on_create_view()
    vid = win._model.views.views()[0].id
    # Switch to SHADED, then recall — style must snap back to WIREFRAME:
    win._render_style.face_style = FaceStyle.SHADED
    win._on_recall_view(vid)
    assert win._render_style.face_style is FaceStyle.WIREFRAME
    assert win._view_animator.is_running        # camera tween started
    win._view_animator.cancel()


def test_delete_scene_is_undoable(qtbot):
    win = _make_window(qtbot)
    win._on_create_view()
    vid = win._model.views.views()[0].id
    win._on_delete_view(vid)
    assert win._model.views.views() == []
    win._command_stack.undo()
    assert len(win._model.views.views()) == 1


def test_render_style_persists_through_save_new_open(qtbot, tmp_path):
    win = _make_window(qtbot)
    win._render_style.face_style = FaceStyle.MONOCHROME
    win._render_style.xray = True
    path = str(tmp_path / "styled.pluton")
    assert win._save_to(path) is True
    win._on_file_new()
    assert win._render_style.face_style is FaceStyle.SHADED   # reset by New
    # Re-open and confirm the saved style is adopted:
    from pluton.io.pluton_file import load_document
    loaded = load_document(path)
    win._reset_document(loaded.model, loaded.camera_state, loaded.units,
                        loaded.style, path)
    assert win._render_style.face_style is FaceStyle.MONOCHROME
    assert win._render_style.xray is True

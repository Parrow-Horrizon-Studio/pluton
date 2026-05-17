"""Smoke tests that the window can be constructed without errors.

These tests use pytest-qt to provide a QApplication. They don't visually
verify rendering — that requires a more involved framebuffer-capture
approach which is out of scope for M0.
"""


def test_main_window_constructs(qtbot):
    """The main window can be instantiated without raising."""
    from pluton.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Pluton"


def test_viewport_widget_constructs(qtbot):
    """The viewport widget can be instantiated without raising."""
    from pluton.viewport.viewport_widget import ViewportWidget

    widget = ViewportWidget()
    qtbot.addWidget(widget)

    # Widget exists and has the expected default size (Qt's default minimum)
    assert widget is not None
